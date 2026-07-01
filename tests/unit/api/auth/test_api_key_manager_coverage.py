"""Coverage tests for src/api/auth/api_key_manager.py.

Targets remaining uncovered error/branch paths:
  * _ensure_table_exists / _create_table (moto-backed DynamoDB)   165, 173-211
  * DynamoDBAPIKeyStore CRUD exception handlers                   243-314
  * APIKeyManager.verify_api_key prefix guard + placeholder       418-434
  * delete_api_key ownership check                                475-479
  * renew_api_key not-found / inactive / update-error paths       498, 501, 517-519
  * cleanup_expired_keys placeholder                              537

boto3/moto are required; guard with importorskip. moto's ``mock_aws`` intercepts
the boto3 resource that ``get_resource`` builds (endpoint is suppressed under
pytest by src/utils/local_cloud).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from src.api.auth import api_key_manager as akm  # noqa: E402
from src.api.auth.api_key_manager import (  # noqa: E402
    APIKey,
    APIKeyGenerator,
    APIKeyManager,
    APIKeyStatus,
    DynamoDBAPIKeyStore,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_key(user_id="user-1", key_id="key_abc", status=APIKeyStatus.ACTIVE,
              expires_at=None):
    now = datetime.now(timezone.utc)
    return APIKey(
        key_id=key_id,
        user_id=user_id,
        key_prefix="nn_abcde",
        key_hash="deadbeef",
        name="test-key",
        status=status,
        created_at=now,
        expires_at=expires_at,
        last_used_at=None,
        usage_count=0,
        permissions=["read"],
        rate_limit=60,
    )


# ---------------------------------------------------------------------------
# Table lifecycle (moto) -- _ensure_table_exists / _create_table
# ---------------------------------------------------------------------------

@mock_aws
def test_store_creates_table_when_missing(monkeypatch):
    """Lines 173-208: no table -> ResourceNotFoundException -> _create_table."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")  # suppress local endpoint
    store = DynamoDBAPIKeyStore()
    # moto starts with no table, so the store must have created it.
    assert store.table is not None
    client = boto3.client("dynamodb", region_name=store.region)
    names = client.list_tables()["TableNames"]
    assert store.table_name in names


@mock_aws
def test_store_detects_existing_table(monkeypatch):
    """Line 170 branch: pre-existing table -> load() succeeds, no create."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    # First instance creates the table.
    first = DynamoDBAPIKeyStore()
    assert first.table is not None
    # Second instance should find and load the existing table.
    second = DynamoDBAPIKeyStore()
    assert second.table is not None


def _bare_store():
    """Store instance without touching AWS (dynamodb/table set manually)."""
    store = DynamoDBAPIKeyStore.__new__(DynamoDBAPIKeyStore)
    store.table_name = "t"
    store.region = "us-east-1"
    store.dynamodb = None
    store.table = None
    return store


def test_ensure_table_exists_noop_without_dynamodb():
    """Line 164-165: no dynamodb client -> early return, no error."""
    store = _bare_store()
    # Should simply return; no exception even though table is None.
    assert store._ensure_table_exists() is None


def test_create_table_noop_without_dynamodb():
    """Lines 180-181: no dynamodb client -> early return."""
    store = _bare_store()
    assert store._create_table() is None


def test_ensure_table_exists_non_rnf_error_logged():
    """Lines 171-176: a ClientError that is NOT ResourceNotFound is logged."""

    class _LoadTable:
        def load(self):
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "denied"}},
                "DescribeTable",
            )

    store = _bare_store()
    store.dynamodb = object()  # truthy -> skips the early return
    store.table = _LoadTable()
    # Must not raise: the non-RNF branch only logs.
    assert store._ensure_table_exists() is None


def test_ensure_table_exists_rnf_triggers_create():
    """Lines 172-174: ResourceNotFoundException -> _create_table invoked."""

    class _MissingTable:
        def load(self):
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": "gone"}},
                "DescribeTable",
            )

    store = _bare_store()
    store.dynamodb = object()
    store.table = _MissingTable()

    created = {"called": False}
    store._create_table = lambda: created.__setitem__("called", True)
    store._ensure_table_exists()
    assert created["called"] is True


def test_create_table_failure_logged():
    """Lines 210-211: create_table raising is caught and logged, not raised."""

    class _BadDynamo:
        def create_table(self, **_):
            raise RuntimeError("boom creating table")

    store = _bare_store()
    store.dynamodb = _BadDynamo()
    # Should swallow the exception (only logs).
    assert store._create_table() is None
    # table stays None because creation failed.
    assert store.table is None


def test_create_table_success_sets_table():
    """Lines 184-208: create_table succeeds -> self.table assigned."""

    class _NewTable:
        def wait_until_exists(self):
            pass

    class _GoodDynamo:
        def create_table(self, **kwargs):
            assert kwargs["TableName"] == "t"
            return _NewTable()

    store = _bare_store()
    store.dynamodb = _GoodDynamo()
    store._create_table()
    assert isinstance(store.table, _NewTable)


# ---------------------------------------------------------------------------
# CRUD happy path + exception handlers via a raising fake table
# ---------------------------------------------------------------------------

class _RaisingTable:
    """Fake DynamoDB Table whose operations all raise."""

    def put_item(self, **_):
        raise RuntimeError("put failed")

    def get_item(self, **_):
        raise RuntimeError("get failed")

    def query(self, **_):
        raise RuntimeError("query failed")

    def update_item(self, **_):
        raise RuntimeError("update failed")

    def delete_item(self, **_):
        raise RuntimeError("delete failed")


def _store_with_table(table):
    store = DynamoDBAPIKeyStore.__new__(DynamoDBAPIKeyStore)
    store.table_name = "t"
    store.region = "us-east-1"
    store.dynamodb = object()
    store.table = table
    return store


def test_store_api_key_exception_returns_false():
    """Lines 228-230: put_item raises -> False."""
    store = _store_with_table(_RaisingTable())
    assert _run(store.store_api_key(_make_key())) is False


def test_get_api_key_exception_returns_none():
    """Lines 243-245: get_item raises -> None."""
    store = _store_with_table(_RaisingTable())
    assert _run(store.get_api_key("key_abc")) is None


def test_get_user_api_keys_exception_returns_empty():
    """Lines 261-263: query raises -> []."""
    store = _store_with_table(_RaisingTable())
    assert _run(store.get_user_api_keys("user-1")) == []


def test_update_usage_exception_returns_false():
    """Lines 279-281: update_item raises -> False."""
    store = _store_with_table(_RaisingTable())
    assert _run(store.update_api_key_usage("key_abc")) is False


def test_revoke_exception_returns_false():
    """Lines 298-300: update_item raises -> False."""
    store = _store_with_table(_RaisingTable())
    assert _run(store.revoke_api_key("key_abc")) is False


def test_delete_exception_returns_false():
    """Lines 312-314: delete_item raises -> False."""
    store = _store_with_table(_RaisingTable())
    assert _run(store.delete_api_key("key_abc")) is False


# ---------------------------------------------------------------------------
# CRUD happy paths (moto) so store methods hit their success branches too
# ---------------------------------------------------------------------------

@mock_aws
def test_store_crud_roundtrip(monkeypatch):
    """Lines 220-226, 238-241, 253-259, 272-277, 289-296, 308-310."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    store = DynamoDBAPIKeyStore()
    key = _make_key(user_id="roundtrip", key_id="key_rt")

    assert _run(store.store_api_key(key)) is True

    fetched = _run(store.get_api_key("key_rt"))
    assert fetched is not None and fetched.user_id == "roundtrip"

    user_keys = _run(store.get_user_api_keys("roundtrip"))
    assert any(k.key_id == "key_rt" for k in user_keys)

    assert _run(store.update_api_key_usage("key_rt")) is True
    assert _run(store.revoke_api_key("key_rt")) is True

    revoked = _run(store.get_api_key("key_rt"))
    assert revoked.status == APIKeyStatus.REVOKED

    assert _run(store.delete_api_key("key_rt")) is True
    assert _run(store.get_api_key("key_rt")) is None


def test_get_api_key_missing_item_returns_none():
    """Line 241: response without 'Item' -> None."""

    class _EmptyTable:
        def get_item(self, **_):
            return {}

    store = _store_with_table(_EmptyTable())
    assert _run(store.get_api_key("nope")) is None


def test_store_methods_return_defaults_when_no_table():
    """Lines 215-217, 234-235, 249-250, 267-268, 285-286, 304-305: table None guards."""
    store = _store_with_table(None)  # table is None

    assert _run(store.store_api_key(_make_key())) is False
    assert _run(store.get_api_key("key_abc")) is None
    assert _run(store.get_user_api_keys("user-1")) == []
    assert _run(store.update_api_key_usage("key_abc")) is False
    assert _run(store.revoke_api_key("key_abc")) is False
    assert _run(store.delete_api_key("key_abc")) is False


# ---------------------------------------------------------------------------
# APIKeyManager: verify / delete / renew / cleanup branches
# ---------------------------------------------------------------------------

def _manager_with_store(store):
    mgr = APIKeyManager.__new__(APIKeyManager)
    mgr.store = store
    mgr.default_expiry_days = 365
    mgr.max_keys_per_user = 10
    return mgr


def test_verify_api_key_rejects_bad_prefix():
    """Line 418-419: keys without the nn_ prefix are rejected immediately."""
    mgr = _manager_with_store(_store_with_table(None))
    assert _run(mgr.verify_api_key("bogus-key")) is None


def test_verify_api_key_valid_prefix_returns_placeholder():
    """Lines 421-434: valid prefix currently returns the placeholder None."""
    mgr = _manager_with_store(_store_with_table(None))
    assert _run(mgr.verify_api_key("nn_realkey")) is None


class _FakeStore:
    """Minimal in-memory stand-in for DynamoDBAPIKeyStore."""

    def __init__(self):
        self.keys = {}
        self.table = None
        self.revoked = []
        self.deleted = []

    async def get_api_key(self, key_id):
        return self.keys.get(key_id)

    async def revoke_api_key(self, key_id):
        self.revoked.append(key_id)
        return True

    async def delete_api_key(self, key_id):
        self.deleted.append(key_id)
        return True


def test_revoke_api_key_wrong_owner_returns_false():
    """Line 467-468: key owned by another user -> False (not revoked)."""
    store = _FakeStore()
    store.keys["key_x"] = _make_key(user_id="owner", key_id="key_x")
    mgr = _manager_with_store(store)

    assert _run(mgr.revoke_api_key("intruder", "key_x")) is False
    assert store.revoked == []


def test_revoke_api_key_correct_owner_delegates():
    """Line 470: correct owner -> delegates to store.revoke_api_key."""
    store = _FakeStore()
    store.keys["key_x"] = _make_key(user_id="owner", key_id="key_x")
    mgr = _manager_with_store(store)

    assert _run(mgr.revoke_api_key("owner", "key_x")) is True
    assert store.revoked == ["key_x"]


def test_delete_api_key_wrong_owner_returns_false():
    """Lines 475-477: key missing or wrong owner -> False."""
    store = _FakeStore()
    store.keys["key_x"] = _make_key(user_id="owner", key_id="key_x")
    mgr = _manager_with_store(store)

    assert _run(mgr.delete_api_key("intruder", "key_x")) is False
    assert store.deleted == []


def test_delete_api_key_missing_key_returns_false():
    """Line 476: key not found at all -> False."""
    store = _FakeStore()
    mgr = _manager_with_store(store)
    assert _run(mgr.delete_api_key("owner", "absent")) is False


def test_delete_api_key_correct_owner_delegates():
    """Line 479: correct owner -> delegates to store.delete_api_key."""
    store = _FakeStore()
    store.keys["key_x"] = _make_key(user_id="owner", key_id="key_x")
    mgr = _manager_with_store(store)

    assert _run(mgr.delete_api_key("owner", "key_x")) is True
    assert store.deleted == ["key_x"]


def test_renew_api_key_not_found_raises():
    """Line 497-498: unknown/foreign key -> ValueError."""
    store = _FakeStore()
    mgr = _manager_with_store(store)
    with pytest.raises(ValueError, match="not found or not owned"):
        _run(mgr.renew_api_key("owner", "absent"))


def test_renew_api_key_inactive_raises():
    """Lines 500-501: non-active key -> ValueError."""
    store = _FakeStore()
    store.keys["key_x"] = _make_key(
        user_id="owner", key_id="key_x", status=APIKeyStatus.REVOKED
    )
    mgr = _manager_with_store(store)
    with pytest.raises(ValueError, match="Cannot renew inactive"):
        _run(mgr.renew_api_key("owner", "key_x"))


def test_renew_api_key_no_table_returns_payload():
    """Lines 503-531 with store.table None: skips DB update, returns metadata."""
    store = _FakeStore()  # table is None
    old_exp = datetime.now(timezone.utc) + timedelta(days=10)
    store.keys["key_x"] = _make_key(
        user_id="owner", key_id="key_x", expires_at=old_exp
    )
    mgr = _manager_with_store(store)

    result = _run(mgr.renew_api_key("owner", "key_x", extends_days=30))
    assert result["status"] == "renewed"
    assert result["extended_days"] == 30
    assert result["old_expires_at"] == old_exp.isoformat()
    # new expiry is ~30 days out
    new_exp = datetime.fromisoformat(result["new_expires_at"])
    assert new_exp > datetime.now(timezone.utc) + timedelta(days=29)


def test_renew_api_key_update_error_raises_runtime():
    """Lines 508-519: table.update_item raising -> RuntimeError."""
    store = _FakeStore()
    store.table = _RaisingTable()  # update_item raises
    store.keys["key_x"] = _make_key(user_id="owner", key_id="key_x")
    mgr = _manager_with_store(store)

    with pytest.raises(RuntimeError, match="Failed to renew"):
        _run(mgr.renew_api_key("owner", "key_x"))


def test_renew_api_key_default_extend_uses_default_expiry():
    """Line 504: extends_days omitted -> default_expiry_days used."""
    store = _FakeStore()
    store.keys["key_x"] = _make_key(user_id="owner", key_id="key_x")
    mgr = _manager_with_store(store)
    mgr.default_expiry_days = 90

    result = _run(mgr.renew_api_key("owner", "key_x"))
    assert result["extended_days"] == 90


def test_cleanup_expired_keys_returns_zero():
    """Line 537: placeholder cleanup returns 0."""
    mgr = _manager_with_store(_FakeStore())
    assert _run(mgr.cleanup_expired_keys()) == 0


# ---------------------------------------------------------------------------
# APIKeyGenerator (lines 108-134) and generate_api_key (lines 348-393)
# ---------------------------------------------------------------------------

def test_generator_key_format_and_uniqueness():
    """Lines 108-120: generated keys/ids have the right prefixes and differ."""
    k1 = APIKeyGenerator.generate_api_key()
    k2 = APIKeyGenerator.generate_api_key()
    assert k1.startswith("nn_") and k2.startswith("nn_")
    assert k1 != k2

    kid = APIKeyGenerator.generate_key_id()
    assert kid.startswith("key_")


def test_generator_hash_and_verify_roundtrip():
    """Lines 123-134: hash is deterministic and verify matches / rejects."""
    key = "nn_verify_me"
    h = APIKeyGenerator.hash_api_key(key)
    assert h == APIKeyGenerator.hash_api_key(key)  # deterministic
    assert APIKeyGenerator.verify_api_key(key, h) is True
    assert APIKeyGenerator.verify_api_key("nn_wrong", h) is False


class _GenStore(_FakeStore):
    """FakeStore that also supports store_api_key + user listing for generate."""

    def __init__(self, existing=None):
        super().__init__()
        self._user_keys = existing or []
        self.stored = []
        self.store_ok = True

    async def get_user_api_keys(self, user_id):
        return list(self._user_keys)

    async def store_api_key(self, api_key):
        self.stored.append(api_key)
        return self.store_ok


def test_generate_api_key_success_returns_key(monkeypatch):
    """Lines 348-406: happy path returns a fresh key with metadata."""
    store = _GenStore(existing=[])
    mgr = _manager_with_store(store)
    mgr.default_expiry_days = 365

    result = _run(mgr.generate_api_key("user-1", "primary", permissions=["read"]))
    assert result["api_key"].startswith("nn_")
    assert result["name"] == "primary"
    assert result["status"] == "active"
    assert result["expires_at"] is not None
    assert result["permissions"] == ["read"]
    assert len(store.stored) == 1


def test_generate_api_key_no_expiry_when_default_zero():
    """Lines 366-370: default_expiry_days == 0 and no explicit -> expires_at None."""
    store = _GenStore(existing=[])
    mgr = _manager_with_store(store)
    mgr.default_expiry_days = 0

    result = _run(mgr.generate_api_key("user-1", "no-exp"))
    assert result["expires_at"] is None


def test_generate_api_key_explicit_expiry_days():
    """Line 367-368: explicit expires_in_days path."""
    store = _GenStore(existing=[])
    mgr = _manager_with_store(store)

    result = _run(mgr.generate_api_key("user-1", "temp", expires_in_days=7))
    exp = datetime.fromisoformat(result["expires_at"])
    assert exp < datetime.now(timezone.utc) + timedelta(days=8)


def test_generate_api_key_over_limit_raises():
    """Lines 351-356: exceeding max_keys_per_user raises ValueError."""
    active = [
        _make_key(user_id="u", key_id="k{0}".format(i)) for i in range(3)
    ]
    store = _GenStore(existing=active)
    mgr = _manager_with_store(store)
    mgr.max_keys_per_user = 3

    with pytest.raises(ValueError, match="maximum API key limit"):
        _run(mgr.generate_api_key("u", "one-too-many"))


def test_generate_api_key_store_failure_raises_runtime():
    """Lines 389-391: store_api_key returning False -> RuntimeError."""
    store = _GenStore(existing=[])
    store.store_ok = False
    mgr = _manager_with_store(store)

    with pytest.raises(RuntimeError, match="Failed to store API key"):
        _run(mgr.generate_api_key("u", "willfail"))


def test_manager_get_user_api_keys_serializes(monkeypatch):
    """Lines 436-461: manager-level listing serializes keys with is_expired."""
    store = _FakeStore()
    expired = _make_key(
        user_id="u",
        key_id="expired",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    active = _make_key(
        user_id="u",
        key_id="active",
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    async def _get_user_keys(user_id):
        return [expired, active]

    store.get_user_api_keys = _get_user_keys
    mgr = _manager_with_store(store)

    listing = _run(mgr.get_user_api_keys("u"))
    by_id = {k["key_id"]: k for k in listing}
    assert by_id["expired"]["is_expired"] is True
    assert by_id["active"]["is_expired"] is False
    # actual key value is never leaked
    assert all("api_key" not in item for item in listing)
