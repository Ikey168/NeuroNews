"""Tests for src/nlp/kubernetes/sentiment_processor.py (mocked analyzer/DB)."""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("torch")

from nlp.kubernetes.sentiment_processor import KubernetesSentimentProcessor  # noqa: E402


@pytest.fixture
def proc(tmp_path):
    p = KubernetesSentimentProcessor(
        batch_size=10, use_gpu=False,
        output_dir=str(tmp_path / "out"), model_cache_dir=str(tmp_path / "models"),
    )
    return p


def article(**over):
    base = dict(
        article_id="a1", title="Good news", content="great stuff happened",
        url="https://x/1", source="bbc", published_date="2026-01-01",
        scraped_at="2026-01-02",
    )
    base.update(over)
    return base


class TestInit:
    def test_defaults(self, proc):
        assert proc.batch_size == 10
        assert proc.use_gpu is False
        assert proc.stats["articles_processed"] == 0
        assert os.path.isdir(proc.output_dir)


class TestProcessBatch:
    def test_batch_with_analyze_batch(self, proc):
        analyzer = MagicMock()
        analyzer.analyze_batch.return_value = [
            {"label": "POSITIVE", "score": 0.9, "confidence": 0.9, "all_scores": {}},
        ]
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article()])
        assert len(results) == 1
        assert results[0]["sentiment_label"] == "POSITIVE"
        assert results[0]["article_id"] == "a1"
        assert proc.stats["articles_processed"] == 1
        assert proc.stats["batches_processed"] == 1

    def test_batch_fallback_individual(self, proc):
        analyzer = MagicMock(spec=["analyze"])  # no analyze_batch
        analyzer.analyze.return_value = {"label": "NEGATIVE", "score": 0.8}
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article(), article(article_id="a2")])
        assert len(results) == 2
        assert all(r["sentiment_label"] == "NEGATIVE" for r in results)

    def test_batch_exception_returns_empty(self, proc):
        analyzer = MagicMock()
        analyzer.analyze_batch.side_effect = RuntimeError("model error")
        proc.sentiment_analyzer = analyzer
        results = proc.process_article_batch([article()])
        assert results == []
        assert proc.stats["articles_failed"] == 1


class TestSaveStats:
    def test_save_stats_writes_file(self, proc):
        proc.stats["articles_processed"] = 5
        proc.stats["total_processing_time"] = 2.0
        proc.save_processing_stats()
        files = [f for f in os.listdir(proc.output_dir) if f.endswith(".json")]
        assert len(files) == 1
        data = json.loads(open(os.path.join(proc.output_dir, files[0])).read())
        assert data["articles_processed"] == 5
        assert "average_processing_time" in data
