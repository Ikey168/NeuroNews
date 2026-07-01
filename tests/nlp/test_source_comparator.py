"""
Tests for the multi-source news comparison engine — Issue #46.

Uses an in-memory DuckDB database seeded with realistic fixture data.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import duckdb
import pytest

# The source queries use rolling, relative-to-now windows:
#   - _fetch_coverage        filters news_articles.publish_date >= now - 90 days
#   - list_source_trustworthiness (default) filters
#     outlet_scores.computed_at >= now - 30 days
# Hard-coded fixture dates therefore drift out of these windows as the clock
# advances. Anchor the fixture data to "recent" dates computed at collection
# time so the tests are stable on any run date.
_TODAY = date.today()
_RECENT_TS = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
_RECENT_DAY = (_TODAY - timedelta(days=2)).isoformat()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE news_articles (
    id              VARCHAR,
    title           VARCHAR,
    url             VARCHAR,
    content         VARCHAR,
    publish_date    TIMESTAMP,
    source          VARCHAR,
    category        VARCHAR,
    sentiment_score DOUBLE,
    sentiment_label VARCHAR
);

CREATE TABLE outlet_scores (
    source            VARCHAR,
    source_type       VARCHAR,
    score_date        VARCHAR,
    frame_diversity   DOUBLE,
    attribution_rate  DOUBLE,
    stance_neutrality DOUBLE,
    composite_score   DOUBLE,
    doc_count         INTEGER,
    claim_count       INTEGER,
    computed_at       VARCHAR
);

CREATE TABLE outlet_clusters (
    source        VARCHAR,
    source_type   VARCHAR,
    cluster_id    INTEGER,
    cluster_label VARCHAR,
    pca_x         DOUBLE,
    pca_y         DOUBLE,
    dominant_frame VARCHAR,
    doc_count     INTEGER,
    computed_at   VARCHAR
);

CREATE TABLE source_stances (
    source         VARCHAR,
    source_type    VARCHAR,
    topic          VARCHAR,
    stance         VARCHAR,
    confidence     DOUBLE,
    document_count INTEGER,
    window_start   VARCHAR,
    window_end     VARCHAR,
    computed_at    VARCHAR
);
"""

_ARTICLES = [
    # AI regulation articles — various sources (all within the 90-day window)
    ("a1", "AI Regulation tightens globally", "http://bbc.example/1", "Governments across the world discuss AI Regulation policy.", _RECENT_TS, "BBC World", "Technology", 0.1, "neutral"),
    ("a2", "AI Regulation: what it means for you", "http://bbc.example/2", "A look at AI Regulation impacts.", _RECENT_TS, "BBC World", "Technology", 0.3, "positive"),
    ("a3", "AI Regulation threatens innovation", "http://nyt.example/1", "Critics of AI Regulation speak out.", _RECENT_TS, "NYT Technology", "Technology", -0.4, "negative"),
    ("a4", "AI Regulation: new rules incoming", "http://nyt.example/2", "AI Regulation in the US is advancing.", _RECENT_TS, "NYT Technology", "Technology", -0.2, "negative"),
    ("a5", "AI Regulation welcomed by experts", "http://guardian.example/1", "Experts praise AI Regulation steps.", _RECENT_TS, "Guardian Technology", "Technology", 0.6, "positive"),
    ("a6", "AI Regulation passes committee", "http://guardian.example/2", "AI Regulation bill passes.", _RECENT_TS, "Guardian Technology", "Technology", 0.4, "positive"),
    ("a7", "AI Regulation update", "http://guardian.example/3", "Latest AI Regulation news.", _RECENT_TS, "Guardian Technology", "Technology", 0.2, "positive"),
    # Unrelated article
    ("a8", "Football results", "http://bbc.example/9", "Weekend football scores.", _RECENT_TS, "BBC Sport", "Sports", 0.5, "positive"),
]

_SCORES = [
    ("BBC World", "news", _RECENT_DAY, 0.85, 0.90, 0.80, 0.85, 20, 5, _RECENT_DAY),
    ("NYT Technology", "news", _RECENT_DAY, 0.65, 0.70, 0.60, 0.65, 15, 3, _RECENT_DAY),
    ("Guardian Technology", "news", _RECENT_DAY, 0.78, 0.82, 0.74, 0.78, 18, 4, _RECENT_DAY),
]

_CLUSTERS = [
    ("BBC World", "news", 1, "centrist", 0.1, 0.2, "policy", 20, _RECENT_DAY),
    ("NYT Technology", "news", 2, "market-focused", -0.3, 0.1, "economic", 15, _RECENT_DAY),
    ("Guardian Technology", "news", 1, "centrist", 0.2, 0.3, "policy", 18, _RECENT_DAY),
]

_STANCES = [
    ("BBC World", "news", "AI Regulation", "neutral", 0.72, 2, _RECENT_DAY, _RECENT_DAY, _RECENT_DAY),
    ("NYT Technology", "news", "AI Regulation", "skeptical", 0.68, 2, _RECENT_DAY, _RECENT_DAY, _RECENT_DAY),
    ("Guardian Technology", "news", "AI Regulation", "supportive", 0.81, 3, _RECENT_DAY, _RECENT_DAY, _RECENT_DAY),
]


@pytest.fixture()
def conn() -> duckdb.DuckDBPyConnection:
    db = duckdb.connect(":memory:")
    db.execute(_SCHEMA)
    db.executemany(
        "INSERT INTO news_articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _ARTICLES,
    )
    db.executemany(
        "INSERT INTO outlet_scores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _SCORES,
    )
    db.executemany(
        "INSERT INTO outlet_clusters VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _CLUSTERS,
    )
    db.executemany(
        "INSERT INTO source_stances VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        _STANCES,
    )
    return db


# ---------------------------------------------------------------------------
# compare_sources
# ---------------------------------------------------------------------------

class TestCompareSources:
    def test_returns_expected_sources(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        sources = {c["source"] for c in result["comparison"]}
        assert "BBC World" in sources
        assert "NYT Technology" in sources
        assert "Guardian Technology" in sources

    def test_unrelated_source_excluded(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        sources = {c["source"] for c in result["comparison"]}
        assert "BBC Sport" not in sources

    def test_article_counts_correct(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        by_source = {c["source"]: c for c in result["comparison"]}
        assert by_source["BBC World"]["article_count"] == 2
        assert by_source["NYT Technology"]["article_count"] == 2
        assert by_source["Guardian Technology"]["article_count"] == 3

    def test_total_articles(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        assert result["total_articles"] == 7

    def test_coverage_share_sums_to_100(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        total = sum(c["coverage_share_pct"] for c in result["comparison"])
        assert abs(total - 100.0) < 0.5

    def test_sentiment_sign_per_source(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        by_source = {c["source"]: c for c in result["comparison"]}
        # BBC: mix positive+neutral → avg > 0
        assert by_source["BBC World"]["avg_sentiment"] > 0
        # NYT: both negative
        assert by_source["NYT Technology"]["avg_sentiment"] < 0
        # Guardian: all positive
        assert by_source["Guardian Technology"]["avg_sentiment"] > 0

    def test_dominant_sentiment(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        by_source = {c["source"]: c for c in result["comparison"]}
        assert by_source["NYT Technology"]["dominant_sentiment"] == "negative"
        assert by_source["Guardian Technology"]["dominant_sentiment"] == "positive"

    def test_sentiment_distribution_keys(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        dist = result["comparison"][0]["sentiment_distribution"]
        assert set(dist) == {"positive", "negative", "neutral"}

    def test_trust_scores_populated(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        by_source = {c["source"]: c for c in result["comparison"]}
        bbc = by_source["BBC World"]["trust_scores"]
        assert bbc is not None
        assert bbc["composite_score"] == pytest.approx(0.85, abs=0.001)
        assert bbc["frame_diversity"] == pytest.approx(0.85, abs=0.001)

    def test_cluster_info_populated(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        by_source = {c["source"]: c for c in result["comparison"]}
        bbc = by_source["BBC World"]["cluster"]
        assert bbc is not None
        assert bbc["cluster_label"] == "centrist"

    def test_stance_populated(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        by_source = {c["source"]: c for c in result["comparison"]}
        assert by_source["NYT Technology"]["stance"] == "skeptical"
        assert by_source["Guardian Technology"]["stance"] == "supportive"
        assert by_source["BBC World"]["stance"] == "neutral"

    def test_summary_most_positive(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        assert result["summary"]["most_positive_source"] == "Guardian Technology"

    def test_summary_most_negative(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        assert result["summary"]["most_negative_source"] == "NYT Technology"

    def test_summary_most_trusted(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        # BBC composite_score 0.85 is highest
        assert result["summary"]["most_trusted_source"] == "BBC World"

    def test_summary_highest_coverage(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        # Guardian has 3 articles
        assert result["summary"]["highest_coverage_source"] == "Guardian Technology"

    def test_summary_stance_spread(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        spread = result["summary"]["stance_spread"]
        assert "supportive" in spread
        assert "skeptical" in spread

    def test_limit_respected(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn, limit=2)
        assert result["sources_found"] <= 2

    def test_empty_topic_returns_empty(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("", conn)
        assert result["total_articles"] == 0
        assert result["sources_found"] == 0

    def test_no_matching_topic_returns_empty(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("ZZZnonexistentZZZ", conn)
        assert result["sources_found"] == 0
        assert result["comparison"] == []

    def test_topic_returned_in_result(self, conn: Any):
        from src.nlp.source_comparator import compare_sources
        result = compare_sources("AI Regulation", conn)
        assert result["topic"] == "AI Regulation"


# ---------------------------------------------------------------------------
# list_source_trustworthiness
# ---------------------------------------------------------------------------

class TestListTrustworthiness:
    def test_returns_all_scored_sources(self, conn: Any):
        from src.nlp.source_comparator import list_source_trustworthiness
        rows = list_source_trustworthiness(conn)
        assert len(rows) == 3

    def test_filter_by_source_type(self, conn: Any):
        from src.nlp.source_comparator import list_source_trustworthiness
        rows = list_source_trustworthiness(conn, source_type="news")
        assert len(rows) == 3
        rows_blog = list_source_trustworthiness(conn, source_type="blog")
        assert len(rows_blog) == 0

    def test_has_required_fields(self, conn: Any):
        from src.nlp.source_comparator import list_source_trustworthiness
        rows = list_source_trustworthiness(conn)
        for r in rows:
            assert "source" in r
            assert "composite_score" in r
            assert "frame_diversity" in r

    def test_empty_when_no_scores(self, conn: Any):
        from src.nlp.source_comparator import list_source_trustworthiness
        conn.execute("DELETE FROM outlet_scores")
        rows = list_source_trustworthiness(conn)
        assert rows == []


# ---------------------------------------------------------------------------
# get_source_profile
# ---------------------------------------------------------------------------

class TestGetSourceProfile:
    def test_article_count(self, conn: Any):
        from src.nlp.source_comparator import get_source_profile
        profile = get_source_profile("BBC World", conn)
        assert profile["total_articles"] == 2

    def test_trust_scores_present(self, conn: Any):
        from src.nlp.source_comparator import get_source_profile
        profile = get_source_profile("BBC World", conn)
        assert profile["trust_scores"] is not None
        assert profile["trust_scores"]["composite_score"] == pytest.approx(0.85, abs=0.001)

    def test_cluster_present(self, conn: Any):
        from src.nlp.source_comparator import get_source_profile
        profile = get_source_profile("BBC World", conn)
        assert profile["cluster"] is not None
        assert profile["cluster"]["cluster_label"] == "centrist"

    def test_stances_present(self, conn: Any):
        from src.nlp.source_comparator import get_source_profile
        profile = get_source_profile("BBC World", conn)
        assert len(profile["stances"]) >= 1
        assert profile["stances"][0]["topic"] == "AI Regulation"

    def test_unknown_source_returns_zero_articles(self, conn: Any):
        from src.nlp.source_comparator import get_source_profile
        profile = get_source_profile("Unknown Source XYZ", conn)
        assert profile["total_articles"] == 0
        assert profile["trust_scores"] is None
        assert profile["cluster"] is None
