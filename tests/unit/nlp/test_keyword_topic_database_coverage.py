"""Coverage-focused tests for src/nlp/keyword_topic_database.py.

The existing tests/unit/nlp/test_keyword_topic_database.py covers __init__,
store_extraction_results and get_articles_by_topic.  This module targets the
remaining uncovered methods:

  * get_articles_by_keyword (row filtering / score thresholding)
  * get_topic_statistics (percentage computation)
  * get_keyword_statistics (aggregation rows)
  * search_articles_by_content_and_topics (dynamic filters, content truncation)
  * create_keyword_topic_db factory (DuckDB shared-connection path)

The Snowflake connector is a MagicMock whose ``execute_query`` is an AsyncMock,
so no real database is touched.
"""

import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.keyword_topic_database as kdb_mod  # noqa: E402
from nlp.keyword_topic_database import (  # noqa: E402
    KeywordTopicDatabase,
    create_keyword_topic_db,
)


@pytest.fixture
def db():
    conn = MagicMock()
    conn.execute_query = AsyncMock(return_value=[])
    return KeywordTopicDatabase(snowflake_connector=conn)


# ---------------------------------------------------------------------------
# get_articles_by_keyword
# ---------------------------------------------------------------------------
class TestGetArticlesByKeyword:
    @pytest.mark.asyncio
    async def test_no_db_raises(self):
        with pytest.raises(ValueError, match="Database connection not initialized"):
            await KeywordTopicDatabase().get_articles_by_keyword("ai")

    @pytest.mark.asyncio
    async def test_matching_keyword_above_threshold_included(self, db):
        # keywords JSON contains "ai" with a high score -> passes the filter.
        db.db.execute_query = AsyncMock(
            return_value=[
                (
                    "id1",
                    "https://x/1",
                    "AI Title",
                    "reuters",
                    datetime(2026, 1, 1),
                    '[{"keyword": "ai research", "score": 0.9}, '
                    '{"keyword": "policy", "score": 0.4}]',
                    '[{"topic_name": "tech"}]',
                    '{"topic_name": "tech"}',
                    "tfidf",
                    datetime(2026, 1, 2),
                ),
            ]
        )
        articles = await db.get_articles_by_keyword("ai", min_score=0.5)
        assert len(articles) == 1
        art = articles[0]
        assert art["id"] == "id1"
        # matched_keywords keeps only "ai research" (score 0.9 >= 0.5); "policy"
        # does not contain "ai" and is dropped.
        matched = art["matched_keywords"]
        assert [k["keyword"] for k in matched] == ["ai research"]
        assert art["published_date"] == "2026-01-01T00:00:00"
        assert art["topics"] == [{"topic_name": "tech"}]
        assert art["dominant_topic"] == {"topic_name": "tech"}

    @pytest.mark.asyncio
    async def test_keyword_below_threshold_excluded(self, db):
        # Only match is below the min_score -> article filtered out entirely.
        db.db.execute_query = AsyncMock(
            return_value=[
                (
                    "id2",
                    "https://x/2",
                    "Weak match",
                    "bbc",
                    datetime(2026, 2, 1),
                    '[{"keyword": "ai", "score": 0.05}]',
                    None,
                    None,
                    "tfidf",
                    None,
                ),
            ]
        )
        articles = await db.get_articles_by_keyword("ai", min_score=0.5)
        assert articles == []

    @pytest.mark.asyncio
    async def test_null_keyword_json_handled(self, db):
        # keywords column is None -> loads to [] and article dropped (no match).
        db.db.execute_query = AsyncMock(
            return_value=[
                ("id3", "u", "t", "s", None, None, None, None, "m", None),
            ]
        )
        assert await db.get_articles_by_keyword("anything") == []


# ---------------------------------------------------------------------------
# get_topic_statistics
# ---------------------------------------------------------------------------
class TestGetTopicStatistics:
    @pytest.mark.asyncio
    async def test_no_db_raises(self):
        with pytest.raises(ValueError):
            await KeywordTopicDatabase().get_topic_statistics()

    @pytest.mark.asyncio
    async def test_percentages_sum_to_100(self, db):
        db.db.execute_query = AsyncMock(
            return_value=[
                ("tech", 6, 0.8, datetime(2026, 1, 1), datetime(2026, 1, 5)),
                ("sports", 4, 0.6, datetime(2026, 1, 2), datetime(2026, 1, 6)),
            ]
        )
        stats = await db.get_topic_statistics(days=14)
        assert len(stats) == 2
        tech, sports = stats
        assert tech["topic_name"] == "tech"
        assert tech["article_count"] == 6
        assert tech["avg_probability"] == pytest.approx(0.8)
        assert tech["earliest_article"] == "2026-01-01T00:00:00"
        # 6/(6+4)=60% and 4/10=40%.
        assert tech["percentage"] == pytest.approx(60.0)
        assert sports["percentage"] == pytest.approx(40.0)
        assert sum(s["percentage"] for s in stats) == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_empty_results_no_division_error(self, db):
        db.db.execute_query = AsyncMock(return_value=[])
        assert await db.get_topic_statistics() == []

    @pytest.mark.asyncio
    async def test_null_probability_and_dates(self, db):
        # avg_probability None -> coerced to 0.0; None dates -> None isoformat.
        db.db.execute_query = AsyncMock(
            return_value=[("misc", 3, None, None, None)]
        )
        stats = await db.get_topic_statistics()
        assert stats[0]["avg_probability"] == 0.0
        assert stats[0]["earliest_article"] is None
        assert stats[0]["latest_article"] is None
        assert stats[0]["percentage"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# get_keyword_statistics
# ---------------------------------------------------------------------------
class TestGetKeywordStatistics:
    @pytest.mark.asyncio
    async def test_no_db_raises(self):
        with pytest.raises(ValueError):
            await KeywordTopicDatabase().get_keyword_statistics()

    @pytest.mark.asyncio
    async def test_rows_mapped(self, db):
        db.db.execute_query = AsyncMock(
            return_value=[
                ("climate", 12, 0.7, 0.3, 0.95),
                ("economy", 8, 0.5, 0.1, 0.9),
            ]
        )
        kws = await db.get_keyword_statistics(days=30, min_frequency=5)
        assert len(kws) == 2
        assert kws[0]["keyword"] == "climate"
        assert kws[0]["frequency"] == 12
        assert kws[0]["avg_score"] == pytest.approx(0.7)
        assert kws[0]["min_score"] == pytest.approx(0.3)
        assert kws[0]["max_score"] == pytest.approx(0.95)
        # Query params carry days + min_frequency.
        called_params = db.db.execute_query.call_args.args[1]
        assert called_params == [30, 5]

    @pytest.mark.asyncio
    async def test_null_scores_coerced_to_zero(self, db):
        db.db.execute_query = AsyncMock(return_value=[("x", 4, None, None, None)])
        kws = await db.get_keyword_statistics()
        assert kws[0]["avg_score"] == 0.0
        assert kws[0]["min_score"] == 0.0
        assert kws[0]["max_score"] == 0.0


# ---------------------------------------------------------------------------
# search_articles_by_content_and_topics
# ---------------------------------------------------------------------------
class TestSearchArticles:
    @pytest.mark.asyncio
    async def test_no_db_raises(self):
        with pytest.raises(ValueError):
            await KeywordTopicDatabase().search_articles_by_content_and_topics("x")

    @pytest.mark.asyncio
    async def test_all_filters_build_params_and_truncate_content(self, db):
        long_content = "z" * 600  # > 500 chars -> gets truncated with "..."
        row = (
            "id1",
            "https://x/1",
            "Deep Title",
            long_content,
            "reuters",
            datetime(2026, 3, 1),
            '[{"keyword": "ai"}]',
            '[{"topic_name": "tech"}]',
            '{"topic_name": "tech"}',
            "tfidf",
            datetime(2026, 3, 2),
            0.87,
            "high",
        )
        # First call: count query. Second call: main query returning one row.
        db.db.execute_query = AsyncMock(side_effect=[[(1,)], [row]])

        result = await db.search_articles_by_content_and_topics(
            search_term="ai",
            topic_filter="tech",
            keyword_filter="ai",
            min_topic_probability=0.3,
            limit=10,
            offset=0,
        )

        assert result["total_count"] == 1
        assert result["returned_count"] == 1
        assert result["has_more"] is False
        article = result["articles"][0]
        # Content truncated to 500 chars + "..."
        assert article["content"].endswith("...")
        assert len(article["content"]) == 503
        assert article["validation_score"] == pytest.approx(0.87)
        assert article["content_quality"] == "high"
        assert article["keywords"] == [{"keyword": "ai"}]

        # Two queries were issued (count + main).
        assert db.db.execute_query.await_count == 2
        # The count-query params include the search term (twice), topic filter,
        # probability and the keyword filter -> at least 5 conditions worth.
        count_params = db.db.execute_query.await_args_list[0].args[1]
        assert "%ai%" in count_params
        assert 0.3 in count_params
        # Main-query params append LIMIT and OFFSET at the end.
        main_params = db.db.execute_query.await_args_list[1].args[1]
        assert main_params[-2:] == [10, 0]

    @pytest.mark.asyncio
    async def test_no_filters_returns_has_more_true(self, db):
        # Short content is not truncated; total_count > returned -> has_more True.
        row = (
            "id9",
            "u",
            "Title",
            "short body",
            "src",
            None,
            None,
            None,
            None,
            "m",
            None,
            None,
            None,
        )
        db.db.execute_query = AsyncMock(side_effect=[[(5,)], [row]])
        result = await db.search_articles_by_content_and_topics(
            search_term="", limit=1, offset=0
        )
        assert result["total_count"] == 5
        assert result["returned_count"] == 1
        assert result["has_more"] is True
        article = result["articles"][0]
        # Not truncated (no trailing ellipsis) and nullable fields handled.
        assert article["content"] == "short body"
        assert article["published_date"] is None
        assert article["validation_score"] is None
        assert result["search_params"]["search_term"] == ""

    @pytest.mark.asyncio
    async def test_empty_count_defaults_to_zero(self, db):
        # count query returns empty list -> total_count falls back to 0.
        db.db.execute_query = AsyncMock(side_effect=[[], []])
        result = await db.search_articles_by_content_and_topics(search_term="")
        assert result["total_count"] == 0
        assert result["returned_count"] == 0
        assert result["has_more"] is False


# ---------------------------------------------------------------------------
# create_keyword_topic_db factory
# ---------------------------------------------------------------------------
class TestFactory:
    @pytest.mark.asyncio
    async def test_uses_provided_connector(self):
        conn = MagicMock()
        result = await create_keyword_topic_db(conn)
        assert isinstance(result, KeywordTopicDatabase)
        assert result.db is conn

    @pytest.mark.asyncio
    async def test_falls_back_to_shared_duckdb_connection(self):
        fake_conn = MagicMock(name="shared_duckdb")
        fake_local_mod = MagicMock()
        fake_local_mod.get_shared_connection.return_value = fake_conn
        # The factory imports get_shared_connection lazily from
        # src.database.local_analytics_connector; patch that module.
        with patch.dict(
            sys.modules,
            {"src.database.local_analytics_connector": fake_local_mod},
        ):
            result = await create_keyword_topic_db()
        assert isinstance(result, KeywordTopicDatabase)
        assert result.db is fake_conn
        fake_local_mod.get_shared_connection.assert_called_once()
