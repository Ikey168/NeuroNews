"""
Extra focused tests for src/nlp/optimized_nlp_pipeline.py.

These target orchestration, caching, batching and operation-routing logic that
the existing test_nlp_optimization.py suite leaves uncovered. All heavy
analyzers/models are mocked so no real transformer/embedder model is loaded.
"""

import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
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


# --------------------------------------------------------------------------
# CacheManager
# --------------------------------------------------------------------------
class TestCacheManager:
    def test_generate_cache_key_deterministic_and_unique(self):
        cm = mod.CacheManager(make_config())
        k1 = cm._generate_cache_key("hello", "m1", "sentiment")
        k2 = cm._generate_cache_key("hello", "m1", "sentiment")
        k3 = cm._generate_cache_key("hello", "m1", "embedding")
        assert k1 == k2
        assert k1 != k3
        assert len(k1) == 64  # sha256 hexdigest

    @pytest.mark.asyncio
    async def test_set_then_get_local_cache_roundtrip(self):
        cm = mod.CacheManager(make_config())
        payload = {"label": "POSITIVE", "score": 0.9}
        assert await cm.set("k", payload) is True
        assert await cm.get("k") == payload
        stats = cm.get_stats()
        assert stats["hits"] == 1
        assert stats["size"] == 1
        assert stats["redis_connected"] is False

    @pytest.mark.asyncio
    async def test_get_miss_increments_misses(self):
        cm = mod.CacheManager(make_config())
        assert await cm.get("nope") is None
        assert cm.get_stats()["misses"] == 1
        assert cm.get_stats()["hit_rate"] == 0

    @pytest.mark.asyncio
    async def test_local_cache_expiry_removes_entry(self):
        cm = mod.CacheManager(make_config(cache_ttl=10))
        # Insert an already-expired entry directly.
        cm.local_cache["old"] = ("value", time.time() - 100)
        result = await cm.get("old")
        assert result is None
        assert "old" not in cm.local_cache
        assert cm.cache_stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_redis_path_get_and_set(self):
        cm = mod.CacheManager(make_config())
        fake_redis = MagicMock()
        # pickled value so get() can unpickle it
        import pickle

        fake_redis.get.return_value = pickle.dumps({"x": 1})
        cm.redis_client = fake_redis

        got = await cm.get("rk")
        assert got == {"x": 1}
        assert cm.cache_stats["hits"] == 1

        await cm.set("rk", {"y": 2})
        fake_redis.setex.assert_called_once()
        # ttl arg should be cache_ttl
        assert fake_redis.setex.call_args[0][1] == cm.config.cache_ttl

    @pytest.mark.asyncio
    async def test_get_handles_redis_exception(self):
        cm = mod.CacheManager(make_config())
        fake_redis = MagicMock()
        fake_redis.get.side_effect = RuntimeError("boom")
        cm.redis_client = fake_redis
        result = await cm.get("k")
        assert result is None
        assert cm.cache_stats["misses"] == 1

    @pytest.mark.asyncio
    async def test_local_cache_eviction_when_over_limit(self):
        cm = mod.CacheManager(make_config())
        # Prefill > 1000 entries with old timestamps; newest set should evict oldest.
        now = time.time()
        for i in range(1001):
            cm.local_cache["key_%d" % i] = (i, now - (2000 - i))
        await cm.set("new_key", "v")
        # oldest (key_0) should have been evicted
        assert "key_0" not in cm.local_cache
        assert cm.cache_stats["evictions"] == 1

    def test_hit_rate_computation(self):
        cm = mod.CacheManager(make_config())
        cm.cache_stats["hits"] = 3
        cm.cache_stats["misses"] = 1
        assert cm.get_stats()["hit_rate"] == 0.75


# --------------------------------------------------------------------------
# ModelManager
# --------------------------------------------------------------------------
class TestModelManager:
    def test_device_cpu_when_gpu_disabled(self):
        mm = mod.ModelManager(make_config(use_gpu_if_available=False))
        assert mm.device == "cpu"

    def test_device_cuda_selected_when_available(self):
        cfg = make_config(use_gpu_if_available=True)
        with patch.object(mod, "TORCH_AVAILABLE", True), patch.object(
            mod, "torch"
        ) as fake_torch:
            fake_torch.cuda.is_available.return_value = True
            mm = mod.ModelManager(cfg)
            assert mm.device == "cuda"

    def test_device_mps_selected_when_available(self):
        cfg = make_config(use_gpu_if_available=True)
        with patch.object(mod, "TORCH_AVAILABLE", True), patch.object(
            mod, "torch"
        ) as fake_torch:
            fake_torch.cuda.is_available.return_value = False
            fake_torch.backends.mps.is_available.return_value = True
            mm = mod.ModelManager(cfg)
            assert mm.device == "mps"

    def test_get_model_loads_via_pipeline_and_caches(self):
        mm = mod.ModelManager(make_config())
        fake_pipeline_obj = MagicMock()
        fake_pipeline_obj.model = MagicMock(spec=[])  # no "hal" attribute
        with patch.object(mod, "TRANSFORMERS_AVAILABLE", True), patch.object(
            mod, "pipeline", return_value=fake_pipeline_obj
        ) as fake_pipeline:
            result = mm.get_model("some-model", "sentiment-analysis")
            assert result is fake_pipeline_obj
            fake_pipeline.assert_called_once()
            # cached in models dict
            assert "some-model:sentiment-analysis" in mm.models

    def test_get_model_raises_when_transformers_unavailable(self):
        mm = mod.ModelManager(make_config())
        with patch.object(mod, "TRANSFORMERS_AVAILABLE", False):
            with pytest.raises(RuntimeError):
                # use a distinct model/task to bypass lru_cache from other tests
                mm.get_model("unavailable-model", "task-x")

    def test_clear_unused_models_removes_least_used(self):
        mm = mod.ModelManager(make_config(model_cache_size=1))
        mm.models = {"a": object(), "b": object()}
        mm.model_stats = {"a": 5, "b": 1}
        mm.clear_unused_models()
        # least used "b" removed
        assert "b" not in mm.models
        assert "a" in mm.models

    def test_clear_unused_models_noop_under_limit(self):
        mm = mod.ModelManager(make_config(model_cache_size=5))
        mm.models = {"a": object()}
        mm.model_stats = {"a": 1}
        mm.clear_unused_models()
        assert "a" in mm.models


# --------------------------------------------------------------------------
# MemoryManager
# --------------------------------------------------------------------------
class TestMemoryManager:
    def test_check_memory_pressure_triggers_gc(self):
        mgr = mod.MemoryManager(make_config(max_memory_usage_mb=100.0, gc_threshold=0.5))
        # Force high reported usage
        with patch.object(mgr, "get_memory_usage_mb", return_value=90.0):
            triggered = mgr.check_memory_pressure()
        assert triggered is True
        assert mgr.memory_stats["gc_triggered"] == 1
        assert mgr.memory_stats["memory_warnings"] == 1
        assert mgr.memory_stats["peak_usage"] == 90.0

    def test_check_memory_pressure_no_trigger(self):
        mgr = mod.MemoryManager(make_config(max_memory_usage_mb=10000.0, gc_threshold=0.9))
        with patch.object(mgr, "get_memory_usage_mb", return_value=10.0):
            assert mgr.check_memory_pressure() is False
        assert mgr.memory_stats["gc_triggered"] == 0


# --------------------------------------------------------------------------
# OptimizedNLPPipeline batching / routing
# --------------------------------------------------------------------------
class TestAdaptiveBatching:
    def test_fixed_batches_when_adaptive_disabled(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=False, batch_size=3))
        pipe.current_batch_size = 3
        articles = [{"id": i, "content": "x"} for i in range(7)]
        batches = pipe._create_adaptive_batches(articles)
        assert [len(b) for b in batches] == [3, 3, 1]

    def test_adaptive_batches_split_on_complexity(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=True))
        pipe.current_batch_size = 1  # threshold = 1000
        articles = [
            {"id": 0, "content": "a" * 600, "title": ""},
            {"id": 1, "content": "b" * 600, "title": ""},
            {"id": 2, "content": "c" * 600, "title": ""},
        ]
        batches = pipe._create_adaptive_batches(articles)
        # each article ~600 chars; 2 in one batch exceeds 1000 -> splits
        assert len(batches) >= 2
        assert sum(len(b) for b in batches) == 3

    def test_update_batch_size_increases_on_high_throughput(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=True, max_batch_size=64))
        pipe.current_batch_size = 8
        for _ in range(3):
            pipe._update_batch_size_performance(throughput=100.0, processing_time=0.1)
        assert pipe.current_batch_size > 8

    def test_update_batch_size_decreases_on_low_throughput(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=True))
        pipe.current_batch_size = 32
        for _ in range(3):
            pipe._update_batch_size_performance(throughput=1.0, processing_time=5.0)
        assert pipe.current_batch_size < 32

    def test_update_batch_size_noop_when_disabled(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=False))
        pipe.current_batch_size = 10
        pipe._update_batch_size_performance(1000.0, 0.01)
        assert pipe.current_batch_size == 10
        assert pipe.performance_history == []

    def test_performance_history_trimmed_to_10(self):
        pipe = mod.OptimizedNLPPipeline(make_config(adaptive_batching=True))
        for _ in range(15):
            pipe._update_batch_size_performance(30.0, 1.0)
        assert len(pipe.performance_history) == 10


class TestOperationBatches:
    @pytest.fixture
    def pipe(self):
        return mod.OptimizedNLPPipeline(make_config())

    @pytest.mark.asyncio
    async def test_keywords_batch(self, pipe):
        batch = [{"id": 1, "content": "elephant wonderful technology innovation tiny"}]
        results = await pipe._process_keywords_batch(batch)
        assert results[0]["processing_method"] == "optimized_batch"
        assert results[0]["keyword_count"] == len(results[0]["keywords"])
        # only words longer than 5 chars
        assert "tiny" not in results[0]["keywords"]
        assert "elephant" in results[0]["keywords"]

    @pytest.mark.asyncio
    async def test_summary_batch(self, pipe):
        content = "First sentence. Second sentence. Third sentence. Fourth ignored."
        batch = [{"id": 1, "content": content}]
        results = await pipe._process_summary_batch(batch)
        r = results[0]
        assert "Fourth" not in r["summary"]
        assert r["summary_length"] == len(r["summary"])
        assert 0 < r["compression_ratio"] <= 1

    @pytest.mark.asyncio
    async def test_summary_batch_empty_content(self, pipe):
        results = await pipe._process_summary_batch([{"id": 1, "content": ""}])
        assert results[0]["compression_ratio"] == 0

    @pytest.mark.asyncio
    async def test_ner_batch(self, pipe):
        results = await pipe._process_ner_batch([{"id": 1, "content": "text"}])
        assert results[0]["entity_count"] == 0
        assert results[0]["entities"] == []

    @pytest.mark.asyncio
    async def test_operation_router_unknown_operation(self, pipe):
        batch = [{"id": 1, "content": "x"}, {"id": 2, "content": "y"}]
        results = await pipe._process_operation_batch(batch, "bogus")
        assert len(results) == 2
        assert all("error" in r for r in results)

    @pytest.mark.asyncio
    async def test_operation_router_dispatches_keywords(self, pipe):
        batch = [{"id": 1, "content": "wonderful technology"}]
        results = await pipe._process_operation_batch(batch, "keywords")
        assert "keywords" in results[0]

    @pytest.mark.asyncio
    async def test_run_sentiment_inference_maps_output(self, pipe):
        model = MagicMock(return_value=[{"label": "POSITIVE", "score": 0.99}])
        out = pipe._run_sentiment_inference(model, ["text"])
        assert out[0]["label"] == "POSITIVE"
        assert out[0]["confidence"] == 0.99
        assert out[0]["model"] == "distilbert-sentiment"

    @pytest.mark.asyncio
    async def test_run_sentiment_inference_error(self, pipe):
        model = MagicMock(side_effect=ValueError("bad"))
        out = pipe._run_sentiment_inference(model, ["a", "b"])
        assert len(out) == 2
        assert all("error" in r for r in out)

    @pytest.mark.asyncio
    async def test_sentiment_batch_uses_model_and_caches(self, pipe):
        fake_model = MagicMock()
        # model not actually called (we patch inference); just must be returned
        pipe.model_manager.get_model = MagicMock(return_value=fake_model)
        with patch.object(
            pipe,
            "_run_sentiment_inference",
            return_value=[{"label": "NEGATIVE", "confidence": 0.7, "model": "m"}],
        ):
            batch = [{"id": 1, "content": "some news content"}]
            results = await pipe._process_sentiment_batch(batch)
        assert results[0]["label"] == "NEGATIVE"
        assert pipe.stats["cache_misses"] == 1
        # second call should hit cache
        with patch.object(pipe, "_run_sentiment_inference") as never:
            results2 = await pipe._process_sentiment_batch(batch)
            never.assert_not_called()
        assert results2[0]["label"] == "NEGATIVE"
        assert pipe.stats["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_embedding_batch_importerror_fallback(self, pipe):
        # Force ImportError inside _process_embedding_batch
        with patch.dict(sys.modules, {"nlp.article_embedder": None}):
            with patch(
                "builtins.__import__", side_effect=ImportError("no embedder")
            ):
                results = await pipe._process_embedding_batch(
                    [{"id": 1, "content": "x"}]
                )
        assert results[0]["error"] == "Simple embedding"
        assert len(results[0]["embedding"]) == 384


# --------------------------------------------------------------------------
# Full async processing flow
# --------------------------------------------------------------------------
class TestProcessArticlesAsync:
    @pytest.mark.asyncio
    async def test_process_articles_keywords_end_to_end(self):
        pipe = mod.OptimizedNLPPipeline(make_config(batch_size=2, adaptive_batching=False))
        pipe.current_batch_size = 2
        articles = [
            {"id": "a%d" % i, "title": "T", "content": "wonderful technology innovation"}
            for i in range(4)
        ]
        try:
            result = await pipe.process_articles_async(articles, operations=["keywords"])
            assert result["articles_processed"] == 4
            assert len(result["results"]) == 4
            assert result["processing_time"] >= 0
            assert pipe.stats["articles_processed"] == 4
            assert pipe.stats["batch_count"] == 2
            for r in result["results"]:
                assert "keywords" in r
                assert "article_id" in r
            assert "cache_stats" in result
            assert "memory_stats" in result
        finally:
            await pipe.cleanup()

    @pytest.mark.asyncio
    async def test_process_articles_default_operations(self):
        pipe = mod.OptimizedNLPPipeline(make_config())
        # Replace sentiment + embedding sub-processors so no models load.
        pipe._process_sentiment_batch = AsyncMock(
            side_effect=lambda b: [{"label": "POSITIVE"} for _ in b]
        )
        pipe._process_embedding_batch = AsyncMock(
            side_effect=lambda b: [{"embedding": [0.1]} for _ in b]
        )
        articles = [{"id": "x", "title": "t", "content": "hello world"}]
        try:
            result = await pipe.process_articles_async(articles)  # default ops
            assert len(result["results"]) == 1
            assert "sentiment" in result["results"][0]
            assert "embedding" in result["results"][0]
        finally:
            await pipe.cleanup()

    @pytest.mark.asyncio
    async def test_get_performance_stats_structure(self):
        pipe = mod.OptimizedNLPPipeline(make_config())
        stats = pipe.get_performance_stats()
        assert set(
            ["pipeline_stats", "cache_stats", "memory_stats", "current_batch_size",
             "device", "models_loaded"]
        ).issubset(stats.keys())
        assert stats["device"] == "cpu"


# --------------------------------------------------------------------------
# Factory functions
# --------------------------------------------------------------------------
class TestFactories:
    def test_create_optimized(self):
        p = mod.create_optimized_nlp_pipeline(max_threads=3, enable_cache=False, enable_gpu=False)
        assert p.config.max_worker_threads == 3
        assert p.config.enable_redis_cache is False
        assert p.config.use_gpu_if_available is False

    def test_create_high_performance(self):
        p = mod.create_high_performance_nlp_pipeline()
        assert p.config.max_worker_threads == 16
        assert p.config.batch_size == 64

    def test_create_memory_optimized(self):
        p = mod.create_memory_optimized_nlp_pipeline(max_memory_mb=128.0)
        assert p.config.max_memory_usage_mb == 128.0
        assert p.config.model_cache_size == 1
