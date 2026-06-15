"""Tests for services/embeddings/backends/qdrant_store.py (QdrantClient mocked)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("qdrant_client")
np = pytest.importorskip("numpy")

import services.embeddings.backends.qdrant_store as mod  # noqa: E402
from services.embeddings.backends.qdrant_store import (  # noqa: E402
    QdrantSearchFilters,
    QdrantSearchResult,
    QdrantVectorStore,
)


@pytest.fixture
def store(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(mod, "QdrantClient", lambda host, port: client)
    s = QdrantVectorStore(host="localhost", port=6333, collection_name="test", vector_size=4)
    return s


def point(pid="1", score=0.9, **payload):
    p = MagicMock()
    p.id = pid
    p.score = score
    p.payload = {"doc_id": "d1", "title": "T", "content": "c", "source": "bbc", **payload}
    return p


class TestInit:
    def test_config(self, store):
        assert store.collection_name == "test"
        assert store.vector_size == 4
        assert store.port == 6333


class TestSearchResult:
    def test_from_point(self):
        r = QdrantSearchResult.from_qdrant_point(point(), 0.8)
        assert r.id == "1"
        assert r.similarity_score == 0.8
        assert r.source == "bbc"


class TestCollection:
    def test_create_new(self, store):
        store.client.get_collections.return_value.collections = []
        assert store.create_collection() is True
        store.client.create_collection.assert_called_once()

    def test_already_exists(self, store):
        existing = MagicMock()
        existing.name = "test"
        store.client.get_collections.return_value.collections = [existing]
        assert store.create_collection() is False

    def test_force_recreate(self, store):
        existing = MagicMock()
        existing.name = "test"
        store.client.get_collections.return_value.collections = [existing]
        assert store.create_collection(force_recreate=True) is True
        store.client.delete_collection.assert_called_once()


class TestSearch:
    def test_search(self, store):
        store.client.search.return_value = [point("1"), point("2")]
        results = store.search([0.1, 0.2, 0.3, 0.4], k=5)
        assert len(results) == 2
        assert results[0].id == "1"

    def test_search_numpy(self, store):
        store.client.search.return_value = []
        assert store.search(np.array([0.1, 0.2, 0.3, 0.4])) == []


class TestDeleteAndInfo:
    def test_delete_by_filter(self, store):
        assert store.delete_by_filter({"source": "bbc"}) == 1
        store.client.delete.assert_called_once()

    def test_delete_no_conditions(self, store):
        assert store.delete_by_filter({"unknown": "x"}) == 0

    def test_health_check_ok(self, store):
        store.client.get_collections.return_value = MagicMock()
        assert store.health_check() is True

    def test_health_check_fails(self, store):
        store.client.get_collections.side_effect = RuntimeError("down")
        assert store.health_check() is False

    def test_close(self, store):
        store.close()
        store.client.close.assert_called_once()


class TestFilters:
    def test_filter_with_source(self):
        f = QdrantSearchFilters(source="bbc", min_similarity=0.5)
        # to_qdrant_filter returns a Filter or None
        assert f.to_qdrant_filter() is not None

    def test_empty_filter(self):
        assert QdrantSearchFilters().to_qdrant_filter() is None
