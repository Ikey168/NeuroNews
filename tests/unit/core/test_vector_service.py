"""Tests for src/services/vector_service.py."""

import sys
import types
from unittest.mock import MagicMock

import pytest

from services.vector_service import (
    PgVectorBackend,
    QdrantBackend,
    UnifiedVectorService,
    get_vector_service,
    vector_search,
)


class FakeResult:
    def __init__(self, i=1):
        self.id = i
        self.doc_id = f"doc-{i}"
        self.chunk_id = f"chunk-{i}"
        self.title = "t"
        self.content = "c"
        self.source = "s"
        self.url = "u"
        self.published_at = None
        self.similarity_score = 0.9
        self.word_count = 10
        self.char_count = 50


@pytest.fixture
def fake_pgvector(monkeypatch):
    """Install a fake services.rag.vector module."""
    mod = types.ModuleType("services.rag.vector")

    class FakeFilters:
        def __init__(self, source=None, date_from=None, date_to=None, min_similarity=0.0):
            self.source = source
            self.min_similarity = min_similarity

    service_instance = MagicMock()
    service_instance.__enter__ = MagicMock(return_value=service_instance)
    service_instance.__exit__ = MagicMock(return_value=False)
    service_instance.search.return_value = [FakeResult(1), FakeResult(2)]
    service_instance.get_search_stats.return_value = {"total": 2}

    mod.VectorSearchService = MagicMock(return_value=service_instance)
    mod.VectorSearchFilters = FakeFilters

    services_pkg = types.ModuleType("services")
    rag_pkg = types.ModuleType("services.rag")
    monkeypatch.setitem(sys.modules, "services", services_pkg)
    monkeypatch.setitem(sys.modules, "services.rag", rag_pkg)
    monkeypatch.setitem(sys.modules, "services.rag.vector", mod)
    return mod, service_instance


@pytest.fixture
def fake_qdrant(monkeypatch):
    """Install a fake qdrant_store module."""
    mod = types.ModuleType("services.embeddings.backends.qdrant_store")

    class FakeFilters:
        def __init__(self, source=None, date_from=None, date_to=None, min_similarity=0.0):
            self.source = source

    store = MagicMock()
    store.create_collection.return_value = True
    store.upsert.return_value = 3
    store.search.return_value = [FakeResult(7)]
    store.delete_by_filter.return_value = 2
    store.health_check.return_value = True
    store.get_collection_info.return_value = {"vectors": 7}

    mod.QdrantVectorStore = MagicMock(return_value=store)
    mod.QdrantSearchFilters = FakeFilters

    for name in (
        "services",
        "services.embeddings",
        "services.embeddings.backends",
    ):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(
        sys.modules, "services.embeddings.backends.qdrant_store", mod
    )
    return mod, store


class TestPgVectorBackend:
    def test_import_error_raises(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "services", None)
        with pytest.raises(ImportError):
            PgVectorBackend()

    def test_create_collection(self, fake_pgvector):
        backend = PgVectorBackend()
        assert backend.create_collection() is True

    def test_upsert_returns_count(self, fake_pgvector):
        backend = PgVectorBackend()
        assert backend.upsert([{"id": 1}, {"id": 2}]) == 2

    def test_search_converts_results(self, fake_pgvector):
        backend = PgVectorBackend()
        results = backend.search([0.1, 0.2], k=2, filters={"source": "bbc"})
        assert len(results) == 2
        assert results[0]["doc_id"] == "doc-1"
        assert results[0]["similarity_score"] == 0.9

    def test_search_without_filters(self, fake_pgvector):
        backend = PgVectorBackend()
        results = backend.search([0.1], k=1)
        assert results[1]["id"] == 2

    def test_delete_by_filter_not_implemented(self, fake_pgvector):
        backend = PgVectorBackend()
        assert backend.delete_by_filter({"source": "x"}) == 0

    def test_health_check_success(self, fake_pgvector):
        backend = PgVectorBackend()
        assert backend.health_check() is True

    def test_health_check_failure(self, fake_pgvector):
        _, service = fake_pgvector
        service.__enter__.side_effect = RuntimeError("down")
        backend = PgVectorBackend()
        assert backend.health_check() is False

    def test_get_stats(self, fake_pgvector):
        backend = PgVectorBackend()
        assert backend.get_stats() == {"total": 2}

    def test_get_stats_error(self, fake_pgvector):
        _, service = fake_pgvector
        service.get_search_stats.side_effect = RuntimeError("boom")
        backend = PgVectorBackend()
        stats = backend.get_stats()
        assert "error" in stats


class TestQdrantBackend:
    def test_import_error_raises(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "services", None)
        with pytest.raises(ImportError):
            QdrantBackend()

    def test_delegation(self, fake_qdrant):
        _, store = fake_qdrant
        backend = QdrantBackend()
        assert backend.create_collection() is True
        assert backend.upsert([{}, {}, {}]) == 3
        assert backend.delete_by_filter({"a": 1}) == 2
        assert backend.health_check() is True
        assert backend.get_stats() == {"vectors": 7}

    def test_search_converts_results(self, fake_qdrant):
        backend = QdrantBackend()
        results = backend.search([0.5], k=1, filters={"source": "cnn"})
        assert results[0]["doc_id"] == "doc-7"

    def test_get_stats_error(self, fake_qdrant):
        _, store = fake_qdrant
        store.get_collection_info.side_effect = RuntimeError("x")
        backend = QdrantBackend()
        assert "error" in backend.get_stats()


class TestUnifiedVectorService:
    def test_pgvector_backend_selected(self, fake_pgvector, monkeypatch):
        monkeypatch.delenv("VECTOR_BACKEND", raising=False)
        service = UnifiedVectorService()
        assert service.get_backend_type() == "pgvector"
        assert isinstance(service.backend, PgVectorBackend)

    def test_qdrant_backend_selected(self, fake_qdrant):
        service = UnifiedVectorService(backend_type="qdrant")
        assert service.get_backend_type() == "qdrant"

    def test_env_var_selection(self, fake_qdrant, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "QDRANT")
        service = UnifiedVectorService()
        assert service.get_backend_type() == "qdrant"

    def test_invalid_backend_raises(self):
        with pytest.raises(ValueError):
            UnifiedVectorService(backend_type="faiss")

    def test_delegation_methods(self, fake_qdrant):
        service = UnifiedVectorService(backend_type="qdrant")
        assert service.create_collection() is True
        assert service.upsert([{}]) == 3
        assert service.delete_by_filter({}) == 2
        assert service.health_check() is True
        results = service.search([0.1], k=1)
        assert len(results) == 1

    def test_get_stats_includes_backend_type(self, fake_qdrant):
        service = UnifiedVectorService(backend_type="qdrant")
        stats = service.get_stats()
        assert stats["backend_type"] == "qdrant"
        assert stats["vectors"] == 7


class TestFactoryFunctions:
    def test_get_vector_service(self, fake_qdrant):
        service = get_vector_service("qdrant")
        assert isinstance(service, UnifiedVectorService)

    def test_vector_search(self, fake_qdrant):
        results = vector_search([0.1, 0.2], k=1, backend_type="qdrant")
        assert results[0]["id"] == 7
