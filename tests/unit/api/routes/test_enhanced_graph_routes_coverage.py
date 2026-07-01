"""Comprehensive coverage tests for src/api/routes/enhanced_graph_routes.py.

Mounts the router on a fresh FastAPI app, overrides the get_optimized_graph
dependency with an AsyncMock-backed graph API, and exercises every endpoint
and branch: success, validation errors (422), bad-date (400), service
unavailable (503), and the 500 fallback paths.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.enhanced_graph_routes as mod  # noqa: E402


def make_graph_api():
    """Build a MagicMock graph API with async methods returning plain dicts."""
    g = MagicMock()
    g.get_related_entities_optimized = AsyncMock(
        return_value={"entities": [{"name": "OpenAI"}], "count": 1}
    )
    g.get_event_timeline_optimized = AsyncMock(
        return_value={"events": [{"title": "launch"}], "count": 1}
    )
    g.search_entities_optimized = AsyncMock(
        return_value={"results": [{"name": "OpenAI"}], "count": 1}
    )
    g.get_cache_stats = AsyncMock(
        return_value={
            "hits": 10,
            "misses": 2,
            "performance": {"error_rate": 0.0},
        }
    )
    g.clear_cache = AsyncMock(return_value={"cleared_entries": 5})

    # graph attribute for health check (_execute_traversal + g.V().limit())
    graph = MagicMock()
    graph._execute_traversal = AsyncMock(return_value=[1])
    graph.g = MagicMock()
    g.graph = graph

    # redis client for health check
    redis = MagicMock()
    redis.ping = AsyncMock(return_value=True)
    g.redis_client = redis
    return g


@pytest.fixture
def graph_api():
    return make_graph_api()


@pytest.fixture
def client(graph_api):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_optimized_graph] = lambda: graph_api
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /related-entities
# ---------------------------------------------------------------------------
def test_related_entities_get_success(client, graph_api):
    resp = client.get(
        "/api/v2/graph/related-entities",
        params={
            "entity": "OpenAI",
            "entity_type": "Organization",
            "max_depth": 3,
            "relationship_types": "PARTNER, FUNDS",
            "use_cache": "false",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["metadata"]["api_version"] == "v2"
    assert body["metadata"]["cache_used"] is False
    assert body["metadata"]["optimized"] is True
    # relationship_types were parsed and split on comma / stripped
    kwargs = graph_api.get_related_entities_optimized.call_args.kwargs
    assert kwargs["relationship_types"] == ["PARTNER", "FUNDS"]
    assert kwargs["entity"] == "OpenAI"


def test_related_entities_get_missing_required_entity(client):
    resp = client.get("/api/v2/graph/related-entities")
    assert resp.status_code == 422


def test_related_entities_get_depth_out_of_range(client):
    resp = client.get(
        "/api/v2/graph/related-entities",
        params={"entity": "OpenAI", "max_depth": 99},
    )
    assert resp.status_code == 422


def test_related_entities_get_internal_error(client, graph_api):
    graph_api.get_related_entities_optimized.side_effect = RuntimeError("boom")
    resp = client.get(
        "/api/v2/graph/related-entities", params={"entity": "OpenAI"}
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# POST /related-entities
# ---------------------------------------------------------------------------
def test_related_entities_post_success(client):
    resp = client.post(
        "/api/v2/graph/related-entities",
        json={
            "entity": "OpenAI",
            "entity_type": "Organization",
            "max_depth": 2,
            "relationship_types": ["PARTNER"],
            "use_cache": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["request_method"] == "POST"
    assert body["count"] == 1


def test_related_entities_post_validation_error(client):
    # entity has min_length=1; empty string violates it
    resp = client.post("/api/v2/graph/related-entities", json={"entity": ""})
    assert resp.status_code == 422


def test_related_entities_post_internal_error(client, graph_api):
    graph_api.get_related_entities_optimized.side_effect = ValueError("nope")
    resp = client.post(
        "/api/v2/graph/related-entities", json={"entity": "OpenAI"}
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# GET /event-timeline
# ---------------------------------------------------------------------------
def test_event_timeline_get_success(client):
    resp = client.get(
        "/api/v2/graph/event-timeline",
        params={
            "topic": "AI",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "limit": 50,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["limit"] == 50
    assert body["count"] == 1


def test_event_timeline_get_bad_start_date(client):
    resp = client.get(
        "/api/v2/graph/event-timeline",
        params={"topic": "AI", "start_date": "not-a-date"},
    )
    assert resp.status_code == 400
    assert "start_date" in resp.json()["detail"]


def test_event_timeline_get_bad_end_date(client):
    resp = client.get(
        "/api/v2/graph/event-timeline",
        params={"topic": "AI", "end_date": "13/40/9999"},
    )
    assert resp.status_code == 400
    assert "end_date" in resp.json()["detail"]


def test_event_timeline_get_start_after_end(client):
    resp = client.get(
        "/api/v2/graph/event-timeline",
        params={
            "topic": "AI",
            "start_date": "2024-12-31",
            "end_date": "2024-01-01",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "start_date must be before end_date"


def test_event_timeline_get_internal_error(client, graph_api):
    graph_api.get_event_timeline_optimized.side_effect = RuntimeError("boom")
    resp = client.get(
        "/api/v2/graph/event-timeline", params={"topic": "AI"}
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# POST /event-timeline
# ---------------------------------------------------------------------------
def test_event_timeline_post_success(client):
    resp = client.post(
        "/api/v2/graph/event-timeline",
        json={"topic": "AI", "limit": 10, "use_cache": False},
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["request_method"] == "POST"


def test_event_timeline_post_start_after_end(client):
    resp = client.post(
        "/api/v2/graph/event-timeline",
        json={
            "topic": "AI",
            "start_date": "2024-12-31T00:00:00",
            "end_date": "2024-01-01T00:00:00",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "start_date must be before end_date"


def test_event_timeline_post_validation_error(client):
    resp = client.post("/api/v2/graph/event-timeline", json={"topic": ""})
    assert resp.status_code == 422


def test_event_timeline_post_internal_error(client, graph_api):
    graph_api.get_event_timeline_optimized.side_effect = RuntimeError("x")
    resp = client.post("/api/v2/graph/event-timeline", json={"topic": "AI"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------
def test_search_get_success(client, graph_api):
    resp = client.get(
        "/api/v2/graph/search",
        params={"q": "OpenAI", "types": "Organization, Person", "limit": 20},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["metadata"]["limit"] == 20
    kwargs = graph_api.search_entities_optimized.call_args.kwargs
    assert kwargs["entity_types"] == ["Organization", "Person"]


def test_search_get_too_short_query(client):
    # q has min_length=2
    resp = client.get("/api/v2/graph/search", params={"q": "a"})
    assert resp.status_code == 422


def test_search_get_internal_error(client, graph_api):
    graph_api.search_entities_optimized.side_effect = RuntimeError("boom")
    resp = client.get("/api/v2/graph/search", params={"q": "OpenAI"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------
def test_search_post_success(client):
    resp = client.post(
        "/api/v2/graph/search",
        json={"search_term": "OpenAI", "entity_types": ["Organization"], "limit": 5},
    )
    assert resp.status_code == 200
    assert resp.json()["metadata"]["request_method"] == "POST"


def test_search_post_validation_error(client):
    # search_term min_length=2
    resp = client.post("/api/v2/graph/search", json={"search_term": "x"})
    assert resp.status_code == 422


def test_search_post_internal_error(client, graph_api):
    graph_api.search_entities_optimized.side_effect = RuntimeError("x")
    resp = client.post("/api/v2/graph/search", json={"search_term": "OpenAI"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Internal server error"


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------
def test_stats_success(client):
    resp = client.get("/api/v2/graph/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["hits"] == 10
    assert body["api_info"]["version"] == "v2"
    assert "/search" in body["api_info"]["endpoints"]


def test_stats_internal_error(client, graph_api):
    graph_api.get_cache_stats.side_effect = RuntimeError("boom")
    resp = client.get("/api/v2/graph/stats")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to retrieve API statistics"


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
def test_health_all_healthy(client):
    resp = client.get("/api/v2/graph/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["components"]["neptune"]["status"] == "healthy"
    assert body["components"]["redis"]["status"] == "healthy"
    assert body["components"]["api"]["status"] == "healthy"


def test_health_neptune_unhealthy_returns_503(client, graph_api):
    graph_api.graph._execute_traversal.side_effect = RuntimeError("neptune down")
    resp = client.get("/api/v2/graph/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "unhealthy"
    assert body["components"]["neptune"]["status"] == "unhealthy"


def test_health_redis_disabled(client, graph_api):
    graph_api.redis_client = None
    resp = client.get("/api/v2/graph/health")
    assert resp.status_code == 200
    assert resp.json()["components"]["redis"]["status"] == "disabled"


def test_health_redis_unhealthy_but_overall_ok(client, graph_api):
    graph_api.redis_client.ping.side_effect = RuntimeError("redis down")
    resp = client.get("/api/v2/graph/health")
    # redis failure is non-critical -> overall still healthy (200)
    assert resp.status_code == 200
    assert resp.json()["components"]["redis"]["status"] == "unhealthy"


def test_health_high_error_rate_degraded(client, graph_api):
    graph_api.get_cache_stats.return_value = {
        "performance": {"error_rate": 0.5}
    }
    resp = client.get("/api/v2/graph/health")
    assert resp.status_code == 200
    assert resp.json()["components"]["api"]["status"] == "degraded"


def test_health_stats_exception_unknown(client, graph_api):
    graph_api.get_cache_stats.side_effect = RuntimeError("stats broke")
    resp = client.get("/api/v2/graph/health")
    assert resp.status_code == 200
    assert resp.json()["components"]["api"]["status"] == "unknown"


# ---------------------------------------------------------------------------
# DELETE /cache
# ---------------------------------------------------------------------------
def test_cache_delete_success(client):
    resp = client.delete(
        "/api/v2/graph/cache", params={"pattern": "entity:*", "force": "true"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared_entries"] == 5
    assert body["metadata"]["forced"] is True
    assert body["metadata"]["operation"] == "cache_clear"


def test_cache_delete_internal_error(client, graph_api):
    graph_api.clear_cache.side_effect = RuntimeError("boom")
    resp = client.delete("/api/v2/graph/cache")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to clear cache"


# ---------------------------------------------------------------------------
# POST /cache/clear
# ---------------------------------------------------------------------------
def test_cache_clear_post_success(client):
    resp = client.post(
        "/api/v2/graph/cache/clear", json={"pattern": "x:*", "force": True}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cleared_entries"] == 5
    assert body["metadata"]["request_method"] == "POST"
    assert body["metadata"]["forced"] is True


def test_cache_clear_post_defaults(client):
    resp = client.post("/api/v2/graph/cache/clear", json={})
    assert resp.status_code == 200
    assert resp.json()["metadata"]["forced"] is False


def test_cache_clear_post_internal_error(client, graph_api):
    graph_api.clear_cache.side_effect = RuntimeError("boom")
    resp = client.post("/api/v2/graph/cache/clear", json={})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to clear cache"


# ---------------------------------------------------------------------------
# get_optimized_graph dependency + 503 when not initialized
# ---------------------------------------------------------------------------
def test_service_unavailable_when_not_initialized(monkeypatch):
    """Without dependency override, get_optimized_graph raises 503."""
    monkeypatch.setattr(mod, "optimized_graph_api", None)
    app = FastAPI()
    app.include_router(mod.router)
    local_client = TestClient(app, raise_server_exceptions=False)
    resp = local_client.get(
        "/api/v2/graph/related-entities", params={"entity": "OpenAI"}
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "Knowledge Graph API service not available"


def test_get_optimized_graph_returns_instance(monkeypatch):
    """When the global is set, the real dependency returns it."""
    import asyncio

    sentinel = object()
    monkeypatch.setattr(mod, "optimized_graph_api", sentinel)
    result = asyncio.get_event_loop().run_until_complete(mod.get_optimized_graph())
    assert result is sentinel


# ---------------------------------------------------------------------------
# lifespan_manager coverage (init failure path + happy path)
# ---------------------------------------------------------------------------
def test_lifespan_manager_init_failure(monkeypatch):
    """create_optimized_graph_api raising -> optimized_graph_api set to None."""
    import asyncio

    def boom(_endpoint):
        raise RuntimeError("cannot create")

    monkeypatch.setattr(mod, "create_optimized_graph_api", boom)

    async def run():
        async with mod.lifespan_manager(FastAPI()):
            pass

    asyncio.get_event_loop().run_until_complete(run())
    assert mod.optimized_graph_api is None


def test_lifespan_manager_happy_path(monkeypatch):
    """Successful init + clean shutdown exercises the close() branch."""
    import asyncio

    fake_api = MagicMock()
    fake_api.initialize = AsyncMock()
    fake_api.close = AsyncMock()
    graph = MagicMock()
    graph.connect = AsyncMock()
    graph.close = AsyncMock()
    fake_api.graph = graph

    monkeypatch.setattr(
        mod, "create_optimized_graph_api", lambda endpoint: fake_api
    )

    async def run():
        async with mod.lifespan_manager(FastAPI()):
            assert mod.optimized_graph_api is fake_api

    asyncio.get_event_loop().run_until_complete(run())
    fake_api.initialize.assert_awaited()
    fake_api.close.assert_awaited()
    graph.close.assert_awaited()
