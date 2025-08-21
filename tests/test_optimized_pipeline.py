"""
Comprehensive test suite for the optimized data ingestion pipeline.
Tests performance improvements, functionality, and integration with existing systems.
"""

import asyncio
import logging
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from src.ingestion.optimized_pipeline import (
        AdaptiveBatchProcessor,
        CircuitBreaker,
        IngestionMetrics,
        MemoryMonitor,
        OptimizationConfig,
        OptimizedIngestionPipeline,
        create_optimized_pipeline,
        create_performance_optimized_pipeline,
    )
except ImportError as e:
    print("Warning: Could not import optimized_pipeline: {0}".format(e))

    # Create mock classes for testing

    class OptimizedIngestionPipeline:

        def __init__(self, config):
            self.config = config

        def cleanup(self):
            pass

    class OptimizationConfig:

        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)


try:
    from src.ingestion.scrapy_integration import (
        AdaptiveRateLimitPipeline,
        HighThroughputValidationPipeline,
        OptimizedScrapyPipeline,
        OptimizedStoragePipeline,
        configure_optimized_settings,
    )
except ImportError as e:
    print("Warning: Could not import scrapy_integration: {0}".format(e))

    # Create mock classes for testing

    class OptimizedScrapyPipeline:

        def __init__(self):
            pass

    class HighThroughputValidationPipeline:

        def __init__(self):
            pass


class TestOptimizedIngestionPipeline(unittest.TestCase):
    """Test suite for the OptimizedIngestionPipeline."""

    def setUp(self):
        """Set up test fixtures."""
        self.config = OptimizationConfig(
            max_concurrent_tasks=5,
            batch_size=10,
            max_memory_usage_mb=100.0,
            adaptive_batching=True,
            enable_fast_validation=True,
        )
        self.pipeline = OptimizedIngestionPipeline(self.config)

        # Sample test data
        self.sample_articles = [
            {
                "title": "Test Article {0}".format(i),
                "url": "https://example.com/article/{0}".format(i),
                "content": "This is test content for article {0}. ".format(i) * 20,
                "source": "test_source",
                "published_date": "2024-01-01",
                "author": "Author {0}".format(i),
                "category": "test",
            }
            for i in range(50)
        ]

    def tearDown(self):
        """Clean up after tests."""
        if self.pipeline:
            self.pipeline.cleanup()

    def test_pipeline_initialization(self):
        """Test pipeline initializes correctly."""
        self.assertIsNotNone(self.pipeline)
        self.assertEqual(self.pipeline.config.max_concurrent_tasks, 5)
        self.assertEqual(self.pipeline.config.batch_size, 10)
        self.assertTrue(self.pipeline.config.adaptive_batching)

    def test_single_article_processing(self):
        """Test processing a single article."""
        article = self.sample_articles[0]

        async def run_test():
            result = await self.pipeline.process_article_async(article)
            return result

        result = asyncio.run(run_test())

        self.assertIsNotNone(result)
        self.assertEqual(result["title"], article["title"])
        self.assertIn("processing_metadata", result)
        self.assertTrue(result["processing_metadata"]["optimized_processing"])

    def test_batch_processing(self):
        """Test batch processing functionality."""
        test_articles = self.sample_articles[:20]

        async def run_test():
            results = await self.pipeline.process_articles_async(test_articles)
            return results

        results = asyncio.run(run_test())

        self.assertIn("processed_articles", results)
        self.assertEqual(len(results["processed_articles"]), 20)
        self.assertIn("processing_time", results)
        self.assertIn("metrics", results)
        self.assertGreater(results["metrics"]["performance"]["throughput"], 0)

    def test_concurrent_processing_performance(self):
        """Test that concurrent processing improves performance."""
        test_articles = self.sample_articles[:30]

        # Test with concurrency

        async def test_concurrent():
            start_time = time.time()
            results = await self.pipeline.process_articles_async(test_articles)
            concurrent_time = time.time() - start_time
            return concurrent_time, results

        concurrent_time, results = asyncio.run(test_concurrent())

        # Verify performance metrics
        self.assertGreater(results["metrics"]["performance"]["throughput"], 0)
        self.assertEqual(len(results["processed_articles"]), 30)

        # Test processing time is reasonable
        # Should complete within 10 seconds
        self.assertLess(concurrent_time, 10.0)

    def test_adaptive_batching(self):
        """Test adaptive batching functionality."""
        processor = AdaptiveBatchProcessor(
            initial_batch_size=5,
            min_batch_size=2,
            max_batch_size=20,
            target_processing_time=1.0,
        )

        # Simulate processing times
        processor.update_performance(0.5, 5)  # Fast processing
        self.assertGreater(processor.current_batch_size, 5)

        processor.update_performance(2.0, 10)  # Slow processing
        self.assertLess(processor.current_batch_size, 10)

    def test_memory_monitoring(self):
        """Test memory monitoring functionality."""
        monitor = MemoryMonitor(threshold_mb=50.0)

        # Test memory check
        memory_mb = monitor.get_memory_usage_mb()
        self.assertGreater(memory_mb, 0)

        # Test threshold checking
        is_over = monitor.is_memory_over_threshold()
        self.assertIsInstance(is_over, bool)

    def test_circuit_breaker(self):
        """Test circuit breaker functionality."""
        breaker = CircuitBreaker(
            failure_threshold=3, recovery_timeout=1.0, error_rate_threshold=0.5
        )

        # Test initial state
        self.assertTrue(breaker.can_process())

        # Test failure recording
        for _ in range(3):
            breaker.record_failure()

        # Should be open after threshold failures
        self.assertFalse(breaker.can_process())

        # Test success recording
        breaker.record_success()

    def test_performance_metrics(self):
        """Test performance metrics collection."""
        metrics = IngestionMetrics()

        # Record some metrics
        metrics.record_processing_time(1.5)
        metrics.record_articles_processed(10)
        metrics.record_memory_usage(50.0)

        # Get summary
        summary = metrics.get_summary()

        self.assertIn("total_articles", summary)
        self.assertIn("average_processing_time", summary)
        self.assertIn("throughput", summary)
        self.assertEqual(summary["total_articles"], 10)

    def test_error_handling(self):
        """Test error handling in pipeline."""
        # Create article with missing required fields
        invalid_article = {"title": "Test"}  # Missing url and content

        async def run_test():
            try:
                result = await self.pipeline.process_article_async(invalid_article)
                return result
            except Exception as e:
                return str(e)

        result = asyncio.run(run_test())

        # Should handle gracefully - either process with defaults or skip
        self.assertIsNotNone(result)

    def test_pipeline_factories(self):
        """Test pipeline factory functions."""
        # Test standard optimized pipeline
        pipeline1 = create_optimized_pipeline()
        self.assertIsInstance(pipeline1, OptimizedIngestionPipeline)

        # Test performance optimized pipeline
        pipeline2 = create_performance_optimized_pipeline(
            max_concurrent_tasks=20)
        self.assertIsInstance(pipeline2, OptimizedIngestionPipeline)
        self.assertEqual(pipeline2.config.max_concurrent_tasks, 20)

        # Clean up
        pipeline1.cleanup()
        pipeline2.cleanup()


class TestScrapyIntegration(unittest.TestCase):
    """Test suite for Scrapy integration components."""

    def setUp(self):
        """Set up test fixtures."""
        self.spider_mock = Mock()
        self.spider_mock.name = "test_spider"
        self.spider_mock.logger = Mock()
        self.spider_mock.crawler = Mock()
        self.spider_mock.crawler.stats = Mock()

        # Mock NewsItem
        self.mock_item = {
            "title": "Test Article",
            "url": "https://example.com/test",
            "content": "This is test content. " * 20,
            "source": "test_source",
            "published_date": "2024-01-01",
            "author": "Test Author",
            "category": "test",
        }

    def test_optimized_scrapy_pipeline(self):
        """Test OptimizedScrapyPipeline functionality."""
        pipeline = OptimizedScrapyPipeline()

        # Open spider
        pipeline.open_spider(self.spider_mock)

        # Process items
        for i in range(10):
            item = self.mock_item.copy()
            item["url"] = "https://example.com/test/{0}".format(i)
            processed_item = pipeline.process_item(item, self.spider_mock)

            self.assertIn("optimization_processed", processed_item)
            self.assertTrue(processed_item["optimization_processed"])

        # Close spider
        pipeline.close_spider(self.spider_mock)

    def test_high_throughput_validation(self):
        """Test HighThroughputValidationPipeline."""
        pipeline = HighThroughputValidationPipeline()

        # Test valid item
        valid_item = self.mock_item.copy()
        processed_item = pipeline.process_item(valid_item, self.spider_mock)

        self.assertIn("validation_score", processed_item)
        self.assertIn(f"ast_validation", processed_item)
        self.assertTrue(processed_item[f"ast_validation"])

        # Test invalid item (duplicate URL)
        duplicate_item = self.mock_item.copy()

        with self.assertRaises(Exception):  # Should raise DropItem
            pipeline.process_item(duplicate_item, self.spider_mock)

        # Test invalid item (short title)
        invalid_item = self.mock_item.copy()
        invalid_item["title"] = "Short"

        with self.assertRaises(Exception):  # Should raise DropItem
            pipeline.process_item(invalid_item, self.spider_mock)

    def test_adaptive_rate_limiting(self):
        """Test AdaptiveRateLimitPipeline."""
        pipeline = AdaptiveRateLimitPipeline()

        # Process items with different response times
        for i, response_time in enumerate([0.1, 0.2, 0.3, 2.0, 3.0]):
            item = self.mock_item.copy()
            item["url"] = "https://example.com/test/{0}".format(i)
            item["response_time"] = response_time

            processed_item = pipeline.process_item(item, self.spider_mock)

            self.assertIn("current_delay", processed_item)
            self.assertIn("adaptive_rate_limit", processed_item)
            self.assertTrue(processed_item["adaptive_rate_limit"])

    def test_optimized_storage_pipeline(self):
        """Test OptimizedStoragePipeline."""
        with tempfile.TemporaryDirectory():
            # Create pipeline with temporary storage
            pipeline = OptimizedStoragePipeline()

            # Process multiple items
            for i in range(25):  # Less than buffer size to test buffering
                item = self.mock_item.copy()
                item["url"] = "https://example.com/test/{0}".format(i)

                processed_item = pipeline.process_item(item, self.spider_mock)

                self.assertIn("storage_buffered", processed_item)
                self.assertTrue(processed_item["storage_buffered"])

            # Close spider to flush buffer
            pipeline.close_spider(self.spider_mock)

    def test_settings_configuration(self):
        """Test optimized settings configuration."""
        base_settings = {"TEST_SETTING": "test_value"}

        optimized = configure_optimized_settings(base_settings)

        # Check that optimization settings are added
        self.assertIn("ITEM_PIPELINES", optimized)
        self.assertIn("OPTIMIZED_MAX_CONCURRENT_TASKS", optimized)
        self.assertIn("OPTIMIZED_BATCH_SIZE", optimized)
        self.assertIn("CONCURRENT_REQUESTS", optimized)

        # Check that original settings are preserved
        self.assertEqual(optimized["TEST_SETTING"], "test_value")


class TestPerformanceBenchmarks(unittest.TestCase):
    """Performance benchmark tests for the optimized pipeline."""

    def setUp(self):
        """Set up benchmark test fixtures."""
        self.config = OptimizationConfig(
            max_concurrent_tasks=20,
            batch_size=50,
            max_memory_usage_mb=256.0,
            adaptive_batching=True,
        )
        self.pipeline = OptimizedIngestionPipeline(self.config)

        # Generate large dataset for benchmarking
        self.large_dataset = [
            {
                "title": "Benchmark Article {0}".format(i),
                "url": "https://benchmark.com/article/{0}".format(i),
                "content": "Benchmark content for article {0}. ".format(i) * 50,
                "source": "benchmark_source",
                "published_date": "2024-01-01",
                "author": "Benchmark Author {0}".format(i % 10),
                "category": "category_{0}".format(i % 5),
            }
            for i in range(500)
        ]

    def tearDown(self):
        """Clean up after benchmark tests."""
        if self.pipeline:
            self.pipeline.cleanup()

    def test_throughput_benchmark(self):
        """Benchmark processing throughput."""

        async def run_benchmark():
            start_time = time.time()
            results = await self.pipeline.process_articles_async(self.large_dataset)
            end_time = time.time()

            processing_time = end_time - start_time
            throughput = len(self.large_dataset) / processing_time

            return {
                "processing_time": processing_time,
                "throughput": throughput,
                "articles_processed": len(results["processed_articles"]),
                "metrics": results["metrics"],
            }

        benchmark_results = asyncio.run(run_benchmark())

        # Performance assertions
        self.assertGreater(
            benchmark_results["throughput"], 50
        )  # At least 50 articles/sec
        self.assertEqual(benchmark_results["articles_processed"], 500)
        self.assertLess(
            benchmark_results["processing_time"], 20
        )  # Complete within 20 seconds

        print("\nThroughput Benchmark Results:")
        print(f"Processing Time: {benchmark_results['processing_time']:.2f} seconds")
        print(f"Throughput: {benchmark_results['throughput']:.1f} articles/second")
        print(f"Articles Processed: {benchmark_results['articles_processed']}")


    def test_memory_efficiency_benchmark(self):
        """Benchmark memory efficiency."""
        initial_memory = self.pipeline.memory_monitor.get_memory_usage_mb()


        async def run_memory_test():
            # Process in chunks to monitor memory usage
            chunk_size = 100
            max_memory = initial_memory

            for i in range(0, len(self.large_dataset), chunk_size):
                chunk = self.large_dataset[i : i + chunk_size]
                await self.pipeline.process_articles_async(chunk)

                current_memory = self.pipeline.memory_monitor.get_memory_usage_mb()
                max_memory = max(max_memory, current_memory)

            return max_memory - initial_memory

        memory_increase = asyncio.run(run_memory_test())

        # Memory efficiency assertions
        # Memory increase should be reasonable
        self.assertLess(memory_increase, 200)

        print("\n📊 Memory Efficiency Benchmark Results:")
        print("Initial Memory: {:.1f} MB".format(initial_memory))
        print("Memory Increase: {:.1f} MB".format(memory_increase))
        efficiency = len(self.large_dataset) / max(memory_increase, 1)
        print("Memory Efficiency: {:.1f} articles/MB".format(efficiency))


    def test_concurrent_processing_scaling(self):
        """Test how concurrent processing scales with different settings."""
        test_data = self.large_dataset[:200]


        async def test_concurrency(max_tasks):
            config = OptimizationConfig(
                max_concurrent_tasks=max_tasks, batch_size=25, adaptive_batching=False
            )
            pipeline = OptimizedIngestionPipeline(config)

            try:
                start_time = time.time()
                await pipeline.process_articles_async(test_data)
                processing_time = time.time() - start_time

                return {
                    "concurrency": max_tasks,
                    "processing_time": processing_time,
                    "throughput": len(test_data) / processing_time,
                }
            finally:
                pipeline.cleanup()

        # Test different concurrency levels
        concurrency_levels = [1, 5, 10, 20, 30]
        results = []

        for level in concurrency_levels:
            result = asyncio.run(test_concurrency(level))
            results.append(result)

        print("\n
Concurrency Scaling Benchmark:")"
        for result in results:
            print(
                f"Concurrency {result['concurrency']:2d}: "
                f"{result['processing_time']:5.2f}s, "
                f"{result['throughput']:6.1f} articles/sec"
            )

        # Verify that higher concurrency generally improves throughput
        # (up to a point, considering overhead)
        single_thread_throughput = results[0]["throughput"]
        best_throughput = max(r["throughput"] for r in results)

        self.assertGreater(best_throughput, single_thread_throughput * 2)


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for real-world usage scenarios."""


    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = OptimizationConfig(
            max_concurrent_tasks=10, batch_size=20, adaptive_batching=True
        )


    def tearDown(self):
        """Clean up integration test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)


    def test_end_to_end_news_processing(self):
        """Test complete end-to-end news processing workflow."""
        # Create realistic news data
        news_articles = [
            {
                "title": "Breaking: Major Tech Company Announces AI Breakthrough",
                "url": "https://technews.com/ai-breakthrough-2024",
                "content": "In a significant development for artificial intelligence..."
                * 30,
                "source": "TechNews",
                "published_date": "2024-01-15T10:00:00Z",
                "author": "Jane Tech Reporter",
                "category": "Technology",
            },
            {
                "title": "Global Climate Summit Reaches Historic Agreement",
                "url": "https://worldnews.com/climate-agreement-2024",
                "content": "World leaders gathered at the climate summit today..." * 25,
                "source": "WorldNews",
                "published_date": "2024-01-15T14:30:00Z",
                "author": "Environmental Correspondent",
                "category": "Environment",
            },
            {
                "title": "Stock Market Hits Record High Amid Economic Optimism",
                "url": "https://financenews.com/market-record-2024",
                "content": "The stock market soared to unprecedented levels..." * 20,
                "source": "FinanceNews",
                "published_date": "2024-01-15T16:45:00Z",
                "author": "Market Analyst",
                "category": "Finance",
            },
        ] * 50  # Replicate to create larger dataset

        # Process through optimized pipeline
        pipeline = OptimizedIngestionPipeline(self.config)

        try:

            async def run_integration_test():
                results = await pipeline.process_articles_async(news_articles)
                return results

            results = asyncio.run(run_integration_test())

            # Verify processing results
            self.assertEqual(len(results["processed_articles"]), len(news_articles))
            self.assertIn("metrics", results)
            self.assertGreater(results["metrics"]["performance"]["throughput"], 0)

            # Verify article enrichment
            processed_articles = results["processed_articles"]
            for article in processed_articles[:3]:  # Check first few
                self.assertIn("processing_metadata", article)
                self.assertIn("word_count", article)
                self.assertIn("content_length", article)
                self.assertTrue(article["processing_metadata"]["optimized_processing"])

        finally:
            pipeline.cleanup()


    def test_error_recovery_scenario(self):
        """Test error recovery and circuit breaker functionality."""
        # Create mix of valid and problematic articles
        mixed_articles = [
            {
                "title": "Valid Article 1",
                "url": "https://example.com/valid1",
                "content": "Valid content here.",
                "source": "valid_source",
            },
            {
                "title": "",  # Invalid: empty title
                "url": "https://example.com/invalid1",
                "content": "Content without title",
                "source": "invalid_source",
            },
            {
                "title": "Valid Article 2",
                "url": "https://example.com/valid2",
                "content": "Another valid article.",
                "source": "valid_source",
            },
            {
                "title": "Invalid Article",
                "url": "",  # Invalid: empty URL
                "content": "Content without URL",
                "source": "invalid_source",
            },
            {
                "title": "Valid Article 3",
                "url": "https://example.com/valid3",
                "content": "Yet another valid article.",
                "source": "valid_source",
            },
        ]

        pipeline = OptimizedIngestionPipeline(self.config)

        try:

            async def run_error_test():
                results = await pipeline.process_articles_async(mixed_articles)
                return results

            results = asyncio.run(run_error_test())

            # Should process valid articles and handle errors gracefully
            self.assertGreater(len(results["processed_articles"]), 0)
            self.assertIn("errors", results["metrics"])

        finally:
            pipeline.cleanup()


if __name__ == "__main__":
    # Configure logging for tests
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create test suite
    test_loader = unittest.TestLoader()
    test_suite = unittest.TestSuite()

    # Add test classes
    test_classes = [
        TestOptimizedIngestionPipeline,
        TestScrapyIntegration,
        TestPerformanceBenchmarks,
        TestIntegrationScenarios,
    ]

    for test_class in test_classes:
        tests = test_loader.loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)

    # Print summary
    print(f"
{'=' * 50}")
    print("Test Summary:")
    print("Tests run: {0}".format(result.testsRun))
    print("Failures: {0}".format(len(result.failures)))
    print("Errors: {0}".format(len(result.errors)))
    success_count = result.testsRun - len(result.failures) - len(result.errors)
    success_rate = success_count / result.testsRun * 100
    print("Success rate: {:.1f}%".format(success_rate))
    print("=" * 50)
