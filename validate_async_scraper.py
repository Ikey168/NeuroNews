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
sys.path.append('/home/runner/work/NeuroNews/NeuroNews/src')

def test_imports():
    """Test that all modules can be imported."""
    try:
        print("Testing imports...")
        
        # Test basic Python modules first
        import aiohttp
        print("✅ aiohttp imported")
        
        import asyncio
        print("✅ asyncio imported")
        
        # Test our modules
        from scraper.async_scraper_engine import AsyncNewsScraperEngine
        print("✅ AsyncNewsScraperEngine imported")
        
        from scraper.async_scraper_runner import AsyncScraperRunner
        print("✅ AsyncScraperRunner imported")
        
        from scraper.async_pipelines import AsyncPipelineProcessor
        print("✅ AsyncPipelineProcessor imported")
        
        from scraper.performance_monitor import PerformanceDashboard
        print("✅ PerformanceDashboard imported")
        
        print("✅ All imports successful!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_config_loading():
    """Test configuration loading."""
    try:
        print("\nTesting config loading...")
        
        config_path = Path('/home/runner/work/NeuroNews/NeuroNews/src/scraper/config_async.json')
        
        if not config_path.exists():
            print(f"❌ Config file not found: {config_path}")
            return False
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Validate config structure
        required_sections = ['async_scraper', 'sources', 'pipelines', 'output']
        for section in required_sections:
            if section not in config:
                print(f"❌ Missing config section: {section}")
                return False
        
        print(f"✅ Config loaded with {len(config['sources'])} sources")
        print(f"✅ Max concurrent: {config['async_scraper']['max_concurrent']}")
        print(f"✅ Max threads: {config['async_scraper']['max_threads']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Config loading error: {e}")
        return False

async def test_engine_creation():
    """Test async scraper engine creation."""
    try:
        print("\nTesting engine creation...")
        
        # Import here to avoid import errors if previous tests fail
        from scraper.async_scraper_engine import AsyncNewsScraperEngine
        
        # Simple test config
        config = {
            'async_scraper': {
                'max_concurrent': 5,
                'max_threads': 2,
                'headless': True,
                'timeout': 10,
                'retry_attempts': 2,
                'rate_limiting': {
                    'default_rate': 1.0,
                    'burst_size': 3
                }
            },
            'sources': [
                {
                    'name': 'Test Source',
                    'base_url': 'https://httpbin.org',
                    'article_selectors': {
                        'title': 'h1',
                        'content': 'p'
                    },
                    'requires_js': False,
                    'enabled': True
                }
            ]
        }
        
        # Create engine
        engine = AsyncNewsScraperEngine(config)
        print("✅ Engine created successfully")
        
        # Test properties
        assert engine.max_concurrent == 5
        assert engine.max_threads == 2
        assert len(engine.sources) == 1
        print("✅ Engine properties validated")
        
        # Cleanup
        await engine.cleanup()
        print("✅ Engine cleanup successful")
        
        return True
        
    except Exception as e:
        print(f"❌ Engine creation error: {e}")
        return False

async def test_pipeline_creation():
    """Test pipeline processor creation."""
    try:
        print("\nTesting pipeline creation...")
        
        from scraper.async_pipelines import AsyncPipelineProcessor
        
        config = {
            'pipelines': {
                'validation': {
                    'enabled': True,
                    'min_content_length': 50
                },
                'duplicate_detection': {
                    'enabled': True,
                    'title_similarity_threshold': 0.8
                },
                'enhancement': {
                    'enabled': True,
                    'category_extraction': True
                }
            }
        }
        
        processor = AsyncPipelineProcessor(config, max_workers=2)
        print("✅ Pipeline processor created successfully")
        
        # Test article validation
        test_article = {
            'title': 'Test Article Title',
            'content': 'This is a test article with sufficient content for validation.',
            'url': 'https://example.com/test',
            'source': 'Test Source'
        }
        
        is_valid = await processor._validate_article(test_article)
        print(f"✅ Article validation: {is_valid}")
        
        return True
        
    except Exception as e:
        print(f"❌ Pipeline creation error: {e}")
        return False

def test_monitor_creation():
    """Test performance monitor creation."""
    try:
        print("\nTesting monitor creation...")
        
        from scraper.performance_monitor import PerformanceDashboard
        
        monitor = PerformanceDashboard(update_interval=5)
        print("✅ Performance monitor created successfully")
        
        # Test recording metrics
        monitor.record_article('Test Source', success=True, response_time=1.5)
        stats = monitor.get_stats()
        
        assert stats['total_articles'] == 1
        assert stats['successful_articles'] == 1
        print("✅ Metrics recording validated")
        
        # Test system info
        system_info = monitor.get_system_info()
        assert 'cpu_percent' in system_info
        assert 'memory_percent' in system_info
        print("✅ System info retrieval validated")
        
        return True
        
    except Exception as e:
        print(f"❌ Monitor creation error: {e}")
        return False

async def test_basic_functionality():
    """Test basic async functionality."""
    try:
        print("\nTesting basic async functionality...")
        
        # Test AsyncIO operations
        async def test_task(delay, name):
            await asyncio.sleep(delay)
            return f"Task {name} completed"
        
        start_time = time.time()
        
        # Run tasks concurrently
        tasks = [
            test_task(0.1, "A"),
            test_task(0.1, "B"),
            test_task(0.1, "C")
        ]
        
        results = await asyncio.gather(*tasks)
        duration = time.time() - start_time
        
        assert len(results) == 3
        assert duration < 0.5  # Should complete concurrently, not sequentially
        print(f"✅ AsyncIO concurrency validated ({duration:.2f}s)")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic functionality error: {e}")
        return False

async def main():
    """Run all validation tests."""
    print("🧪 AsyncIO Scraper Validation Tests")
    print("=" * 40)
    
    tests = [
        ("Import Test", test_imports),
        ("Config Loading", test_config_loading),
        ("Engine Creation", test_engine_creation),
        ("Pipeline Creation", test_pipeline_creation),
        ("Monitor Creation", test_monitor_creation),
        ("Basic AsyncIO", test_basic_functionality)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n🔍 Running {test_name}...")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "=" * 40)
    print("📊 Test Results Summary:")
    print("=" * 40)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1
    
    print("=" * 40)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! AsyncIO scraper is ready to use.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == '__main__':
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
