"""Tests for src/nlp/nlp_integration.py (mocked pipeline)."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.nlp_integration as mod  # noqa: E402


@pytest.fixture(autouse=True)
def light_pipeline(monkeypatch):
    # Avoid constructing the heavy real OptimizedNLPPipeline
    monkeypatch.setattr(mod, "OptimizedNLPPipeline", MagicMock())


@pytest.fixture
def analyzer():
    return mod.OptimizedSentimentAnalyzer()


class TestSentimentAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_batch_success(self, analyzer):
        analyzer.pipeline.process_articles_async = AsyncMock(return_value={
            "results": [
                {"article_id": "1", "sentiment": {"label": "POSITIVE", "confidence": 0.9},
                 "processing_time": 0.1},
            ]
        })
        results = await analyzer.analyze_batch([{"id": "1", "content": "great"}])
        assert results[0]["label"] == "POSITIVE"
        assert results[0]["confidence"] == 0.9
        assert results[0]["cached"] is True

    @pytest.mark.asyncio
    async def test_analyze_batch_missing_sentiment(self, analyzer):
        analyzer.pipeline.process_articles_async = AsyncMock(return_value={
            "results": [{"article_id": "1", "processing_time": 0.1}]
        })
        results = await analyzer.analyze_batch([{"id": "1", "content": "x"}])
        assert "error" in results[0]

    @pytest.mark.asyncio
    async def test_fallback_on_pipeline_error(self, analyzer):
        analyzer.pipeline.process_articles_async = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        legacy = MagicMock()
        legacy.analyze_sentiment.return_value = {"sentiment": "NEGATIVE", "confidence": 0.7}
        analyzer.legacy_analyzer = legacy
        results = await analyzer.analyze_batch([{"id": "1", "content": "bad"}])
        assert results[0]["label"] == "NEGATIVE"
        assert results[0]["fallback"] is True

    @pytest.mark.asyncio
    async def test_no_fallback_reraises(self, analyzer):
        analyzer.pipeline.process_articles_async = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        analyzer.legacy_analyzer = None
        with pytest.raises(RuntimeError):
            await analyzer.analyze_batch([{"id": "1", "content": "x"}])

    @pytest.mark.asyncio
    async def test_fallback_handles_per_article_error(self, analyzer):
        legacy = MagicMock()
        legacy.analyze_sentiment.side_effect = ValueError("nope")
        analyzer.legacy_analyzer = legacy
        results = await analyzer._fallback_sentiment_analysis([{"id": "1", "content": "x"}])
        assert "error" in results[0]
        assert results[0]["fallback"] is True

    def test_get_performance_stats(self, analyzer):
        analyzer.pipeline.get_performance_stats.return_value = {"ok": True}
        assert analyzer.get_performance_stats() == {"ok": True}


class TestSimpleClusteringFallback:
    @pytest.fixture
    def clusterer(self):
        return mod.OptimizedEventClusterer()

    def test_clusters_similar(self, clusterer):
        # Two identical vectors -> one cluster of 2; a third orthogonal -> excluded
        embeddings = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        articles = [{"id": str(i)} for i in range(3)]
        result = clusterer._simple_clustering_fallback(articles, embeddings)
        assert result["algorithm"] == "simple_fallback"
        assert result["cluster_count"] == 1
        assert result["clustered_articles"] == 2

    def test_no_clusters_when_all_dissimilar(self, clusterer):
        embeddings = [[1.0, 0.0], [0.0, 1.0]]
        result = clusterer._simple_clustering_fallback([{"id": "0"}, {"id": "1"}], embeddings)
        assert result["cluster_count"] == 0

    def test_skips_empty_embeddings(self, clusterer):
        embeddings = [[], [1.0, 0.0]]
        result = clusterer._simple_clustering_fallback([{"id": "0"}, {"id": "1"}], embeddings)
        assert result["cluster_count"] == 0
