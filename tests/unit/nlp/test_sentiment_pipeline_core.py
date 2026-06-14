"""Tests for src/nlp/sentiment_pipeline.py (mocked analyzer + DB)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.sentiment_pipeline as sp  # noqa: E402
from nlp.sentiment_pipeline import SentimentPipeline  # noqa: E402


@pytest.fixture
def mock_pg(monkeypatch):
    pg = MagicMock()
    monkeypatch.setattr(sp, "psycopg2", pg)
    # execute_batch / Json are imported directly into the module namespace
    monkeypatch.setattr(sp, "execute_batch", MagicMock(), raising=False)
    monkeypatch.setattr(sp, "Json", lambda x: x, raising=False)
    return pg


@pytest.fixture
def pipeline(monkeypatch, mock_pg):
    analyzer = MagicMock()
    analyzer.analyze_batch.return_value = [
        {"label": "POSITIVE", "score": 0.92},
        {"label": "NEGATIVE", "score": 0.85},
    ]
    monkeypatch.setattr(sp, "create_analyzer", lambda **kw: analyzer)
    return SentimentPipeline(
        snowflake_account="a", snowflake_user="u", snowflake_password="p",
        batch_size=10,
    )


class TestInit:
    def test_config(self, pipeline):
        assert pipeline.batch_size == 10
        assert pipeline.sentiment_provider == "huggingface"
        assert pipeline.conn_params["account"] == "a"

    def test_analyzer_failure_raises(self, monkeypatch, mock_pg):
        def boom(**kw):
            raise RuntimeError("no model")
        monkeypatch.setattr(sp, "create_analyzer", boom)
        with pytest.raises(RuntimeError):
            SentimentPipeline(snowflake_account="a", snowflake_user="u",
                              snowflake_password="p")


class TestProcessArticles:
    def test_empty(self, pipeline):
        assert pipeline.process_articles([]) == []

    def test_processes_with_sentiment(self, pipeline):
        articles = [
            {"article_id": "1", "title": "Good news", "content": "great stuff"},
            {"article_id": "2", "title": "Bad news", "content": "terrible stuff"},
        ]
        results = pipeline.process_articles(articles)
        assert len(results) == 2

    def test_uses_analyze_batch(self, pipeline):
        pipeline.process_articles([{"article_id": "1", "title": "t", "content": "c"}])
        assert pipeline.analyzer.analyze_batch.called


class TestStats:
    def test_get_sentiment_stats(self, pipeline, mock_pg):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = [0]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_pg.connect.return_value.__enter__.return_value = conn
        stats = pipeline.get_sentiment_stats(days=30)
        assert isinstance(stats, dict)
