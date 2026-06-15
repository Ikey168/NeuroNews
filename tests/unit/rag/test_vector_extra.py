"""Tests for services/rag/vector.py (psycopg2 mocked)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

pytest.importorskip("numpy")

import services.rag.vector as mod  # noqa: E402
from services.rag.vector import (  # noqa: E402
    VectorSearchFilters,
    VectorSearchService,
    get_vector_search_service,
)


def make_conn(fetchall=None, fetchone=None):
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall or []
    cursor.fetchone.return_value = fetchone
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cm
    return conn, cursor


ROW = {
    "id": 1, "doc_id": "d1", "chunk_id": "c1", "title": "T", "content": "body",
    "source": "bbc", "url": "http://x", "published_at": None,
    "similarity_score": 0.88, "word_count": 5, "char_count": 20,
}


@pytest.fixture
def svc():
    return VectorSearchService({"host": "localhost", "database": "test"})


class TestConnection:
    def test_default_params(self):
        s = VectorSearchService()
        assert "host" in s.connection_params

    def test_connect_disconnect(self, svc, monkeypatch):
        pg = MagicMock()
        monkeypatch.setattr(mod, "psycopg2", pg)
        svc.connect()
        assert svc.connection is pg.connect.return_value
        svc.disconnect()
        assert svc.connection is None

    def test_context_manager(self, svc, monkeypatch):
        monkeypatch.setattr(mod, "psycopg2", MagicMock())
        with svc as s:
            assert s.connection is not None
        assert svc.connection is None

    def test_search_without_connection_raises(self, svc):
        with pytest.raises(RuntimeError):
            svc.search([0.1, 0.2, 0.3])


class TestSearch:
    def test_search_list_embedding(self, svc):
        conn, _ = make_conn(fetchall=[ROW])
        svc.connection = conn
        results = svc.search([0.1, 0.2, 0.3], k=5)
        assert len(results) == 1
        assert results[0].similarity_score == 0.88
        assert results[0].doc_id == "d1"

    def test_search_numpy_embedding(self, svc):
        import numpy as np
        conn, _ = make_conn(fetchall=[ROW])
        svc.connection = conn
        results = svc.search(np.array([0.1, 0.2, 0.3]))
        assert len(results) == 1

    def test_search_with_filters(self, svc):
        conn, cursor = make_conn(fetchall=[ROW])
        svc.connection = conn
        svc.search([0.1, 0.2], filters=VectorSearchFilters(source="bbc"))
        # source filter should be appended to params
        args = cursor.execute.call_args[0]
        assert "bbc" in args[1]

    def test_search_by_function(self, svc):
        func_row = {
            "document_id": 7, "chunk_id": "c1", "title": "T", "content": "body",
            "source": "bbc", "published_at": None, "similarity_score": 0.77,
        }
        conn, _ = make_conn(fetchall=[func_row])
        svc.connection = conn
        results = svc.search_by_function([0.1, 0.2], similarity_threshold=0.5, k=3)
        assert len(results) == 1
        assert results[0].similarity_score == 0.77


def test_factory():
    assert isinstance(get_vector_search_service(), VectorSearchService)
