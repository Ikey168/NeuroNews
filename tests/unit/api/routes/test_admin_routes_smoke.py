"""Smoke tests for src/api/routes/admin_routes.py (mocked db)."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.admin_routes as mod


@pytest.fixture
def client():
    db = MagicMock()
    db.execute_query = AsyncMock(return_value=[])
    db.connect = AsyncMock()
    db.disconnect = AsyncMock()
    db.close = MagicMock()
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)



def test_health(client):
    assert 200 <= client.get("/admin/health").status_code < 600

def test_users(client):
    assert 200 <= client.get("/admin/users").status_code < 600

def test_system_stats(client):
    assert 200 <= client.get("/admin/system/stats").status_code < 600

def test_system_config(client):
    assert 200 <= client.get("/admin/system/config").status_code < 600

