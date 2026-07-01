"""Coverage tests for src/api/routes/rate_limit_routes.py.

These target lines/branches not exercised by test_rate_limit_routes_smoke.py:
the 403 authz branches, admin-only endpoints (success + 403), the reset
endpoint (memory + admin), the internal-error (500) path, health degraded
path, and the helper functions (_get_user_tier, _get_tier_config,
_reset_user_limits_memory).

All tests mount the router on a fresh app, override require_auth via
dependency_overrides, and assert real status codes and response bodies.
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

import src.api.routes.rate_limit_routes as mod  # noqa: E402
from src.api.auth.jwt_auth import require_auth  # noqa: E402


def _make_client(user):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[require_auth] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def admin_client():
    return _make_client({"user_id": "admin1", "sub": "admin1", "role": "admin"})


@pytest.fixture
def user_client():
    return _make_client({"user_id": "u1", "sub": "u1", "role": "free"})


# --------------------------------------------------------------------------
# GET /api/api_limits
# --------------------------------------------------------------------------

def test_api_limits_own_user_success(user_client):
    """A user may fetch their own limits; response is fully populated."""
    resp = user_client.get("/api/api_limits", params={"user_id": "u1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "u1"
    # u1 is not enterprise_/premium_ prefixed -> free tier.
    assert body["tier"] == "free"
    assert body["limits"]["requests_per_minute"] == 10
    assert body["max_concurrent"] == 3
    # remaining minute == free minute limit minus current usage (0).
    assert body["remaining"]["minute"] == 10
    assert set(body["current_usage"].keys()) == {"minute", "hour", "day"}
    assert set(body["reset_times"].keys()) == {"minute", "hour", "day"}


def test_api_limits_admin_can_view_other_user(admin_client):
    """Admins may view any user's limits, and tier prefix is honoured."""
    resp = admin_client.get("/api/api_limits", params={"user_id": "premium_bob"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "premium_bob"
    assert body["tier"] == "premium"
    assert body["limits"]["requests_per_minute"] == 100
    assert body["max_concurrent"] == 10


def test_api_limits_forbidden_for_other_user(user_client):
    """Non-admin fetching someone else's limits gets 403."""
    resp = user_client.get("/api/api_limits", params={"user_id": "someone_else"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Access denied"


def test_api_limits_missing_user_id_422(user_client):
    """user_id is a required query param."""
    resp = user_client.get("/api/api_limits")
    assert resp.status_code == 422


def test_api_limits_internal_error_500(monkeypatch, user_client):
    """An unexpected error inside the handler surfaces as a 500."""
    async def boom(_user_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(mod, "_get_user_tier", boom)
    resp = user_client.get("/api/api_limits", params={"user_id": "u1"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# --------------------------------------------------------------------------
# GET /api/api_limits/suspicious_activity  (admin only)
# --------------------------------------------------------------------------

def test_suspicious_activity_forbidden_for_non_admin(user_client):
    resp = user_client.get("/api/api_limits/suspicious_activity")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


def test_suspicious_activity_admin_filters_by_time(monkeypatch, admin_client):
    """Only alerts newer than the cutoff are returned."""
    from datetime import datetime, timedelta

    recent = (datetime.now() - timedelta(hours=1)).isoformat()
    old = (datetime.now() - timedelta(hours=200)).isoformat()
    fake_detector = MagicMock()
    fake_detector.alerts = [
        {
            "user_id": "u_recent",
            "alerts": ["rapid_requests"],
            "timestamp": recent,
            "ip_address": "1.2.3.4",
            "endpoint": "/news",
        },
        {
            "user_id": "u_old",
            "alerts": ["endpoint_abuse"],
            "timestamp": old,
            "ip_address": "5.6.7.8",
            "endpoint": "/graph",
        },
    ]
    monkeypatch.setattr(mod, "suspicious_detector", fake_detector)

    resp = admin_client.get("/api/api_limits/suspicious_activity", params={"hours": 24})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["user_id"] == "u_recent"
    assert body[0]["details"]["ip_address"] == "1.2.3.4"
    assert body[0]["details"]["endpoint"] == "/news"


def test_suspicious_activity_hours_out_of_range_422(admin_client):
    """hours must be between 1 and 168."""
    resp = admin_client.get("/api/api_limits/suspicious_activity", params={"hours": 999})
    assert resp.status_code == 422


def test_suspicious_activity_internal_error_500(monkeypatch, admin_client):
    """A malformed alert timestamp bubbles up as a 500."""
    bad_detector = MagicMock()
    bad_detector.alerts = [
        {
            "user_id": "x",
            "alerts": [],
            "timestamp": "not-a-timestamp",
            "ip_address": "0.0.0.0",
            "endpoint": "/x",
        }
    ]
    monkeypatch.setattr(mod, "suspicious_detector", bad_detector)
    resp = admin_client.get("/api/api_limits/suspicious_activity")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# --------------------------------------------------------------------------
# GET /api/api_limits/usage_statistics  (admin only)
# --------------------------------------------------------------------------

def test_usage_statistics_forbidden_for_non_admin(user_client):
    resp = user_client.get("/api/api_limits/usage_statistics")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


def test_usage_statistics_admin_success(admin_client):
    resp = admin_client.get("/api/api_limits/usage_statistics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_requests"] == 125430
    assert body["unique_users"] == 1247
    assert body["tier_distribution"]["free"] == 1100
    assert len(body["top_endpoints"]) == 5


# --------------------------------------------------------------------------
# GET /api/api_limits/tier_info
# --------------------------------------------------------------------------

def test_tier_info_success(user_client):
    resp = user_client.get("/api/api_limits/tier_info")
    assert resp.status_code == 200
    body = resp.json()
    assert body["current_tier"] == "free"
    names = [t["name"] for t in body["available_tiers"]]
    assert names == ["free", "premium", "enterprise"]
    assert "premium" in body["upgrade_benefits"]
    assert "enterprise" in body["upgrade_benefits"]


def test_tier_info_internal_error_500(monkeypatch, user_client):
    async def boom(_user_id):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(mod, "_get_user_tier", boom)
    resp = user_client.get("/api/api_limits/tier_info")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# --------------------------------------------------------------------------
# POST /api/api_limits/reset  (admin only)
# --------------------------------------------------------------------------

def test_reset_forbidden_for_non_admin(user_client):
    resp = user_client.post("/api/api_limits/reset", params={"user_id": "u1"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin access required"


def test_reset_memory_success(monkeypatch, admin_client):
    """Reset via the in-memory path clears the user's stored counters."""
    store = MagicMock()
    store.use_redis = False
    store.memory_store = {
        "victim": {"requests": [1, 2, 3], "concurrent": 5, "metrics": [1]}
    }
    monkeypatch.setattr(mod, "rate_limit_store", store)

    resp = admin_client.post("/api/api_limits/reset", params={"user_id": "victim"})
    assert resp.status_code == 200
    assert "victim" in resp.json()["message"]
    # _reset_user_limits_memory should have wiped the entry.
    assert store.memory_store["victim"] == {
        "requests": [],
        "concurrent": 0,
        "metrics": [],
    }


def test_reset_redis_success(monkeypatch, admin_client):
    """Reset via the redis path awaits the redis reset helper."""
    store = MagicMock()
    store.use_redis = True
    store.redis_client = MagicMock()
    store.redis_client.delete = AsyncMock(return_value=1)
    monkeypatch.setattr(mod, "rate_limit_store", store)

    resp = admin_client.post("/api/api_limits/reset", params={"user_id": "ent_user"})
    assert resp.status_code == 200
    assert store.redis_client.delete.await_count == 4  # 3 windows + concurrent key


def test_reset_internal_error_500(monkeypatch, admin_client):
    store = MagicMock()
    store.use_redis = False
    monkeypatch.setattr(mod, "rate_limit_store", store)

    def boom(_user_id):
        raise RuntimeError("reset failed")

    monkeypatch.setattr(mod, "_reset_user_limits_memory", boom)
    resp = admin_client.post("/api/api_limits/reset", params={"user_id": "x"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# --------------------------------------------------------------------------
# GET /api/api_limits/health  (no auth)
# --------------------------------------------------------------------------

def test_health_memory_backend(monkeypatch):
    store = MagicMock()
    store.use_redis = False
    monkeypatch.setattr(mod, "rate_limit_store", store)
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/api_limits/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["store_backend"] == "memory"
    assert body["memory_store"] == "active"


def test_health_redis_connected(monkeypatch):
    store = MagicMock()
    store.use_redis = True
    store.redis_client = MagicMock()
    store.redis_client.ping = AsyncMock(return_value=True)
    monkeypatch.setattr(mod, "rate_limit_store", store)
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/api_limits/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["store_backend"] == "redis"
    assert body["redis_connection"] == "connected"


def test_health_redis_degraded(monkeypatch):
    """If ping raises, the health status is degraded and carries the error."""
    store = MagicMock()
    store.use_redis = True
    store.redis_client = MagicMock()
    store.redis_client.ping = AsyncMock(side_effect=RuntimeError("no redis"))
    monkeypatch.setattr(mod, "rate_limit_store", store)
    app = FastAPI()
    app.include_router(mod.router)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/api/api_limits/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert "no redis" in body["error"]


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------

def test_get_user_tier_prefixes():
    import asyncio

    assert asyncio.run(mod._get_user_tier("enterprise_a")) == "enterprise"
    assert asyncio.run(mod._get_user_tier("premium_b")) == "premium"
    assert asyncio.run(mod._get_user_tier("plain")) == "free"


def test_get_tier_config_mapping():
    assert mod._get_tier_config("premium").name == "premium"
    assert mod._get_tier_config("enterprise").name == "enterprise"
    # Unknown tier falls back to free.
    assert mod._get_tier_config("does-not-exist").name == "free"


def test_reset_user_limits_memory_absent_user(monkeypatch):
    """Resetting a user not present in the store is a no-op (no KeyError)."""
    store = MagicMock()
    store.memory_store = {}
    monkeypatch.setattr(mod, "rate_limit_store", store)
    mod._reset_user_limits_memory("ghost")
    assert store.memory_store == {}
