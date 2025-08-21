#!/usr/bin/env python3
"""
Simple validation script for AsyncIO scraper implementation.
Tests basic functionality without requiring external dependencies.
"""

import asyncio
import json
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.append("/workspaces/NeuroNews/src")


def test_imports():
    """Test that all modules can be imported."""
    try:
        print("Testing imports...")

        # Test basic Python modules first
        import aiohttp

        print(" aiohttp imported")

        import asyncio

        print(" asyncio imported")

        # Test our modules
        from scraper.async_scraper_engine import AsyncNewsScraperEngine

        print(" AsyncNewsScraperEngine imported")

        from scraper.async_scraper_runner import AsyncScraperRunner

        print(" AsyncScraperRunner imported")

        from scraper.async_pipelines import AsyncPipelineProcessor

        print(" AsyncPipelineProcessor imported")

        from scraper.performance_monitor import PerformanceDashboard

        print(" PerformanceDashboard imported")

        print(" All imports successful!")
        return True

    except ImportError as e:
        print("❌ Import error: {0}".format(e))
        return False
    except Exception as e:
        print("❌ Unexpected error: {0}".format(e))
        return False


def test_config_loading():
    """Test configuration loading."""
    try:
        print(""
Testing config loading...")"

        config_path=Path("/workspaces/NeuroNews/src/scraper/config_async.json")

        if not config_path.exists():
            print("❌ Config file not found: {0}".format(config_path))
            return False

        with open(config_path, "r") as f:
            config=json.load(f)

        # Validate config structure
        required_sections=["async_scraper", "sources", "pipelines", "output"]
        for section in required_sections:
            if section not in config:
                print("❌ Missing config section: {0}".format(section))
                return False

        print(f" Config loaded with {len(config['sources'])} sources")
        print(f" Max concurrent: {config['async_scraper']['max_concurrent']}")
        print(f" Max threads: {config['async_scraper']['max_threads']}")

        return True

    except Exception as e:
        print("❌ Config loading error: {0}".format(e))
        return False


async def test_engine_creation():
    """Test async scraper engine creation."""
    try:
        print(""
Testing engine creation...")"

        # Import here to avoid import errors if previous tests fail
        from scraper.async_scraper_engine import AsyncNewsScraperEngine

        # Create engine with direct parameters (matching actual API)
        engine=AsyncNewsScraperEngine(max_concurrent=5, max_threads=2, headless=True)
        print(" Engine created successfully")

        # Test properties
        assert engine.max_concurrent == 5
        assert engine.max_threads == 2
        assert engine.headless is True
        print(" Engine properties validated")

        # Test that monitor is initialized
        assert engine.monitor is not None
        print(" Performance monitor initialized")

        # Don't start the engine (to avoid Playwright browser requirements)
        print(" Engine validation completed (skipping browser initialization)")'

        return True

    except Exception as e:
        print("❌ Engine creation error: {0}".format(e))
        return False


async def test_pipeline_creation():
    """Test pipeline processor creation."""
    try:
        print(""
Testing pipeline creation...")"

        from scraper.async_pipelines import AsyncPipelineProcessor

        # Create processor with direct parameters (matching actual API)
        processor = AsyncPipelineProcessor(max_threads=2)
        print(" Pipeline processor created successfully")

        # Test article validation
        test_article = {
            "title": "Test Article Title",
            "content": "This is a test article with sufficient content for validation.",
            "url": "https://example.com/test",
            "source": "Test Source",
        }

        is_valid = await processor.validate_article_async(test_article)
        print(" Article validation: {0}".format(is_valid))

        return True

    except Exception as e:
        print("❌ Pipeline creation error: {0}".format(e))
        return False


def test_monitor_creation():
    """Test performance monitor creation."""
    try:
        print(""
Testing monitor creation...")"

        from scraper.performance_monitor import PerformanceDashboard

        monitor = PerformanceDashboard(update_interval=5)
        print(" Performance monitor created successfully")

        # Test recording metrics (using correct API)
        monitor.record_article("Test Source", response_time=1.5)
        monitor.record_request(success=True, response_time=1.5, source="Test Source")

        stats = monitor.get_performance_stats()

        assert stats["total_articles"] == 1
        assert stats["successful_requests"] == 1
        print(" Metrics recording validated")

        return True

    except Exception as e:
        print("❌ Monitor creation error: {0}".format(e))
        return False


async def test_basic_functionality():
    """Test basic async functionality."""
    try:
        print(""
Testing basic async functionality...")"

        # Test AsyncIO operations

        async def test_task(delay, name):
            await asyncio.sleep(delay)
            return "Task {0} completed".format(name)

        start_time = time.time()

        # Run tasks concurrently
        tasks = [test_task(0.1, "A"), test_task(0.1, "B"), test_task(0.1, "C")]

        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time

        assert len(results) == 3
        assert duration < 0.5  # Should complete concurrently, not sequentially
        print(" AsyncIO concurrency validated ({0}s)".format(duration:.2f))

        return True

    except Exception as e:
        print("❌ Basic functionality error: {0}".format(e))
        return False


async def main():
    """Run all validation tests."""
    print(" AsyncIO Scraper Validation Tests")
    print("=" * 40)

    tests = [
        ("Import Test", test_imports),
        ("Config Loading", test_config_loading),
        ("Engine Creation", test_engine_creation),
        ("Pipeline Creation", test_pipeline_creation),
        ("Monitor Creation", test_monitor_creation),
        ("Basic AsyncIO", test_basic_functionality),
    ]

    results = {}

    for test_name, test_func in tests:
        print(""
 Running {0}...".format(test_name))"
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results[test_name] = result
        except Exception as e:
            print("❌ {0} failed with exception: {1}".format(test_name, e))
            results[test_name] = False

    # Summary
    print(""
" + "=" * 40)
    print(" Test Results Summary:")
    print("=" * 40)"

    passed = 0
    total = len(results)

    for test_name, result in results.items():
        status = " PASS" if result else "❌ FAIL"
        print("{0} {1}".format(test_name:<20, status))
        if result:
            passed += 1

    print("=" * 40)
    print("Tests passed: {0}/{1}".format(passed, total))

    if passed == total:
        print(" All tests passed! AsyncIO scraper is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
