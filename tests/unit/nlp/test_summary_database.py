"""Tests for src/nlp/summary_database.py (psycopg2 mocked)."""

import os
import sys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.summary_database as mod  # noqa: E402
from nlp.summary_database import SummaryDatabase, SummaryRecord  # noqa: E402


def make_conn(fetchone=None, fetchall=None, rowcount=0):
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.rowcount = rowcount
    cursor_cm = MagicMock()
    cursor_cm.__enter__ = MagicMock(return_value=cursor)
    cursor_cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    conn_cm = MagicMock()
    conn_cm.__enter__ = MagicMock(return_value=conn)
    conn_cm.__exit__ = MagicMock(return_value=False)
    return conn_cm, conn, cursor


@pytest.fixture
def db():
    return SummaryDatabase({"host": "localhost", "dbname": "test"})


def fake_summary():
    s = MagicMock()
    s.text = "A short summary."
    s.length.value = "short"
    s.model.value = "bart-large-cnn"
    s.confidence_score = 0.9
    s.processing_time = 0.12
    s.word_count = 8
    s.sentence_count = 1
    s.compression_ratio = 0.4
    return s


class TestInitAndMetrics:
    def test_init(self, db):
        assert db.table_name == "article_summaries"
        assert db.metrics["queries_executed"] == 0

    def test_update_metrics(self, db):
        db._update_metrics(0.5, cache_hit=False)
        db._update_metrics(1.5, cache_hit=True)
        assert db.metrics["queries_executed"] == 2
        assert db.metrics["average_query_time"] == 1.0
        assert db.metrics["cache_hits"] == 1
        assert db.metrics["cache_misses"] == 1

    def test_performance_metrics_copy(self, db):
        m = db.get_performance_metrics()
        m["queries_executed"] = 999
        assert db.metrics["queries_executed"] == 0  # copy, not reference


class TestCache:
    def test_set_get(self, db):
        rec = SummaryRecord(id=1, article_id="a1")
        db._cache_set("k", rec)
        assert db._cache_get("k") is rec

    def test_expired_entry_removed(self, db):
        rec = SummaryRecord(id=1)
        db._cache_set("k", rec)
        db._cache_timestamps["k"] = datetime.now() - timedelta(hours=2)
        assert db._cache_get("k") is None
        assert "k" not in db._cache

    def test_is_cache_valid_missing(self, db):
        assert db._is_cache_valid("nope") is False

    def test_clear_cache(self, db):
        db._cache_set("k", SummaryRecord(id=1))
        db.clear_cache()
        assert db._cache == {}
        assert db._cache_timestamps == {}


class TestStore:
    @pytest.mark.asyncio
    async def test_store_new(self, db, monkeypatch):
        monkeypatch.setattr(mod, "create_summary_hash", lambda *a: "hash123")
        monkeypatch.setattr(db, "get_summary_by_hash", AsyncMock(return_value=None))
        conn_cm, conn, cursor = make_conn(fetchone=[42])
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)

        new_id = await db.store_summary("art-1", "original text", fake_summary())
        assert new_id == 42
        conn.commit.assert_called_once()
        # The record should be cached by hash
        assert db._cache_get("hash:hash123").id == 42

    @pytest.mark.asyncio
    async def test_store_existing_returns_existing_id(self, db, monkeypatch):
        monkeypatch.setattr(mod, "create_summary_hash", lambda *a: "hash123")
        existing = SummaryRecord(id=7, content_hash="hash123")
        monkeypatch.setattr(db, "get_summary_by_hash", AsyncMock(return_value=existing))
        # _get_connection must NOT be called in this path
        monkeypatch.setattr(db, "_get_connection",
                            MagicMock(side_effect=AssertionError("should not connect")))
        assert await db.store_summary("art-1", "txt", fake_summary()) == 7


class TestRetrieve:
    @pytest.mark.asyncio
    async def test_get_by_hash_cache_hit(self, db):
        rec = SummaryRecord(id=1, content_hash="h")
        db._cache_set("hash:h", rec)
        result = await db.get_summary_by_hash("h")
        assert result is rec
        assert db.metrics["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_get_by_hash_db_hit(self, db, monkeypatch):
        row = (5, "art-1", "h", "summary", "short", "bart", 0.9, 0.1, 10, 2, 0.5,
               datetime(2026, 1, 1), None)
        conn_cm, conn, cursor = make_conn(fetchone=row)
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        result = await db.get_summary_by_hash("h")
        assert result.id == 5
        assert result.confidence_score == 0.9
        assert db.metrics["cache_misses"] == 1

    @pytest.mark.asyncio
    async def test_get_by_hash_db_miss(self, db, monkeypatch):
        conn_cm, conn, cursor = make_conn(fetchone=None)
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        assert await db.get_summary_by_hash("h") is None


class TestDeleteAndStats:
    @pytest.mark.asyncio
    async def test_delete(self, db, monkeypatch):
        conn_cm, conn, cursor = make_conn(rowcount=3)
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        db._cache["article:a1:x"] = SummaryRecord(id=1)
        db._cache_timestamps["article:a1:x"] = datetime.now()
        deleted = await db.delete_summaries_by_article("a1")
        assert deleted == 3
        assert "article:a1:x" not in db._cache

    @pytest.mark.asyncio
    async def test_statistics(self, db, monkeypatch):
        rows = [
            (10, 8, 0.9, 0.1, 100.0, 0.5, "short", 4),
            (20, 15, 0.85, 0.2, 200.0, 0.4, "total", 20),
        ]
        conn_cm, conn, cursor = make_conn(fetchall=rows)
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        stats = await db.get_summary_statistics()
        assert stats["short"]["total_summaries"] == 10
        assert stats["total"]["count"] == 20
        assert "cache" in stats

    @pytest.mark.asyncio
    async def test_create_table(self, db, monkeypatch):
        conn_cm, conn, cursor = make_conn()
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        await db.create_table()
        assert cursor.execute.called
        conn.commit.assert_called()
