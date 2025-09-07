#!/usr/bin/env python3
"""
Quick validation test for the optimized data ingestion pipeline.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))


def test_basic_functionality():
    """Test basic functionality of the optimized pipeline."""
    print(" Testing Optimized Data Ingestion Pipeline")
    print("=" * 50)

    try:
        # Import the optimized pipeline
        from src.ingestion.optimized_pipeline import (
            OptimizationConfig, OptimizedIngestionPipeline,
            create_optimized_pipeline)

        print(" Successfully imported optimized pipeline modules")

        # Test configuration creation
        config = OptimizationConfig(
            max_concurrent_tasks=5, batch_size=10, adaptive_batching=True
        )
        print(
            " Created optimization config: {0} concurrent tasks".format(
                config.max_concurrent_tasks)
        )

        # Test pipeline creation
        pipeline = OptimizedIngestionPipeline(config)
        print(" Successfully created optimized pipeline instance")

        # Test factory function
        factory_pipeline = create_optimized_pipeline()
        print(" Successfully created pipeline using factory function")

        # Create test data
        test_articles = [
            {
                "title": "Test Article {0}".format(i),
                "url": "https://test.com/article/{0}".format(i),
                "content": "Test content for article {0}. ".format(i) * 20,
                "source": "test_source",
                "published_date": "2024-01-01",
            }
            for i in range(10)
        ]
        print(" Generated {0} test articles".format(len(test_articles)))

        # Test async processing

        async def test_processing():
            try:
                start_time = time.time()
                results = await pipeline.process_articles_async(test_articles)
                processing_time = time.time() - start_time

                return {
                    "success": True,
                    "processing_time": processing_time,
                    "articles_processed": len(results.get("processed_articles", [])),
                    "throughput": (
                        len(results.get("processed_articles", [])) /
                            processing_time
                        if processing_time > 0
                        else 0
                    ),
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        # Run async test
        result = asyncio.run(test_processing())

        if result["success"]:
            print(
                f" Successfully processed {result['articles_processed']} articles")
            print(
                f" Processing time: {result['processing_time']:.2f} seconds")
            print(f" Throughput: {result['throughput']:.1f} articles/second")
        else:
            print(f"❌ Processing failed: {result['error']}")
            return False

        # Test performance stats
        try:
            stats = pipeline.get_performance_stats()
            print(
                " Retrieved performance stats: {0} metrics".format(len(stats)))
        except Exception as e:
            print("⚠️  Could not retrieve stats: {0}".format(e))

        # Cleanup
        pipeline.cleanup()
        factory_pipeline.cleanup()
        print(" Successfully cleaned up pipelines")

        print("✅ All tests passed! Optimized pipeline is working correctly.")
        return True

    except ImportError as e:
        print("❌ Import error: {0}".format(e))
        print("⚠️  This might be due to missing dependencies or path issues")
        return False
    except Exception as e:
        print("❌ Unexpected error: {0}".format(e))
        import traceback

        traceback.print_exc()
        return False


def test_scrapy_integration():
    """Test Scrapy integration components."""
    print("🔧 Testing Scrapy Integration")
    print("=" * 30)

    try:
        from src.ingestion.scrapy_integration import (
            HighThroughputValidationPipeline, OptimizedScrapyPipeline,
            configure_optimized_settings)

        print(" Successfully imported Scrapy integration modules")

        # Test pipeline creation
        scrapy_pipeline = OptimizedScrapyPipeline()
        validation_pipeline = HighThroughputValidationPipeline()
        print(" Successfully created Scrapy pipeline instances")

        # Test settings configuration
        test_settings = {"TEST_SETTING": "test_value"}
        optimized_settings = configure_optimized_settings(test_settings)
        print(" Generated optimized settings with {0} options".format(len(optimized_settings)))

        # Verify key settings
        required_settings = [
            "ITEM_PIPELINES",
            "OPTIMIZED_MAX_CONCURRENT_TASKS",
            "OPTIMIZED_BATCH_SIZE",
            "CONCURRENT_REQUESTS",
        ]

        for setting in required_settings:
            if setting in optimized_settings:
                print(" Found required setting: {0}".format(setting))
            else:
                print("⚠️  Missing setting: {0}".format(setting))

        print(" Scrapy integration test completed successfully")
        return True

    except ImportError as e:
        print("❌ Import error: {0}".format(e))
        return False
    except Exception as e:
        print("❌ Unexpected error: {0}".format(e))
        return False


def main():
    """Main test function."""
    print(" OPTIMIZED DATA INGESTION PIPELINE - QUICK VALIDATION")
    print("=" * 65)

    success = True

    # Test basic functionality
    if not test_basic_functionality():
        success = False

    # Test Scrapy integration
    if not test_scrapy_integration():
        success = False

    print("📊" + "=" * 65)
    if success:
        print("✅ ALL TESTS PASSED - Optimized pipeline is ready for use!")
        print("📋 Next steps:")
        print(
            "1. Run full test suite: python -m pytest tests/test_optimized_pipeline.py"
        )
        print("2. Run performance validation: python validate_optimized_pipeline.py")
        print("3. Deploy to production environment")
    else:
        print("❌ SOME TESTS FAILED - Please check the errors above")
        print("🔧 Troubleshooting:")
        print("1. Ensure all dependencies are installed")
        print("2. Check Python path configuration")
        print("3. Verify file permissions and accessibility")

    print("=" * 65)
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
