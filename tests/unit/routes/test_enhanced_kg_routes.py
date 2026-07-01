"""
Unit tests for the Enhanced Knowledge Graph API routes (Issue #37).

These tests mount ``src.api.routes.enhanced_kg_routes.router`` on a *fresh*
FastAPI app and override the ``get_enhanced_graph_populator`` dependency with an
``AsyncMock`` so no real Neptune / Gremlin backend is required. Every test sets
up its own mocks and app instance, so the module passes in isolation and does
not depend on state from any other test file.

The previous version of this file was a set of generated "mega-mock" coverage
loops that called every symbol with random arguments inside blanket
``try/except: pass`` blocks (ending in ``assert True``). Those asserted nothing
meaningful and corrupted interpreter state, so they have been replaced with real
request/response assertions against the actual router.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.api.routes.enhanced_kg_routes as ekg


PREFIX = "/api/v1/knowledge-graph"


@pytest.fixture
def mock_populator():
    """A mock EnhancedKnowledgeGraphPopulator with async query methods."""
    populator = AsyncMock()
    # query_entity_relationships is awaited directly by the route.
    populator.query_entity_relationships = AsyncMock(
        return_value={
            "related_entities": [
                {
                    "id": "ent_1",
                    "name": "OpenAI",
                    "type": "ORG",
                    "relationship_type": "PARTNER",
                    "confidence": 0.9,
                    "context": "OpenAI partnered with the entity",
                    "source_articles": ["art_1"],
                    "properties": {"industry": "AI"},
                },
                {
                    "id": "ent_2",
                    "name": "LowConf",
                    "type": "ORG",
                    "relationship_type": "MENTIONED",
                    "confidence": 0.1,
                    "context": "weak link",
                    "source_articles": [],
                    "properties": {},
                },
            ]
        }
    )
    # SPARQL query is awaited directly by the route.
    populator.execute_sparql_query = AsyncMock(
        return_value=[{"s": "subject", "p": "pred", "o": "object"}]
    )
    # The timeline / entity-details / search / analytics endpoints reach through
    # populator.graph_builder._execute_traversal. graph_builder itself must be a
    # *sync* MagicMock so the Gremlin-style fluent chains the helpers build
    # (``graph_builder.g.V().has(...).count()``) return plain mocks rather than
    # un-awaited coroutines. Only _execute_traversal is awaited, so it is an
    # AsyncMock. Default to an empty result unless a test overrides it.
    populator.graph_builder = MagicMock()
    populator.graph_builder._execute_traversal = AsyncMock(return_value=[])
    return populator


@pytest.fixture
def client(mock_populator):
    """Fresh FastAPI app with just the enhanced-KG router mounted.

    The heavy ``get_enhanced_graph_populator`` dependency (which would try to
    build a real Neptune client) is overridden with the mock populator.
    """
    app = FastAPI()
    app.include_router(ekg.router)
    app.dependency_overrides[ekg.get_enhanced_graph_populator] = (
        lambda: mock_populator
    )
    with TestClient(app) as test_client:
        yield test_client


def test_router_is_mounted_with_expected_routes(client):
    """All documented endpoints are registered under the KG prefix."""
    paths = {route.path for route in ekg.router.routes}
    expected = {
        f"{PREFIX}/related_entities",
        f"{PREFIX}/event_timeline",
        f"{PREFIX}/entity_details/{{entity_id}}",
        f"{PREFIX}/graph_search",
        f"{PREFIX}/graph_analytics",
        f"{PREFIX}/sparql_query",
        f"{PREFIX}/health",
    }
    assert expected.issubset(paths)


def test_health_check_reports_healthy(client):
    resp = client.get(f"{PREFIX}/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "knowledge-graph-api"
    # These flags are booleans reflecting import availability in the source.
    assert isinstance(body["enhanced_kg_available"], bool)
    assert isinstance(body["config_available"], bool)


def test_related_entities_filters_by_confidence(client, mock_populator):
    """Only entities meeting min_confidence should be returned."""
    resp = client.get(
        f"{PREFIX}/related_entities",
        params={"entity": "Microsoft", "min_confidence": 0.5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_entity"] == "Microsoft"
    # The 0.1-confidence entity is filtered out; only the 0.9 one remains.
    assert body["total_results"] == 1
    names = [e["entity_name"] for e in body["related_entities"]]
    assert names == ["OpenAI"]
    # The populator was actually queried with the requested entity.
    mock_populator.query_entity_relationships.assert_awaited_once()
    kwargs = mock_populator.query_entity_relationships.await_args.kwargs
    assert kwargs["entity_name"] == "Microsoft"


def test_related_entities_rejects_short_entity(client):
    """Entity names shorter than 2 chars are a 400 error."""
    resp = client.get(f"{PREFIX}/related_entities", params={"entity": "A"})
    assert resp.status_code == 400
    assert "at least 2 characters" in resp.json()["detail"]


def test_related_entities_parses_relationship_type_filter(client, mock_populator):
    """Comma-separated relationship_types are split and forwarded."""
    resp = client.get(
        f"{PREFIX}/related_entities",
        params={
            "entity": "Google",
            "relationship_types": "PARTNER,RIVAL",
            "min_confidence": 0.0,
        },
    )
    assert resp.status_code == 200
    kwargs = mock_populator.query_entity_relationships.await_args.kwargs
    assert kwargs["relationship_types"] == ["PARTNER", "RIVAL"]


def test_event_timeline_rejects_short_topic(client):
    resp = client.get(f"{PREFIX}/event_timeline", params={"topic": "x"})
    assert resp.status_code == 400
    assert "at least 2 characters" in resp.json()["detail"]


def test_event_timeline_rejects_bad_start_date(client):
    resp = client.get(
        f"{PREFIX}/event_timeline",
        params={"topic": "AI Policy", "start_date": "not-a-date"},
    )
    assert resp.status_code == 400
    assert "Invalid start_date" in resp.json()["detail"]


def test_event_timeline_returns_events_from_traversal(client, mock_populator):
    """A populated traversal produces timeline events."""
    article_rows = [
        {
            "id": ["art_42"],
            "title": ["AI regulation advances"],
            "content": ["Long form content about AI regulation. " * 5],
            "published_date": ["2024-03-01T00:00:00"],
            "author": ["Jane Doe"],
            "source_url": ["https://example.com/a"],
            "category": ["policy"],
        }
    ]

    async def fake_traversal(query):
        # The first traversal call fetches articles; entity lookups return [].
        if "Article" in str(query):
            return article_rows
        return []

    mock_populator.graph_builder._execute_traversal = AsyncMock(
        side_effect=fake_traversal
    )

    resp = client.get(
        f"{PREFIX}/event_timeline",
        params={"topic": "AI regulation", "max_events": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["topic"] == "AI regulation"
    assert body["total_events"] == 1
    event = body["events"][0]
    assert event["event_title"] == "AI regulation advances"
    assert event["source_article_id"] == "art_42"
    assert event["event_type"] == "article"


def test_entity_details_not_found_returns_404(client, mock_populator):
    """No traversal results -> the entity is reported missing."""
    mock_populator.graph_builder._execute_traversal = AsyncMock(return_value=[])
    resp = client.get(f"{PREFIX}/entity_details/does_not_exist")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_entity_details_returns_entity(client, mock_populator):
    """A matching vertex is serialised into entity details."""

    calls = {"n": 0}

    async def sequenced(query):
        # First traversal returns the entity valueMap; relationship/article
        # follow-up traversals return empty lists.
        calls["n"] += 1
        if calls["n"] == 1:
            return [
                {
                    "id": ["google_inc_001"],
                    "normalized_form": ["Google"],
                    "entity_type": ["ORG"],
                    "confidence": [0.95],
                    "mention_count": [12],
                    "created_at": ["2024-01-01T00:00:00"],
                }
            ]
        return []

    mock_populator.graph_builder._execute_traversal = AsyncMock(side_effect=sequenced)

    resp = client.get(
        f"{PREFIX}/entity_details/google_inc_001",
        params={
            "include_relationships": False,
            "include_articles": False,
            "include_properties": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity_id"] == "google_inc_001"
    assert body["entity_name"] == "Google"
    assert body["entity_type"] == "ORG"


def test_graph_search_rejects_invalid_query_type(client):
    resp = client.post(
        f"{PREFIX}/graph_search",
        json={"query_type": "bogus", "search_terms": ["x"]},
    )
    assert resp.status_code == 400
    assert "Invalid query_type" in resp.json()["detail"]


def test_graph_search_entity_returns_results(client, mock_populator):
    """A valid entity search returns formatted search results."""
    mock_populator.graph_builder._execute_traversal = AsyncMock(
        return_value=[
            {
                "id": ["e1"],
                "normalized_form": ["OpenAI"],
                "entity_type": ["ORG"],
                "confidence": [0.9],
                "mention_count": [5],
            }
        ]
    )
    resp = client.post(
        f"{PREFIX}/graph_search",
        json={
            "query_type": "entity",
            "search_terms": ["OpenAI"],
            "sort_by": "confidence",
            "limit": 10,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_type"] == "entity"
    assert body["total_results"] == 1
    assert body["results"][0]["entity_name"] == "OpenAI"


def test_graph_analytics_rejects_invalid_metric(client):
    resp = client.get(
        f"{PREFIX}/graph_analytics", params={"metric_type": "nonsense"}
    )
    assert resp.status_code == 400
    assert "Invalid metric_type" in resp.json()["detail"]


def test_graph_analytics_overview(client, mock_populator):
    """Overview analytics aggregates vertex/edge counts from traversals."""

    calls = {"n": 0}

    async def sequenced(query):
        calls["n"] += 1
        if calls["n"] == 1:  # vertex count
            return [100]
        if calls["n"] == 2:  # edge count
            return [250]
        return [{"ORG": 40, "PERSON": 60}]  # type distribution

    mock_populator.graph_builder._execute_traversal = AsyncMock(side_effect=sequenced)

    resp = client.get(
        f"{PREFIX}/graph_analytics", params={"metric_type": "overview"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric_type"] == "overview"
    assert body["analytics"]["total_vertices"] == 100
    assert body["analytics"]["total_edges"] == 250


def test_sparql_query_rejects_short_query(client):
    resp = client.get(f"{PREFIX}/sparql_query", params={"query": "short"})
    assert resp.status_code == 400
    assert "at least 10 characters" in resp.json()["detail"]


def test_sparql_query_executes(client, mock_populator):
    resp = client.get(
        f"{PREFIX}/sparql_query",
        params={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["results"] == [{"s": "subject", "p": "pred", "o": "object"}]
    mock_populator.execute_sparql_query.assert_awaited_once()


def test_populator_dependency_returns_503_when_kg_unavailable(monkeypatch):
    """When enhanced KG components are unavailable the dependency 503s.

    This exercises the real ``get_enhanced_graph_populator`` (no override) so we
    build a separate app without the dependency override.
    """
    monkeypatch.setattr(ekg, "ENHANCED_KG_AVAILABLE", False)

    app = FastAPI()
    app.include_router(ekg.router)
    with TestClient(app) as local_client:
        resp = local_client.get(
            f"{PREFIX}/related_entities", params={"entity": "Test"}
        )
    assert resp.status_code == 503
    assert "not available" in resp.json()["detail"]


def test_pydantic_models_validate_ranges():
    """The request models enforce their documented bounds."""
    q = ekg.EntityRelationshipQuery(entity_name="X", max_depth=3, max_results=10)
    assert q.max_depth == 3

    with pytest.raises(Exception):
        # max_depth above the documented le=5 bound must fail validation.
        ekg.EntityRelationshipQuery(entity_name="X", max_depth=99)

    event = ekg.TimelineEvent(
        event_id="e1",
        event_title="T",
        event_date=datetime(2024, 1, 1),
        event_type="article",
        description="desc",
        entities_involved=["A"],
        confidence=0.8,
    )
    assert event.event_id == "e1"
