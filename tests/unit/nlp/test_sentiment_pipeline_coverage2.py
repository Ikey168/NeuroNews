"""Coverage-focused tests for src/nlp/sentiment_pipeline.py.

Complements ``test_sentiment_pipeline_core.py`` by driving the branches it
does not touch: the ERROR-label handling in ``process_articles``, the
``analyze``-per-text fallback when the analyzer has no ``analyze_batch``, the
full ``reprocess_articles`` flow (both the id-list and days-back queries plus
the empty-result short-circuit), ``get_sentiment_stats`` row aggregation, and
every ``except`` block that logs then re-raises.

psycopg2, execute_batch and Json are all mocked; no real DB is touched.
"""

# --- Warm up heavy C-extension imports BEFORE coverage traces them. ----------
import torch  # noqa: E402,F401

try:
    import torch._dynamo  # noqa: E402,F401
except Exception:
    pass
try:
    from transformers import pipeline as _warm_pipeline  # noqa: E402,F401
except Exception:
    pass
# -----------------------------------------------------------------------------

import os  # noqa: E402
import sys  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.sentiment_pipeline as sp  # noqa: E402
from nlp.sentiment_pipeline import SentimentPipeline  # noqa: E402


@pytest.fixture
def mock_pg(monkeypatch):
    pg = MagicMock()
    monkeypatch.setattr(sp, "psycopg2", pg)
    monkeypatch.setattr(sp, "execute_batch", MagicMock(), raising=False)
    monkeypatch.setattr(sp, "Json", lambda x: x, raising=False)
    return pg


def _set_cursor(pg, fetchall=None, fetchone=None):
    """Wire the mocked psycopg2 connect() to yield a cursor with canned data."""
    cursor = MagicMock()
    cursor.fetchall.return_value = fetchall or []
    cursor.fetchone.return_value = fetchone
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    pg.connect.return_value.__enter__.return_value = conn
    return cursor


@pytest.fixture
def pipeline(monkeypatch, mock_pg):
    analyzer = MagicMock()
    analyzer.analyze_batch.return_value = [
        {"label": "POSITIVE", "score": 0.92, "all_scores": {"positive": 0.92}},
    ]
    monkeypatch.setattr(sp, "create_analyzer", lambda **kw: analyzer)
    return SentimentPipeline(
        snowflake_account="a", snowflake_user="u", snowflake_password="p",
        batch_size=10,
    )


# --------------------------------------------------------------------------- #
# _initialize_database error path (lines 135-137)
# --------------------------------------------------------------------------- #
class TestInitDatabaseError:
    def test_init_db_failure_raises(self, monkeypatch, mock_pg):
        analyzer = MagicMock()
        monkeypatch.setattr(sp, "create_analyzer", lambda **kw: analyzer)
        mock_pg.connect.side_effect = RuntimeError("schema boom")
        with pytest.raises(RuntimeError, match="schema boom"):
            SentimentPipeline(
                snowflake_account="a", snowflake_user="u", snowflake_password="p"
            )


# --------------------------------------------------------------------------- #
# process_articles: ERROR label + confidence fallback + analyze fallback
# --------------------------------------------------------------------------- #
class TestProcessArticlesBranches:
    def test_error_label_nullifies_sentiment(self, pipeline):
        pipeline.analyzer.analyze_batch.return_value = [
            {"label": "ERROR", "message": "bad"},
        ]
        results = pipeline.process_articles(
            [{"article_id": "1", "title": "t", "content": "c"}]
        )
        assert results[0]["sentiment_label"] is None
        assert results[0]["sentiment_score"] is None
        assert results[0]["sentiment_confidence"] is None

    def test_all_scores_and_confidence_used(self, pipeline):
        pipeline.analyzer.analyze_batch.return_value = [
            {
                "label": "positive",
                "score": 0.8,
                "confidence": 0.95,
                "all_scores": {"positive": 0.8, "negative": 0.2},
                "text": "hello world",
                "language_code": "en",
            }
        ]
        results = pipeline.process_articles(
            [{"article_id": "1", "title": "t", "content": "c"}]
        )
        assert results[0]["sentiment_label"] == "POSITIVE"
        assert results[0]["sentiment_confidence"] == 0.95
        assert results[0]["all_scores"] == {"positive": 0.8, "negative": 0.2}

    def test_fallback_to_individual_analyze(self, monkeypatch, mock_pg):
        # Analyzer WITHOUT analyze_batch -> uses [analyze(t) for t in texts]
        class NoBatchAnalyzer:
            def analyze(self, text):
                return {"label": "NEGATIVE", "score": 0.4}

        monkeypatch.setattr(sp, "create_analyzer", lambda **kw: NoBatchAnalyzer())
        pipe = SentimentPipeline(
            snowflake_account="a", snowflake_user="u", snowflake_password="p"
        )
        results = pipe.process_articles(
            [{"article_id": "9", "title": "x", "content": "y"}]
        )
        assert len(results) == 1
        assert results[0]["sentiment_label"] == "NEGATIVE"

    def test_process_error_reraises(self, pipeline, monkeypatch):
        pipeline.analyzer.analyze_batch.side_effect = RuntimeError("analyze boom")
        with pytest.raises(RuntimeError, match="analyze boom"):
            pipeline.process_articles(
                [{"article_id": "1", "title": "t", "content": "c"}]
            )

    def test_store_results_error_reraises(self, pipeline, monkeypatch):
        # Make the store step raise via execute_batch to hit lines 227-229.
        monkeypatch.setattr(
            sp, "execute_batch", MagicMock(side_effect=RuntimeError("store boom"))
        )
        with pytest.raises(RuntimeError, match="store boom"):
            pipeline.process_articles(
                [{"article_id": "1", "title": "t", "content": "c"}]
            )


# --------------------------------------------------------------------------- #
# reprocess_articles (lines 343-401)
# --------------------------------------------------------------------------- #
class TestReprocessArticles:
    def test_reprocess_by_days_back_no_rows(self, pipeline, mock_pg):
        _set_cursor(mock_pg, fetchall=[])
        out = pipeline.reprocess_articles(days_back=3)
        assert out["processed"] == 0
        assert "No articles" in out["message"]

    def test_reprocess_by_ids_processes(self, pipeline, mock_pg, monkeypatch):
        rows = [("id1", "Title 1", "Content 1", "http://x", "src", "2026-01-01")]
        _set_cursor(mock_pg, fetchall=rows)
        # Stub process_articles so we exercise the reprocess wrapper + stats calc.
        monkeypatch.setattr(
            pipeline,
            "process_articles",
            lambda arts: [{"sentiment_label": "POSITIVE"}],
        )
        out = pipeline.reprocess_articles(article_ids=["id1"])
        assert out["processed"] == 1
        assert out["sentiment_distribution"]["POSITIVE"] == 1
        assert out["reprocessed_articles"] == 1
        assert out["provider"] == "huggingface"

    def test_reprocess_error_reraises(self, pipeline, mock_pg):
        mock_pg.connect.side_effect = RuntimeError("fetch boom")
        with pytest.raises(RuntimeError, match="fetch boom"):
            pipeline.reprocess_articles(days_back=1)


# --------------------------------------------------------------------------- #
# get_sentiment_stats row aggregation + error (lines 433-448)
# --------------------------------------------------------------------------- #
class TestSentimentStats:
    def test_stats_aggregates_rows(self, pipeline, mock_pg):
        rows = [
            ("POSITIVE", 10, 0.8, 0.5, 0.95, "huggingface"),
            ("NEGATIVE", 4, 0.3, 0.1, 0.4, "huggingface"),
        ]
        _set_cursor(mock_pg, fetchall=rows)
        stats = pipeline.get_sentiment_stats(days=14)
        assert stats["period_days"] == 14
        assert stats["total_processed"] == 14
        assert len(stats["sentiment_breakdown"]) == 2
        assert stats["sentiment_breakdown"][0]["sentiment"] == "POSITIVE"
        assert stats["sentiment_breakdown"][0]["avg_score"] == pytest.approx(0.8)

    def test_stats_null_scores_default_zero(self, pipeline, mock_pg):
        rows = [("NEUTRAL", 2, None, None, None, "huggingface")]
        _set_cursor(mock_pg, fetchall=rows)
        stats = pipeline.get_sentiment_stats(days=7)
        row = stats["sentiment_breakdown"][0]
        assert row["avg_score"] == 0.0
        assert row["min_score"] == 0.0
        assert row["max_score"] == 0.0

    def test_stats_error_reraises(self, pipeline, mock_pg):
        mock_pg.connect.side_effect = RuntimeError("stats boom")
        with pytest.raises(RuntimeError, match="stats boom"):
            pipeline.get_sentiment_stats(days=30)
