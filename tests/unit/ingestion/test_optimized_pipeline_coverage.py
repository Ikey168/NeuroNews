"""
Coverage-focused tests for src/ingestion/optimized_pipeline.py.

Drives the async processing paths (batches, single-article enhancement,
validation failures, duplicate skipping, cache clearing, storage backends,
and the performance-report writer) plus the memory-monitor error branch.
Async coroutines are executed via asyncio.run() so the tests are independent
of any asyncio plugin mode configuration.
"""

import asyncio
import json

import pytest

import src.ingestion.optimized_pipeline as op
from src.ingestion.optimized_pipeline import (
    AdaptiveBatchProcessor,
    CircuitBreaker,
    IngestionMetrics,
    MemoryMonitor,
    OptimizationConfig,
    OptimizedIngestionPipeline,
    create_optimized_pipeline,
    create_performance_optimized_pipeline,
    process_articles_optimized,
)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# CircuitBreaker
# --------------------------------------------------------------------------- #

def test_circuit_breaker_success_passthrough():
    cb = CircuitBreaker(failure_threshold=2)
    assert cb.call(lambda x: x + 1, 4) == 5
    assert cb.state == "CLOSED"


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=60.0)

    def boom():
        raise ValueError("fail")

    for _ in range(2):
        with pytest.raises(ValueError):
            cb.call(boom)
    assert cb.state == "OPEN"
    # While OPEN and within recovery timeout, calls are short-circuited.
    with pytest.raises(Exception) as exc:
        cb.call(lambda: "unused")
    assert "OPEN" in str(exc.value)


def test_circuit_breaker_half_open_recovers():
    cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0)

    def boom():
        raise ValueError("fail")

    with pytest.raises(ValueError):
        cb.call(boom)
    assert cb.state == "OPEN"
    # recovery_timeout=0 -> next call transitions to HALF_OPEN then CLOSED.
    assert cb.call(lambda: "ok") == "ok"
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0


# --------------------------------------------------------------------------- #
# AdaptiveBatchProcessor
# --------------------------------------------------------------------------- #

def test_adaptive_batch_needs_min_history():
    proc = AdaptiveBatchProcessor(initial_batch_size=100)
    proc.adjust_batch_size(0.5, 1.0)
    proc.adjust_batch_size(0.5, 1.0)
    # Fewer than 3 data points -> no change.
    assert proc.get_batch_size() == 100


def test_adaptive_batch_grows_on_improvement():
    proc = AdaptiveBatchProcessor(initial_batch_size=100, max_size=1000)
    # Seed poor history, then strong recent scores -> grow.
    proc.adjust_batch_size(10.0, 0.1)
    proc.adjust_batch_size(10.0, 0.1)
    proc.adjust_batch_size(0.1, 1.0)
    proc.adjust_batch_size(0.1, 1.0)
    proc.adjust_batch_size(0.1, 1.0)
    assert proc.get_batch_size() > 100


def test_adaptive_batch_shrinks_on_degradation():
    proc = AdaptiveBatchProcessor(initial_batch_size=100, min_size=10)
    proc.adjust_batch_size(0.1, 1.0)
    proc.adjust_batch_size(0.1, 1.0)
    proc.adjust_batch_size(10.0, 0.1)
    proc.adjust_batch_size(10.0, 0.1)
    proc.adjust_batch_size(10.0, 0.1)
    assert proc.get_batch_size() < 100


def test_adaptive_batch_stable_no_change():
    proc = AdaptiveBatchProcessor(initial_batch_size=100)
    for _ in range(5):
        proc.adjust_batch_size(1.0, 1.0)  # identical scores -> stable
    assert proc.get_batch_size() == 100


# --------------------------------------------------------------------------- #
# IngestionMetrics
# --------------------------------------------------------------------------- #

def test_ingestion_metrics_update_and_summary():
    m = IngestionMetrics()
    m.update_metrics(0.5, True)
    m.update_metrics(0.5, False, "TypeError")
    summary = m.get_summary()
    assert summary["summary"]["total_processed"] == 2
    assert summary["summary"]["successful"] == 1
    assert summary["summary"]["failed"] == 1
    assert summary["errors"]["TypeError"] == 1
    assert m.average_processing_time == 0.5


def _good_article(i=0):
    return {
        "title": f"A sufficiently long headline number {i}",
        "url": f"https://example.com/article-{i}",
        "content": "word " * 60,  # >100 chars, >50 words
        "author": "Jane Doe",
        "published_date": "2024-01-01T00:00:00Z",
    }


@pytest.fixture()
def pipeline():
    # Disable metrics so no background memory thread is spun up during tests.
    cfg = OptimizationConfig(enable_metrics=False, adaptive_batching=True)
    p = OptimizedIngestionPipeline(cfg)
    yield p
    p.cleanup()


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def test_fast_validate_accepts_good_article(pipeline):
    assert _run(pipeline._fast_validate_article(_good_article())) is True


def test_fast_validate_missing_field(pipeline):
    art = _good_article()
    del art["title"]
    assert _run(pipeline._fast_validate_article(art)) is False


def test_fast_validate_content_too_short(pipeline):
    art = _good_article()
    art["content"] = "tiny"
    assert _run(pipeline._fast_validate_article(art)) is False


def test_fast_validate_bad_url_scheme(pipeline):
    art = _good_article()
    art["url"] = "not-a-url"
    assert _run(pipeline._fast_validate_article(art)) is False


def test_fast_validate_title_too_short(pipeline):
    art = _good_article()
    art["title"] = "short"
    # content ok but title < 10 already fails at content stage? title len 5.
    # Ensure content passes so we reach the title check (lines 648-651).
    art["content"] = "word " * 60
    assert _run(pipeline._fast_validate_article(art)) is False


def test_fast_validate_title_too_long(pipeline):
    art = _good_article()
    art["title"] = "x" * 400
    assert _run(pipeline._fast_validate_article(art)) is False


def test_fast_validate_urlparse_exception(pipeline, monkeypatch):
    # Force urlparse to raise so the except branch (645-646) returns False.
    def _boom(_url):
        raise ValueError("bad url parse")

    monkeypatch.setattr(op, "urlparse", _boom)
    assert _run(pipeline._fast_validate_article(_good_article())) is False


# --------------------------------------------------------------------------- #
# Enhancement + quality score
# --------------------------------------------------------------------------- #

def test_enhance_article_adds_metadata(pipeline):
    enhanced = _run(pipeline._enhance_article_async(_good_article(1)))
    assert enhanced["pipeline_version"] == "optimized_v1"
    assert enhanced["word_count"] == 60
    assert enhanced["source_domain"] == "example.com"
    assert enhanced["reading_time"] >= 1
    assert 0.0 <= enhanced["quality_score"] <= 100.0


def test_quality_score_penalties_and_bonuses(pipeline):
    low = pipeline._calculate_quality_score(
        {"content_length": 50, "word_count": 10, "title": "hi"}
    )
    assert low < 100
    high = pipeline._calculate_quality_score(
        {
            "content_length": 1000,
            "word_count": 500,
            "title": "A nice long descriptive title here",
            "author": "someone",
            "published_date": "2024-01-01",
        }
    )
    assert high == 100.0


def test_quality_score_long_content_penalty(pipeline):
    # content_length > 5000 triggers the -10 branch (line 689).
    score = pipeline._calculate_quality_score(
        {"content_length": 6000, "word_count": 500,
         "title": "A nice long descriptive title here"}
    )
    assert score == 90.0


# --------------------------------------------------------------------------- #
# Single-article processing
# --------------------------------------------------------------------------- #

def test_process_single_article_success(pipeline):
    result = _run(pipeline._process_single_article_async(_good_article(2)))
    assert result is not None
    assert result["quality_score"] >= 0
    assert pipeline.metrics.successful_articles == 1


def test_process_single_article_duplicate_skipped(pipeline):
    art = _good_article(3)
    pipeline.url_cache.add(art["url"])
    result = _run(pipeline._process_single_article_async(art))
    assert result is None
    assert pipeline.metrics.skipped_articles == 1


def test_process_single_article_validation_failed(pipeline):
    art = _good_article(4)
    art["content"] = "x"  # too short
    result = _run(pipeline._process_single_article_async(art))
    assert result is None
    assert pipeline.metrics.failed_articles == 1
    assert "validation_failed" in pipeline.metrics.errors_by_type


def test_process_single_article_cache_overflow_clears(pipeline):
    pipeline.config.skip_duplicate_check_after = 1
    # Pre-seed one URL; processing a second pushes len to 2 (> threshold 1),
    # triggering the cache clear branch (lines 606-609).
    pipeline.url_cache.add("https://example.com/preexisting")
    _run(pipeline._process_single_article_async(_good_article(5)))
    assert len(pipeline.url_cache) == 0


def test_process_single_article_enhance_exception(pipeline, monkeypatch):
    async def _boom(_article):
        raise RuntimeError("enhance failed")

    monkeypatch.setattr(pipeline, "_enhance_article_async", _boom)
    result = _run(pipeline._process_single_article_async(_good_article(6)))
    assert result is None
    assert pipeline.metrics.failed_articles == 1
    assert "RuntimeError" in pipeline.metrics.errors_by_type


# --------------------------------------------------------------------------- #
# Batch processing
# --------------------------------------------------------------------------- #

def test_create_adaptive_batches(pipeline):
    articles = [_good_article(i) for i in range(5)]
    batches = pipeline._create_adaptive_batches(articles)
    assert sum(len(b) for b in batches) == 5


def test_create_fixed_batches_when_adaptive_off():
    p = OptimizedIngestionPipeline(
        OptimizationConfig(adaptive_batching=False, batch_size=2, enable_metrics=False)
    )
    try:
        batches = p._create_adaptive_batches([_good_article(i) for i in range(5)])
        assert [len(b) for b in batches] == [2, 2, 1]
    finally:
        p.cleanup()


def test_process_batch_async(pipeline):
    sem = asyncio.Semaphore(5)
    batch = [_good_article(i) for i in range(3)]
    results = _run(pipeline._process_batch_async(sem, batch, 0, None))
    assert len(results) == 3


def test_process_batch_async_logs_failed_article(pipeline, monkeypatch):
    # A coroutine that raises -> gather returns the Exception -> warning
    # branch at lines 543-548 runs (result is an Exception, not a dict).
    async def _raise(_article):
        raise RuntimeError("single failed")

    monkeypatch.setattr(pipeline, "_process_single_article_async", _raise)
    sem = asyncio.Semaphore(5)
    results = _run(pipeline._process_batch_async(sem, [_good_article()], 3, None))
    assert results == []  # nothing succeeded


def test_process_batch_async_with_storage_backend(pipeline):
    stored = {}

    async def backend(articles):
        stored["count"] = len(articles)

    sem = asyncio.Semaphore(5)
    batch = [_good_article(i) for i in range(2)]
    _run(pipeline._process_batch_async(sem, batch, 1, [backend]))
    assert stored["count"] == 2


def test_process_batch_async_critical_error(pipeline, monkeypatch):
    # Make gather raise inside the batch body -> critical error path (570-576).
    async def _boom(_article):
        raise RuntimeError("x")

    def _bad_create_task(coro):
        coro.close()
        raise RuntimeError("cannot schedule")

    monkeypatch.setattr(pipeline, "_process_single_article_async", _boom)
    monkeypatch.setattr(op.asyncio, "create_task", _bad_create_task)
    sem = asyncio.Semaphore(5)
    result = _run(pipeline._process_batch_async(sem, [_good_article()], 9, None))
    assert result == []
    assert "batch_critical" in pipeline.metrics.errors_by_type


# --------------------------------------------------------------------------- #
# Storage backends
# --------------------------------------------------------------------------- #

def test_execute_storage_backend_async(pipeline):
    async def backend(articles):
        return len(articles)

    out = _run(pipeline._execute_storage_backend(backend, [1, 2, 3]))
    assert out == 3


def test_execute_storage_backend_sync_in_threadpool(pipeline):
    def backend(articles):
        return "sync-ok:" + str(len(articles))

    out = _run(pipeline._execute_storage_backend(backend, [1, 2]))
    assert out == "sync-ok:2"


def test_execute_storage_backend_raises(pipeline):
    async def backend(articles):
        raise ValueError("store fail")

    with pytest.raises(ValueError):
        _run(pipeline._execute_storage_backend(backend, []))


def test_store_batch_async_records_backend_failure(pipeline):
    async def ok_backend(articles):
        return "ok"

    async def bad_backend(articles):
        raise RuntimeError("nope")

    _run(pipeline._store_batch_async([_good_article()], [ok_backend, bad_backend]))
    assert "storage_failed" in pipeline.metrics.errors_by_type
    assert pipeline.metrics.storage_time >= 0


def test_store_batch_async_critical_error(pipeline, monkeypatch):
    def _bad_create_task(coro):
        coro.close()
        raise RuntimeError("scheduling blew up")

    monkeypatch.setattr(op.asyncio, "create_task", _bad_create_task)

    async def backend(articles):
        return None

    _run(pipeline._store_batch_async([_good_article()], [backend]))
    assert "storage_critical" in pipeline.metrics.errors_by_type


# --------------------------------------------------------------------------- #
# Full pipeline run + report
# --------------------------------------------------------------------------- #

def test_process_articles_async_end_to_end(pipeline):
    articles = [_good_article(i) for i in range(6)]
    result = _run(pipeline.process_articles_async(articles))
    assert len(result["processed_articles"]) == 6
    assert result["processing_time"] >= 0
    assert "metrics" in result
    assert "memory_stats" in result


def test_process_articles_async_batch_exception_aggregation(pipeline, monkeypatch):
    # Make one batch task raise so the Exception branch (429-431) runs.
    original = pipeline._process_batch_async
    state = {"first": True}

    async def flaky(sem, batch, batch_id, backends):
        if state["first"]:
            state["first"] = False
            raise RuntimeError("batch failed")
        return await original(sem, batch, batch_id, backends)

    monkeypatch.setattr(pipeline, "_process_batch_async", flaky)
    # Force multiple batches with a small batch size.
    pipeline.batch_processor.current_batch_size = 2
    articles = [_good_article(i) for i in range(6)]
    result = _run(pipeline.process_articles_async(articles))
    assert "batch_error" in pipeline.metrics.errors_by_type
    # Remaining batches still processed some articles.
    assert isinstance(result["processed_articles"], list)


def test_save_performance_report(pipeline, tmp_path):
    path = tmp_path / "report.json"
    _run(pipeline.save_performance_report(str(path)))
    data = json.loads(path.read_text())
    assert "timestamp" in data
    assert "configuration" in data
    assert "performance_stats" in data


def test_get_performance_stats(pipeline):
    stats = pipeline.get_performance_stats()
    assert "metrics" in stats
    assert "circuit_breaker" in stats
    assert stats["circuit_breaker"]["state"] == "CLOSED"


# --------------------------------------------------------------------------- #
# MemoryMonitor error branch
# --------------------------------------------------------------------------- #

def test_memory_monitor_loop_handles_error(monkeypatch):
    mon = MemoryMonitor(max_memory_mb=1.0, check_interval=0.0)

    class _FakeProcess:
        def __init__(self):
            self._n = 0

        def memory_info(self):
            self._n += 1
            mon._stop_monitoring = True  # stop after first iteration
            raise RuntimeError("psutil boom")

    monkeypatch.setattr(op.psutil, "Process", lambda: _FakeProcess())
    # Directly invoke the loop; the error branch (248-250) is exercised.
    mon._monitor_memory()
    # Loop caught the error and exited when _stop_monitoring flipped.
    assert mon.peak_usage == 0.0


def test_memory_monitor_start_and_stop_real_thread(monkeypatch):
    # Exercise the normal monitoring thread path (start/loop/stop) with a
    # fake psutil.Process so no real sampling loop churns.
    class _MI:
        rss = 10 * 1024 * 1024  # 10 MB

    class _Proc:
        def memory_info(self):
            return _MI()

    monkeypatch.setattr(op.psutil, "Process", lambda: _Proc())
    mon = MemoryMonitor(max_memory_mb=1024.0, check_interval=0.01)
    mon.start_monitoring()
    # Give the daemon thread a moment to record at least one sample.
    deadline = 0
    while mon.peak_usage == 0.0 and deadline < 200:
        deadline += 1
    mon.stop_monitoring()
    assert mon.peak_usage >= 10.0
    assert mon._stop_monitoring is True


def test_memory_monitor_triggers_gc_on_high_usage(monkeypatch):
    class _MI:
        # rss high enough to exceed 80% of a tiny max_memory_mb.
        rss = 2 * 1024 * 1024  # 2 MB

    class _Proc:
        def memory_info(self):
            return _MI()

    monkeypatch.setattr(op.psutil, "Process", lambda: _Proc())
    mon = MemoryMonitor(max_memory_mb=1.0, check_interval=0.0)

    calls = {"gc": 0}
    import gc as _gc

    real_collect = _gc.collect

    def _count_collect():
        calls["gc"] += 1
        mon._stop_monitoring = True  # stop after one iteration
        return 0

    monkeypatch.setattr(_gc, "collect", _count_collect)
    try:
        mon._monitor_memory()
    finally:
        monkeypatch.setattr(_gc, "collect", real_collect)
    assert calls["gc"] == 1  # high memory -> gc.collect invoked (lines 236-244)


def test_process_articles_async_with_metrics_enabled(monkeypatch):
    # enable_metrics=True exercises the memory-monitor start/stop calls
    # (lines 391 and 463). Fake psutil.Process to keep the thread cheap.
    class _MI:
        rss = 5 * 1024 * 1024

    class _Proc:
        def memory_info(self):
            return _MI()

    monkeypatch.setattr(op.psutil, "Process", lambda: _Proc())
    p = OptimizedIngestionPipeline(
        OptimizationConfig(enable_metrics=True, memory_check_interval=0.01)
    )
    try:
        result = _run(p.process_articles_async([_good_article(i) for i in range(3)]))
        assert len(result["processed_articles"]) == 3
        # After the run the monitor thread has been stopped.
        assert p.memory_monitor._stop_monitoring is True
    finally:
        p.cleanup()


def test_memory_monitor_stats():
    mon = MemoryMonitor(max_memory_mb=100.0)
    mon.current_usage = 25.0
    mon.peak_usage = 40.0
    stats = mon.get_usage_stats()
    assert stats["current_mb"] == 25.0
    assert stats["utilization_percent"] == 25.0
    assert mon.get_memory_usage_mb() == 25.0
    assert mon.is_memory_available(50.0) is True
    assert mon.is_memory_available(80.0) is False


# --------------------------------------------------------------------------- #
# Factory + convenience functions
# --------------------------------------------------------------------------- #

def test_create_optimized_pipeline_factory():
    p = create_optimized_pipeline(max_concurrent_tasks=10, batch_size=5)
    try:
        assert p.config.max_concurrent_tasks == 10
        assert p.config.batch_size == 5
    finally:
        p.cleanup()


def test_create_performance_optimized_pipeline_factory():
    p = create_performance_optimized_pipeline(max_concurrent_tasks=8, batch_size=4)
    try:
        assert p.config.max_concurrent_tasks == 8
        assert p.config.enable_fast_validation is True
    finally:
        p.cleanup()


def test_process_articles_optimized_convenience():
    articles = [_good_article(i) for i in range(3)]
    cfg = OptimizationConfig(enable_metrics=False)
    result = _run(process_articles_optimized(articles, None, cfg))
    assert len(result["processed_articles"]) == 3
