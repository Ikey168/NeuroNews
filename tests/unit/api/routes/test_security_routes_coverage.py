"""Coverage tests for src/api/routes/security_routes.py.

Covers:
- _require_admin gate: 401 (no auth), 403 (non-admin role), admin passes
- POST /admin/api-keys create (201) + 422 validation
- GET  /admin/api-keys list (200)
- GET  /admin/api-keys/{id} (200 + 404)
- DELETE /admin/api-keys/{id} (204 + 404)
- POST /admin/mfa/setup (200 + 503 on RuntimeError)
- POST /admin/mfa/verify (200 valid + 400 invalid)
- GET  /admin/mfa/status (200)
"""
import os
import sys
from unittest.mock import patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.security_routes as mod

ADMIN_USER = {"sub": "admin-1", "role": "admin"}
VIEWER_USER = {"sub": "viewer-1", "role": "viewer"}


def _app(user=None):
    """Build an app; override require_auth to return `user` when given."""
    app = FastAPI()
    app.include_router(mod.router)
    if user is not None:
        app.dependency_overrides[mod.require_auth] = lambda: user
    return app


@pytest.fixture
def admin_client():
    return TestClient(_app(ADMIN_USER), raise_server_exceptions=False)


# --------------------------------------------------------------------------
# Auth gate
# --------------------------------------------------------------------------

def test_no_auth_returns_401():
    # require_auth NOT overridden -> real JWTAuth rejects missing bearer token
    client = TestClient(_app(user=None), raise_server_exceptions=False)
    resp = client.get("/admin/api-keys")
    assert resp.status_code == 401


def test_non_admin_returns_403():
    client = TestClient(_app(VIEWER_USER), raise_server_exceptions=False)
    resp = client.get("/admin/api-keys")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Admin role required"


def test_administrator_role_allowed():
    client = TestClient(
        _app({"sub": "a", "role": "Administrator"}), raise_server_exceptions=False
    )
    with patch("src.api.auth.local_api_keys.list_api_keys", return_value=[]):
        resp = client.get("/admin/api-keys")
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# POST /admin/api-keys
# --------------------------------------------------------------------------

def test_create_api_key_success(admin_client):
    created = {"key_id": "k1", "raw_key": "raw-secret"}
    record = {
        "key_id": "k1",
        "key_prefix": "abcd",
        "name": "svc",
        "role": "viewer",
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
        "expires_at": None,
        "last_used_at": None,
        "usage_count": 0,
    }
    with patch(
        "src.api.auth.local_api_keys.create_api_key", return_value=created
    ), patch("src.api.auth.local_api_keys.get_api_key", return_value=record):
        resp = admin_client.post(
            "/admin/api-keys", json={"name": "svc", "role": "viewer"}
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["key_id"] == "k1"
    assert body["raw_key"] == "raw-secret"


def test_create_api_key_record_missing_returns_500(admin_client):
    # Covers the `get_api_key(...) or {}` branch: when the just-created key
    # cannot be re-read, `record` is {} and the response is only
    # {"raw_key": ...}. That fails CreateKeyResponse validation, so FastAPI
    # returns 500. (Genuine source robustness gap: the create path assumes
    # the stored record is always retrievable.)
    with patch(
        "src.api.auth.local_api_keys.create_api_key",
        return_value={"key_id": "k2", "raw_key": "r2"},
    ), patch("src.api.auth.local_api_keys.get_api_key", return_value=None):
        resp = admin_client.post(
            "/admin/api-keys", json={"name": "svc2", "role": "editor"}
        )
    assert resp.status_code == 500


def test_create_api_key_invalid_role_422(admin_client):
    resp = admin_client.post(
        "/admin/api-keys", json={"name": "svc", "role": "superuser"}
    )
    assert resp.status_code == 422


def test_create_api_key_empty_name_422(admin_client):
    resp = admin_client.post("/admin/api-keys", json={"name": "", "role": "viewer"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# GET /admin/api-keys
# --------------------------------------------------------------------------

def test_list_api_keys_success(admin_client):
    rows = [
        {
            "key_id": "k1",
            "key_prefix": "abcd",
            "name": "svc",
            "role": "viewer",
            "status": "active",
            "created_at": "2026-01-01T00:00:00",
            "expires_at": None,
            "last_used_at": None,
            "usage_count": 3,
        }
    ]
    with patch("src.api.auth.local_api_keys.list_api_keys", return_value=rows):
        resp = admin_client.get("/admin/api-keys")
    assert resp.status_code == 200
    assert resp.json()[0]["key_id"] == "k1"


# --------------------------------------------------------------------------
# GET /admin/api-keys/{key_id}
# --------------------------------------------------------------------------

def test_get_api_key_success(admin_client):
    record = {
        "key_id": "k1",
        "key_prefix": "abcd",
        "name": "svc",
        "role": "viewer",
        "status": "active",
        "created_at": "2026-01-01T00:00:00",
        "expires_at": None,
        "last_used_at": None,
        "usage_count": 0,
    }
    with patch("src.api.auth.local_api_keys.get_api_key", return_value=record):
        resp = admin_client.get("/admin/api-keys/k1")
    assert resp.status_code == 200
    assert resp.json()["key_id"] == "k1"


def test_get_api_key_not_found_404(admin_client):
    with patch("src.api.auth.local_api_keys.get_api_key", return_value=None):
        resp = admin_client.get("/admin/api-keys/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "API key not found"


# --------------------------------------------------------------------------
# DELETE /admin/api-keys/{key_id}
# --------------------------------------------------------------------------

def test_revoke_api_key_success_204(admin_client):
    with patch("src.api.auth.local_api_keys.revoke_api_key", return_value=True):
        resp = admin_client.delete("/admin/api-keys/k1")
    assert resp.status_code == 204
    assert resp.content == b""


def test_revoke_api_key_not_found_404(admin_client):
    with patch("src.api.auth.local_api_keys.revoke_api_key", return_value=False):
        resp = admin_client.delete("/admin/api-keys/missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "API key not found"


# --------------------------------------------------------------------------
# POST /admin/mfa/setup
# --------------------------------------------------------------------------

def test_mfa_setup_success(admin_client):
    payload = {"totp_uri": "otpauth://totp/x", "secret": "SECRET123"}
    with patch("src.api.auth.totp_mfa.setup_totp", return_value=payload):
        resp = admin_client.post(
            "/admin/mfa/setup", json={"email": "admin@example.com"}
        )
    assert resp.status_code == 200
    assert resp.json()["secret"] == "SECRET123"


def test_mfa_setup_runtime_error_503(admin_client):
    with patch(
        "src.api.auth.totp_mfa.setup_totp", side_effect=RuntimeError("pyotp missing")
    ):
        resp = admin_client.post(
            "/admin/mfa/setup", json={"email": "admin@example.com"}
        )
    assert resp.status_code == 503
    assert "pyotp missing" in resp.json()["detail"]


def test_mfa_setup_missing_email_422(admin_client):
    resp = admin_client.post("/admin/mfa/setup", json={})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# POST /admin/mfa/verify
# --------------------------------------------------------------------------

def test_mfa_verify_valid(admin_client):
    with patch("src.api.auth.totp_mfa.verify_totp", return_value=True):
        resp = admin_client.post("/admin/mfa/verify", json={"code": "123456"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mfa_enabled"] is True
    assert body["user_id"] == "admin-1"


def test_mfa_verify_invalid_400(admin_client):
    with patch("src.api.auth.totp_mfa.verify_totp", return_value=False):
        resp = admin_client.post("/admin/mfa/verify", json={"code": "000000"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid or expired TOTP code"


def test_mfa_verify_short_code_422(admin_client):
    resp = admin_client.post("/admin/mfa/verify", json={"code": "12"})
    assert resp.status_code == 422


# --------------------------------------------------------------------------
# GET /admin/mfa/status
# --------------------------------------------------------------------------

def test_mfa_status_enabled(admin_client):
    with patch("src.api.auth.totp_mfa.is_mfa_enabled", return_value=True):
        resp = admin_client.get("/admin/mfa/status")
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "admin-1", "mfa_enabled": True}


def test_mfa_status_default_sub():
    # admin with no 'sub' claim -> user_id defaults to "admin"
    client = TestClient(_app({"role": "admin"}), raise_server_exceptions=False)
    with patch("src.api.auth.totp_mfa.is_mfa_enabled", return_value=False):
        resp = client.get("/admin/mfa/status")
    assert resp.status_code == 200
    assert resp.json() == {"user_id": "admin", "mfa_enabled": False}
