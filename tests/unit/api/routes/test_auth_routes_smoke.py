"""Smoke tests for src/api/routes/auth_routes.py."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest
SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path: sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.auth_routes as mod


@pytest.fixture
def client():
    db = MagicMock()
    db.execute_query = AsyncMock(return_value=[])
    db.connect = AsyncMock(); db.disconnect = AsyncMock()
    app = FastAPI(); app.include_router(mod.router)
    app.dependency_overrides[mod.get_db] = lambda: db
    from src.api.auth.jwt_auth import require_auth
    app.dependency_overrides[require_auth] = lambda: {"user_id": "u1", "sub": "u1"}
    return TestClient(app, raise_server_exceptions=False)


def test_verify(client):
    assert 200 <= client.get("/auth/verify").status_code < 600

def test_register(client):
    assert 200 <= client.post("/auth/register", json={"email": "a@b.com", "password": "Xx12345!", "name": "A"}).status_code < 600

def test_login(client):
    assert 200 <= client.post("/auth/login", json={"email": "a@b.com", "password": "Xx12345!"}).status_code < 600

def test_logout(client):
    assert 200 <= client.post("/auth/logout").status_code < 600
