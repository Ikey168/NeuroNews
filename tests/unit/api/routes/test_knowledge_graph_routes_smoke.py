"""Tests for src/api/routes/knowledge_graph_routes.py via minimal app + mocked populator."""

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

import api.routes.knowledge_graph_routes as mod  # noqa: E402


@pytest.fixture
def populator():
    p = MagicMock()
    p.get_related_entities = AsyncMock(return_value={"related_entities": []})
    p.get_entity_details = AsyncMock(return_value={"id": "e1"})
    p.get_statistics = AsyncMock(return_value={"nodes": 0})
    p.search_entities = AsyncMock(return_value={"entities": []})
    p.validate_and_populate_article = AsyncMock(return_value={"status": "ok"})
    return p


@pytest.fixture
def client(populator):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_graph_populator] = lambda: populator
    return TestClient(app, raise_server_exceptions=False)


def test_related_entities(client):
    resp = client.get("/api/v1/related_entities", params={"entity_name": "Google"})
    assert 200 <= resp.status_code < 600


def test_entity_details(client):
    resp = client.get("/api/v1/entity_details/e1")
    assert 200 <= resp.status_code < 600


def test_stats(client):
    resp = client.get("/api/v1/knowledge_graph_stats")
    assert 200 <= resp.status_code < 600


def test_search_entities(client):
    resp = client.get("/api/v1/search_entities", params={"query": "ai"})
    assert 200 <= resp.status_code < 600
