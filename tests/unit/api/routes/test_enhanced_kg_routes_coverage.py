"""Coverage tests for src/api/routes/enhanced_kg_routes.py.

Two layers:

1. HTTP layer -- router mounted on a fresh FastAPI app with the populator
   dependency overridden.  Drives the endpoints (including the helper
   functions they call) through the request path and asserts on real status
   codes AND response bodies.  Covers validation (400), 404, and 500 branches.

2. Direct-helper layer -- the private ``_search_*`` / ``_query_*`` /
   ``_get_*`` coroutines are awaited directly with a populator whose
   ``graph_builder._execute_traversal`` returns canned Gremlin results.
"""

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

import src.api.routes.enhanced_kg_routes as mod  # noqa: E402


# ---------------------------------------------------------------------------
# Populator helpers
# ---------------------------------------------------------------------------

def make_populator(execute_returns=None, side_effect=None):
    """Build a populator whose graph_builder._execute_traversal is scripted."""
    p = MagicMock()
    p.graph_builder = MagicMock()
    p.graph_builder.g = MagicMock()
    if side_effect is not None:
        p.graph_builder._execute_traversal = AsyncMock(side_effect=side_effect)
    else:
        p.graph_builder._execute_traversal = AsyncMock(
            side_effect=execute_returns or []
        )
    return p


def build_client(populator):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_enhanced_graph_populator] = lambda: populator
    return TestClient(app, raise_server_exceptions=False)


BASE = "/api/v1/knowledge-graph"


# ---------------------------------------------------------------------------
# /related_entities
# ---------------------------------------------------------------------------

class TestRelatedEntities:
    def test_success_filters_confidence(self):
        p = make_populator()
        p.query_entity_relationships = AsyncMock(
            return_value={
                "related_entities": [
                    {
                        "id": "e1",
                        "name": "Google",
                        "type": "ORG",
                        "relationship_type": "OWNS",
                        "confidence": 0.9,
                        "context": "ctx",
                        "source_articles": ["a1"],
                        "properties": {"x": 1},
                    },
                    {
                        "id": "e2",
                        "name": "Weak",
                        "type": "ORG",
                        "confidence": 0.1,  # below threshold -> filtered out
                    },
                ]
            }
        )
        client = build_client(p)
        resp = client.get(
            BASE + "/related_entities",
            params={
                "entity": "Google",
                "min_confidence": 0.5,
                "relationship_types": "OWNS,RELATED",
                "include_context": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_entity"] == "Google"
        assert body["total_results"] == 1
        assert body["related_entities"][0]["entity_name"] == "Google"
        assert body["related_entities"][0]["context"] == "ctx"

    def test_include_context_false_nulls_context(self):
        p = make_populator()
        p.query_entity_relationships = AsyncMock(
            return_value={
                "related_entities": [
                    {"id": "e1", "name": "G", "type": "ORG", "confidence": 0.9,
                     "context": "ctx"}
                ]
            }
        )
        client = build_client(p)
        resp = client.get(
            BASE + "/related_entities",
            params={"entity": "Google", "include_context": False},
        )
        assert resp.status_code == 200
        assert resp.json()["related_entities"][0]["context"] is None

    def test_entity_too_short_400(self):
        p = make_populator()
        p.query_entity_relationships = AsyncMock(return_value={"related_entities": []})
        client = build_client(p)
        resp = client.get(BASE + "/related_entities", params={"entity": "G"})
        assert resp.status_code == 400
        assert "at least 2 characters" in resp.json()["detail"]

    def test_populator_error_500(self):
        p = make_populator()
        p.query_entity_relationships = AsyncMock(side_effect=RuntimeError("gremlin"))
        client = build_client(p)
        resp = client.get(BASE + "/related_entities", params={"entity": "Google"})
        assert resp.status_code == 500
        assert "Failed to retrieve related entities" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /event_timeline
# ---------------------------------------------------------------------------

class TestEventTimeline:
    def test_success_with_events(self):
        # _query_timeline_events -> _execute_traversal returns article rows,
        # then _get_article_entities -> _execute_traversal returns entity names.
        article_rows = [
            {
                "id": ["art1"],
                "title": ["Breaking News"],
                "content": ["some content body"],
                "published_date": ["2024-01-01T00:00:00"],
                "author": ["Reporter"],
                "source_url": ["http://x"],
                "category": ["Tech"],
            }
        ]
        p = make_populator(execute_returns=[article_rows, ["Google", "AI"]])
        client = build_client(p)
        resp = client.get(
            BASE + "/event_timeline",
            params={"topic": "AI", "start_date": "2024-01-01", "end_date": "2024-02-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["topic"] == "AI"
        assert body["total_events"] == 1
        assert body["events"][0]["event_title"] == "Breaking News"
        assert "Google" in body["events"][0]["entities_involved"]

    def test_success_no_dates_infers_span(self):
        article_rows = [
            {
                "id": ["art1"],
                "title": ["News"],
                "content": ["body"],
                "published_date": ["2024-03-05T00:00:00"],
            }
        ]
        p = make_populator(execute_returns=[article_rows, []])
        client = build_client(p)
        resp = client.get(BASE + "/event_timeline", params={"topic": "Climate"})
        assert resp.status_code == 200
        body = resp.json()
        # timeline span inferred from the single event's date
        assert body["timeline_span"]["start_date"] is not None
        assert body["timeline_span"]["end_date"] is not None

    def test_topic_too_short_400(self):
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.get(BASE + "/event_timeline", params={"topic": "A"})
        assert resp.status_code == 400
        assert "at least 2 characters" in resp.json()["detail"]

    def test_bad_start_date_400(self):
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.get(
            BASE + "/event_timeline",
            params={"topic": "AI", "start_date": "not-a-date"},
        )
        assert resp.status_code == 400
        assert "Invalid start_date" in resp.json()["detail"]

    def test_bad_end_date_400(self):
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.get(
            BASE + "/event_timeline",
            params={"topic": "AI", "end_date": "13-13-13"},
        )
        assert resp.status_code == 400
        assert "Invalid end_date" in resp.json()["detail"]

    def test_event_types_filter_and_empty(self):
        # _query_timeline_events returns no articles -> empty timeline
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.get(
            BASE + "/event_timeline",
            params={"topic": "AI", "event_types": "announcement,research"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_events"] == 0


# ---------------------------------------------------------------------------
# /entity_details/{entity_id}
# ---------------------------------------------------------------------------

class TestEntityDetails:
    def test_success(self):
        # 1st traversal: entity valueMap; 2nd: out relationships; 3rd: in
        # relationships; 4th: articles.
        entity_row = [
            {
                "normalized_form": ["Google"],
                "entity_type": ["ORG"],
                "confidence": [0.95],
                "mention_count": [42],
                "created_at": ["2024-01-01"],
                "extra_prop": ["value"],
            }
        ]
        out_rels = [
            {"type": "OWNS", "target": {"normalized_form": ["YouTube"]}, "properties": {}}
        ]
        in_rels = [
            {"type": "FOUNDED_BY", "source": {"normalized_form": ["Larry"]}, "properties": {}}
        ]
        articles = [
            {"id": ["a1"], "title": ["T"], "published_date": ["2024-01-01"], "author": ["A"]}
        ]
        p = make_populator(execute_returns=[entity_row, out_rels, in_rels, articles])
        client = build_client(p)
        resp = client.get(BASE + "/entity_details/google_001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_id"] == "google_001"
        assert body["entity_name"] == "Google"
        assert "extra_prop" in body["properties"]
        assert len(body["relationships"]) == 2
        assert body["source_articles"][0]["article_id"] == "a1"

    def test_not_found_404(self):
        # entity valueMap traversal returns [] -> _query_entity_details None
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.get(BASE + "/entity_details/missing")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_without_optional_sections(self):
        entity_row = [
            {
                "normalized_form": ["Google"],
                "entity_type": ["ORG"],
                "confidence": [0.95],
                "mention_count": [42],
                "created_at": ["2024-01-01"],
            }
        ]
        p = make_populator(execute_returns=[entity_row])
        client = build_client(p)
        resp = client.get(
            BASE + "/entity_details/google_001",
            params={
                "include_relationships": False,
                "include_articles": False,
                "include_properties": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "relationships" not in body
        assert "source_articles" not in body
        assert "properties" not in body


# ---------------------------------------------------------------------------
# POST /graph_search
# ---------------------------------------------------------------------------

class TestGraphSearch:
    def test_entity_search(self):
        entity_rows = [
            {
                "id": ["e1"],
                "normalized_form": ["Google"],
                "entity_type": ["ORG"],
                "confidence": [0.9],
                "mention_count": [10],
                "label": ["Entity"],
            }
        ]
        p = make_populator(execute_returns=[entity_rows])
        client = build_client(p)
        resp = client.post(
            BASE + "/graph_search",
            json={
                "query_type": "entity",
                "search_terms": ["Google"],
                "filters": {"entity_type": "ORG"},
                "sort_by": "confidence",
                "limit": 10,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query_type"] == "entity"
        assert body["total_results"] == 1
        assert body["results"][0]["entity_name"] == "Google"

    def test_entity_search_no_terms_default_sort(self):
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.post(
            BASE + "/graph_search",
            json={
                "query_type": "entity",
                "search_terms": [],
                "sort_by": "relevance",
                "limit": 5,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["total_results"] == 0

    def test_relationship_search(self):
        rel_rows = [
            {
                "type": "OWNS",
                "source": {"normalized_form": ["Google"]},
                "target": {"normalized_form": ["YouTube"]},
                "properties": {},
            }
        ]
        p = make_populator(execute_returns=[rel_rows])
        client = build_client(p)
        resp = client.post(
            BASE + "/graph_search",
            json={"query_type": "relationship", "search_terms": ["OWNS"], "limit": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["relationship_type"] == "OWNS"

    def test_path_search(self):
        path_rows = [["Google", "edge", "YouTube"]]
        p = make_populator(execute_returns=[path_rows])
        client = build_client(p)
        resp = client.post(
            BASE + "/graph_search",
            json={
                "query_type": "path",
                "search_terms": ["Google", "YouTube"],
                "limit": 5,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["results"][0]["source"] == "Google"
        assert body["results"][0]["target"] == "YouTube"

    def test_invalid_query_type_400(self):
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.post(
            BASE + "/graph_search",
            json={"query_type": "bogus", "search_terms": ["x"]},
        )
        assert resp.status_code == 400
        assert "Invalid query_type" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /graph_analytics
# ---------------------------------------------------------------------------

class TestGraphAnalytics:
    def test_overview(self):
        p = make_populator(execute_returns=[[5], [10], [{"ORG": 3}]])
        client = build_client(p)
        resp = client.get(BASE + "/graph_analytics", params={"metric_type": "overview"})
        assert resp.status_code == 200
        assert resp.json()["analytics"]["total_vertices"] == 5

    def test_centrality(self):
        rows = [
            {
                "entity": {"normalized_form": ["Google"], "entity_type": ["ORG"]},
                "degree": 7,
            }
        ]
        p = make_populator(execute_returns=[rows])
        client = build_client(p)
        resp = client.get(
            BASE + "/graph_analytics",
            params={"metric_type": "centrality", "entity_type": "ORG", "top_n": 5},
        )
        assert resp.status_code == 200
        analytics = resp.json()["analytics"]
        assert analytics["top_central_entities"][0]["entity_name"] == "Google"

    def test_clustering(self):
        p = make_populator(execute_returns=[[{"ORG": 5, "PERSON": 3}]])
        client = build_client(p)
        resp = client.get(
            BASE + "/graph_analytics", params={"metric_type": "clustering"}
        )
        assert resp.status_code == 200
        assert resp.json()["analytics"]["analysis_method"] == "entity_type_grouping"

    def test_invalid_metric_400(self):
        p = make_populator(execute_returns=[[]])
        client = build_client(p)
        resp = client.get(BASE + "/graph_analytics", params={"metric_type": "nope"})
        assert resp.status_code == 400
        assert "Invalid metric_type" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /sparql_query
# ---------------------------------------------------------------------------

class TestSparqlQuery:
    def test_success(self):
        p = make_populator()
        p.execute_sparql_query = AsyncMock(return_value={"bindings": []})
        client = build_client(p)
        resp = client.get(
            BASE + "/sparql_query",
            params={"query": "SELECT * WHERE { ?s ?p ?o } LIMIT 10"},
        )
        assert resp.status_code == 200
        assert resp.json()["results"] == {"bindings": []}

    def test_query_too_short_400(self):
        p = make_populator()
        p.execute_sparql_query = AsyncMock(return_value={})
        client = build_client(p)
        resp = client.get(BASE + "/sparql_query", params={"query": "short"})
        assert resp.status_code == 400
        assert "at least 10 characters" in resp.json()["detail"]

    def test_error_500(self):
        p = make_populator()
        p.execute_sparql_query = AsyncMock(side_effect=RuntimeError("neptune down"))
        client = build_client(p)
        resp = client.get(
            BASE + "/sparql_query",
            params={"query": "SELECT * WHERE { ?s ?p ?o }"},
        )
        assert resp.status_code == 500
        assert "Failed to execute SPARQL query" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health():
    p = make_populator()
    client = build_client(p)
    resp = client.get(BASE + "/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["service"] == "knowledge-graph-api"


# ---------------------------------------------------------------------------
# get_enhanced_graph_populator dependency (503 branches)
# ---------------------------------------------------------------------------

class TestPopulatorDependency:
    @pytest.mark.asyncio
    async def test_not_available_503(self, monkeypatch):
        monkeypatch.setattr(mod, "ENHANCED_KG_AVAILABLE", False)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await mod.get_enhanced_graph_populator()
        assert exc.value.status_code == 503
        assert "not available" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_failure_503(self, monkeypatch):
        monkeypatch.setattr(mod, "ENHANCED_KG_AVAILABLE", True)
        monkeypatch.setattr(mod, "CONFIG_AVAILABLE", False)
        monkeypatch.setattr(
            mod,
            "create_enhanced_knowledge_graph_populator",
            MagicMock(side_effect=RuntimeError("no neptune")),
        )
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await mod.get_enhanced_graph_populator()
        assert exc.value.status_code == 503
        assert "Knowledge graph service not available" in exc.value.detail

    @pytest.mark.asyncio
    async def test_create_success(self, monkeypatch):
        monkeypatch.setattr(mod, "ENHANCED_KG_AVAILABLE", True)
        monkeypatch.setattr(mod, "CONFIG_AVAILABLE", False)
        sentinel = object()
        monkeypatch.setattr(
            mod,
            "create_enhanced_knowledge_graph_populator",
            MagicMock(return_value=sentinel),
        )
        result = await mod.get_enhanced_graph_populator()
        assert result is sentinel


# ---------------------------------------------------------------------------
# Direct helper coverage for error/edge branches
# ---------------------------------------------------------------------------

class TestHelpersDirect:
    @pytest.mark.asyncio
    async def test_query_timeline_events_error_returns_empty(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._query_timeline_events(
            populator=p,
            topic="AI",
            start_date=None,
            end_date=None,
            max_events=10,
            event_types=None,
            include_articles=True,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_query_timeline_events_bad_date_falls_back(self):
        rows = [
            {"id": ["a1"], "title": ["T"], "content": ["c"],
             "published_date": ["not-a-date"]}
        ]
        p = make_populator(execute_returns=[rows, []])
        out = await mod._query_timeline_events(
            populator=p,
            topic="AI",
            start_date=None,
            end_date=None,
            max_events=10,
            event_types=None,
            include_articles=True,
        )
        assert len(out) == 1  # falls back to utcnow on ValueError

    @pytest.mark.asyncio
    async def test_get_article_entities_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._get_article_entities(p, "a1")
        assert out == []

    @pytest.mark.asyncio
    async def test_query_entity_details_error_returns_none(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._query_entity_details(
            populator=p,
            entity_id="e1",
            include_relationships=True,
            include_articles=True,
            include_properties=True,
        )
        assert out is None

    @pytest.mark.asyncio
    async def test_get_entity_relationships_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._get_entity_relationships(p, "e1")
        assert out == []

    @pytest.mark.asyncio
    async def test_get_entity_articles_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._get_entity_articles(p, "e1")
        assert out == []

    @pytest.mark.asyncio
    async def test_execute_advanced_search_unknown_type(self):
        p = make_populator(execute_returns=[[]])
        out = await mod._execute_advanced_search(
            populator=p,
            query_type="unknown",
            search_terms=["x"],
            filters={},
            sort_by="relevance",
            limit=5,
        )
        assert out == []

    @pytest.mark.asyncio
    async def test_search_entities_date_sort(self):
        rows = [
            {"id": ["e1"], "normalized_form": ["G"], "entity_type": ["ORG"],
             "confidence": [0.9], "mention_count": [1], "label": ["Entity"]}
        ]
        p = make_populator(execute_returns=[rows])
        out = await mod._search_entities(p, ["G"], {}, "date", 10)
        assert out[0]["entity_name"] == "G"

    @pytest.mark.asyncio
    async def test_search_entities_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._search_entities(p, ["G"], {}, "relevance", 10)
        assert out == []

    @pytest.mark.asyncio
    async def test_search_relationships_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._search_relationships(p, [], {}, "relevance", 10)
        assert out == []

    @pytest.mark.asyncio
    async def test_search_paths_too_few_terms(self):
        p = make_populator(execute_returns=[[]])
        out = await mod._search_paths(p, ["only-one"], {}, "relevance", 10)
        assert out == []

    @pytest.mark.asyncio
    async def test_search_paths_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._search_paths(p, ["a", "b"], {}, "relevance", 10)
        assert out == []

    @pytest.mark.asyncio
    async def test_clustering_analytics_with_entity_type(self):
        p = make_populator(execute_returns=[[{"ORG": 5}]])
        out = await mod._get_clustering_analytics(p, "ORG", 5)
        assert out["entity_type_clusters"] == {"ORG": 5}

    @pytest.mark.asyncio
    async def test_clustering_analytics_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._get_clustering_analytics(p, None, 5)
        assert out == {}

    @pytest.mark.asyncio
    async def test_centrality_analytics_error(self):
        p = make_populator(side_effect=RuntimeError("boom"))
        out = await mod._get_centrality_analytics(p, None, 5)
        assert out == {}

    @pytest.mark.asyncio
    async def test_graph_analytics_dispatch_clustering(self):
        p = make_populator(execute_returns=[[{"ORG": 1}]])
        out = await mod._get_graph_analytics(p, "clustering", None, 5)
        assert "entity_type_clusters" in out
