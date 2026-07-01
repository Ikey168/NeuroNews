"""Coverage tests for src/api/routes/event_routes.py.

Mounts the router on a fresh FastAPI app, overrides the embedder/clusterer
dependencies and patches the warehouse-view functions and ``psycopg2.connect``
so the DB-backed endpoints run against fakes.  Covers success paths with data,
empty results, 404 and 500 fallbacks, and the manual event-detection POST.
"""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import src.api.routes.event_routes as mod  # noqa: E402
import src.database.local_warehouse_views as views  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _breaking_event():
    return {
        "cluster_id": "cl-1",
        "cluster_name": "Big Event",
        "event_type": "breaking",
        "category": "Technology",
        "trending_score": 9.5,
        "impact_score": 8.0,
        "velocity_score": 7.0,
        "cluster_size": 12,
        "first_article_date": "2024-01-01",
        "last_article_date": "2024-01-02",
        "peak_activity_date": "2024-01-01",
        "event_duration_hours": 24.0,
        "sample_headlines": "H1 | H2",
        "source_count": 5,
        "avg_confidence": 0.9,
    }


def _cluster_row(significance=50.0):
    return {
        "cluster_id": "cl-1",
        "cluster_name": "Cluster One",
        "event_type": "trending",
        "category": "Politics",
        "cluster_size": 8,
        "silhouette_score": 0.5,
        "cohesion_score": 0.6,
        "separation_score": 0.7,
        "trending_score": 5.0,
        "impact_score": 4.0,
        "velocity_score": 3.0,
        "significance_score": significance,
        "first_article_date": "2024-01-01",
        "last_article_date": "2024-01-02",
        "event_duration_hours": 12.0,
        "primary_sources": ["src1"],
        "geographic_focus": ["US"],
        "key_entities": ["Entity"],
        "status": "active",
        "created_at": "2024-01-01T00:00:00",
        "avg_sentiment": 0.1,
        "sample_headlines": ["H1"],
    }


class _FakeCursor:
    """Context-manager cursor.

    ``rows_sequence`` is a list of row-sets.  ``fetchall`` returns the first
    set; ``fetchone`` returns the head row of the *current* set and advances to
    the next set on each call, so a single cursor can service several
    ``execute``/``fetchone`` pairs (as the /events/stats endpoint does).
    """

    def __init__(self, rows_sequence):
        self._seq = list(rows_sequence)
        self._i = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return None

    def fetchall(self):
        return self._seq[0] if self._seq else []

    def fetchone(self):
        rows = self._seq[self._i] if self._i < len(self._seq) else []
        self._i += 1
        return rows[0] if rows else None


class _FakeConn:
    def __init__(self, rows_sequence):
        self._seq = list(rows_sequence)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self, *a, **k):
        # A fresh cursor sees the full sequence so multi-fetchone works.
        return _FakeCursor(self._seq)


def _make_psycopg2_module(rows_sequence):
    """Build a fake psycopg2 module whose connect() yields a _FakeConn."""
    fake = MagicMock()
    fake.connect.return_value = _FakeConn(rows_sequence)
    fake.extras.RealDictCursor = object
    return fake


@pytest.fixture
def clusterer():
    c = MagicMock()
    c.detect_events = AsyncMock(return_value=None)
    c.get_statistics = MagicMock(
        return_value={
            "articles_clustered": 10,
            "clusters_created": 3,
            "events_detected": 2,
            "processing_time": 1.5,
            "last_clustering_run": "2024-01-01T00:00:00",
        }
    )
    return c


@pytest.fixture
def embedder():
    e = MagicMock()
    e.get_embeddings_for_clustering = AsyncMock(
        return_value=[{"article_id": "a1", "embedding": [0.1, 0.2]}]
    )
    e.get_statistics = MagicMock(return_value={"model_name": "all-MiniLM-L6-v2"})
    return e


@pytest.fixture
def client(clusterer, embedder):
    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[mod.get_clusterer] = lambda: clusterer
    app.dependency_overrides[mod.get_embedder] = lambda: embedder
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /breaking_news
# ---------------------------------------------------------------------------

class TestBreakingNews:
    def test_with_events(self, client, monkeypatch):
        monkeypatch.setattr(
            views, "get_breaking_news", AsyncMock(return_value=[_breaking_event()])
        )
        resp = client.get("/api/v1/breaking_news", params={"category": "Technology"})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["cluster_id"] == "cl-1"
        assert body[0]["trending_score"] == 9.5

    def test_empty(self, client, monkeypatch):
        monkeypatch.setattr(views, "get_breaking_news", AsyncMock(return_value=[]))
        resp = client.get("/api/v1/breaking_news")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_error_500(self, client, monkeypatch):
        monkeypatch.setattr(
            views, "get_breaking_news", AsyncMock(side_effect=RuntimeError("boom"))
        )
        resp = client.get("/api/v1/breaking_news")
        assert resp.status_code == 500
        assert "Error retrieving breaking news" in resp.json()["detail"]

    def test_validation_hours_back_too_large(self, client):
        resp = client.get("/api/v1/breaking_news", params={"hours_back": 999})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /entity_graph
# ---------------------------------------------------------------------------

class TestEntityGraph:
    def test_success(self, client, monkeypatch):
        monkeypatch.setattr(
            views,
            "get_entity_graph",
            AsyncMock(return_value={"nodes": [], "edges": []}),
        )
        resp = client.get("/api/v1/entity_graph", params={"days": 5, "max_nodes": 10})
        assert resp.status_code == 200
        assert resp.json() == {"nodes": [], "edges": []}

    def test_error_500(self, client, monkeypatch):
        monkeypatch.setattr(
            views, "get_entity_graph", AsyncMock(side_effect=ValueError("bad"))
        )
        resp = client.get("/api/v1/entity_graph")
        assert resp.status_code == 500
        assert "Error building entity graph" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /events/clusters
# ---------------------------------------------------------------------------

class TestEventClusters:
    def test_success_filters_by_significance(self, client, monkeypatch):
        rows = [_cluster_row(significance=50.0), _cluster_row(significance=1.0)]
        monkeypatch.setattr(
            views, "get_event_clusters", AsyncMock(return_value=rows)
        )
        resp = client.get(
            "/api/v1/events/clusters", params={"min_significance": 10.0}
        )
        assert resp.status_code == 200
        body = resp.json()
        # only the significance=50 row survives the >= 10 filter
        assert len(body) == 1
        assert body[0]["significance_score"] == 50.0

    def test_error_500(self, client, monkeypatch):
        monkeypatch.setattr(
            views, "get_event_clusters", AsyncMock(side_effect=RuntimeError("db"))
        )
        resp = client.get("/api/v1/events/clusters")
        assert resp.status_code == 500
        assert "Error retrieving event clusters" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /events/{cluster_id}/articles  (psycopg2 path)
# ---------------------------------------------------------------------------

class TestArticlesInCluster:
    def test_success(self, client, monkeypatch):
        row = {
            "article_id": "a1",
            "title": "Title",
            "source": "Src",
            "published_date": datetime(2024, 1, 1),
            "assignment_confidence": 0.9,
            "distance_to_centroid": 0.1,
            "is_cluster_representative": True,
            "contribution_score": 0.5,
            "novelty_score": 0.4,
        }
        fake = _make_psycopg2_module([[row]])
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/cl-1/articles")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["article_id"] == "a1"
        assert body[0]["is_cluster_representative"] is True

    def test_not_found_when_no_rows(self, client, monkeypatch):
        fake = _make_psycopg2_module([[]])
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/nope/articles")
        assert resp.status_code == 404
        assert "not found or has no articles" in resp.json()["detail"]

    def test_error_500(self, client, monkeypatch):
        fake = MagicMock()
        fake.connect.side_effect = RuntimeError("connection refused")
        fake.extras.RealDictCursor = object
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/cl-1/articles")
        assert resp.status_code == 500
        assert "Error retrieving articles" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /events/detect
# ---------------------------------------------------------------------------

class TestTriggerEventDetection:
    def test_success(self, client, clusterer):
        resp = client.post(
            "/api/v1/events/detect",
            json={
                "days_back": 3,
                "max_articles": 50,
                "clustering_method": "kmeans",
                "min_cluster_size": 3,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["articles_clustered"] == 10
        assert body["clustering_method"] == "kmeans"
        clusterer.detect_events.assert_awaited_once()

    def test_no_articles_404(self, client, embedder):
        embedder.get_embeddings_for_clustering = AsyncMock(return_value=[])
        resp = client.post(
            "/api/v1/events/detect",
            json={"days_back": 3, "max_articles": 50},
        )
        assert resp.status_code == 404
        assert "No articles found" in resp.json()["detail"]

    def test_detect_error_500(self, client, clusterer):
        clusterer.detect_events = AsyncMock(side_effect=RuntimeError("cluster fail"))
        resp = client.post(
            "/api/v1/events/detect",
            json={"days_back": 3, "max_articles": 50},
        )
        assert resp.status_code == 500
        assert "Error in event detection" in resp.json()["detail"]

    def test_validation_bad_method(self, client):
        resp = client.post(
            "/api/v1/events/detect",
            json={"clustering_method": "invalid_algo"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /events/categories  (psycopg2 path)
# ---------------------------------------------------------------------------

class TestTrendingCategories:
    def test_success(self, client, monkeypatch):
        row = {
            "category": "Technology",
            "active_events": 5,
            "total_articles": 100,
            "avg_trending_score": 7.5,
            "avg_impact_score": 6.0,
            "max_trending_score": 9.0,
            "top_events": "Event A | Event B",
        }
        fake = _make_psycopg2_module([[row]])
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/categories")
        assert resp.status_code == 200
        body = resp.json()
        assert body[0]["category"] == "Technology"
        assert body[0]["top_events"] == ["Event A", "Event B"]

    def test_top_events_empty(self, client, monkeypatch):
        row = {
            "category": "General",
            "active_events": 0,
            "total_articles": 0,
            "avg_trending_score": 0.0,
            "avg_impact_score": 0.0,
            "max_trending_score": 0.0,
            "top_events": None,
        }
        fake = _make_psycopg2_module([[row]])
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/categories")
        assert resp.status_code == 200
        assert resp.json()[0]["top_events"] == []

    def test_error_500(self, client, monkeypatch):
        fake = MagicMock()
        fake.connect.side_effect = RuntimeError("db down")
        fake.extras.RealDictCursor = object
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/categories")
        assert resp.status_code == 500
        assert "Error retrieving trending categories" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /events/stats  (psycopg2 path, three cursors)
# ---------------------------------------------------------------------------

class TestEventDetectionStats:
    def test_success(self, client, monkeypatch):
        cluster_stats = {
            "total_clusters": 10,
            "active_clusters": 4,
            "avg_cluster_size": 6.0,
            "avg_trending_score": 5.0,
            "avg_impact_score": 4.0,
            "max_trending_score": 9.0,
            "breaking_events": 2,
            "trending_events": 3,
        }
        embedding_stats = {
            "total_embeddings": 200,
            "unique_models": 1,
            "avg_quality_score": 0.9,
            "avg_processing_time": 0.5,
        }
        assignment_stats = {
            "total_assignments": 150,
            "avg_confidence": 0.8,
            "representative_articles": 10,
        }
        # three separate cursor() calls -> three row-sets
        fake = _make_psycopg2_module(
            [[cluster_stats], [embedding_stats], [assignment_stats]]
        )
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/stats")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cluster_statistics"]["total_clusters"] == 10
        assert body["embedding_statistics"]["total_embeddings"] == 200
        assert body["assignment_statistics"]["total_assignments"] == 150
        assert body["system_info"]["version"] == "1.0"

    def test_error_500(self, client, monkeypatch):
        fake = MagicMock()
        fake.connect.side_effect = RuntimeError("no db")
        fake.extras.RealDictCursor = object
        monkeypatch.setitem(sys.modules, "psycopg2", fake)
        monkeypatch.setitem(sys.modules, "psycopg2.extras", fake.extras)
        resp = client.get("/api/v1/events/stats")
        assert resp.status_code == 500
        assert "Error retrieving statistics" in resp.json()["detail"]
