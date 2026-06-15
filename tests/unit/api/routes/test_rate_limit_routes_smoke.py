"""Smoke tests for src/api/routes/rate_limit_routes.py."""
import os, sys
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.rate_limit_routes as mod


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mod.router)
    # require_auth is imported into the module namespace; override the dep object
    from src.api.auth.jwt_auth import require_auth
    app.dependency_overrides[require_auth] = lambda: {"user_id": "u1", "sub": "u1"}
    return TestClient(app, raise_server_exceptions=False)


def test_api_limits(client):
    assert 200 <= client.get("/api/api_limits").status_code < 600

def test_usage_statistics(client):
    assert 200 <= client.get("/api/api_limits/usage_statistics").status_code < 600

def test_tier_info(client):
    assert 200 <= client.get("/api/api_limits/tier_info").status_code < 600

def test_health(client):
    assert 200 <= client.get("/api/api_limits/health").status_code < 600
