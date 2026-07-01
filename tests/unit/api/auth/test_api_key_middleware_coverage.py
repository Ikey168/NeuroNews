"""Coverage tests for src/api/auth/api_key_middleware.py.

Drives the REAL Starlette middleware stack (APIKeyAuthMiddleware /
APIKeyMetricsMiddleware) through a real ``TestClient`` so ``dispatch``,
``_is_excluded_path``, ``_extract_api_key`` and ``_validate_api_key`` all run
against genuine Request objects. External I/O (DynamoDB usage tracking) is
mocked at ``api_key_manager.store.update_api_key_usage``; the async
``_validate_api_key`` is patched per-test to simulate valid / invalid keys so
the auth-success / auth-failure branches are both exercised for real.

NOTE (genuine source bug — reported, not fixed): the default
``excluded_paths`` list starts with ``"/"`` and ``_is_excluded_path`` uses
``path.startswith(excluded)``. Because *every* path starts with ``"/"``, the
default configuration excludes the ENTIRE API from key auth. The tests below
document this behaviour rather than assert a (non-existent) fix, and use an
explicit ``excluded_paths`` without ``"/"`` when they need auth to actually run.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import src.api.auth.api_key_middleware as mw


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _echo(request):
    # Surface any state the middleware attached, so tests can assert on it.
    return JSONResponse(
        {
            "path": request.url.path,
            "api_key_auth": getattr(request.state, "api_key_auth", None),
            "user_id": getattr(request.state, "user_id", None),
            "permissions": getattr(request.state, "api_key_permissions", None),
            "rate_limit": getattr(request.state, "api_key_rate_limit", None),
        }
    )


def _build_app(excluded_paths=None):
    routes = [
        Route("/", _echo),
        Route("/health", _echo),
        Route("/api/data", _echo),
        Route("/auth/login", _echo),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(mw.APIKeyAuthMiddleware, excluded_paths=excluded_paths)
    return app


def _fake_key_details(**overrides):
    base = dict(
        key_id="key_abcdef0123456789",
        user_id="user-42",
        permissions=["read", "write"],
        rate_limit=120,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# _is_excluded_path (unit-level, real instance)
# ---------------------------------------------------------------------------

def test_default_excluded_paths_include_health_and_docs():
    m = mw.APIKeyAuthMiddleware(app=None)
    assert m._is_excluded_path("/health") is True
    assert m._is_excluded_path("/docs") is True
    assert m._is_excluded_path("/openapi.json") is True


def test_default_excluded_paths_root_prefix_bug_excludes_everything():
    """Documents the '/' + startswith bug: any path is 'excluded' by default."""
    m = mw.APIKeyAuthMiddleware(app=None)
    # These are NOT semantically excluded, yet startswith("/") matches all.
    assert m._is_excluded_path("/api/anything") is True
    assert m._is_excluded_path("/some/deep/route") is True


def test_custom_excluded_paths_without_root():
    m = mw.APIKeyAuthMiddleware(app=None, excluded_paths=["/health"])
    assert m._is_excluded_path("/health") is True
    assert m._is_excluded_path("/api/data") is False


# ---------------------------------------------------------------------------
# _extract_api_key (real instance, real Request via a tiny app)
# ---------------------------------------------------------------------------

def _extract_via_request(headers=None, query=""):
    """Run _extract_api_key against a real Request built by the test client."""
    captured = {}

    m = mw.APIKeyAuthMiddleware(app=None, excluded_paths=["/never-excluded"])

    async def route(request):
        captured["key"] = m._extract_api_key(request)
        return JSONResponse({})

    app = Starlette(routes=[Route("/x", route)])
    client = TestClient(app)
    client.get("/x" + query, headers=headers or {})
    return captured["key"]


def test_extract_api_key_from_bearer_header():
    key = _extract_via_request(headers={"Authorization": "Bearer nn_secrettoken"})
    assert key == "nn_secrettoken"


def test_extract_api_key_from_x_api_key_header():
    key = _extract_via_request(headers={"X-API-Key": "nn_headerkey"})
    assert key == "nn_headerkey"


def test_extract_api_key_from_query_param():
    key = _extract_via_request(query="?api_key=nn_querykey")
    assert key == "nn_querykey"


def test_extract_api_key_bearer_without_nn_prefix_ignored():
    key = _extract_via_request(headers={"Authorization": "Bearer jwt.token.here"})
    assert key is None


def test_extract_api_key_wrong_prefix_returns_none():
    key = _extract_via_request(headers={"X-API-Key": "sk_not_ours"})
    assert key is None


def test_extract_api_key_none_when_absent():
    assert _extract_via_request() is None


# ---------------------------------------------------------------------------
# _validate_api_key (the real placeholder implementation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_validate_api_key_placeholder_returns_none_for_valid_prefix():
    m = mw.APIKeyAuthMiddleware(app=None)
    # The demo implementation always returns None (documented placeholder).
    assert await m._validate_api_key("nn_anything") is None


@pytest.mark.asyncio
async def test_validate_api_key_rejects_wrong_prefix():
    m = mw.APIKeyAuthMiddleware(app=None)
    assert await m._validate_api_key("bad_key") is None


# ---------------------------------------------------------------------------
# dispatch — full middleware flow
# ---------------------------------------------------------------------------

def test_dispatch_excluded_path_skips_auth():
    app = _build_app(excluded_paths=["/health"])
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    # No auth state set on an excluded path.
    assert body["api_key_auth"] is None


def test_dispatch_no_api_key_passes_through():
    app = _build_app(excluded_paths=["/health"])
    client = TestClient(app)
    resp = client.get("/api/data")
    assert resp.status_code == 200
    assert resp.json()["api_key_auth"] is None
    # No API key auth headers added when no key was presented.
    assert "X-API-Key-Auth" not in resp.headers


def test_dispatch_valid_api_key_sets_state_and_headers(monkeypatch):
    details = _fake_key_details()

    async def fake_validate(self, api_key):
        assert api_key == "nn_validkey"
        return details

    usage_calls = []

    async def fake_update_usage(key_id):
        usage_calls.append(key_id)
        return True

    monkeypatch.setattr(mw.APIKeyAuthMiddleware, "_validate_api_key", fake_validate)
    monkeypatch.setattr(
        mw.api_key_manager.store, "update_api_key_usage", fake_update_usage
    )

    app = _build_app(excluded_paths=["/health"])
    client = TestClient(app)
    resp = client.get("/api/data", headers={"X-API-Key": "nn_validkey"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key_auth"] is True
    assert body["user_id"] == "user-42"
    assert body["permissions"] == ["read", "write"]
    assert body["rate_limit"] == 120

    # Response headers reflect successful key auth (ID truncated to 8 chars).
    assert resp.headers["X-API-Key-Auth"] == "true"
    assert resp.headers["X-API-Key-ID"] == details.key_id[:8]
    # Usage tracking was invoked exactly once with the key id.
    assert usage_calls == [details.key_id]


def test_dispatch_valid_api_key_permissions_default_empty(monkeypatch):
    details = _fake_key_details(permissions=None)

    async def fake_validate(self, api_key):
        return details

    async def fake_update_usage(key_id):
        return True

    monkeypatch.setattr(mw.APIKeyAuthMiddleware, "_validate_api_key", fake_validate)
    monkeypatch.setattr(
        mw.api_key_manager.store, "update_api_key_usage", fake_update_usage
    )

    app = _build_app(excluded_paths=["/health"])
    client = TestClient(app)
    resp = client.get("/api/data", headers={"X-API-Key": "nn_valid2"})
    assert resp.status_code == 200
    # permissions or [] -> empty list when None.
    assert resp.json()["permissions"] == []


def test_dispatch_invalid_api_key_raises_401(monkeypatch):
    """A key present but rejected by _validate_api_key hits the else-branch and
    raises HTTPException(401). Raised from BaseHTTPMiddleware.dispatch, Starlette
    propagates it (no route-level exception handler wraps middleware), so the
    TestClient surfaces the exception — we assert on that real behaviour."""
    from fastapi import HTTPException

    async def fake_validate(self, api_key):
        return None  # simulate a key that failed validation

    monkeypatch.setattr(mw.APIKeyAuthMiddleware, "_validate_api_key", fake_validate)

    app = _build_app(excluded_paths=["/health"])
    client = TestClient(app)
    with pytest.raises(HTTPException) as exc_info:
        client.get("/api/data", headers={"X-API-Key": "nn_bogus"})
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid API key"


# ---------------------------------------------------------------------------
# APIKeyMetricsMiddleware
# ---------------------------------------------------------------------------

def test_metrics_middleware_tracks_usage_when_key_id_present(monkeypatch):
    details = _fake_key_details(key_id="key_metric001")

    async def fake_validate(self, api_key):
        return details

    async def fake_update_usage(key_id):
        return True

    monkeypatch.setattr(mw.APIKeyAuthMiddleware, "_validate_api_key", fake_validate)
    monkeypatch.setattr(
        mw.api_key_manager.store, "update_api_key_usage", fake_update_usage
    )

    metrics = mw.APIKeyMetricsMiddleware(None)

    app = Starlette(routes=[Route("/api/data", _echo)])
    # Metrics is the OUTER middleware; auth (inner) sets request.state.api_key_id.
    app.add_middleware(mw.APIKeyAuthMiddleware, excluded_paths=["/health"])

    # Wrap the metrics dispatch manually by mounting it as the outermost layer.
    app.add_middleware(mw.BaseHTTPMiddleware, dispatch=metrics.dispatch)

    client = TestClient(app)
    resp = client.get("/api/data", headers={"X-API-Key": "nn_metrics"})
    assert resp.status_code == 200

    m = metrics.get_metrics()
    assert m["total_api_requests"] == 1
    assert m["active_api_keys"] == 1
    assert "key_metric001" in m["request_counts"]
    assert m["request_counts"]["key_metric001"] == 1
    endpoint = "GET /api/data"
    assert m["api_key_usage"]["key_metric001"][endpoint] == 1


def test_metrics_middleware_no_tracking_without_key_id():
    metrics = mw.APIKeyMetricsMiddleware(None)

    app = Starlette(routes=[Route("/plain", _echo)])
    app.add_middleware(mw.BaseHTTPMiddleware, dispatch=metrics.dispatch)

    client = TestClient(app)
    resp = client.get("/plain")
    assert resp.status_code == 200

    m = metrics.get_metrics()
    # No api_key_id on request.state -> nothing recorded.
    assert m["total_api_requests"] == 0
    assert m["active_api_keys"] == 0
    assert m["api_key_usage"] == {}


def test_metrics_get_metrics_accumulates_across_requests():
    metrics = mw.APIKeyMetricsMiddleware(None)
    # Directly seed two endpoints for one key to exercise the aggregation math.
    metrics.api_key_usage["k1"] = {"GET /a": 2, "POST /b": 1}
    metrics.request_counts["k1"] = 3
    metrics.request_counts["k2"] = 5

    m = metrics.get_metrics()
    assert m["total_api_requests"] == 8
    assert m["active_api_keys"] == 2
    assert m["request_counts"] == {"k1": 3, "k2": 5}


def test_global_metrics_instance_exists():
    assert isinstance(mw.api_key_metrics, mw.APIKeyMetricsMiddleware)
