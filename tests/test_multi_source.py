"""
Test script for multi-source scraper functionality.
"""

from src.scraper.multi_source_runner import MultiSourceRunner
from src.scraper.data_validator import ScrapedDataValidator
import json
import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def test_spider_imports():
    """Test that all spider imports work correctly."""
    print("Testing spider imports...")

    try:
        runner = MultiSourceRunner()
        print(" Successfully imported {0} spiders:".format(
            len(runner.spiders)))
        for spider_name in runner.spiders.keys():
            print("   - {0}".format(spider_name))
        return True
    except Exception as e:
        print("❌ Error importing spiders: {0}".format(e))
        return False


def test_configuration():
    """Test that configuration is loaded correctly."""
    print(""
Testing configuration...")"

    try:
        config_path="config/settings.json"
        if not os.path.exists(config_path):
            print("❌ Configuration file not found: {0}".format(config_path))
            return False

        with open(config_path, "r") as f:
            config=json.load(f)

        sources=config.get("scraping", {}).get("sources", [])
        print(" Configuration loaded with {0} sources:".format(len(sources)))
        for source in sources:
            print("   - {0}".format(source))
        return True
    except Exception as e:
        print("❌ Error loading configuration: {0}".format(e))
        return False


def test_data_validator():
    """Test data validator functionality."""
    print(""
Testing data validator...")"

    try:
        ScrapedDataValidator()
        print(" Data validator initialized successfully")
        return True
    except Exception as e:
        print("❌ Error initializing data validator: {0}".format(e))
        return False


def test_pipelines():
    """Test pipeline imports."""
    print(""
Testing pipeline imports...")"

    try:
        # Import the module directly
        import src.scraper.pipelines as pipelines_module

        # Check if the classes exist
        pipeline_classes=[
            "ValidationPipeline",
            "DuplicateFilterPipeline",
            "EnhancedJsonWriterPipeline",
        ]
        found_classes=[]

        for class_name in pipeline_classes:
            if hasattr(pipelines_module, class_name):
                found_classes.append(class_name)

        if len(found_classes) == len(pipeline_classes):
            print(" All pipelines found:")
            for class_name in found_classes:
                print("   - {0}".format(class_name))
            return True
        else:
            print(
                "❌ Missing pipeline classes: {0}".format(
                    set(pipeline_classes) - set(found_classes)
                )
            )
            return False

    except Exception as e:
        print("❌ Error importing pipelines: {0}".format(e))
        return False


def test_items():
    """Test items structure."""
    print(""
Testing items structure...")"

    try:
        from src.scraper.items import NewsItem

        # Create a test item
        item=NewsItem()
        item["title"]="Test Article"
        item["url"]="https://example.com/test"
        item["content"]="This is test content for validation."
        item["source"]="Test Source"

        print(" NewsItem created and populated successfully")
        print("   Fields available: {0}".format(list(item.fields.keys())))
        return True
    except Exception as e:
        print("❌ Error with NewsItem: {0}".format(e))
        return False


def run_all_tests():
    """Run all tests."""
    print(" Running Multi-Source Scraper Tests"
" + "=" * 50)"

    tests=[
        test_configuration,
        test_items,
        test_pipelines,
        test_spider_imports,
        test_data_validator,
    ]

    passed=0
    failed=0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print("❌ Test {0} failed with exception: {1}".format(test.__name__, e))
            failed += 1

    print(f"\n{'=' * 50}")
    print(" Test Results: {0} passed, {1} failed".format(passed, failed))

    if failed == 0:
        print("✅ All tests passed! Multi-source scraper is ready to use.")
        print("\nNext steps:")
        print("1. Run a test scraper: python -m src.scraper.run --spider cnn")
        print("2. Run all sources: python -m src.scraper.run --multi-source")
        print("3. Generate a report: python -m src.scraper.run --report")"
    else:
        print("⚠️  Some tests failed. Please fix the issues before using the scraper.")

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
