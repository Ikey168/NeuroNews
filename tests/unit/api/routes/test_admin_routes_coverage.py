"""Coverage tests for src/api/routes/admin_routes.py.

Mounts the router on a fresh app and overrides dependencies so the endpoint
bodies actually execute (the smoke test only reaches 401 auth failures).
Targets the remaining uncovered lines: endpoint bodies, error handlers,
the require_admin role gate, and per-endpoint branch conditions.
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.admin_routes as mod


def _make_client(db, admin_user=None):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_db] = lambda: db
    if admin_user is not None:
        app.dependency_overrides[mod.require_admin] = lambda: admin_user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_user():
    return {"sub": "admin-1", "role": "admin"}


@pytest.fixture
def db_ok():
    db = MagicMock()
    # metrics row with a real datetime for latest_article_date branch
    from datetime import datetime

    db.execute_query = AsyncMock(
        return_value=[[5, 3, 2, datetime(2026, 1, 1, 12, 0, 0)]]
    )
    return db


# --- require_admin gate -------------------------------------------------

def test_require_admin_rejects_non_admin(db_ok):
    # No require_admin override -> real gate runs; override require_auth instead
    from src.api.auth.jwt_auth import require_auth

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_db] = lambda: db_ok
    app.dependency_overrides[require_auth] = lambda: {"sub": "u1", "role": "viewer"}
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/admin/users")
    assert resp.status_code == 403
    assert "Admin privileges required" in resp.json()["detail"]


def test_require_admin_allows_administrator(db_ok):
    from src.api.auth.jwt_auth import require_auth

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_db] = lambda: db_ok
    app.dependency_overrides[require_auth] = lambda: {"sub": "u1", "role": "Administrator"}
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/admin/users")
    assert resp.status_code == 200


# --- /admin/health ------------------------------------------------------

def test_health_healthy(db_ok, admin_user):
    client = _make_client(db_ok, admin_user)
    resp = client.get("/admin/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["database_status"] == "healthy"
    assert body["metrics"]["total_articles_7d"] == 5
    assert body["metrics"]["unique_sources"] == 3
    assert body["metrics"]["latest_article_date"] == "2026-01-01T12:00:00"
    assert body["services"]["database"]["type"] == "snowflake"


def test_health_db_unhealthy_degraded(admin_user):
    # First execute_query (SELECT 1) raises -> db_status unhealthy/degraded,
    # subsequent metrics query returns rows so overall body completes.
    from datetime import datetime

    db = MagicMock()
    calls = {"n": 0}

    async def exec_query(q, p):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("no connection")
        return [[0, 0, 0, None]]

    db.execute_query = AsyncMock(side_effect=exec_query)
    client = _make_client(db, admin_user)
    resp = client.get("/admin/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["database_status"] == "unhealthy"
    assert body["status"] == "degraded"
    # None latest date branch
    assert body["metrics"]["latest_article_date"] is None


def test_health_error_500(admin_user):
    # SELECT 1 succeeds (caught), metrics query raises unhandled -> 500 path
    db = MagicMock()
    calls = {"n": 0}

    async def exec_query(q, p):
        calls["n"] += 1
        if calls["n"] == 1:
            return [[1]]
        raise ValueError("boom")

    db.execute_query = AsyncMock(side_effect=exec_query)
    client = _make_client(db, admin_user)
    resp = client.get("/admin/health")
    assert resp.status_code == 500
    assert "Error retrieving system health" in resp.json()["detail"]


# --- /admin/users -------------------------------------------------------

def test_users_body(db_ok, admin_user):
    client = _make_client(db_ok, admin_user)
    resp = client.get("/admin/users", params={"limit": 10, "offset": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["offset"] == 5
    assert body["has_more"] is False
    assert body["users"][0]["username"] == "admin"


# --- /admin/users/manage ------------------------------------------------

def test_manage_user_valid(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.post(
        "/admin/users/manage",
        json={"user_id": "u42", "action": "activate", "reason": "test"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u42"
    assert body["action"] == "activate"
    assert body["performed_by"] == "admin-1"
    assert body["reason"] == "test"


def test_manage_user_invalid_action(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.post(
        "/admin/users/manage",
        json={"user_id": "u42", "action": "explode"},
    )
    assert resp.status_code == 400
    assert "Invalid action" in resp.json()["detail"]


# --- /admin/system/stats ------------------------------------------------

def test_system_stats_body(admin_user):
    db = MagicMock()

    async def exec_query(q, params):
        if "AVG" in q:
            return [[100, 4, 3, 0.5]]
        if "category" in q.lower():
            return [["Tech", 40], ["Sports", 20]]
        return [["cnn", 30], ["bbc", 25]]

    db.execute_query = AsyncMock(side_effect=exec_query)
    client = _make_client(db, admin_user)
    resp = client.get("/admin/system/stats", params={"days_back": 14})
    assert resp.status_code == 200
    body = resp.json()
    assert body["period"]["days"] == 14
    assert body["article_stats"]["total_articles"] == 100
    assert body["article_stats"]["avg_sentiment"] == 0.5
    assert body["top_categories"][0] == {"category": "Tech", "count": 40}
    assert body["top_sources"][0] == {"source": "cnn", "count": 30}


def test_system_stats_null_sentiment(admin_user):
    db = MagicMock()

    async def exec_query(q, params):
        if "AVG" in q:
            return [[0, 0, 0, None]]
        return []

    db.execute_query = AsyncMock(side_effect=exec_query)
    client = _make_client(db, admin_user)
    resp = client.get("/admin/system/stats")
    assert resp.status_code == 200
    assert resp.json()["article_stats"]["avg_sentiment"] is None


def test_system_stats_error_500(admin_user):
    db = MagicMock()
    db.execute_query = AsyncMock(side_effect=RuntimeError("db down"))
    client = _make_client(db, admin_user)
    resp = client.get("/admin/system/stats")
    assert resp.status_code == 500
    assert "Error retrieving system statistics" in resp.json()["detail"]


# --- /admin/system/config (POST + GET) ----------------------------------

def test_update_system_config(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.post(
        "/admin/system/config",
        json={"setting_key": "rate_limit", "setting_value": 500, "category": "api"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["setting_key"] == "rate_limit"
    assert body["new_value"] == 500
    assert body["updated_by"] == "admin-1"


def test_get_system_config_all(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.get("/admin/system/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "configuration" in body
    assert body["configuration"]["database"]["max_connections"] == 100


def test_get_system_config_category_found(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.get("/admin/system/config", params={"category": "api"})
    assert resp.status_code == 200
    body = resp.json()
    assert "api" in body
    assert body["api"]["enable_caching"] is True


def test_get_system_config_category_missing(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.get("/admin/system/config", params={"category": "nope"})
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


# --- /admin/system/maintenance -----------------------------------------

def test_maintenance_enable(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.post(
        "/admin/system/maintenance",
        params={"enabled": "true", "message": "brb"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["maintenance_enabled"] is True
    assert "enabled successfully" in body["message"]
    assert body["maintenance_message"] == "brb"


def test_maintenance_disable(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.post("/admin/system/maintenance", params={"enabled": "false"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["maintenance_enabled"] is False
    assert "disabled successfully" in body["message"]


# --- /admin/logs --------------------------------------------------------

def test_logs_body(admin_user):
    client = _make_client(MagicMock(), admin_user)
    resp = client.get("/admin/logs", params={"level": "WARN", "hours": 12, "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["level_filter"] == "WARN"
    assert body["time_range"]["hours"] == 12
    assert body["logs"][0]["level"] == "WARN"


# --- get_db dependency body --------------------------------------------

def test_get_db_returns_shared_connection(monkeypatch):
    import src.database.local_analytics_connector as lac
    import asyncio

    sentinel = object()
    monkeypatch.setattr(lac, "get_shared_connection", lambda: sentinel)
    result = asyncio.get_event_loop().run_until_complete(mod.get_db())
    assert result is sentinel


# --- reachable 500 handlers (endpoint bodies raising) -------------------

class _RaisingUser(dict):
    """dict whose .get raises, to trip the generic except handlers."""

    def get(self, *a, **k):
        raise RuntimeError("user lookup boom")


def test_manage_user_500(monkeypatch):
    client = _make_client(MagicMock(), _RaisingUser({"role": "admin"}))
    resp = client.post(
        "/admin/users/manage",
        json={"user_id": "u1", "action": "activate"},
    )
    assert resp.status_code == 500
    assert "Error managing user" in resp.json()["detail"]


def test_update_config_500():
    client = _make_client(MagicMock(), _RaisingUser({"role": "admin"}))
    resp = client.post(
        "/admin/system/config",
        json={"setting_key": "k", "setting_value": 1},
    )
    assert resp.status_code == 500
    assert "Error updating configuration" in resp.json()["detail"]


def test_maintenance_500():
    client = _make_client(MagicMock(), _RaisingUser({"role": "admin"}))
    resp = client.post("/admin/system/maintenance", params={"enabled": "true"})
    assert resp.status_code == 500
    assert "Error toggling maintenance mode" in resp.json()["detail"]
