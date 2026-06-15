"""Smoke tests for src/api/routes/influence_routes.py."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.influence_routes as mod


@pytest.fixture
def client(monkeypatch):
    analyzer = MagicMock()
    analyzer.get_top_influencers = AsyncMock(return_value=[])
    analyzer.find_influence_path = AsyncMock(return_value={})
    analyzer.get_network_stats = AsyncMock(return_value={})
    analyzer.calculate_influence_scores = AsyncMock(return_value={})
    monkeypatch.setattr(mod, "analyzer", analyzer)
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


def test_health(client):
    assert 200 <= client.get("/api/influence/health").status_code < 600

def test_stats(client):
    assert 200 <= client.get("/api/influence/stats").status_code < 600

def test_top_influencers(client):
    assert 200 <= client.get("/api/influence/top-influencers").status_code < 600

def test_path(client):
    assert 200 <= client.get("/api/influence/path/a/b").status_code < 600
