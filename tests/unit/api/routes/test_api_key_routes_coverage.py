"""Comprehensive coverage tests for src/api/routes/api_key_routes.py.

Mounts the router on a fresh FastAPI app. Auth is faked in two ways:
- endpoints depending on get_user_id: override get_user_id
- endpoints depending on require_auth directly (query-param generate, admin
  metrics, admin cleanup): override require_auth to return a claims dict
The module-level api_key_manager is replaced with an AsyncMock-backed mock.
Exercises success, ValueError->400, RuntimeError->500, generic->500, 404,
403 (non-admin / cross-user), and 422 validation paths.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.api_key_routes as mod  # noqa: E402


def make_key(key_id="key-1", status="active", is_expired=False, usage_count=3):
    return {
        "key_id": key_id,
        "key_prefix": "nk_abc",
        "name": "My Key",
        "status": status,
        "created_at": "2024-01-01T00:00:00",
        "expires_at": "2025-01-01T00:00:00",
        "last_used_at": "2024-06-01T00:00:00",
        "usage_count": usage_count,
        "permissions": ["read"],
        "rate_limit": 100,
        "is_expired": is_expired,
    }


def make_generate_result():
    return {
        "key_id": "key-1",
        "api_key": "nk_secret_value",
        "key_prefix": "nk_abc",
        "name": "My Key",
        "status": "active",
        "created_at": "2024-01-01T00:00:00",
        "expires_at": "2025-01-01T00:00:00",
        "permissions": ["read"],
        "rate_limit": 100,
        "message": "API key generated successfully",
    }


@pytest.fixture
def manager(monkeypatch):
    m = MagicMock()
    m.generate_api_key = AsyncMock(return_value=make_generate_result())
    m.get_user_api_keys = AsyncMock(return_value=[make_key()])
    m.revoke_api_key = AsyncMock(return_value=True)
    m.delete_api_key = AsyncMock(return_value=True)
    m.renew_api_key = AsyncMock(
        return_value={"key_id": "key-1", "status": "active", "message": "renewed"}
    )
    m.cleanup_expired_keys = AsyncMock(return_value=2)
    monkeypatch.setattr(mod, "api_key_manager", m)
    return m


@pytest.fixture
def admin_claims():
    return {"sub": "user-1", "role": "admin"}


@pytest.fixture
def user_claims():
    return {"sub": "user-1", "role": "user"}


@pytest.fixture
def client(manager, user_claims):
    """Default client: user-1 authenticated as a regular user."""
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_user_id] = lambda: "user-1"
    app.dependency_overrides[mod.require_auth] = lambda: user_claims
    return TestClient(app, raise_server_exceptions=False)


def make_client(manager, user_id="user-1", claims=None):
    app = FastAPI()
    app.include_router(mod.router)
    if user_id is not None:
        app.dependency_overrides[mod.get_user_id] = lambda: user_id
    if claims is not None:
        app.dependency_overrides[mod.require_auth] = lambda: claims
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /generate (generate_api_key)
# ---------------------------------------------------------------------------
def test_generate_success(client):
    resp = client.post(
        "/api/keys/generate",
        json={"name": "My Key", "expires_in_days": 30, "permissions": ["read"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key"] == "nk_secret_value"
    assert body["key_id"] == "key-1"


def test_generate_value_error_400(client, manager):
    manager.generate_api_key.side_effect = ValueError("bad name")
    resp = client.post("/api/keys/generate", json={"name": "My Key"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "bad name"


def test_generate_runtime_error_500(client, manager):
    manager.generate_api_key.side_effect = RuntimeError("store down")
    resp = client.post("/api/keys/generate", json={"name": "My Key"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "store down"


def test_generate_generic_error_500(client, manager):
    manager.generate_api_key.side_effect = KeyError("weird")
    resp = client.post("/api/keys/generate", json={"name": "My Key"})
    assert resp.status_code == 500
    assert "Failed to generate API key" in resp.json()["detail"]


def test_generate_validation_error_missing_name(client):
    resp = client.post("/api/keys/generate", json={})
    assert resp.status_code == 422


def test_generate_validation_error_name_too_long(client):
    resp = client.post("/api/keys/generate", json={"name": "x" * 101})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /generate_api_key (generate_api_key_query_param)
# ---------------------------------------------------------------------------
def test_generate_query_param_self_success(manager, user_claims):
    c = make_client(manager, claims=user_claims)
    resp = c.get(
        "/api/keys/generate_api_key",
        params={"user_id": "user-1", "name": "Key"},
    )
    assert resp.status_code == 200
    assert resp.json()["api_key"] == "nk_secret_value"


def test_generate_query_param_admin_for_other_user(manager, admin_claims):
    c = make_client(manager, claims=admin_claims)
    resp = c.get(
        "/api/keys/generate_api_key", params={"user_id": "someone-else"}
    )
    assert resp.status_code == 200


def test_generate_query_param_forbidden_cross_user(manager, user_claims):
    c = make_client(manager, claims=user_claims)
    resp = c.get(
        "/api/keys/generate_api_key", params={"user_id": "someone-else"}
    )
    assert resp.status_code == 403
    assert "your own account" in resp.json()["detail"]


def test_generate_query_param_missing_user_id(manager, user_claims):
    c = make_client(manager, claims=user_claims)
    resp = c.get("/api/keys/generate_api_key")
    assert resp.status_code == 422


def test_generate_query_param_value_error_400(manager, user_claims):
    manager.generate_api_key.side_effect = ValueError("bad")
    c = make_client(manager, claims=user_claims)
    resp = c.get("/api/keys/generate_api_key", params={"user_id": "user-1"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "bad"


def test_generate_query_param_runtime_error_500(manager, user_claims):
    manager.generate_api_key.side_effect = RuntimeError("down")
    c = make_client(manager, claims=user_claims)
    resp = c.get("/api/keys/generate_api_key", params={"user_id": "user-1"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "down"


def test_generate_query_param_generic_error_500(manager, user_claims):
    manager.generate_api_key.side_effect = KeyError("weird")
    c = make_client(manager, claims=user_claims)
    resp = c.get("/api/keys/generate_api_key", params={"user_id": "user-1"})
    assert resp.status_code == 500
    assert "Failed to generate API key" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET / (list_api_keys)
# ---------------------------------------------------------------------------
def test_list_keys_success(client):
    resp = client.get("/api/keys/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["key_id"] == "key-1"


def test_list_keys_internal_error(client, manager):
    manager.get_user_api_keys.side_effect = RuntimeError("db down")
    resp = client.get("/api/keys/")
    assert resp.status_code == 500
    assert "Failed to retrieve API keys" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /{key_id} (get_api_key)
# ---------------------------------------------------------------------------
def test_get_key_found(client):
    resp = client.get("/api/keys/key-1")
    assert resp.status_code == 200
    assert resp.json()["key_id"] == "key-1"


def test_get_key_not_found(client, manager):
    manager.get_user_api_keys.return_value = [make_key(key_id="other")]
    resp = client.get("/api/keys/key-1")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "API key not found"


def test_get_key_internal_error(client, manager):
    manager.get_user_api_keys.side_effect = RuntimeError("db down")
    resp = client.get("/api/keys/key-1")
    assert resp.status_code == 500
    assert "Failed to retrieve API key" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /revoke (revoke_api_key)
# ---------------------------------------------------------------------------
def test_revoke_success(client):
    resp = client.post("/api/keys/revoke", json={"key_id": "key-1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "revoked"
    assert body["key_id"] == "key-1"


def test_revoke_not_found(client, manager):
    manager.revoke_api_key.return_value = False
    resp = client.post("/api/keys/revoke", json={"key_id": "key-1"})
    assert resp.status_code == 404
    assert "not found or not owned" in resp.json()["detail"]


def test_revoke_internal_error(client, manager):
    manager.revoke_api_key.side_effect = RuntimeError("down")
    resp = client.post("/api/keys/revoke", json={"key_id": "key-1"})
    assert resp.status_code == 500
    assert "Failed to revoke API key" in resp.json()["detail"]


def test_revoke_validation_error(client):
    resp = client.post("/api/keys/revoke", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /{key_id} (delete_api_key)
# ---------------------------------------------------------------------------
def test_delete_success(client):
    resp = client.delete("/api/keys/key-1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "deleted"
    assert body["key_id"] == "key-1"


def test_delete_not_found(client, manager):
    manager.delete_api_key.return_value = False
    resp = client.delete("/api/keys/key-1")
    assert resp.status_code == 404
    assert "not found or not owned" in resp.json()["detail"]


def test_delete_internal_error(client, manager):
    manager.delete_api_key.side_effect = RuntimeError("down")
    resp = client.delete("/api/keys/key-1")
    assert resp.status_code == 500
    assert "Failed to delete API key" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /renew (renew_api_key)
# ---------------------------------------------------------------------------
def test_renew_success(client):
    resp = client.post(
        "/api/keys/renew", json={"key_id": "key-1", "extends_days": 90}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_renew_value_error_400(client, manager):
    manager.renew_api_key.side_effect = ValueError("cannot renew")
    resp = client.post("/api/keys/renew", json={"key_id": "key-1"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "cannot renew"


def test_renew_runtime_error_500(client, manager):
    manager.renew_api_key.side_effect = RuntimeError("down")
    resp = client.post("/api/keys/renew", json={"key_id": "key-1"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "down"


def test_renew_generic_error_500(client, manager):
    manager.renew_api_key.side_effect = KeyError("weird")
    resp = client.post("/api/keys/renew", json={"key_id": "key-1"})
    assert resp.status_code == 500
    assert "Failed to renew API key" in resp.json()["detail"]


def test_renew_validation_error(client):
    resp = client.post("/api/keys/renew", json={})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /usage/stats (get_api_key_usage_stats)
# ---------------------------------------------------------------------------
def test_usage_stats_success(client, manager, monkeypatch):
    manager.get_user_api_keys.return_value = [
        make_key(key_id="k1", status="active", is_expired=False, usage_count=5),
        make_key(key_id="k2", status="revoked", is_expired=False, usage_count=2),
        make_key(key_id="k3", status="expired", is_expired=True, usage_count=1),
    ]
    # patch api_key_metrics used inside the endpoint
    import src.api.auth.api_key_middleware as mw

    metrics_obj = MagicMock()
    metrics_obj.get_metrics.return_value = {
        "request_counts": {"k1": 10, "k2": 3, "unknown": 99},
        "total_api_requests": 13,
        "active_api_keys": 2,
    }
    monkeypatch.setattr(mw, "api_key_metrics", metrics_obj)

    resp = client.get("/api/keys/usage/stats")
    assert resp.status_code == 200
    body = resp.json()
    summary = body["summary"]
    assert summary["total_keys"] == 3
    assert summary["active_keys"] == 1
    assert summary["expired_keys"] == 1
    assert summary["total_usage"] == 8
    # only k1 + k2 requests count (unknown is not the user's key)
    assert summary["recent_requests"] == 13
    assert len(body["keys"]) == 3


def test_usage_stats_internal_error(client, manager):
    manager.get_user_api_keys.side_effect = RuntimeError("db down")
    resp = client.get("/api/keys/usage/stats")
    assert resp.status_code == 500
    assert "Failed to get usage stats" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /admin/metrics (get_admin_api_key_metrics)
# ---------------------------------------------------------------------------
def test_admin_metrics_success(manager, admin_claims, monkeypatch):
    import src.api.auth.api_key_middleware as mw

    metrics_obj = MagicMock()
    metrics_obj.get_metrics.return_value = {
        "total_api_requests": 100,
        "active_api_keys": 5,
    }
    monkeypatch.setattr(mw, "api_key_metrics", metrics_obj)

    c = make_client(manager, claims=admin_claims)
    resp = c.get("/api/keys/admin/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["system_stats"]["total_api_requests"] == 100
    assert body["system_stats"]["active_api_keys"] == 5


def test_admin_metrics_forbidden_for_non_admin(manager, user_claims):
    c = make_client(manager, claims=user_claims)
    resp = c.get("/api/keys/admin/metrics")
    assert resp.status_code == 403
    assert "Admin privileges required" in resp.json()["detail"]


def test_admin_metrics_internal_error(manager, admin_claims, monkeypatch):
    import src.api.auth.api_key_middleware as mw

    metrics_obj = MagicMock()
    metrics_obj.get_metrics.side_effect = RuntimeError("metrics down")
    monkeypatch.setattr(mw, "api_key_metrics", metrics_obj)

    c = make_client(manager, claims=admin_claims)
    resp = c.get("/api/keys/admin/metrics")
    assert resp.status_code == 500
    assert "Failed to get admin metrics" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /admin/cleanup (cleanup_expired_keys)
# ---------------------------------------------------------------------------
def test_admin_cleanup_success(manager, admin_claims):
    c = make_client(manager, claims=admin_claims)
    resp = c.post("/api/keys/admin/cleanup")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cleaned_count"] == 2


def test_admin_cleanup_forbidden_for_non_admin(manager, user_claims):
    c = make_client(manager, claims=user_claims)
    resp = c.post("/api/keys/admin/cleanup")
    assert resp.status_code == 403
    assert "Admin privileges required" in resp.json()["detail"]


def test_admin_cleanup_internal_error(manager, admin_claims):
    manager.cleanup_expired_keys.side_effect = RuntimeError("cleanup down")
    c = make_client(manager, claims=admin_claims)
    resp = c.post("/api/keys/admin/cleanup")
    assert resp.status_code == 500
    assert "Failed to cleanup expired keys" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /health (api_key_system_health)
#
# Route-shadowing note (genuine source ordering bug): GET /health is declared
# AFTER GET /{key_id}, so /health matches the parameterized route with
# key_id="health".  That route depends on get_user_id -> require_auth, so with
# no auth override it is unreachable / auth-gated rather than returning the
# health payload.  The tests below (a) assert the shadowed route requires auth,
# and (b) invoke the health coroutine directly for its real branches.
# ---------------------------------------------------------------------------
def _run(coro):
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


def test_health_route_is_shadowed(manager):
    # No auth override: /health -> /{key_id} -> require_auth -> not 200 health
    c = make_client(manager, user_id=None)
    resp = c.get("/api/keys/health")
    assert resp.status_code in (401, 403)


def test_health_connected(manager):
    manager.store = MagicMock()
    manager.store.table = object()  # truthy -> connected
    result = _run(mod.api_key_system_health())
    assert result["status"] == "healthy"
    assert result["components"]["dynamodb"] == "connected"
    assert result["components"]["api_key_manager"] == "operational"


def test_health_disconnected(manager):
    manager.store = MagicMock()
    manager.store.table = None  # falsy -> disconnected
    result = _run(mod.api_key_system_health())
    assert result["status"] == "healthy"
    assert result["components"]["dynamodb"] == "disconnected"


def test_health_unhealthy_on_exception(manager):
    # Accessing store.table raises -> unhealthy branch
    broken_store = MagicMock()
    type(broken_store).table = property(
        lambda self: (_ for _ in ()).throw(RuntimeError("no store"))
    )
    manager.store = broken_store
    result = _run(mod.api_key_system_health())
    assert result["status"] == "unhealthy"
    assert "error" in result


# ---------------------------------------------------------------------------
# get_user_id helper (real dependency, not overridden)
# ---------------------------------------------------------------------------
def test_get_user_id_valid():
    result = mod.get_user_id({"sub": "abc"})
    assert result == "abc"


def test_get_user_id_missing_sub():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        mod.get_user_id({})
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid user token"
