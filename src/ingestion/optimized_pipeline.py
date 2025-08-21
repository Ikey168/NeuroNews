"""
Optimized Data Ingestion Pipeline - Issue #26

This module provides a high-performance, optimized data ingestion pipeline
that addresses bottlenecks in the current scraping and processing workflow.
It includes concurrent processing, intelligent batching, memory optimization,
and advanced error handling.
"""

import asyncio
import json
import logging
import queue

# Internal imports
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field_name
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

import aiofiles
import psutil

sys.path.append(str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


@dataclass
class IngestionMetrics:
    """Metrics for tracking ingestion performance."""

    total_articles_processed: int = 0
    successful_articles: int = 0
    failed_articles: int = 0
    skipped_articles: int = 0

    total_processing_time: float = 0.0
    average_processing_time: float = 0.0
    peak_memory_usage: float = 0.0

    validation_time: float = 0.0
    storage_time: float = 0.0
    enhancement_time: float = 0.0

    throughput_articles_per_second: float = 0.0
    errors_by_type: Dict[str, int] = field_name(default_factory=dict)
    processing_stages: Dict[str, float] = field_name(default_factory=dict)

    # Source-specific metrics
    source_metrics: Dict[str, Dict[str, Any]
        ] = field_name(default_factory=dict)

    def update_metrics(
        self, processing_time: float, success: bool, error_type: str = None
    ):
        """Update metrics after processing an article."""
        self.total_articles_processed += 1
        self.total_processing_time += processing_time

        if success:
            self.successful_articles += 1
        else:
            self.failed_articles += 1
            if error_type:
                self.errors_by_type[error_type] = (
                    self.errors_by_type.get(error_type, 0) + 1
                )

        # Update average processing time
        if self.total_articles_processed > 0:
            self.average_processing_time = (
                self.total_processing_time / self.total_articles_processed
            )
            self.throughput_articles_per_second = (
                self.total_articles_processed / self.total_processing_time
            )

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of ingestion metrics."""
        success_rate = (
            self.successful_articles / max(self.total_articles_processed, 1)
        ) * 100

        return {
            "summary": {
                "total_processed": self.total_articles_processed,
                "successful": self.successful_articles,
                f"ailed": self.failed_articles,
                "skipped": self.skipped_articles,
                "success_rate_percent": round(success_rate, 2),
            },
            "performance": {
                "total_time_seconds": round(self.total_processing_time, 2),
                "average_time_per_article": round(self.average_processing_time, 4),
                "throughput_articles_per_second": round(
                    self.throughput_articles_per_second, 2
                ),
                "peak_memory_mb": round(self.peak_memory_usage, 2),
            },
            "processing_breakdown": {
                "validation_time": round(self.validation_time, 2),
                "storage_time": round(self.storage_time, 2),
                "enhancement_time": round(self.enhancement_time, 2),
            },
            "errors": dict(self.errors_by_type),
            "source_metrics": dict(self.source_metrics),
        }


@dataclass
class OptimizationConfig:
    """Configuration for the optimized ingestion pipeline."""

    # Concurrency settings
    max_concurrent_tasks: int = 50
    max_worker_threads: int = 8
    max_processes: int = 4

    # Batch processing settings
    batch_size: int = 100
    max_batch_wait_time: float = 5.0
    adaptive_batching: bool = True

    # Memory management
    max_memory_usage_mb: float = 1024.0
    memory_check_interval: float = 1.0
    gc_threshold: float = 0.8

    # Performance optimization
    enable_compression: bool = True
    enable_caching: bool = True
    cache_size_mb: float = 256.0

    # Storage optimization
    enable_parallel_storage: bool = True
    storage_batch_size: int = 50
    storage_timeout: float = 30.0

    # Quality and validation
    enable_fast_validation: bool = True
    skip_duplicate_check_after: int = 10000
    min_content_length: int = 100

    # Error handling
    max_retries: int = 3
    retry_backoff: float = 1.0
    enable_circuit_breaker: bool = True

    # Monitoring
    enable_metrics: bool = True
    metrics_interval: float = 10.0
    enable_profiling: bool = False


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self._lock = threading.Lock()

    def call(self, func: Callable, *args, **kwargs):
        """Execute function with circuit breaker protection."""
        with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise Exception("Circuit breaker is OPEN")

            try:
                result = func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.state = "CLOSED"
                    self.failure_count = 0
                return result

            except Exception as e:
                self.failure_count += 1
                self.last_failure_time = time.time()

                if self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"

                raise e


class MemoryMonitor:
    """Monitor and manage memory usage during ingestion."""

    def __init__(self, max_memory_mb: float = 1024.0, check_interval: float = 1.0):
        self.max_memory_mb = max_memory_mb
        self.check_interval = check_interval
        self.peak_usage = 0.0
        self.current_usage = 0.0
        self._stop_monitoring = False
        self._monitor_thread = None

    def start_monitoring(self):
        """Start memory monitoring in background thread."""
        self._stop_monitoring = False
        self._monitor_thread = threading.Thread(target=self._monitor_memory)
        self._monitor_thread.daemon = True
        self._monitor_thread.start()

    def stop_monitoring(self):
        """Stop memory monitoring."""
        self._stop_monitoring = True
        if self._monitor_thread:
            self._monitor_thread.join(timeout=1.0)

    def _monitor_memory(self):
        """Monitor memory usage continuously."""
        process = psutil.Process()

        while not self._stop_monitoring:
            try:
                memory_info = process.memory_info()
                self.current_usage = memory_info.rss / 1024 / 1024  # MB

                if self.current_usage > self.peak_usage:
                    self.peak_usage = self.current_usage

                # Trigger garbage collection if memory usage is high
                if self.current_usage > self.max_memory_mb * 0.8:
                    import gc

                    gc.collect()
                    logger.warning(
                        "High memory usage detected: {0:.1f}MB, triggered GC".format(
                            self.current_usage
                        )
                    )

                time.sleep(self.check_interval)

            except Exception as e:
                logger.error("Memory monitoring error: {0}".format(e))
                time.sleep(self.check_interval)

    def is_memory_available(self, required_mb: float = 0) -> bool:
        """Check if sufficient memory is available."""
        return (self.current_usage + required_mb) <= self.max_memory_mb

    def get_usage_stats(self) -> Dict[str, float]:
        """Get memory usage statistics."""
        return {
            "current_mb": self.current_usage,
            "peak_mb": self.peak_usage,
            "max_mb": self.max_memory_mb,
            "utilization_percent": (self.current_usage / self.max_memory_mb) * 100,
        }


class AdaptiveBatchProcessor:
    """Adaptive batch processor that optimizes batch sizes based on performance."""

    def __init__(
        self, initial_batch_size: int = 100, min_size: int = 10, max_size: int = 1000
    ):
        self.current_batch_size = initial_batch_size
        self.min_size = min_size
        self.max_size = max_size
        self.performance_history = deque(maxlen=10)
        self.adjustment_factor = 1.1

    def adjust_batch_size(self, processing_time: float, success_rate: float):
        """Adjust batch size based on performance metrics."""
        # Calculate performance score (higher is better)
        performance_score = success_rate / max(processing_time, 0.1)
        self.performance_history.append(performance_score)

        if len(self.performance_history) < 3:
            return  # Need more data points

        # Compare recent performance to historical average
        recent_avg = sum(list(self.performance_history)[-3:]) / 3
        historical_avg = sum(self.performance_history) / \
                             len(self.performance_history)

        if recent_avg > historical_avg * 1.1:
            # Performance is improving, try larger batches
            new_size = min(
                self.max_size, int(self.current_batch_size *
                                   self.adjustment_factor)
            )
        elif recent_avg < historical_avg * 0.9:
            # Performance is degrading, try smaller batches
            new_size = max(
                self.min_size, int(self.current_batch_size /
                                   self.adjustment_factor)
            )
        else:
            # Performance is stable
            return

        logger.info(
            "Adjusting batch size from {0} to {1} (performance score: {2:.3f})".format(
                self.current_batch_size, new_size, recent_avg
            )
        )
        self.current_batch_size = new_size

    def get_batch_size(self) -> int:
        """Get current optimal batch size."""
        return self.current_batch_size


class OptimizedIngestionPipeline:
    """
    High-performance, optimized data ingestion pipeline.

    Features:
    - Concurrent processing with async/await and thread pools
    - Adaptive batch sizing based on performance
    - Memory monitoring and management
    - Circuit breaker pattern for fault tolerance
    - Intelligent caching and compression
    - Comprehensive metrics and monitoring
    """

    def __init__(self, config: OptimizationConfig = None):
        self.config = config or OptimizationConfig()
        self.metrics = IngestionMetrics()
        self.memory_monitor = MemoryMonitor(
            max_memory_mb=self.config.max_memory_usage_mb,
            check_interval=self.config.memory_check_interval,
        )

        # Processing components
        self.batch_processor = AdaptiveBatchProcessor(
            initial_batch_size=self.config.batch_size
        )
        self.circuit_breaker = CircuitBreaker()

        # Threading and async components
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.config.max_worker_threads
        )
        self.processing_queue = queue.Queue()
        self.result_queue = queue.Queue()

        # Cache for deduplication and performance
        self.content_cache = {}
        self.url_cache = set()

        # State management
        self._processing = False
        self._stop_requested = False

        logger.info(
            "Optimized ingestion pipeline initialized with config: {0}".format(
                self.config
            )
        )

    async def process_articles_async(
        self, articles: List[Dict[str, Any]], storage_backends: List[Callable] = None
    ) -> Dict[str, Any]:
        """
        Process articles through the optimized pipeline asynchronously.

        Args:
            articles: List of article dictionaries to process
            storage_backends: Optional list of storage backend functions

        Returns:
            Dictionary with processing results and metrics
        """
        start_time = time.time()
        self._processing = True
        self._stop_requested = False

        # Start memory monitoring
        if self.config.enable_metrics:
            self.memory_monitor.start_monitoring()

        try:
            logger.info(
                "Starting optimized ingestion pipeline for {0} articles".format(
                    len(articles)
                )
            )

            # Process articles in optimized batches
            processed_articles = []

            # Use semaphore to control concurrency
            semaphore = asyncio.Semaphore(self.config.max_concurrent_tasks)

            # Create batches for processing
            batches = self._create_adaptive_batches(articles)
            logger.info(
                "Created {0} adaptive batches for processing".format(
                    len(batches))
            )

            # Process batches concurrently
            batch_tasks = []
            for i, batch in enumerate(batches):
                task = asyncio.create_task(
                    self._process_batch_async(
                        semaphore, batch, i, storage_backends)
                )
                batch_tasks.append(task)

            # Wait for all batches to complete
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            # Aggregate results
            for result in batch_results:
                if isinstance(result, list):
                    processed_articles.extend(result)
                elif isinstance(result, Exception):
                    logger.error("Batch processing error: {0}".format(result))
                    self.metrics.errors_by_type["batch_error"] = (
                        self.metrics.errors_by_type.get("batch_error", 0) + 1
                    )

            # Final processing metrics
            total_time = time.time() - start_time
            self.metrics.total_processing_time = total_time

            # Update throughput metrics
            if total_time > 0:
                self.metrics.throughput_articles_per_second = (
                    len(processed_articles) / total_time
                )

            logger.info(
                "Pipeline processing completed: {0} articles processed in {1:.2f}s ({2:.2f} articles/sec)".format(
                    len(processed_articles),
                    total_time,
                    self.metrics.throughput_articles_per_second,
                )
            )

            return {
                "processed_articles": processed_articles,
                "metrics": self.metrics.get_summary(),
                "processing_time": total_time,
                "memory_stats": self.memory_monitor.get_usage_stats(),
            }

        finally:
            self._processing = False
            if self.config.enable_metrics:
                self.memory_monitor.stop_monitoring()

    def _create_adaptive_batches(
        self, articles: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Create adaptive batches based on article characteristics and system resources."""
        if not self.config.adaptive_batching:
            # Simple fixed-size batching
            batch_size = self.batch_processor.get_batch_size()
            return [
                articles[i: i + batch_size]
                for i in range(0, len(articles), batch_size)
            ]

        batches = []
        current_batch = []
        current_batch_size = 0
        estimated_memory_per_article = 50  # KB

        for article in articles:
            # Estimate memory usage for this article
            content_size = len(article.get("content", "")) / 1024  # KB
            estimated_memory = max(estimated_memory_per_article, content_size)

            # Check if adding this article would exceed memory or batch size
            # limits
            if (
                current_batch_size + estimated_memory
                > self.config.max_memory_usage_mb * 1024 / 10
                or len(current_batch) >= self.batch_processor.get_batch_size()
            ):

                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_batch_size = 0

            current_batch.append(article)
            current_batch_size += estimated_memory

        # Add the last batch if it has articles
        if current_batch:
            batches.append(current_batch)

        return batches

    async def _process_batch_async(
        self,
        semaphore: asyncio.Semaphore,
        batch: List[Dict[str, Any]],
        batch_id: int,
        storage_backends: List[Callable] = None,
    ) -> List[Dict[str, Any]]:
        """Process a single batch of articles asynchronously."""
        async with semaphore:
            batch_start_time = time.time()
            processed_articles = []

            try:
                logger.debug(
                    "Processing batch {0} with {1} articles".format(
                        batch_id, len(batch)
                    )
                )

                # Process articles in the batch concurrently
                tasks = []
                for article in batch:
                    task = asyncio.create_task(
                        self._process_single_article_async(article)
                    )
                    tasks.append(task)

                # Wait for all articles in batch to be processed
                article_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Collect successful results
                for result in article_results:
                    if isinstance(result, dict):
                        processed_articles.append(result)
                    elif isinstance(result, Exception):
                        logger.warning(
                            "Article processing failed in batch {0}: {1}".format(
                                batch_id, result
                            )
                        )

                # Store processed articles if storage backends are provided
                if storage_backends and processed_articles:
                    await self._store_batch_async(processed_articles, storage_backends)

                # Update batch processor performance metrics
                batch_time = time.time() - batch_start_time
                success_rate = len(processed_articles) / \
                                   len(batch) if batch else 0
                self.batch_processor.adjust_batch_size(
                    batch_time, success_rate)

                logger.debug(
                    "Batch {0} completed: {1}/{2} articles processed in {3:.2f}s".format(
                        batch_id, len(processed_articles), len(
                            batch), batch_time
                    )
                )

                return processed_articles

            except Exception as e:
                logger.error(
                    "Critical error in batch {0}: {1}".format(batch_id, e))
                self.metrics.errors_by_type["batch_critical"] = (
                    self.metrics.errors_by_type.get("batch_critical", 0) + 1
                )
                return []

    async def _process_single_article_async(
        self, article: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process a single article through the optimized pipeline."""
        article_start_time = time.time()

        try:
            # Fast duplicate check using URL cache
            url = article.get("url", "")
            if url in self.url_cache:
                self.metrics.skipped_articles += 1
                return None

            # Enhanced validation (if enabled)
            if self.config.enable_fast_validation:
                if not await self._fast_validate_article(article):
                    self.metrics.failed_articles += 1
                    self.metrics.errors_by_type["validation_failed"] = (
                        self.metrics.errors_by_type.get(
                            "validation_failed", 0) + 1
                    )
                    return None

            # Process article through enhancement pipeline
            enhanced_article = await self._enhance_article_async(article)

            # Add to caches
            self.url_cache.add(url)
            if len(self.url_cache) > self.config.skip_duplicate_check_after:
                # Prevent memory overflow in cache
                self.url_cache.clear()
                logger.debug("Cleared URL cache to prevent memory overflow")

            # Update metrics
            processing_time = time.time() - article_start_time
            self.metrics.update_metrics(processing_time, True)

            return enhanced_article

        except Exception as e:
            processing_time = time.time() - article_start_time
            self.metrics.update_metrics(
                processing_time, False, type(e).__name__)
            logger.warning(
                f"Article processing failed for {article.get('url', 'unknown')}: {e}"
            )
            return None

    async def _fast_validate_article(self, article: Dict[str, Any]) -> bool:
        """Fast validation for articles with optimized checks."""
        # Required fields check
        required_fields = ["title", "url", "content"]
        for field_name in required_fields:
            if not article.get(field_name):
                return False

        # Content length check
        content = article.get("content", "")
        if len(content) < self.config.min_content_length:
            return False

        # URL format validation
        url = article.get("url", "")
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return False
        except Exception:
            return False

        # Title validation
        title = article.get("title", "")
        if len(title) < 10 or len(title) > 300:
            return False

        return True

    async def _enhance_article_async(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance article with additional metadata and processing."""
        enhanced = article.copy()

        # Add processing metadata
        enhanced["processed_at"] = datetime.now(timezone.utc).isoformat()
        enhanced["pipeline_version"] = "optimized_v1"

        # Calculate content metrics
        content = enhanced.get("content", "")
        enhanced["word_count"] = len(content.split())
        enhanced["content_length"] = len(content)
        enhanced["reading_time"] = max(
            1, enhanced["word_count"] // 200
        )  # Assume 200 WPM

        # Extract additional metadata
        enhanced["source_domain"] = urlparse(enhanced.get("url", "")).netloc

        # Add quality score based on content characteristics
        quality_score = self._calculate_quality_score(enhanced)
        enhanced["quality_score"] = quality_score

        return enhanced

    def _calculate_quality_score(self, article: Dict[str, Any]) -> float:
        """Calculate a quality score for the article."""
        score = 100.0

        # Content length factor
        content_length = article.get("content_length", 0)
        if content_length < 200:
            score -= 30
        elif content_length > 5000:
            score -= 10

        # Word count factor
        word_count = article.get("word_count", 0)
        if word_count < 50:
            score -= 25

        # Title quality
        title = article.get("title", "")
        if len(title) < 20:
            score -= 15

        # Has author
        if article.get("author"):
            score += 5

        # Has publish date
        if article.get("published_date"):
            score += 5

        return max(0.0, min(100.0, score))

    async def _store_batch_async(
        self, articles: List[Dict[str, Any]], storage_backends: List[Callable]
    ):
        """Store processed articles using multiple storage backends."""
        storage_start_time = time.time()

        try:
            # Execute all storage backends concurrently
            storage_tasks = []
            for backend in storage_backends:
                task = asyncio.create_task(
                    self._execute_storage_backend(backend, articles)
                )
                storage_tasks.append(task)

            # Wait for all storage operations to complete
            results = await asyncio.gather(*storage_tasks, return_exceptions=True)

            # Log storage results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(
                        "Storage backend {0} failed: {1}".format(i, result))
                    self.metrics.errors_by_type["storage_failed"] = (
                        self.metrics.errors_by_type.get(
                            "storage_failed", 0) + 1
                    )

            storage_time = time.time() - storage_start_time
            self.metrics.storage_time += storage_time

        except Exception as e:
            logger.error("Batch storage failed: {0}".format(e))
            self.metrics.errors_by_type["storage_critical"] = (
                self.metrics.errors_by_type.get("storage_critical", 0) + 1
            )

    async def _execute_storage_backend(
        self, backend: Callable, articles: List[Dict[str, Any]]
    ):
        """Execute a single storage backend."""
        try:
            if asyncio.iscoroutinefunction(backend):
                return await backend(articles)
            else:
                # Run synchronous backend in thread pool
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(self.thread_pool, backend, articles)
        except Exception as e:
            logger.error("Storage backend execution failed: {0}".format(e))
            raise

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        return {
            "metrics": self.metrics.get_summary(),
            "memory": self.memory_monitor.get_usage_stats(),
            "batch_processor": {
                "current_batch_size": self.batch_processor.get_batch_size(),
                "performance_history_length": len(
                    self.batch_processor.performance_history
                ),
            },
            "circuit_breaker": {
                "state": self.circuit_breaker.state,
                f"ailure_count": self.circuit_breaker.failure_count,
            },
            "cache_stats": {
                "url_cache_size": len(self.url_cache),
                "content_cache_size": len(self.content_cache),
            },
        }

    async def save_performance_report(self, output_path: str):
        """Save detailed performance report to file."""
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "configuration": {
                "max_concurrent_tasks": self.config.max_concurrent_tasks,
                "max_worker_threads": self.config.max_worker_threads,
                "batch_size": self.config.batch_size,
                "adaptive_batching": self.config.adaptive_batching,
                "max_memory_usage_mb": self.config.max_memory_usage_mb,
            },
            "performance_stats": self.get_performance_stats(),
        }

        async with aiofiles.open(output_path, "w") as f:
            await f.write(json.dumps(report, indent=2))

        logger.info("Performance report saved to: {0}".format(output_path))

    def cleanup(self):
        """Clean up resources and stop background processes."""
        self._stop_requested = True
        self.memory_monitor.stop_monitoring()
        self.thread_pool.shutdown(wait=True)
        logger.info("Optimized ingestion pipeline cleanup completed")


# Factory functions for easy integration


def create_optimized_pipeline(
    max_concurrent_tasks: int = 50,
    batch_size: int = 100,
    max_memory_mb: float = 1024.0,
    enable_adaptive_batching: bool = True,
) -> OptimizedIngestionPipeline:
    """Create an optimized ingestion pipeline with common settings."""
    config = OptimizationConfig(
        max_concurrent_tasks=max_concurrent_tasks,
        batch_size=batch_size,
        max_memory_usage_mb=max_memory_mb,
        adaptive_batching=enable_adaptive_batching,
    )
    return OptimizedIngestionPipeline(config)


def create_performance_optimized_pipeline(
    max_concurrent_tasks: int = 40,
    batch_size: int = 50,
    max_memory_usage_mb: float = 1024.0,
) -> OptimizedIngestionPipeline:
    """
    Factory function to create a high-performance optimized ingestion pipeline.

    Args:
        max_concurrent_tasks: Maximum number of concurrent processing tasks
        batch_size: Base batch size for processing
        max_memory_usage_mb: Maximum memory usage threshold in MB

    Returns:
        High-performance configured OptimizedIngestionPipeline instance
    """
    config = OptimizationConfig(
        max_concurrent_tasks=max_concurrent_tasks,
        batch_size=batch_size,
        max_memory_usage_mb=max_memory_usage_mb,
        adaptive_batching=True,
        enable_fast_validation=True,
    )

    return OptimizedIngestionPipeline(config)


async def process_articles_optimized(
    articles: List[Dict[str, Any]],
    storage_backends: List[Callable] = None,
    config: OptimizationConfig = None,
) -> Dict[str, Any]:
    """
    Convenience function to process articles through the optimized pipeline.

    Args:
        articles: List of articles to process
        storage_backends: Optional storage backends for processed articles
        config: Optional optimization configuration

    Returns:
        Processing results and metrics
    """
    pipeline = OptimizedIngestionPipeline(config)

    try:
        results = await pipeline.process_articles_async(articles, storage_backends)
        return results
    finally:
        pipeline.cleanup()


if __name__ == "__main__":
    # Example usage and testing

    async def main():
        # Sample articles for testing
        sample_articles = [
            {
                "title": "Test Article {0}".format(i),
                "url": "https://example.com/article-{0}".format(i),
                "content": "This is the content of test article {0}. ".format(i) * 20,
                "source": "example.com",
                "published_date": datetime.now().isoformat(),
            }
            for i in range(100)
        ]

        # Create optimized pipeline
        config = OptimizationConfig(
            max_concurrent_tasks=20,
            batch_size=25,
            adaptive_batching=True,
            enable_metrics=True,
        )

        pipeline = OptimizedIngestionPipeline(config)

        try:
            # Process articles
            results = await pipeline.process_articles_async(sample_articles)

            # Print results
            print("Optimized Ingestion Pipeline Results:")
            print(f"Processed: {len(results['processed_articles'])} articles")
            print(f"Processing time: {results['processing_time']:.2f}s")
            print(
                f"Throughput: {len(results['processed_articles']) / results['processing_time']:.2f} articles/sec"
            )
            print("Metrics:")
            print(json.dumps(results["metrics"], indent=2))

        finally:
            pipeline.cleanup()

    # Run the example
    asyncio.run(main())
