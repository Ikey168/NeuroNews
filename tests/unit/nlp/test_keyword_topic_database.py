"""Tests for src/nlp/keyword_topic_database.py (mocked Snowflake connector)."""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nlp.keyword_topic_database import KeywordTopicDatabase  # noqa: E402
from nlp.keyword_topic_extractor import (  # noqa: E402
    ExtractionResult,
    KeywordResult,
    TopicResult,
)


def make_result(article_id="a1"):
    return ExtractionResult(
        article_id=article_id, url="https://x.com/1", title="T",
        keywords=[KeywordResult(keyword="ai", score=0.9, method="tfidf")],
        topics=[TopicResult(topic_id=1, topic_name="tech", topic_words=["ai"], probability=0.8)],
        dominant_topic=TopicResult(topic_id=1, topic_name="tech", topic_words=["ai"], probability=0.8),
        extraction_method="tfidf", processed_at=datetime(2026, 1, 1), processing_time=0.5,
    )


@pytest.fixture
def db():
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=[])
    return KeywordTopicDatabase(snowflake_connector=conn)


class TestInit:
    def test_with_connector(self, db):
        assert db.db is not None

    def test_without_connector(self):
        assert KeywordTopicDatabase().db is None


class TestStore:
    @pytest.mark.asyncio
    async def test_store_success(self, db):
        result = await db.store_extraction_results([make_result("a1"), make_result("a2")])
        assert result["success_count"] == 2
        assert result["error_count"] == 0
        assert result["total_processed"] == 2

    @pytest.mark.asyncio
    async def test_store_no_db_raises(self):
        kdb = KeywordTopicDatabase()
        with pytest.raises(ValueError):
            await kdb.store_extraction_results([make_result()])

    @pytest.mark.asyncio
    async def test_store_counts_errors(self, db):
        db.db.execute_query = AsyncMock(side_effect=RuntimeError("db down"))
        result = await db.store_extraction_results([make_result()])
        assert result["error_count"] == 1
        assert result["success_count"] == 0
        assert result["errors"]


class TestQueries:
    @pytest.mark.asyncio
    async def test_get_articles_by_topic(self, db):
        db.db.execute_query = AsyncMock(return_value=[
            ("id1", "https://x.com/1", "Title", "bbc", datetime(2026, 1, 1),
             '[{"keyword":"ai"}]', '[{"topic_name":"tech"}]', '{"topic_name":"tech"}',
             "tfidf", datetime(2026, 1, 2)),
        ])
        articles = await db.get_articles_by_topic("tech")
        assert len(articles) == 1
        a = articles[0]
        assert a["id"] == "id1"
        assert a["keywords"] == [{"keyword": "ai"}]
        assert a["dominant_topic"] == {"topic_name": "tech"}
        assert a["published_date"] == "2026-01-01T00:00:00"

    @pytest.mark.asyncio
    async def test_get_articles_by_topic_no_db(self):
        kdb = KeywordTopicDatabase()
        with pytest.raises(ValueError):
            await kdb.get_articles_by_topic("tech")

    @pytest.mark.asyncio
    async def test_get_articles_empty(self, db):
        db.db.execute_query = AsyncMock(return_value=[])
        assert await db.get_articles_by_topic("tech") == []

    @pytest.mark.asyncio
    async def test_get_articles_by_keyword(self, db):
        db.db.execute_query = AsyncMock(return_value=[])
        result = await db.get_articles_by_keyword("ai")
        assert isinstance(result, list)
