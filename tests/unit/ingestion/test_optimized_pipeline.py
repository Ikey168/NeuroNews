"""Comprehensive tests for src/ingestion/optimized_pipeline.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("psutil")

from ingestion.optimized_pipeline import (  # noqa: E402
    AdaptiveBatchProcessor,
    CircuitBreaker,
    IngestionMetrics,
    MemoryMonitor,
    OptimizationConfig,
    OptimizedIngestionPipeline,
    create_optimized_pipeline,
    create_performance_optimized_pipeline,
)


class TestIngestionMetrics:
    def test_update_success(self):
        m = IngestionMetrics()
        m.update_metrics(0.5, success=True)
        assert m.total_articles_processed == 1
        assert m.successful_articles == 1
        assert m.average_processing_time == 0.5

    def test_update_failure_tracks_error_type(self):
        m = IngestionMetrics()
        m.update_metrics(0.2, success=False, error_type="validation")
        assert m.failed_articles == 1
        assert m.errors_by_type["validation"] == 1

    def test_get_summary(self):
        m = IngestionMetrics()
        m.update_metrics(1.0, success=True)
        m.update_metrics(1.0, success=False, error_type="storage")
        summary = m.get_summary()
        assert summary["summary"]["total_processed"] == 2
        assert summary["summary"]["success_rate_percent"] == 50.0
        assert "storage" in summary["errors"]


class TestOptimizationConfig:
    def test_defaults(self):
        c = OptimizationConfig()
        assert c.batch_size == 100
        assert c.min_content_length == 100
        assert c.enable_circuit_breaker is True


class TestCircuitBreaker:
    def test_success_passes_through(self):
        cb = CircuitBreaker()
        assert cb.call(lambda: 42) == 42
        assert cb.state == "CLOSED"

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)

        def boom():
            raise ValueError("x")

        for _ in range(3):
            with pytest.raises(ValueError):
                cb.call(boom)
        assert cb.state == "OPEN"
        # subsequent call short-circuits
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            cb.call(lambda: 1)

    def test_half_open_recovers(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.0)

        with pytest.raises(ValueError):
            cb.call(lambda: (_ for _ in ()).throw(ValueError("x")))
        assert cb.state == "OPEN"
        # recovery_timeout=0 -> next call transitions to HALF_OPEN then CLOSED
        assert cb.call(lambda: "ok") == "ok"
        assert cb.state == "CLOSED"


class TestMemoryMonitor:
    def test_is_memory_available(self):
        mon = MemoryMonitor(max_memory_mb=1000.0)
        mon.current_usage = 200.0
        assert mon.is_memory_available(100) is True
        assert mon.is_memory_available(900) is False

    def test_usage_stats(self):
        mon = MemoryMonitor(max_memory_mb=1000.0)
        mon.current_usage = 250.0
        mon.peak_usage = 400.0
        stats = mon.get_usage_stats()
        assert stats["current_mb"] == 250.0
        assert stats["peak_mb"] == 400.0
        assert stats["utilization_percent"] == 25.0

    def test_get_memory_usage_mb(self):
        mon = MemoryMonitor()
        mon.current_usage = 123.0
        assert mon.get_memory_usage_mb() == 123.0


class TestAdaptiveBatchProcessor:
    def test_initial_size(self):
        p = AdaptiveBatchProcessor(initial_batch_size=50)
        assert p.get_batch_size() == 50

    def test_needs_data_before_adjusting(self):
        p = AdaptiveBatchProcessor(initial_batch_size=50)
        p.adjust_batch_size(1.0, 1.0)
        assert p.get_batch_size() == 50  # < 3 data points

    def test_grows_when_improving(self):
        p = AdaptiveBatchProcessor(initial_batch_size=100, max_size=1000)
        # feed improving performance scores
        p.adjust_batch_size(1.0, 0.5)
        p.adjust_batch_size(1.0, 0.5)
        for _ in range(5):
            p.adjust_batch_size(0.1, 1.0)  # high success, low time => high score
        assert p.get_batch_size() >= 100

    def test_respects_min_max(self):
        p = AdaptiveBatchProcessor(initial_batch_size=10, min_size=10, max_size=20)
        for _ in range(10):
            p.adjust_batch_size(10.0, 0.1)  # poor performance
        assert p.get_batch_size() >= 10


@pytest.fixture
def pipeline():
    return OptimizedIngestionPipeline(OptimizationConfig(min_content_length=100))


class TestPipelineValidation:
    @pytest.mark.asyncio
    async def test_valid_article(self, pipeline):
        article = {
            "title": "A valid title that is long enough",
            "url": "https://example.com/a",
            "content": "word " * 50,
        }
        assert await pipeline._fast_validate_article(article) is True

    @pytest.mark.asyncio
    async def test_missing_field(self, pipeline):
        assert await pipeline._fast_validate_article({"title": "x"}) is False

    @pytest.mark.asyncio
    async def test_short_content(self, pipeline):
        article = {"title": "A valid long title here", "url": "https://x.com", "content": "short"}
        assert await pipeline._fast_validate_article(article) is False

    @pytest.mark.asyncio
    async def test_bad_url(self, pipeline):
        article = {"title": "A valid long title here", "url": "noturl", "content": "word " * 50}
        assert await pipeline._fast_validate_article(article) is False

    @pytest.mark.asyncio
    async def test_short_title(self, pipeline):
        article = {"title": "tiny", "url": "https://x.com", "content": "word " * 50}
        assert await pipeline._fast_validate_article(article) is False


class TestPipelineEnhancement:
    @pytest.mark.asyncio
    async def test_enhance_adds_metadata(self, pipeline):
        enhanced = await pipeline._enhance_article_async({
            "title": "T", "url": "https://news.example.com/a", "content": "one two three",
        })
        assert enhanced["word_count"] == 3
        assert enhanced["source_domain"] == "news.example.com"
        assert enhanced["pipeline_version"] == "optimized_v1"
        assert "quality_score" in enhanced

    def test_quality_score_range(self, pipeline):
        score = pipeline._calculate_quality_score(
            {"content_length": 5000, "word_count": 800, "title": "Good Title Here"}
        )
        assert 0.0 <= score <= 100.0


class TestPipelineStatsAndFactories:
    def test_get_performance_stats(self, pipeline):
        stats = pipeline.get_performance_stats()
        assert isinstance(stats, dict)

    def test_create_optimized_pipeline(self):
        assert isinstance(create_optimized_pipeline(), OptimizedIngestionPipeline)

    def test_create_performance_optimized(self):
        p = create_performance_optimized_pipeline()
        assert isinstance(p, OptimizedIngestionPipeline)

    def test_cleanup(self, pipeline):
        pipeline.cleanup()  # should not raise
