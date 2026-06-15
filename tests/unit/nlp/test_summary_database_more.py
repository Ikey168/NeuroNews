"""Additional tests for src/nlp/summary_database.py query methods."""

import os
import sys
from datetime import datetime
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nlp.summary_database import SummaryDatabase, SummaryRecord  # noqa: E402


def make_conn(fetchall=None, fetchone=None):
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall or []
    cursor.fetchone.return_value = fetchone
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cursor)
    cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cm
    cm2 = MagicMock()
    cm2.__enter__ = MagicMock(return_value=conn)
    cm2.__exit__ = MagicMock(return_value=False)
    return cm2


@pytest.fixture
def db():
    return SummaryDatabase({"host": "localhost"})


ROW = (1, "art-1", "h", "summary text", "short", "bart", 0.9, 0.1, 10, 2, 0.5,
       datetime(2026, 1, 1), None)


class TestGetSummariesByArticle:
    @pytest.mark.asyncio
    async def test_db_rows(self, db, monkeypatch):
        monkeypatch.setattr(db, "_get_connection", lambda: make_conn(fetchall=[ROW, ROW]))
        records = await db.get_summaries_by_article("art-1")
        assert len(records) == 2
        assert records[0].article_id == "art-1"

    @pytest.mark.asyncio
    async def test_empty(self, db, monkeypatch):
        monkeypatch.setattr(db, "_get_connection", lambda: make_conn(fetchall=[]))
        assert await db.get_summaries_by_article("art-1") == []

    @pytest.mark.asyncio
    async def test_cache_hit(self, db):
        rec = SummaryRecord(id=1, article_id="art-1")
        db._cache_set("article:art-1", rec)
        result = await db.get_summaries_by_article("art-1")
        assert result == [rec]
        assert db.metrics["cache_hits"] == 1
