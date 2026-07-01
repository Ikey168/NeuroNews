"""Coverage tests for src/nlp/nlp_integration.py.

The heavy ``OptimizedNLPPipeline`` is replaced by a MagicMock so constructing the
wrapper classes is cheap and we can drive each code path via AsyncMock returns.
All assertions target real result-shaping / branching logic in the module.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

import src.nlp.nlp_integration as mod


@pytest.fixture(autouse=True)
def light_pipeline(monkeypatch):
    # Avoid constructing the real OptimizedNLPPipeline (loads models, threads).
    monkeypatch.setattr(mod, "OptimizedNLPPipeline", MagicMock())
    yield


# ===========================================================================
# OptimizedArticleEmbedder
# ===========================================================================

class TestArticleEmbedder:
    def test_init_uses_model_name(self):
        emb = mod.OptimizedArticleEmbedder(model_name="my-model")
        assert emb.model_name == "my-model"

    @pytest.mark.asyncio
    async def test_generate_embeddings_success(self):
        emb = mod.OptimizedArticleEmbedder(model_name="m")
        emb.pipeline.process_articles_async = AsyncMock(return_value={
            "results": [
                {"article_id": "a1", "embedding": {"embedding": [0.1, 0.2],
                 "quality_score": 0.8}, "processing_time": 0.5},
            ]
        })
        out = await emb.generate_embeddings_batch([{"id": "a1", "content": "x"}])
        assert out[0]["article_id"] == "a1"
        assert out[0]["embedding"] == [0.1, 0.2]
        assert out[0]["embedding_quality"] == 0.8
        assert out[0]["cached"] is True
        assert out[0]["model"] == "m"

    @pytest.mark.asyncio
    async def test_generate_embeddings_missing_embedding(self):
        emb = mod.OptimizedArticleEmbedder()
        emb.pipeline.process_articles_async = AsyncMock(return_value={
            "results": [{"article_id": "a2", "processing_time": 0.1}]
        })
        out = await emb.generate_embeddings_batch([{"id": "a2"}])
        assert "error" in out[0]
        assert out[0]["error"] == "Embedding generation failed"

    @pytest.mark.asyncio
    async def test_generate_embeddings_fallback_on_error(self):
        emb = mod.OptimizedArticleEmbedder()
        emb.pipeline.process_articles_async = AsyncMock(side_effect=RuntimeError("boom"))
        legacy = MagicMock()
        legacy.generate_embeddings_batch = AsyncMock(return_value=[{"article_id": "a3", "embedding": [1.0]}])
        emb.legacy_embedder = legacy
        out = await emb.generate_embeddings_batch([{"id": "a3"}])
        assert out[0]["fallback"] is True

    @pytest.mark.asyncio
    async def test_generate_embeddings_no_fallback_reraises(self):
        emb = mod.OptimizedArticleEmbedder()
        emb.pipeline.process_articles_async = AsyncMock(side_effect=RuntimeError("boom"))
        emb.legacy_embedder = None
        with pytest.raises(RuntimeError):
            await emb.generate_embeddings_batch([{"id": "a"}])

    @pytest.mark.asyncio
    async def test_fallback_embedding_generation_legacy_error(self):
        emb = mod.OptimizedArticleEmbedder()
        legacy = MagicMock()
        legacy.generate_embeddings_batch = AsyncMock(side_effect=ValueError("legacy fail"))
        emb.legacy_embedder = legacy
        out = await emb._fallback_embedding_generation([{"id": "z"}])
        assert out[0]["error"] == "legacy fail"
        assert out[0]["fallback"] is True


# ===========================================================================
# OptimizedEventClusterer
# ===========================================================================

class TestEventClusterer:
    @pytest.mark.asyncio
    async def test_cluster_with_provided_embeddings_legacy(self):
        clus = mod.OptimizedEventClusterer()
        legacy = MagicMock()
        legacy.cluster_articles_async = AsyncMock(return_value={"clusters": [[0, 1]], "cluster_count": 1})
        clus.legacy_clusterer = legacy
        articles = [{"id": "1"}, {"id": "2"}]
        embeddings = [np.array([1.0, 0.0]), np.array([1.0, 0.0])]
        result = await clus.cluster_articles_async(articles, embeddings)
        assert result["cluster_count"] == 1
        assert result["optimized"] is True
        assert result["articles_count"] == 2
        assert "processing_time" in result

    @pytest.mark.asyncio
    async def test_cluster_generates_embeddings_when_none(self, monkeypatch):
        clus = mod.OptimizedEventClusterer()
        clus.legacy_clusterer = None  # forces simple fallback path

        # Patch the embedder used internally to avoid the real pipeline.
        fake_embedder = MagicMock()
        fake_embedder.generate_embeddings_batch = AsyncMock(return_value=[
            {"embedding": [1.0, 0.0]},
            {"embedding": [1.0, 0.0]},
        ])
        monkeypatch.setattr(mod, "OptimizedArticleEmbedder", lambda config=None: fake_embedder)

        articles = [{"id": "1"}, {"id": "2"}]
        result = await clus.cluster_articles_async(articles, embeddings=None)
        assert result["algorithm"] == "simple_fallback"
        assert result["cluster_count"] == 1  # two identical vectors group together
        assert result["clustered_articles"] == 2

    @pytest.mark.asyncio
    async def test_cluster_reraises_on_error(self, monkeypatch):
        clus = mod.OptimizedEventClusterer()
        clus.legacy_clusterer = None

        def bad_embedder(config=None):
            m = MagicMock()
            m.generate_embeddings_batch = AsyncMock(side_effect=RuntimeError("nope"))
            return m

        monkeypatch.setattr(mod, "OptimizedArticleEmbedder", bad_embedder)
        with pytest.raises(RuntimeError):
            await clus.cluster_articles_async([{"id": "1"}], embeddings=None)

    def test_simple_clustering_fallback_groups_similar(self):
        clus = mod.OptimizedEventClusterer()
        # Two near-identical vectors + one orthogonal.
        embeddings = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
        articles = [{"id": str(i)} for i in range(3)]
        result = clus._simple_clustering_fallback(articles, embeddings)
        assert result["algorithm"] == "simple_fallback"
        assert result["cluster_count"] == 1
        assert result["clustered_articles"] == 2

    def test_simple_clustering_fallback_skips_empty_embeddings(self):
        clus = mod.OptimizedEventClusterer()
        embeddings = [[], [], []]  # all empty -> no clusters
        articles = [{"id": str(i)} for i in range(3)]
        result = clus._simple_clustering_fallback(articles, embeddings)
        assert result["cluster_count"] == 0
        assert result["clustered_articles"] == 0


# ===========================================================================
# IntegratedNLPProcessor
# ===========================================================================

@pytest.fixture
def processor():
    return mod.IntegratedNLPProcessor()


class TestIntegratedProcessor:
    def test_init_state(self, processor):
        assert processor.total_stats["sessions"] == 0
        assert processor.total_stats["articles_processed"] == 0

    @pytest.mark.asyncio
    async def test_process_comprehensive_individual_ops(self, processor):
        processor.pipeline.process_articles_async = AsyncMock(return_value={
            "results": [{"article_id": "1", "sentiment": {"label": "POS"}}],
            "batch_count": 1,
        })
        processor.pipeline.get_performance_stats = MagicMock(return_value={
            "cache_stats": {"hit_rate": 0.5},
            "memory_stats": {"current_usage_mb": 10},
            "pipeline_stats": {"batch_count": 2},
        })
        result = await processor.process_articles_comprehensive(
            [{"id": "1", "content": "x"}], operations=["sentiment"]
        )
        assert result["articles"] == [{"article_id": "1", "sentiment": {"label": "POS"}}]
        assert result["clustering"] is None
        pm = result["performance_metrics"]
        assert pm["cache_hit_rate"] == 0.5
        assert pm["memory_usage_mb"] == 10
        assert pm["batch_count"] == 2
        assert processor.total_stats["sessions"] == 1
        assert processor.total_stats["articles_processed"] == 1

    @pytest.mark.asyncio
    async def test_process_comprehensive_default_operations(self, processor):
        processor.pipeline.process_articles_async = AsyncMock(return_value={"results": []})
        processor.pipeline.get_performance_stats = MagicMock(return_value={"cache_stats": {}})
        result = await processor.process_articles_comprehensive([{"id": "1", "content": "x"}])
        # Defaults are sentiment/embedding/keywords -> clustering stays None.
        assert result["clustering"] is None
        assert "performance_metrics" in result

    @pytest.mark.asyncio
    async def test_process_comprehensive_with_clustering_regenerates(self, processor):
        # No per-result embeddings -> _process_clustering regenerates them
        # (all-None list, so `None in embeddings` is a safe membership test).
        processor.pipeline.process_articles_async = AsyncMock(return_value={
            # 'embedding' op ran but produced no vector -> None placeholders.
            "results": [{"article_id": "1"}, {"article_id": "2"}],
        })
        processor.pipeline.get_performance_stats = MagicMock(return_value={"cache_stats": {}})
        processor.article_embedder.generate_embeddings_batch = AsyncMock(
            return_value=[{"embedding": [1.0, 0.0]}, {"embedding": [1.0, 0.0]}]
        )
        processor.event_clusterer.cluster_articles_async = AsyncMock(
            return_value={"cluster_count": 1, "clusters": [[0, 1]]}
        )
        result = await processor.process_articles_comprehensive(
            [{"id": "1"}, {"id": "2"}], operations=["embedding", "clustering"]
        )
        assert result["clustering"]["cluster_count"] == 1
        processor.article_embedder.generate_embeddings_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_comprehensive_error_increments_errors(self, processor):
        processor.pipeline.process_articles_async = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError):
            await processor.process_articles_comprehensive(
                [{"id": "1"}], operations=["sentiment"]
            )
        assert processor.total_stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_process_clustering_missing_embeddings_regenerates(self, processor):
        # processed_results lacks embeddings -> triggers regeneration path.
        processor.article_embedder.generate_embeddings_batch = AsyncMock(
            return_value=[{"embedding": [1.0, 0.0]}, {"embedding": [1.0, 0.0]}]
        )
        processor.event_clusterer.cluster_articles_async = AsyncMock(
            return_value={"cluster_count": 1}
        )
        result = await processor._process_clustering(
            [{"id": "1"}, {"id": "2"}], [{"article_id": "1"}, {"article_id": "2"}]
        )
        assert result["cluster_count"] == 1
        processor.article_embedder.generate_embeddings_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_process_clustering_all_embeddings_present_hits_numpy_ambiguity(self, processor):
        # When every processed result carries an embedding, the list is populated
        # with numpy arrays. The module then evaluates `None in embeddings`, which
        # numpy makes ambiguous -> ValueError -> caught -> empty error result.
        processor.event_clusterer.cluster_articles_async = AsyncMock(
            return_value={"cluster_count": 2}
        )
        processed = [
            {"embedding": {"embedding": [1.0, 0.0]}},
            {"embedding": {"embedding": [0.0, 1.0]}},
        ]
        result = await processor._process_clustering([{"id": "1"}, {"id": "2"}], processed)
        assert result["cluster_count"] == 0
        assert result["clusters"] == []
        assert "error" in result

    @pytest.mark.asyncio
    async def test_process_clustering_error_returns_empty(self, processor):
        processor.event_clusterer.cluster_articles_async = AsyncMock(
            side_effect=RuntimeError("clustering blew up")
        )
        processed = [{"embedding": {"embedding": [1.0]}}]
        result = await processor._process_clustering([{"id": "1"}], processed)
        assert result["clusters"] == []
        assert result["cluster_count"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_analyze_sentiment_optimized_delegates(self, processor):
        processor.sentiment_analyzer.analyze_batch = AsyncMock(return_value=[{"label": "POS"}])
        out = await processor.analyze_sentiment_optimized([{"id": "1"}])
        assert out == [{"label": "POS"}]

    @pytest.mark.asyncio
    async def test_generate_embeddings_optimized_delegates(self, processor):
        processor.article_embedder.generate_embeddings_batch = AsyncMock(return_value=[{"e": 1}])
        out = await processor.generate_embeddings_optimized([{"id": "1"}])
        assert out == [{"e": 1}]

    @pytest.mark.asyncio
    async def test_cluster_events_optimized_delegates(self, processor):
        processor.event_clusterer.cluster_articles_async = AsyncMock(return_value={"cluster_count": 3})
        out = await processor.cluster_events_optimized([{"id": "1"}])
        assert out["cluster_count"] == 3

    def test_get_comprehensive_stats(self, processor):
        processor.pipeline.get_performance_stats = MagicMock(return_value={"perf": 1})
        processor.sentiment_analyzer.get_performance_stats = MagicMock(return_value={"s": 1})
        stats = processor.get_comprehensive_stats()
        assert stats["optimization_enabled"] is True
        assert "fallback_available" in stats
        assert stats["pipeline_performance"] == {"perf": 1}
        assert set(stats["fallback_available"]) == {"sentiment", "embedder", "clustering", "ner"}

    @pytest.mark.asyncio
    async def test_cleanup(self, processor):
        processor.pipeline.cleanup = AsyncMock()
        await processor.cleanup()
        processor.pipeline.cleanup.assert_awaited_once()


# ===========================================================================
# Factory functions
# ===========================================================================

class TestFactories:
    def test_high_performance(self):
        p = mod.create_high_performance_nlp_processor()
        assert isinstance(p, mod.IntegratedNLPProcessor)
        assert p.config.batch_size == 64
        assert p.config.max_worker_threads == 16

    def test_balanced(self):
        p = mod.create_balanced_nlp_processor()
        assert isinstance(p, mod.IntegratedNLPProcessor)
        assert p.config.batch_size == 32
        assert p.config.max_worker_threads == 8

    def test_memory_efficient(self):
        p = mod.create_memory_efficient_nlp_processor()
        assert isinstance(p, mod.IntegratedNLPProcessor)
        assert p.config.batch_size == 16
        assert p.config.enable_redis_cache is False
