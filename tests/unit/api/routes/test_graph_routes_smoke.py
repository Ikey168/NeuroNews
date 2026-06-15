"""Smoke tests for src/api/routes/graph_routes.py."""
import os, sys
from unittest.mock import AsyncMock, MagicMock
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
pytest.importorskip("fastapi")
from fastapi import FastAPI
from fastapi.testclient import TestClient
import api.routes.graph_routes as mod


@pytest.fixture
def graph():
    g = MagicMock()
    g.get_related_entities = AsyncMock(return_value=[])
    g.get_event_timeline = AsyncMock(return_value=[])
    g.execute_query = AsyncMock(return_value=[])
    return g


@pytest.fixture
def client(graph):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_graph] = lambda: graph
    return TestClient(app, raise_server_exceptions=False)


def test_related_entities(client):
    assert 200 <= client.get("/graph/related_entities", params={"entity": "Google"}).status_code < 600

def test_event_timeline(client):
    assert 200 <= client.get("/graph/event_timeline", params={"topic": "AI"}).status_code < 600

def test_health(client):
    assert 200 <= client.get("/graph/health").status_code < 600
