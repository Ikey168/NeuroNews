"""Coverage tests for src/api/routes/rbac_routes.py.

Targets branches not covered by test_rbac_routes_smoke.py: the require_admin
403 gate, invalid-role 404, DB-write success + failure paths, the
get_user_permissions authorization / DB-fallback / not-found branches,
check-access, endpoint-permissions, metrics, delete, and the 500 error
handlers on each endpoint.

require_auth is overridden via dependency_overrides. require_admin depends on
require_auth, so overriding require_auth with an admin/non-admin claim drives
its 403 branch for real.
"""
import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.rbac_routes as mod  # noqa: E402
from src.api.auth.jwt_auth import require_auth  # noqa: E402
from src.api.rbac.rbac_system import UserRole  # noqa: E402


def _client(user):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[require_auth] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_client():
    return _client({"sub": "admin1", "role": "admin"})


@pytest.fixture
def user_client():
    return _client({"sub": "u1", "role": "free"})


# --------------------------------------------------------------------------
# GET /api/rbac/roles
# --------------------------------------------------------------------------

def test_get_all_roles_success(user_client):
    resp = user_client.get("/api/rbac/roles")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"admin", "premium", "free"}
    assert body["admin"]["permission_count"] == len(body["admin"]["permissions"])


def test_get_all_roles_500(monkeypatch, user_client):
    rm = MagicMock()
    rm.get_role_summary = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = user_client.get("/api/rbac/roles")
    assert resp.status_code == 500
    assert "Failed to retrieve roles" in resp.json()["detail"]


# --------------------------------------------------------------------------
# GET /api/rbac/roles/{role_name}
# --------------------------------------------------------------------------

def test_get_role_info_success(user_client):
    resp = user_client.get("/api/rbac/roles/Admin")  # case-insensitive
    assert resp.status_code == 200
    assert resp.json()["name"]


def test_get_role_info_invalid_404(user_client):
    resp = user_client.get("/api/rbac/roles/wizard")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_get_role_info_500(monkeypatch, user_client):
    rm = MagicMock()
    rm.get_role_summary = MagicMock(side_effect=RuntimeError("db"))
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = user_client.get("/api/rbac/roles/admin")
    assert resp.status_code == 500
    assert "Failed to retrieve role information" in resp.json()["detail"]


# --------------------------------------------------------------------------
# POST /api/rbac/users/{user_id}/role  (admin only)
# --------------------------------------------------------------------------

def test_update_user_role_forbidden_for_non_admin(user_client):
    resp = user_client.post(
        "/api/rbac/users/target/role",
        json={"user_id": "target", "new_role": "premium"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin privileges required"


def test_update_user_role_success(monkeypatch, admin_client):
    rm = MagicMock()
    rm.store_user_permissions = AsyncMock(return_value=True)
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.post(
        "/api/rbac/users/target/role",
        json={"user_id": "target", "new_role": "premium"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "target"
    assert body["new_role"] == "premium"
    assert body["updated_by"] == "admin1"
    rm.store_user_permissions.assert_awaited_once()


def test_update_user_role_store_returns_false_500(monkeypatch, admin_client):
    rm = MagicMock()
    rm.store_user_permissions = AsyncMock(return_value=False)
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.post(
        "/api/rbac/users/target/role",
        json={"user_id": "target", "new_role": "premium"},
    )
    assert resp.status_code == 500
    assert "Failed to update user role" in resp.json()["detail"]


def test_update_user_role_store_raises_500(monkeypatch, admin_client):
    rm = MagicMock()
    rm.store_user_permissions = AsyncMock(side_effect=RuntimeError("ddb"))
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.post(
        "/api/rbac/users/target/role",
        json={"user_id": "target", "new_role": "premium"},
    )
    assert resp.status_code == 500
    assert "Failed to update user role" in resp.json()["detail"]


def test_update_user_role_invalid_role_422(admin_client):
    resp = admin_client.post(
        "/api/rbac/users/target/role",
        json={"user_id": "target", "new_role": "sudo"},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# GET /api/rbac/users/{user_id}/permissions
# --------------------------------------------------------------------------

def test_get_user_permissions_from_db(monkeypatch, user_client):
    """When the DB knows the user's role, it is used directly."""
    rm = MagicMock()
    rm.get_user_role_from_db = AsyncMock(return_value=UserRole.PREMIUM)
    rm.permission_manager = MagicMock()
    rm.permission_manager.get_role_permissions = MagicMock(
        return_value=list(mod.rbac_manager.permission_manager.get_role_permissions(UserRole.PREMIUM))
    )
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = user_client.get("/api/rbac/users/u1/permissions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u1"
    assert body["role"] == "premium"
    assert isinstance(body["permissions"], list)


def test_get_user_permissions_fallback_to_token_role(monkeypatch):
    """Not in DB, viewing own perms -> fall back to the token's role."""
    rm = MagicMock()
    rm.get_user_role_from_db = AsyncMock(return_value=None)
    rm.permission_manager = mod.rbac_manager.permission_manager
    monkeypatch.setattr(mod, "rbac_manager", rm)
    client = _client({"sub": "u1", "role": "premium"})
    resp = client.get("/api/rbac/users/u1/permissions")
    assert resp.status_code == 200
    assert resp.json()["role"] == "premium"


def test_get_user_permissions_invalid_token_role_defaults_free(monkeypatch):
    """A bad role string in the token falls back to FREE."""
    rm = MagicMock()
    rm.get_user_role_from_db = AsyncMock(return_value=None)
    rm.permission_manager = mod.rbac_manager.permission_manager
    monkeypatch.setattr(mod, "rbac_manager", rm)
    client = _client({"sub": "u1", "role": "banana"})
    resp = client.get("/api/rbac/users/u1/permissions")
    assert resp.status_code == 200
    assert resp.json()["role"] == "free"


def test_get_user_permissions_other_user_forbidden(user_client):
    resp = user_client.get("/api/rbac/users/other/permissions")
    assert resp.status_code == 403
    assert "your own" in resp.json()["detail"]


def test_get_user_permissions_admin_other_not_in_db(monkeypatch, admin_client):
    """Admin querying another user absent from the DB.

    SOURCE BUG: the handler intends to return 404 ("User permissions not
    found"), but that HTTPException(404) is raised *inside* the try block and
    is swallowed by the trailing `except Exception` clause, which re-wraps it
    as a 500. So the observable behaviour is a 500 whose detail mentions the
    original 404 message. We assert the real (buggy) behaviour; the 404-raising
    line still executes, exercising that branch.
    """
    rm = MagicMock()
    rm.get_user_role_from_db = AsyncMock(return_value=None)
    rm.permission_manager = mod.rbac_manager.permission_manager
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.get("/api/rbac/users/ghost/permissions")
    assert resp.status_code == 500
    assert "Failed to retrieve user permissions" in resp.json()["detail"]
    assert "User permissions not found" in resp.json()["detail"]


def test_get_user_permissions_500(monkeypatch, user_client):
    rm = MagicMock()
    rm.get_user_role_from_db = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = user_client.get("/api/rbac/users/u1/permissions")
    assert resp.status_code == 500
    assert "Failed to retrieve user permissions" in resp.json()["detail"]


# --------------------------------------------------------------------------
# POST /api/rbac/check-access
# --------------------------------------------------------------------------

def test_check_access_success(user_client):
    resp = user_client.post(
        "/api/rbac/check-access",
        json={"user_role": "admin", "method": "GET", "path": "/api/x"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_role"] == "admin"
    assert body["endpoint"] == "GET /api/x"
    assert isinstance(body["has_access"], bool)
    assert isinstance(body["required_permissions"], list)


def test_check_access_500(monkeypatch, user_client):
    rm = MagicMock()
    rm.has_access = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = user_client.post(
        "/api/rbac/check-access",
        json={"user_role": "admin", "method": "GET", "path": "/api/x"},
    )
    assert resp.status_code == 500
    assert "Failed to check access" in resp.json()["detail"]


def test_check_access_invalid_role_422(user_client):
    resp = user_client.post(
        "/api/rbac/check-access",
        json={"user_role": "nope", "method": "GET", "path": "/x"},
    )
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# GET /api/rbac/permissions
# --------------------------------------------------------------------------

def test_get_all_permissions_success(user_client):
    resp = user_client.get("/api/rbac/permissions")
    assert resp.status_code == 200
    perms = resp.json()
    assert isinstance(perms, list)
    assert "read_articles" in perms


# --------------------------------------------------------------------------
# GET /api/rbac/endpoint-permissions
# --------------------------------------------------------------------------

def test_get_endpoint_permissions_success(user_client):
    resp = user_client.get(
        "/api/rbac/endpoint-permissions", params={"method": "GET", "path": "/api/x"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["endpoint"] == "GET /api/x"
    assert isinstance(body["required_permissions"], list)
    assert body["permission_count"] == len(body["required_permissions"])
    assert body["public_endpoint"] == (body["permission_count"] == 0)


def test_get_endpoint_permissions_missing_params_422(user_client):
    resp = user_client.get("/api/rbac/endpoint-permissions")
    assert resp.status_code == 422


def test_get_endpoint_permissions_500(monkeypatch, user_client):
    rm = MagicMock()
    rm.get_endpoint_permissions = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = user_client.get(
        "/api/rbac/endpoint-permissions", params={"method": "GET", "path": "/x"}
    )
    assert resp.status_code == 500
    assert "Failed to get endpoint permissions" in resp.json()["detail"]


# --------------------------------------------------------------------------
# GET /api/rbac/metrics  (admin only)
# --------------------------------------------------------------------------

def test_metrics_forbidden_for_non_admin(user_client):
    resp = user_client.get("/api/rbac/metrics")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin privileges required"


def test_metrics_admin_success(admin_client):
    resp = admin_client.get("/api/rbac/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "rbac_metrics" in body
    assert "role_summary" in body
    assert body["total_roles"] == 3


# --------------------------------------------------------------------------
# DELETE /api/rbac/users/{user_id}/permissions  (admin only)
# --------------------------------------------------------------------------

def test_delete_permissions_forbidden_for_non_admin(user_client):
    resp = user_client.delete("/api/rbac/users/target/permissions")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin privileges required"


def test_delete_permissions_success(monkeypatch, admin_client):
    rm = MagicMock()
    rm.permission_store = MagicMock()
    rm.permission_store.delete_user_permissions = AsyncMock(return_value=True)
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.delete("/api/rbac/users/target/permissions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "target"
    assert body["deleted_by"] == "admin1"


def test_delete_permissions_returns_false_500(monkeypatch, admin_client):
    rm = MagicMock()
    rm.permission_store = MagicMock()
    rm.permission_store.delete_user_permissions = AsyncMock(return_value=False)
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.delete("/api/rbac/users/target/permissions")
    assert resp.status_code == 500
    assert "Failed to delete user permissions" in resp.json()["detail"]


def test_delete_permissions_raises_500(monkeypatch, admin_client):
    rm = MagicMock()
    rm.permission_store = MagicMock()
    rm.permission_store.delete_user_permissions = AsyncMock(
        side_effect=RuntimeError("ddb")
    )
    monkeypatch.setattr(mod, "rbac_manager", rm)
    resp = admin_client.delete("/api/rbac/users/target/permissions")
    assert resp.status_code == 500
    assert "Failed to delete user permissions" in resp.json()["detail"]


# --------------------------------------------------------------------------
# require_admin dependency directly
# --------------------------------------------------------------------------

def test_require_admin_accepts_administrator_alias(monkeypatch):
    """The 'administrator' spelling is also accepted (no 403)."""
    client = _client({"sub": "a", "role": "administrator"})
    resp = client.get("/api/rbac/metrics")
    assert resp.status_code == 200
