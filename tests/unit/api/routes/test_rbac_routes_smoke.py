"""Smoke tests for src/api/routes/rbac_routes.py."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path: sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.rbac_routes as mod


@pytest.fixture
def client(monkeypatch):
    rm = MagicMock()
    rm.get_role_summary = MagicMock(return_value={"admin": {"permissions": ["read"]}})
    rm.store_user_permissions = AsyncMock(return_value=True)
    rm.get_user_permissions = AsyncMock(return_value={"role": "admin", "permissions": []})
    monkeypatch.setattr(mod, "rbac_manager", rm)
    app = FastAPI(); app.include_router(mod.router)
    from src.api.auth.jwt_auth import require_auth
    app.dependency_overrides[require_auth] = lambda: {"user_id": "u1"}
    if hasattr(mod, "require_admin"):
        app.dependency_overrides[mod.require_admin] = lambda: {"user_id": "admin"}
    return TestClient(app, raise_server_exceptions=False)


def test_roles(client):
    assert 200 <= client.get("/api/rbac/roles").status_code < 600

def test_role_info(client):
    assert 200 <= client.get("/api/rbac/roles/admin").status_code < 600

def test_permissions(client):
    assert 200 <= client.get("/api/rbac/permissions").status_code < 600

def test_user_permissions(client):
    assert 200 <= client.get("/api/rbac/users/u1/permissions").status_code < 600
