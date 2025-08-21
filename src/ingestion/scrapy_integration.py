"""
This module provides optimized Scrapy pipelines and components that integrate
with the high-performance ingestion pipeline to improve overall throughput
and efficiency of the news scraping workflow.
"""

from scraper.items import NewsItem
from ingestion.optimized_pipeline import OptimizationConfig, OptimizedIngestionPipeline
import asyncio
import json
import logging
import queue

# Internal imports
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

from scrapy import Spider
from scrapy.exceptions import DropItem
from scrapy.utils.project import get_project_settings

sys.path.append(str(Path(__file__).parent.parent))


logger = logging.getLogger(__name__)


class OptimizedScrapyPipeline:
    """
    Optimized Scrapy pipeline that uses the high-performance ingestion engine
    for processing scraped items with improved throughput and efficiency.
    """

    def __init__(self):
        self.ingestion_pipeline = None
        self.article_buffer = []
        self.buffer_size = 50
        self.buffer_timeout = 10.0
        self.last_flush_time = time.time()

        # Threading for async processing
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        self.processing_queue = queue.Queue()
        self.result_queue = queue.Queue()

        # Metrics
        self.items_processed = 0
        self.items_buffered = 0
        self.flush_count = 0

        # Configuration from Scrapy settings
        settings = get_project_settings()
        self.config = OptimizationConfig(
            max_concurrent_tasks=settings.getint("OPTIMIZED_MAX_CONCURRENT_TASKS", 30),
            batch_size=settings.getint("OPTIMIZED_BATCH_SIZE", 50),
            max_memory_usage_mb=settings.getfloat("OPTIMIZED_MAX_MEMORY_MB", 512.0),
            adaptive_batching=settings.getbool("OPTIMIZED_ADAPTIVE_BATCHING", True),
            enable_fast_validation=settings.getbool("OPTIMIZED_FAST_VALIDATION", True),
        )

        logger.info(
            "OptimizedScrapyPipeline initialized with config: {0}".format(self.config)
        )

    def open_spider(self, spider: Spider):
        """Initialize the pipeline when spider opens."""
        self.ingestion_pipeline = OptimizedIngestionPipeline(self.config)
        self.last_flush_time = time.time()
        logger.info("Optimized pipeline opened for spider: {0}".format(spider.name))

    def close_spider(self, spider: Spider):
        """Clean up when spider closes."""
        # Flush any remaining items
        if self.article_buffer:
            self._flush_buffer_sync(spider)

        # Get final stats
        if self.ingestion_pipeline:
            stats = self.ingestion_pipeline.get_performance_stats()
            spider.logger.info(
                f"Optimized pipeline stats: {stats['metrics']['summary']}"
            )

            # Save performance report
            report_path = "data/optimization_report_{0}_{1}.json".format(
                spider.name, int(time.time())
            )
            asyncio.run(self.ingestion_pipeline.save_performance_report(report_path))

            # Cleanup
            self.ingestion_pipeline.cleanup()

        # Cleanup thread pool
        self.thread_pool.shutdown(wait=True)

        logger.info("Optimized pipeline closed for spider: {0}".format(spider.name))

    def process_item(self, item: NewsItem, spider: Spider) -> NewsItem:
        """Process item through the optimized pipeline."""
        try:
            # Convert item to dictionary
            article_data = self._item_to_dict(item)

            # Add to buffer
            self.article_buffer.append(article_data)
            self.items_buffered += 1

            # Check if buffer should be flushed
            current_time = time.time()
            should_flush = (
                len(self.article_buffer) >= self.buffer_size
                or current_time - self.last_flush_time >= self.buffer_timeout
            )

            if should_flush:
                self._flush_buffer_async(spider)

            self.items_processed += 1

            # Update item with optimization metadata
            item["optimization_processed"] = True
            item["buffer_size"] = len(self.article_buffer)
            item["processed_count"] = self.items_processed

            return item

        except Exception as e:
            spider.logger.error("Error in optimized pipeline: {0}".format(e))
            raise DropItem("Optimization processing failed: {0}".format(e))

    def _item_to_dict(self, item: NewsItem) -> Dict[str, Any]:
        """Convert Scrapy item to dictionary."""
        return {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "source": item.get("source", ""),
            "published_date": item.get("published_date", ""),
            "author": item.get("author", ""),
            "category": item.get("category", ""),
            "scraped_date": item.get("scraped_date", ""),
            "content_length": item.get("content_length", 0),
            "word_count": item.get("word_count", 0),
            "validation_score": item.get("validation_score", 0),
            "content_quality": item.get("content_quality", ""),
            "duplicate_check": item.get("duplicate_check", ""),
        }

    def _flush_buffer_async(self, spider: Spider):
        """Flush buffer asynchronously without blocking the spider."""
        if not self.article_buffer:
            return

        # Copy buffer and clear it
        articles_to_process = self.article_buffer.copy()
        self.article_buffer.clear()
        self.last_flush_time = time.time()
        self.flush_count += 1

        # Submit to thread pool for async processing
        self.thread_pool.submit(
            self._process_articles_batch, articles_to_process, spider
        )

        spider.logger.debug(
            "Flushed buffer with {0} articles (flush #{1})".format(
                len(articles_to_process), self.flush_count
            )
        )

    def _flush_buffer_sync(self, spider: Spider):
        """Flush buffer synchronously (used during spider close)."""
        if not self.article_buffer:
            return

        articles_to_process = self.article_buffer.copy()
        self.article_buffer.clear()

        try:
            self._process_articles_batch(articles_to_process, spider)
        except Exception as e:
            spider.logger.error("Error in synchronous buffer flush: {0}".format(e))

    def _process_articles_batch(self, articles: List[Dict[str, Any]], spider: Spider):
        """Process a batch of articles through the ingestion pipeline."""
        try:
            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Process articles through optimized pipeline
                results = loop.run_until_complete(
                    self.ingestion_pipeline.process_articles_async(articles)
                )

                # Log results
                processed_count = len(results["processed_articles"])
                processing_time = results["processing_time"]
                throughput = processed_count / max(processing_time, 0.001)

                spider.logger.info(
                    "Batch processed: {0}/{1} articles in {2:.2f}s ({3:.1f} articles/sec)".format(
                        processed_count, len(articles), processing_time, throughput
                    )
                )

                # Update spider stats if available
                if hasattr(spider, "crawler") and spider.crawler.stats:
                    stats = spider.crawler.stats
                    stats.inc_value("optimization/batches_processed", 1)
                    stats.inc_value("optimization/articles_processed", processed_count)
                    stats.set_value("optimization/last_throughput", throughput)
                    stats.set_value(
                        "optimization/average_processing_time",
                        results["metrics"]["performance"]["average_time_per_article"],
                    )

            finally:
                loop.close()

        except Exception as e:
            spider.logger.error("Error processing article batch: {0}".format(e))


class HighThroughputValidationPipeline:
    """
    High-throughput validation pipeline optimized for speed and efficiency.
    Uses fast validation techniques and caching to improve performance.
    """

    def __init__(self):
        self.validation_cache = {}
        self.url_seen = set()
        self.cache_size_limit = 10000

        # Fast validation settings
        self.min_title_length = 10
        self.min_content_length = 100
        self.max_title_length = 300

        # Stats
        self.items_validated = 0
        self.items_passed = 0
        self.items_failed = 0
        self.cache_hits = 0

        logger.info("HighThroughputValidationPipeline initialized")

    def process_item(self, item: NewsItem, spider: Spider) -> NewsItem:
        """Fast validation of scraped items."""
        start_time = time.time()

        try:
            # Fast duplicate check
            url = item.get("url", "")
            if url in self.url_seen:
                self.items_failed += 1
                raise DropItem("Duplicate URL: {0}".format(url))

            # Fast validation checks
            validation_result = self._fast_validate_item(item)

            if not validation_result["is_valid"]:
                self.items_failed += 1
                raise DropItem(
                    f"Validation failed: {
                        validation_result['reason']}"
                )

            # Add to seen URLs
            self.url_seen.add(url)

            # Limit cache size to prevent memory issues
            if len(self.url_seen) > self.cache_size_limit:
                self.url_seen.clear()
                spider.logger.debug("Cleared URL cache to prevent memory overflow")

            # Add validation metadata
            item["validation_score"] = validation_result["score"]
            item["validation_time"] = time.time() - start_time
            item["fast_validation"] = True

            self.items_passed += 1
            self.items_validated += 1

            return item

        except DropItem:
            self.items_validated += 1
            raise
        except Exception as e:
            self.items_failed += 1
            self.items_validated += 1
            spider.logger.error("Fast validation error: {0}".format(e))
            raise DropItem("Validation error: {0}".format(e))

    def _fast_validate_item(self, item: NewsItem) -> Dict[str, Any]:
        """Perform fast validation checks on item."""
        score = 100.0

        # Title validation
        title = item.get("title", "")
        if not title:
            return {"is_valid": False, "reason": "Missing title", "score": 0}

        if len(title) < self.min_title_length:
            return {
                "is_valid": False,
                "reason": "Title too short: {0}".format(len(title)),
                "score": 0,
            }

        if len(title) > self.max_title_length:
            score -= 10

        # Content validation
        content = item.get("content", "")
        if not content:
            return {"is_valid": False, "reason": "Missing content", "score": 0}

        if len(content) < self.min_content_length:
            return {
                "is_valid": False,
                "reason": "Content too short: {0}".format(len(content)),
                "score": 0,
            }

        # URL validation
        url = item.get("url", "")
        if not url or not url.startswith(("http://", "https://")):
            return {"is_valid": False, "reason": "Invalid URL", "score": 0}

        # Source validation
        source = item.get("source", "")
        if not source:
            score -= 15

        # Author validation (optional)
        if item.get("author"):
            score += 5

        # Publication date validation (optional)
        if item.get("published_date"):
            score += 5

        return {
            "is_valid": True,
            "reason": "Passed validation",
            "score": max(0.0, min(100.0, score)),
        }

    def close_spider(self, spider: Spider):
        """Log validation statistics when spider closes."""
        if self.items_validated > 0:
            pass_rate = (self.items_passed / self.items_validated) * 100
            spider.logger.info(
                "Fast validation stats: {0}/{1} passed ({2:.1f}% pass rate), {3} cache hits".format(
                    self.items_passed, self.items_validated, pass_rate, self.cache_hits
                )
            )


class AdaptiveRateLimitPipeline:
    """
    Adaptive rate limiting pipeline that adjusts crawling speed based on
    system performance and target site responsiveness.
    """

    def __init__(self):
        self.response_times = deque(maxlen=50)
        self.error_rates = deque(maxlen=20)
        self.current_delay = 1.0
        self.min_delay = 0.1
        self.max_delay = 10.0
        self.adjustment_factor = 1.2

        self.items_processed = 0
        self.last_adjustment_time = time.time()
        self.adjustment_interval = 30.0  # Adjust every 30 seconds

        logger.info("AdaptiveRateLimitPipeline initialized")

    def process_item(self, item: NewsItem, spider: Spider) -> NewsItem:
        """Process item and adapt rate limiting based on performance."""
        self.items_processed += 1

        # Record response time if available
        if hasattr(item, "response_time"):
            self.response_times.append(item.response_time)

        # Check if it's time to adjust rate limiting
        current_time = time.time()
        if current_time - self.last_adjustment_time >= self.adjustment_interval:
            self._adjust_rate_limit(spider)
            self.last_adjustment_time = current_time

        # Add rate limiting metadata
        item["current_delay"] = self.current_delay
        item["adaptive_rate_limit"] = True

        return item

    def _adjust_rate_limit(self, spider: Spider):
        """Adjust rate limiting based on performance metrics."""
        if not self.response_times:
            return

        # Calculate average response time
        avg_response_time = sum(self.response_times) / len(self.response_times)

        # Calculate current error rate
        current_error_rate = 0.0
        if hasattr(spider, "crawler") and spider.crawler.stats:
            stats = spider.crawler.stats
            total_requests = stats.get_value("downloader/request_count", 0)
            failed_requests = stats.get_value("downloader/exception_count", 0)

            if total_requests > 0:
                current_error_rate = failed_requests / total_requests

        self.error_rates.append(current_error_rate)

        # Determine if we should increase or decrease delay
        old_delay = self.current_delay

        if avg_response_time > 2.0 or current_error_rate > 0.1:
            # Slow down - increase delay
            self.current_delay = min(
                self.max_delay, self.current_delay * self.adjustment_factor
            )
        elif avg_response_time < 0.5 and current_error_rate < 0.02:
            # Speed up - decrease delay
            self.current_delay = max(
                self.min_delay, self.current_delay / self.adjustment_factor
            )

        # Update spider settings if changed
        if abs(self.current_delay - old_delay) > 0.01:
            if hasattr(spider, "download_delay"):
                spider.download_delay = self.current_delay

            spider.logger.info(
                "Adaptive rate limit adjusted: {0:.2f}s -> {1:.2f}s (avg response: {2:.2f}s, error rate: {3:.1%})".format(
                    old_delay, self.current_delay, avg_response_time, current_error_rate
                )
            )


class OptimizedStoragePipeline:
    """
    Optimized storage pipeline that batches writes and uses async I/O
    for improved storage performance.
    """

    def __init__(self):
        self.storage_buffer = []
        self.buffer_size = 100
        self.buffer_timeout = 15.0
        self.last_flush_time = time.time()

        # Storage backends
        self.storage_backends = []
        self._init_storage_backends()

        # Stats
        self.items_stored = 0
        self.batches_written = 0
        self.storage_errors = 0

        logger.info("OptimizedStoragePipeline initialized")

    def _init_storage_backends(self):
        """Initialize storage backends based on configuration."""
        # This would be configured based on settings
        # For now, we'll use a simple file backend
        self.storage_backends.append(self._write_to_file)

    def process_item(self, item: NewsItem, spider: Spider) -> NewsItem:
        """Buffer items for optimized batch storage."""
        # Convert item to storage format
        storage_item = self._prepare_for_storage(item)

        # Add to buffer
        self.storage_buffer.append(storage_item)

        # Check if buffer should be flushed
        current_time = time.time()
        should_flush = (
            len(self.storage_buffer) >= self.buffer_size
            or current_time - self.last_flush_time >= self.buffer_timeout
        )

        if should_flush:
            self._flush_storage_buffer(spider)

        # Add storage metadata
        item["storage_buffered"] = True
        item["buffer_size"] = len(self.storage_buffer)

        return item

    def _prepare_for_storage(self, item: NewsItem) -> Dict[str, Any]:
        """Prepare item for storage."""
        return {
            "id": item.get("url", ""),  # Use URL as ID
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "content": item.get("content", ""),
            "source": item.get("source", ""),
            "published_date": item.get("published_date", ""),
            "scraped_date": item.get("scraped_date", ""),
            "author": item.get("author", ""),
            "category": item.get("category", ""),
            "validation_score": item.get("validation_score", 0),
            "word_count": item.get("word_count", 0),
            "content_length": item.get("content_length", 0),
            "processing_metadata": {
                "optimized_pipeline": True,
                "storage_time": time.time(),
            },
        }

    def _flush_storage_buffer(self, spider: Spider):
        """Flush storage buffer to all backends."""
        if not self.storage_buffer:
            return

        items_to_store = self.storage_buffer.copy()
        self.storage_buffer.clear()
        self.last_flush_time = time.time()

        try:
            # Execute all storage backends
            for backend in self.storage_backends:
                backend(items_to_store, spider)

            self.items_stored += len(items_to_store)
            self.batches_written += 1

            spider.logger.debug(
                "Storage batch written: {0} items".format(len(items_to_store))
            )

        except Exception as e:
            self.storage_errors += 1
            spider.logger.error("Storage batch failed: {0}".format(e))

    def _write_to_file(self, items: List[Dict[str, Any]], spider: Spider):
        """Write items to file (example storage backend)."""
        output_path = "data/optimized_articles_{0}.jsonl".format(spider.name)

        try:
            with open(output_path, "a", encoding="utf-8") as f:
                for item in items:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("File write failed: {0}".format(e))
            raise

    def close_spider(self, spider: Spider):
        """Flush remaining items when spider closes."""
        if self.storage_buffer:
            self._flush_storage_buffer(spider)

        spider.logger.info(
            "Optimized storage stats: {0} items stored "
            "in {1} batches, {2} errors".format(
                self.items_stored, self.batches_written, self.storage_errors
            )
        )


# Settings integration for Scrapy


def configure_optimized_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Configure Scrapy settings for optimized performance."""
    optimized_settings = settings.copy()

    # Pipeline configuration
    optimized_settings["ITEM_PIPELINES"] = {
        "src.ingestion.scrapy_integration.HighThroughputValidationPipeline": 100,
        "src.ingestion.scrapy_integration.OptimizedScrapyPipeline": 200,
        "src.ingestion.scrapy_integration.AdaptiveRateLimitPipeline": 300,
        "src.ingestion.scrapy_integration.OptimizedStoragePipeline": 900,
    }

    # Concurrency optimization
    optimized_settings["CONCURRENT_REQUESTS"] = 32
    optimized_settings["CONCURRENT_REQUESTS_PER_DOMAIN"] = 8
    optimized_settings["DOWNLOAD_DELAY"] = 0.5
    optimized_settings["RANDOMIZE_DOWNLOAD_DELAY"] = True

    # Memory optimization
    optimized_settings["REACTOR_THREADPOOL_MAXSIZE"] = 20

    # Optimized pipeline settings
    optimized_settings["OPTIMIZED_MAX_CONCURRENT_TASKS"] = 30
    optimized_settings["OPTIMIZED_BATCH_SIZE"] = 50
    optimized_settings["OPTIMIZED_MAX_MEMORY_MB"] = 512.0
    optimized_settings["OPTIMIZED_ADAPTIVE_BATCHING"] = True
    optimized_settings["OPTIMIZED_FAST_VALIDATION"] = True

    # AutoThrottle optimization
    optimized_settings["AUTOTHROTTLE_ENABLED"] = True
    optimized_settings["AUTOTHROTTLE_START_DELAY"] = 0.1
    optimized_settings["AUTOTHROTTLE_MAX_DELAY"] = 3.0
    optimized_settings["AUTOTHROTTLE_TARGET_CONCURRENCY"] = 2.0

    return optimized_settings


if __name__ == "__main__":
    # Example configuration
    print("Optimized Scrapy Integration Configuration:")
    example_settings = configure_optimized_settings({})

    for key, value in example_settings.items():
        if "OPTIMIZED" in key or "PIPELINE" in key:
            print("{0}: {1}".format(key, value))
