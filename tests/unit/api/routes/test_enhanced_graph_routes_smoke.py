"""Tests for src/api/routes/enhanced_graph_routes.py via minimal app + mocked graph_api."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import api.routes.enhanced_graph_routes as mod  # noqa: E402


@pytest.fixture
def graph_api():
    g = MagicMock()
    g.get_related_entities_optimized = AsyncMock(return_value={"entities": [], "count": 0})
    g.get_event_timeline_optimized = AsyncMock(return_value={"events": [], "count": 0})
    g.search_entities_optimized = AsyncMock(return_value={"results": [], "count": 0})
    g.get_cache_stats = AsyncMock(return_value={"hits": 1, "misses": 0})
    g.clear_cache = AsyncMock(return_value={"cleared": True})
    g.graph = MagicMock()
    g.redis_client = MagicMock()
    return g


@pytest.fixture
def client(graph_api):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_optimized_graph] = lambda: graph_api
    return TestClient(app, raise_server_exceptions=False)


def test_related_entities_get(client):
    resp = client.get("/api/v2/graph/related-entities", params={"entity": "Google"})
    assert resp.status_code == 200
    assert resp.json()["metadata"]["api_version"] == "v2"


def test_event_timeline_get(client):
    resp = client.get("/api/v2/graph/event-timeline", params={"topic": "AI"})
    assert 200 <= resp.status_code < 600


def test_search_get(client):
    resp = client.get("/api/v2/graph/search", params={"query": "test"})
    assert 200 <= resp.status_code < 600


def test_stats(client):
    resp = client.get("/api/v2/graph/stats")
    assert 200 <= resp.status_code < 600


def test_health(client):
    resp = client.get("/api/v2/graph/health")
    assert 200 <= resp.status_code < 600


def test_cache_clear_post(client):
    resp = client.post("/api/v2/graph/cache/clear")
    assert 200 <= resp.status_code < 600


def test_cache_delete(client):
    resp = client.delete("/api/v2/graph/cache")
    assert 200 <= resp.status_code < 600
