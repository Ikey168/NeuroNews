"""Coverage tests for src/nlp/optimized_nlp_pipeline.py.

Complements test_optimized_nlp_pipeline_extra.py by driving the remaining
uncovered branches:

* Redis connection success (ping) in ``CacheManager``
* ``CacheManager.set`` error handling
* ``ModelManager.get_model`` cached-return path and FP16 quantization branch
* the CUDA ``empty_cache`` branches (clear_unused_models, memory pressure, cleanup)
* operation routing to the NER and summary sub-processors
* the embedding success path (mocked embedder)
* batch-level and pipeline-level exception aggregation

All Redis/torch/transformers/embedder objects are mocked; no real model loads.
"""

import os
import sys

# Warm up torch before coverage's C tracer (nlp package import pulls torch in).
try:  # pragma: no cover - defensive
    import torch  # noqa: F401
except Exception:  # pragma: no cover
    pass

import asyncio  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.optimized_nlp_pipeline as mod  # noqa: E402


def make_config(**kwargs):
    base = dict(
        max_worker_threads=2,
        max_process_workers=1,
        batch_size=4,
        max_batch_size=8,
        enable_redis_cache=False,
        use_gpu_if_available=False,
        max_memory_usage_mb=4096.0,
        cache_ttl=60,
    )
    base.update(kwargs)
    return mod.NLPConfig(**base)


class TestCacheManagerRedis:
    def test_redis_connection_success_pings(self):
        fake_redis_mod = MagicMock()
        client = MagicMock()
        fake_redis_mod.Redis.return_value = client
        with patch.object(mod, "REDIS_AVAILABLE", True), patch.object(
            mod, "redis", fake_redis_mod
        ):
            cm = mod.CacheManager(make_config(enable_redis_cache=True))
        client.ping.assert_called_once()
        assert cm.redis_client is client

    def test_redis_connection_failure_falls_back_to_local(self):
        fake_redis_mod = MagicMock()
        client = MagicMock()
        client.ping.side_effect = Exception("no redis")
        fake_redis_mod.Redis.return_value = client
        with patch.object(mod, "REDIS_AVAILABLE", True), patch.object(
            mod, "redis", fake_redis_mod
        ):
            cm = mod.CacheManager(make_config(enable_redis_cache=True))
        assert cm.redis_client is None

    @pytest.mark.asyncio
    async def test_set_error_returns_false(self):
        cm = mod.CacheManager(make_config())
        # pickle.dumps raising simulates a serialization failure
        with patch.object(mod, "pickle") as fake_pickle:
            fake_pickle.dumps.side_effect = TypeError("cannot pickle")
            ok = await cm.set("k", object())
        assert ok is False


class TestModelManagerBranches:
    def test_get_model_returns_cached_within_lock(self):
        mm = mod.ModelManager(make_config())
        sentinel = MagicMock()
        # pre-populate cache so the lock branch returns immediately
        mm.models["cached-model:sentiment-analysis"] = sentinel
        result = mm.get_model("cached-model", "sentiment-analysis")
        assert result is sentinel
        # stats incremented for a cache hit
        assert mm.model_stats["cached-model:sentiment-analysis"] == 1

    def test_get_model_applies_fp16_quantization_on_cuda(self):
        cfg = make_config(use_gpu_if_available=True, enable_model_quantization=True)
        with patch.object(mod, "TORCH_AVAILABLE", True), patch.object(
            mod, "torch"
        ) as t:
            t.cuda.is_available.return_value = True
            mm = mod.ModelManager(cfg)
            assert mm.device == "cuda"

            pipe_obj = MagicMock()
            # model must expose a "hal" attribute for the quantization branch
            original_model = MagicMock()
            pipe_obj.model = original_model
            halved = MagicMock()
            original_model.half.return_value = halved

            with patch.object(mod, "TRANSFORMERS_AVAILABLE", True), patch.object(
                mod, "pipeline", return_value=pipe_obj
            ):
                result = mm.get_model("fp16-model", "quant-task")
        # The FP16 branch reassigns model = model.half()
        original_model.half.assert_called_once()
        assert result.model is halved

    def test_clear_unused_models_cuda_empty_cache(self):
        with patch.object(mod, "TORCH_AVAILABLE", True), patch.object(mod, "torch") as t:
            t.cuda.is_available.return_value = True
            mm = mod.ModelManager(make_config(model_cache_size=1, use_gpu_if_available=False))
            mm.models = {"a": object(), "b": object()}
            mm.model_stats = {"a": 5, "b": 1}
            mm.clear_unused_models()
            t.cuda.empty_cache.assert_called_once()
        assert "b" not in mm.models


class TestMemoryAndCleanupCuda:
    def test_memory_pressure_cuda_empty_cache(self):
        with patch.object(mod, "TORCH_AVAILABLE", True), patch.object(mod, "torch") as t:
            t.cuda.is_available.return_value = True
            mgr = mod.MemoryManager(make_config(max_memory_usage_mb=100.0, gc_threshold=0.5))
            with patch.object(mgr, "get_memory_usage_mb", return_value=90.0):
                assert mgr.check_memory_pressure() is True
            t.cuda.empty_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_cuda_empty_cache(self):
        with patch.object(mod, "TORCH_AVAILABLE", True), patch.object(mod, "torch") as t:
            t.cuda.is_available.return_value = False  # keep device cpu during init
            pipe = mod.OptimizedNLPPipeline(make_config())
            t.cuda.is_available.return_value = True  # now trigger cleanup branch
            await pipe.cleanup()
            t.cuda.empty_cache.assert_called_once()


class TestOperationRouting:
    @pytest.fixture
    def pipe(self):
        return mod.OptimizedNLPPipeline(make_config())

    @pytest.mark.asyncio
    async def test_router_dispatches_ner(self, pipe):
        results = await pipe._process_operation_batch(
            [{"id": 1, "content": "text"}], "ner"
        )
        assert results[0]["processing_method"] == "optimized_batch"
        assert results[0]["entity_count"] == 0

    @pytest.mark.asyncio
    async def test_router_dispatches_summary(self, pipe):
        content = "One sentence. Two sentence. Three sentence."
        results = await pipe._process_operation_batch(
            [{"id": 1, "content": content}], "summary"
        )
        assert "summary" in results[0]

    @pytest.mark.asyncio
    async def test_router_dispatches_sentiment(self, pipe):
        with patch.object(
            pipe,
            "_process_sentiment_batch",
            new=AsyncMock(return_value=[{"label": "POSITIVE"}]),
        ):
            results = await pipe._process_operation_batch(
                [{"id": 1, "content": "x"}], "sentiment"
            )
        assert results[0]["label"] == "POSITIVE"

    @pytest.mark.asyncio
    async def test_router_dispatches_embedding(self, pipe):
        with patch.object(
            pipe,
            "_process_embedding_batch",
            new=AsyncMock(return_value=[{"embedding": [0.1]}]),
        ):
            results = await pipe._process_operation_batch(
                [{"id": 1, "content": "x"}], "embedding"
            )
        assert results[0]["embedding"] == [0.1]

    @pytest.mark.asyncio
    async def test_operation_batch_exception_wraps_error(self, pipe):
        with patch.object(
            pipe, "_process_ner_batch", new=AsyncMock(side_effect=ValueError("nerr"))
        ):
            results = await pipe._process_operation_batch(
                [{"id": 1}, {"id": 2}], "ner"
            )
        assert len(results) == 2
        assert all("error" in r for r in results)


class TestEmbeddingSuccess:
    @pytest.mark.asyncio
    async def test_embedding_batch_success_path(self):
        pipe = mod.OptimizedNLPPipeline(make_config())
        fake_embedder = MagicMock()
        fake_embedder.generate_embeddings_batch = AsyncMock(
            return_value=[{"embedding": [1.0, 2.0], "error": None}]
        )
        fake_module = MagicMock()
        fake_module.ArticleEmbedder = MagicMock(return_value=fake_embedder)
        # Inject a fake nlp.article_embedder module so the relative import resolves.
        with patch.dict(sys.modules, {"nlp.article_embedder": fake_module}):
            results = await pipe._process_embedding_batch(
                [{"id": 1, "content": "some text"}]
            )
        assert results[0]["embedding"] == [1.0, 2.0]
        fake_embedder.generate_embeddings_batch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_embedding_batch_generic_exception(self):
        pipe = mod.OptimizedNLPPipeline(make_config())
        fake_embedder = MagicMock()
        fake_embedder.generate_embeddings_batch = AsyncMock(
            side_effect=RuntimeError("embed boom")
        )
        fake_module = MagicMock()
        fake_module.ArticleEmbedder = MagicMock(return_value=fake_embedder)
        with patch.dict(sys.modules, {"nlp.article_embedder": fake_module}):
            results = await pipe._process_embedding_batch([{"id": 1, "content": "x"}])
        assert results[0]["error"] == "embed boom"


class TestBatchAndPipelineErrors:
    @pytest.mark.asyncio
    async def test_process_batch_async_swallows_and_returns_empty(self):
        pipe = mod.OptimizedNLPPipeline(make_config())
        sem = asyncio.Semaphore(1)
        # Force the batch to raise inside _process_operation_batch.
        with patch.object(
            pipe,
            "_process_operation_batch",
            new=AsyncMock(side_effect=RuntimeError("batch boom")),
        ):
            out = await pipe._process_batch_async(
                sem, [{"id": 1, "content": "x"}], ["keywords"], 0
            )
        assert out == []
        assert pipe.stats["errors"] == 1

    @pytest.mark.asyncio
    async def test_process_articles_async_aggregates_batch_exception(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=False, batch_size=1))
        pipe.current_batch_size = 1
        articles = [{"id": "a", "content": "x"}, {"id": "b", "content": "y"}]

        # Return an Exception object for one batch to hit the aggregation branch.
        real_gather = asyncio.gather

        async def fake_batch(*a, **k):
            return RuntimeError("boom")  # not raised, returned

        # Patch the per-batch coroutine so gather collects an Exception result.
        with patch.object(
            pipe, "_process_batch_async", side_effect=RuntimeError("boom")
        ):
            # gather(return_exceptions=True) captures the raised error as a result
            result = await pipe.process_articles_async(articles, operations=["keywords"])
        assert pipe.stats["errors"] >= 1
        assert result["articles_processed"] == 0
        await pipe.cleanup()

    @pytest.mark.asyncio
    async def test_process_articles_async_reraises_on_setup_error(self):
        pipe = mod.OptimizedNLPPipeline(make_config())
        with patch.object(
            pipe, "_create_adaptive_batches", side_effect=ValueError("setup fail")
        ):
            with pytest.raises(ValueError, match="setup fail"):
                await pipe.process_articles_async([{"id": 1, "content": "x"}])
        assert pipe.stats["errors"] >= 1
        await pipe.cleanup()
