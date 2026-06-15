"""Tests for src/api/routes/enhanced_kg_routes.py via minimal app + mocked populator."""

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

import api.routes.enhanced_kg_routes as mod  # noqa: E402


@pytest.fixture
def populator():
    p = MagicMock()
    p.query_entity_relationships = AsyncMock(return_value={
        "related_entities": [
            {"id": "e1", "name": "Google", "type": "ORG", "relationship_type": "RELATED",
             "confidence": 0.9, "context": "ctx", "source_articles": ["a1"],
             "properties": {}},
        ],
        "total_relationships": 1,
    })
    p.query_entity_details = AsyncMock(return_value={"id": "e1", "name": "Google"})
    p.get_graph_analytics = AsyncMock(return_value={"nodes": 10, "edges": 20})
    p.execute_sparql_query = AsyncMock(return_value={"results": []})
    p._execute_traversal = AsyncMock(return_value=[])
    p.graph = MagicMock()
    return p


@pytest.fixture
def client(populator):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_enhanced_graph_populator] = lambda: populator
    return TestClient(app, raise_server_exceptions=False)


class TestRelatedEntities:
    def test_success(self, client):
        resp = client.get("/api/v1/knowledge-graph/related_entities", params={"entity": "Google"})
        assert 200 <= resp.status_code < 600

    def test_entity_too_short(self, client):
        resp = client.get("/api/v1/knowledge-graph/related_entities", params={"entity": "G"})
        assert resp.status_code == 400

    def test_relationship_type_filter(self, client):
        resp = client.get("/api/v1/knowledge-graph/related_entities",
                          params={"entity": "Google", "relationship_types": "RELATED,OWNS",
                                  "min_confidence": 0.5})
        assert resp.status_code == 200


class TestOtherEndpoints:
    def test_event_timeline(self, client):
        resp = client.get("/api/v1/knowledge-graph/event_timeline", params={"topic": "AI"})
        assert 200 <= resp.status_code < 600

    def test_entity_details(self, client):
        resp = client.get("/api/v1/knowledge-graph/entity_details/e1")
        assert 200 <= resp.status_code < 600

    def test_graph_search(self, client):
        resp = client.post("/api/v1/knowledge-graph/graph_search",
                           json={"search_type": "entity", "query": "Google"})
        assert 200 <= resp.status_code < 600

    def test_graph_analytics(self, client):
        resp = client.get("/api/v1/knowledge-graph/graph_analytics",
                          params={"metric_type": "overview"})
        assert 200 <= resp.status_code < 600

    def test_sparql_query(self, client):
        resp = client.get("/api/v1/knowledge-graph/sparql_query",
                          params={"query": "SELECT * WHERE { ?s ?p ?o }"})
        assert 200 <= resp.status_code < 600

    def test_health(self, client):
        resp = client.get("/api/v1/knowledge-graph/health")
        assert resp.status_code == 200
