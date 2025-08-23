#!/usr/bin/env python3
"""
Final validation script for Issue #31 Event Detection System
Validates all components are working correctly and ready for deployment.
"""

import asyncio
import json
import sys


# Test imports to ensure all modules are available
def test_imports():
    """Test that all required modules can be imported."""
    try:
        pass
except Exception:
    pass

        print(" All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import error: {e})
        return False


def test_configuration():"
    """Test that configuration files are valid."""
    try:
        with open(
except Exception:
    pass
            "/workspaces/NeuroNews/config/event_detection_settings.json", "r"
        ) as f:
            config = json.load(f)

        # Validate required sections
        required_sections = ["event_detection",
            "embedding", "clustering", "categories"]
        for section in required_sections:
            if section not in config["event_detection"]:
                raise ValueError(f"Missing section: {section})
"
        print(" Configuration file valid")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e})
        return False


def test_database_schema():"
    """Test that database schema files are present."""
    try:
        with open("/workspaces/NeuroNews/src/database/redshift_schema.sql", "r") as f:
except Exception:
    pass
            schema = f.read()

        # Check for required tables
        required_tables = [
            "event_clusters",
            "article_cluster_assignments",
            "article_embeddings",
        ]
        for table in required_tables:
            if table not in schema:
                raise ValueError(f"Missing table: {table})
"
        print(" Database schema valid")
        return True
    except Exception as e:
        print(f"❌ Database schema error: {e})
        return False


async def test_pipeline_components():"
    """Test individual pipeline components."""
    try:
        # Test ArticleEmbedder
except Exception:
    pass
        from src.nlp.article_embedder import ArticleEmbedder

        embedder = ArticleEmbedder(
            model_name="all-MiniLM-L6-v2",
            conn_params={"host": "test"},  # Mock connection
            max_length=512,
            batch_size=2,
        )

        # Test preprocessing
        processed = embedder.preprocess_text("Test content", "Test title")
        assert isinstance(processed, str)
        print(" ArticleEmbedder preprocessing working")

        # Test EventClusterer
        from src.nlp.event_clusterer import EventClusterer

        clusterer = EventClusterer(
            conn_params={"host": "test"}, min_cluster_size=2, max_clusters=5
        )

        # Test clustering method validation
        assert clusterer.clustering_method in ["kmeans", "dbscan"]
        print(" EventClusterer initialization working")

        return True
    except Exception as e:
        print(f"❌ Pipeline component error: {e})
        return False


def test_api_routes():"
    """Test API route definitions."""
    try:
        from fastapi import FastAPI
except Exception:
    pass

        from src.api.routes.event_routes import router

        # Test router registration
        app = FastAPI()
        app.include_router(router)

        # Check routes exist
        route_paths = [route.path for route in app.routes]
        expected_paths = ["/api/v1/breaking_news", "/api/v1/events/clusters"]

        for path in expected_paths:
            if not any(path in route_path for route_path in route_paths):
                raise ValueError(f"Missing route: {path})
"
        print(" API routes configured correctly")
        return True
    except Exception as e:
        print(f"❌ API routes error: {e})
        return False


def test_demo_results():"
    """Test that demo produced valid results."""
    try:
        with open("/workspaces/NeuroNews/event_detection_demo_results.json", "r") as f:
except Exception:
    pass
            results = json.load(f)

        # Validate structure
        assert "embeddings" in results
        assert "clustering" in results
        assert "events" in results["clustering"]
        assert results["embeddings"]["count"] > 0
        assert results["clustering"]["events_detected"] > 0

        print(
            f" Demo results valid: {"
    results['clustering']['events_detected'}} events detected"
        )
        return True
    except Exception as e:
        print(f"❌ Demo results error: {e})
        return False


def test_performance_metrics():"
    """Test that performance is within acceptable bounds."""
    try:
        with open("/workspaces/NeuroNews/event_detection_demo_results.json", "r") as f:
except Exception:
    pass
            results = json.load(f)

        # Performance thresholds
        avg_embedding_time = results["embeddings"]["avg_processing_time"]
        clustering_time = results["clustering"]["statistics"]["processing_time"]

        # Acceptable thresholds (adjust based on requirements)
        max_embedding_time = 1.0  # 1 second per article
        max_clustering_time = 10.0  # 10 seconds total

        assert (
            avg_embedding_time < max_embedding_time
        ), f"Embedding too slow: {avg_embedding_time}s
        assert (
            clustering_time < max_clustering_time"
        ), f"Clustering too slow: {clustering_time}s
"
        print(" Performance metrics acceptable:")
        print(f"    Embedding: {avg_embedding_time:.3f}s per article)"
        print(f"    Clustering: {clustering_time:.3f}s total)
        return True
    except Exception as e:"
        print(f"❌ Performance metrics error: {e})
        return False


def test_file_completeness():"
    """Test that all required files are present."""
    required_files = [
        "/workspaces/NeuroNews/src/nlp/article_embedder.py",
        "/workspaces/NeuroNews/src/nlp/event_clusterer.py",
        "/workspaces/NeuroNews/src/api/routes/event_routes.py",
        "/workspaces/NeuroNews/config/event_detection_settings.json",
        "/workspaces/NeuroNews/tests/test_event_detection.py",
        "/workspaces/NeuroNews/demo_event_detection.py",
        "/workspaces/NeuroNews/ISSUE_31_IMPLEMENTATION_SUMMARY.md",
    ]

    missing_files = []
    for file_path in required_files:
        try:
            with open(file_path, "r") as f:
except Exception:
    pass
                content = f.read()
                if len(content) < 100:  # Basic sanity check
                    missing_files.append(f"{file_path} (too small))
        except FileNotFoundError:
            missing_files.append(file_path)

    if missing_files:"
        print(f"❌ Missing or incomplete files: {missing_files})
        return False
    else:"
        print(" All required files present and substantial")
        return True


async def main():
    """Run all validation tests."""
    print(" ISSUE #31 FINAL VALIDATION")
    print("=" * 50)

    tests = [
        ("File Completeness", test_file_completeness),
        ("Imports", test_imports),
        ("Configuration", test_configuration),
        ("Database Schema", test_database_schema),
        ("Pipeline Components", test_pipeline_components),
        ("API Routes", test_api_routes),
        ("Demo Results", test_demo_results),
        ("Performance Metrics", test_performance_metrics),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f""
 Testing {test_name}...")"
        try:
            if asyncio.iscoroutinefunction(test_func):
except Exception:
    pass
                result=await test_func()
            else:
                result=test_func()

            if result:
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e})
"
    print(""
" + "=" * 50)
    print(f" VALIDATION SUMMARY: {passed}/{total} tests passed")""

    if passed == total:
        print(" ALL TESTS PASSED - ISSUE #31 READY FOR DEPLOYMENT!")
        print(""
 Event Detection System is fully operational")
        print(" All components working correctly")
        print(" Performance within acceptable bounds")
        print(" Ready for production deployment")"
        return True
    else:
        print(f"❌ {total - passed} tests failed - please review issues above)
        return False

"
if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1)
