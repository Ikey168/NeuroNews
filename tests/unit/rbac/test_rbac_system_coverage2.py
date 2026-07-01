"""Coverage tests for src/api/rbac/rbac_system.py.

Exercises remaining branches: role inheritance permission union,
RolePermissionManager lookups, the DynamoDBPermissionStore CRUD against a
moto-mocked DynamoDB (including auto table creation), and RBACManager
endpoint/permission resolution + DB-backed role lookups.

DynamoDB is mocked with moto's mock_aws(); src.utils.local_cloud.get_resource
resolves to a moto-intercepted boto3 resource because get_endpoint_url returns
None under pytest.
"""

import asyncio
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from src.api.rbac import rbac_system
from src.api.rbac.rbac_system import (
    DynamoDBPermissionStore,
    Permission,
    RBACManager,
    RoleDefinition,
    RolePermissionManager,
    UserRole,
)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --------------------------------------------------------------------------
# RoleDefinition / RolePermissionManager
# --------------------------------------------------------------------------

def test_role_definition_inherited_permissions_union():
    base = RoleDefinition(
        name="base",
        description="",
        permissions={Permission.READ_ARTICLES},
    )
    child = RoleDefinition(
        name="child",
        description="",
        permissions={Permission.VIEW_ANALYTICS},
        inherits_from=base,
    )
    all_perms = child.get_all_permissions()
    assert Permission.READ_ARTICLES in all_perms  # inherited
    assert Permission.VIEW_ANALYTICS in all_perms  # own


def test_permission_manager_role_permissions_and_lookups():
    mgr = RolePermissionManager()
    admin_perms = mgr.get_role_permissions(UserRole.ADMIN)
    # Admin inherits premium + free, so it must include a free-tier permission
    assert Permission.READ_ARTICLES in admin_perms
    assert Permission.MANAGE_SYSTEM in admin_perms
    assert mgr.has_permission(UserRole.ADMIN, Permission.MANAGE_SYSTEM) is True
    assert mgr.has_permission(UserRole.FREE, Permission.MANAGE_SYSTEM) is False
    role_def = mgr.get_role_definition(UserRole.PREMIUM)
    assert role_def is not None
    assert role_def.name == "Premium User"


def test_permission_manager_unknown_role_returns_empty():
    mgr = RolePermissionManager()

    class Fake:
        pass

    # Non-registered role -> empty set (line 147-149 guard)
    assert mgr.get_role_permissions(Fake()) == set()


# --------------------------------------------------------------------------
# DynamoDBPermissionStore against moto
# --------------------------------------------------------------------------

@mock_aws
def test_permission_store_creates_table_and_crud():
    store = DynamoDBPermissionStore()
    # Table did not exist -> _create_table ran and table is usable
    assert store.table is not None

    # store_user_permissions with custom perms
    ok = run(
        store.store_user_permissions(
            "user-1", UserRole.PREMIUM, custom_permissions=["extra_perm"]
        )
    )
    assert ok is True

    # get_user_permissions returns the stored item
    item = run(store.get_user_permissions("user-1"))
    assert item is not None
    assert item["role"] == "premium"
    assert item["custom_permissions"] == ["extra_perm"]

    # update_user_role
    updated = run(store.update_user_role("user-1", UserRole.ADMIN))
    assert updated is True
    item2 = run(store.get_user_permissions("user-1"))
    assert item2["role"] == "admin"

    # delete_user_permissions
    deleted = run(store.delete_user_permissions("user-1"))
    assert deleted is True
    assert run(store.get_user_permissions("missing")) is None


@mock_aws
def test_permission_store_existing_table_load_path():
    # Pre-create the table so _ensure_table_exists hits the load() success path
    import boto3

    table_name = "neuronews_rbac_permissions"
    client = boto3.client("dynamodb", region_name="us-east-1")
    client.create_table(
        TableName=table_name,
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)

    store = DynamoDBPermissionStore()
    assert store.table is not None
    # store then read back to prove the reused table works
    assert run(store.store_user_permissions("u2", UserRole.FREE)) is True
    got = run(store.get_user_permissions("u2"))
    assert got["role"] == "free"


def test_permission_store_no_table_returns_safe_defaults(monkeypatch):
    # Force init failure so self.table stays None and guard branches run
    def boom(*a, **k):
        raise RuntimeError("no dynamo")

    monkeypatch.setattr(rbac_system, "get_resource", boom, raising=False)
    # get_resource is imported lazily inside __init__; patch the module attr it
    # imports from via the local_cloud module instead.
    import src.utils.local_cloud as lc

    monkeypatch.setattr(lc, "get_resource", boom)

    store = DynamoDBPermissionStore()
    assert store.table is None
    assert run(store.store_user_permissions("x", UserRole.FREE)) is False
    assert run(store.get_user_permissions("x")) is None
    assert run(store.update_user_role("x", UserRole.ADMIN)) is False
    assert run(store.delete_user_permissions("x")) is False


@mock_aws
def test_permission_store_crud_exception_handlers():
    """Force each CRUD op to raise so the except/return-False paths run."""
    store = DynamoDBPermissionStore()
    assert store.table is not None

    failing = MagicMock()
    failing.put_item.side_effect = RuntimeError("boom")
    failing.get_item.side_effect = RuntimeError("boom")
    failing.update_item.side_effect = RuntimeError("boom")
    failing.delete_item.side_effect = RuntimeError("boom")
    store.table = failing

    assert run(store.store_user_permissions("u", UserRole.FREE)) is False
    assert run(store.get_user_permissions("u")) is None
    assert run(store.update_user_role("u", UserRole.ADMIN)) is False
    assert run(store.delete_user_permissions("u")) is False


@mock_aws
def test_ensure_table_exists_non_notfound_error(monkeypatch):
    """A non-ResourceNotFound ClientError on load() is logged, not raised."""
    store = DynamoDBPermissionStore()

    err = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
        "DescribeTable",
    )
    bad_table = MagicMock()
    bad_table.load.side_effect = err
    store.table = bad_table
    # Should swallow the error (else branch, line 197-198), not raise
    store._ensure_table_exists()
    bad_table.load.assert_called_once()


@mock_aws
def test_ensure_and_create_table_no_dynamodb_guard():
    store = DynamoDBPermissionStore()
    # Simulate an unavailable client -> both methods hit their early-return guard
    store.dynamodb = None
    assert store._ensure_table_exists() is None  # line 186-187
    assert store._create_table() is None  # line 202-203


@mock_aws
def test_create_table_exception_is_swallowed(monkeypatch):
    store = DynamoDBPermissionStore()
    # Make create_table blow up -> except branch (lines 224-225)
    store.dynamodb = MagicMock()
    store.dynamodb.create_table.side_effect = RuntimeError("cannot create")
    # Should not raise
    store._create_table()
    store.dynamodb.create_table.assert_called_once()


# --------------------------------------------------------------------------
# RBACManager
# --------------------------------------------------------------------------

@mock_aws
def _make_manager():
    return RBACManager()


def test_endpoint_permissions_exact_param_and_default():
    mgr = RBACManager()
    # exact match
    assert mgr.get_endpoint_permissions("GET", "/api/articles") == {
        Permission.READ_ARTICLES
    }
    # parameterized route -> matches pattern with {id}
    assert mgr.get_endpoint_permissions("DELETE", "/api/articles/42") == {
        Permission.DELETE_ARTICLES
    }
    # public endpoint -> empty set
    assert mgr.get_endpoint_permissions("GET", "/health") == set()
    # unknown endpoint -> default basic API
    assert mgr.get_endpoint_permissions("GET", "/totally/unknown") == {
        Permission.ACCESS_BASIC_API
    }


def test_matches_pattern_length_mismatch():
    mgr = RBACManager()
    # Different segment counts -> not a match
    assert mgr._matches_pattern("GET /a/b/c", "GET /a/b") is False
    # Literal mismatch on non-param segment
    assert mgr._matches_pattern("GET /api/x", "GET /api/y") is False


def test_has_access_rules():
    mgr = RBACManager()
    # Public endpoint -> always accessible
    assert mgr.has_access(UserRole.FREE, "GET", "/health") is True
    # Free user cannot manage system
    assert mgr.has_access(UserRole.FREE, "POST", "/api/admin/system") is False
    # Admin can manage system
    assert mgr.has_access(UserRole.ADMIN, "POST", "/api/admin/system") is True
    # Free user can read articles
    assert mgr.has_access(UserRole.FREE, "GET", "/api/articles") is True


@mock_aws
def test_manager_store_and_get_role_from_db():
    mgr = RBACManager()
    assert run(mgr.store_user_permissions("admin-user", UserRole.ADMIN)) is True
    role = run(mgr.get_user_role_from_db("admin-user"))
    assert role == UserRole.ADMIN
    # Missing user -> None
    assert run(mgr.get_user_role_from_db("ghost")) is None


@mock_aws
def test_manager_get_role_from_db_invalid_value():
    mgr = RBACManager()
    # Store a raw item with an invalid role string
    mgr.permission_store.table.put_item(
        Item={"user_id": "weird", "role": "superuser"}
    )
    # Invalid role value -> ValueError caught -> None (lines 421-425)
    assert run(mgr.get_user_role_from_db("weird")) is None


def test_get_role_summary_structure():
    mgr = RBACManager()
    summary = mgr.get_role_summary()
    assert set(summary.keys()) == {"admin", "premium", "free"}
    admin = summary["admin"]
    assert admin["name"] == "Administrator"
    assert admin["permission_count"] == len(admin["permissions"])
    assert "manage_system" in admin["permissions"]
