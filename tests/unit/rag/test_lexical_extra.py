"""Tests for services/rag/lexical.py (psycopg2 mocked)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import services.rag.lexical as mod  # noqa: E402
from services.rag.lexical import (  # noqa: E402
    LexicalSearchService,
    SearchFilters,
    get_lexical_search_service,
)


def make_cursor(fetchall=None, fetchone=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall or []
    cursor.fetchone.return_value = fetchone
    cursor.rowcount = rowcount
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    return cm, cursor


def connect_with(cursor_cm):
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    return conn


SEARCH_ROW = {
    "id": 1, "doc_id": "d1", "chunk_id": "c1", "title": "Title", "content": "Body",
    "source": "bbc", "language": "en", "published_at": None, "url": "http://x",
    "rank": 0.95, "headline": "<b>Title</b>", "word_count": 10, "char_count": 50,
}


@pytest.fixture
def svc():
    return LexicalSearchService({"host": "localhost", "database": "test"})


class TestConnection:
    def test_default_params(self):
        s = LexicalSearchService()
        assert "host" in s.connection_params and "database" in s.connection_params

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
            svc.search("query")


class TestSearch:
    def test_search_returns_results(self, svc):
        cm, _ = make_cursor(fetchall=[SEARCH_ROW])
        svc.connection = connect_with(cm)
        results = svc.search("ai news", k=5, filters=SearchFilters(source="bbc"))
        assert len(results) == 1
        assert results[0].doc_id == "d1"
        assert results[0].rank == 0.95

    def test_simple_search(self, svc):
        row = {"doc_id": "d1", "chunk_id": "c1", "title": "T", "rank": 0.5,
               "headline": "h"}
        cm, _ = make_cursor(fetchall=[row])
        svc.connection = connect_with(cm)
        results = svc.simple_search("ai")
        assert results[0]["doc_id"] == "d1"
        assert results[0]["rank"] == 0.5

    def test_get_search_stats(self, svc):
        cm, _ = make_cursor(fetchone={"total_chunks": 100})
        svc.connection = connect_with(cm)
        assert svc.get_search_stats() == {"total_chunks": 100}

    def test_get_search_stats_empty(self, svc):
        cm, _ = make_cursor(fetchone=None)
        svc.connection = connect_with(cm)
        assert svc.get_search_stats() == {}

    def test_test_query_parsing(self, svc):
        cm, _ = make_cursor(fetchone={"original_query": "ai", "parsed_tsquery": "ai"})
        svc.connection = connect_with(cm)
        result = svc.test_query_parsing("ai")
        assert result["original_query"] == "ai"

    def test_query_parsing_error_returns_dict(self, svc):
        cm, cursor = make_cursor()
        cursor.execute.side_effect = RuntimeError("bad")
        svc.connection = connect_with(cm)
        assert "error" in svc.test_query_parsing("ai")


class TestReindex:
    def test_reindex_chunk(self, svc):
        cm, _ = make_cursor()
        conn = connect_with(cm)
        svc.connection = conn
        svc.reindex_chunk("c1")
        conn.commit.assert_called_once()

    def test_reindex_all(self, svc):
        cm, _ = make_cursor(rowcount=42)
        conn = connect_with(cm)
        svc.connection = conn
        assert svc.reindex_all() == 42
        conn.commit.assert_called_once()


def test_factory():
    assert isinstance(get_lexical_search_service(), LexicalSearchService)
