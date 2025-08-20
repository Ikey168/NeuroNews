#!/usr/bin/env python3
"""
Comprehensive containerized test demonstrating the superiority of this approach.
This replaces complex mocking with real service integration.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_database_operations():
    """Test advanced database operations that would be difficult to mock."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "test-postgres"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "neuronews_test"),
            user=os.getenv("DB_USER", "test_user"),
            password=os.getenv("DB_PASSWORD", "test_password"),
        )

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Create a test table
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS test_articles (
                    id SERIAL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert test data
            cur.execute(
                """
                INSERT INTO test_articles (title, content) 
                VALUES (%s, %s) RETURNING id
            """,
                ("Test Article", "This is test content"),
            )

            article_id = cur.fetchone()["id"]

            # Query with complex operations
            cur.execute(
                """
                SELECT id, title, 
                       length(content) as content_length,
                       created_at
                FROM test_articles 
                WHERE id = %s
            """,
                (article_id,),
            )

            result = cur.fetchone()

            # Verify results
            assert result["title"] == "Test Article"
            assert result["content_length"] == 20
            assert result["id"] == article_id

            # Clean up
            cur.execute("DROP TABLE test_articles")
            conn.commit()

        conn.close()
        logger.info("✅ Advanced database operations test passed")
        return True

    except Exception as e:
        logger.error("❌ Database operations test failed: {0}".format(e))
        return False


def test_redis_advanced():
    """Test Redis operations that demonstrate real service benefits."""
    try:
        import json

        import redis

        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "test-redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True,
        )

        # Test complex data structures
        test_data = {
            "articles": [
                {"id": 1, "title": "Article 1", "score": 0.95},
                {"id": 2, "title": "Article 2", "score": 0.87},
            ],
            "clusters": {"tech": [1, 2], "science": [3, 4]},
            "metadata": {"version": "1.0", "updated": time.time()},
        }

        # Store complex data
        r.setex("test:complex_data", 60, json.dumps(test_data))

        # Test list operations
        r.lpush("test:queue", "task1", "task2", "task3")
        queue_length = r.llen("test:queue")

        # Test set operations
        r.sadd("test:tags", "machine-learning", "nlp", "ai")
        tags_count = r.scard("test:tags")

        # Test hash operations
        r.hset(
            "test:article:1", mapping={"title": "ML Article", "views": 100, "likes": 25}
        )
        views = int(r.hget("test:article:1", "views"))

        # Verify all operations
        retrieved_data = json.loads(r.get("test:complex_data"))
        assert retrieved_data["articles"][0]["title"] == "Article 1"
        assert queue_length == 3
        assert tags_count == 3
        assert views == 100

        # Clean up
        r.delete("test:complex_data", "test:queue", "test:tags", "test:article:1")

        logger.info("✅ Advanced Redis operations test passed")
        return True

    except Exception as e:
        logger.error("❌ Redis advanced operations test failed: {0}".format(e))
        return False


def test_service_integration():
    """Test integration between services (impossible with mocking)."""
    try:
        import json

        import psycopg2
        import redis

        # Database connection
        db_conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "test-postgres"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "neuronews_test"),
            user=os.getenv("DB_USER", "test_user"),
            password=os.getenv("DB_PASSWORD", "test_password"),
        )

        # Redis connection
        redis_conn = redis.Redis(
            host=os.getenv("REDIS_HOST", "test-redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True,
        )

        # Create test table
        with db_conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS integration_test (
                    id SERIAL PRIMARY KEY,
                    data JSONB,
                    cache_key VARCHAR(100)
                )
            """
            )

            # Insert data
            cache_key = "integration_test:{0}".format(int(time.time()))
            test_data = {"integration": True, "timestamp": time.time()}

            cur.execute(
                """
                INSERT INTO integration_test (data, cache_key) 
                VALUES (%s, %s) RETURNING id
            """,
                (json.dumps(test_data), cache_key),
            )

            record_id = cur.fetchone()[0]
            db_conn.commit()

            # Cache the data in Redis
            redis_conn.setex(
                cache_key,
                300,
                json.dumps({"id": record_id, "data": test_data, "source": "database"}),
            )

            # Verify integration: Read from cache, verify in DB
            cached_data = json.loads(redis_conn.get(cache_key))
            assert cached_data["id"] == record_id

            cur.execute("SELECT data FROM integration_test WHERE id = %s", (record_id,))
            db_data = cur.fetchone()[0]
            assert db_data["integration"] == True

            # Clean up
            cur.execute("DROP TABLE integration_test")
            db_conn.commit()
            redis_conn.delete(cache_key)

        db_conn.close()
        logger.info("✅ Service integration test passed")
        return True

    except Exception as e:
        logger.error("❌ Service integration test failed: {0}".format(e))
        return False


def run_comprehensive_tests():
    """Run comprehensive tests demonstrating containerization benefits."""
    logger.info("🚀 Starting comprehensive containerized testing...")

    tests = [
        (
            "Environment Check",
            lambda: len(
                [
                    v
                    for v in [
                        "DB_HOST",
                        "DB_PORT",
                        "DB_NAME",
                        "DB_USER",
                        "DB_PASSWORD",
                        "REDIS_HOST",
                        "REDIS_PORT",
                    ]
                    if os.getenv(v)
                ]
            )
            == 7,
        ),
        ("Database Operations", test_database_operations),
        ("Redis Advanced", test_redis_advanced),
        ("Service Integration", test_service_integration),
    ]

    results = []
    for test_name, test_func in tests:
        logger.info("Running {0}...".format(test_name))
        try:
            result = test_func()
            results.append(result)
            if result:
                logger.info("✅ {0} PASSED".format(test_name))
            else:
                logger.error("❌ {0} FAILED".format(test_name))
        except Exception as e:
            logger.error("❌ {0} FAILED: {1}".format(test_name, e))
            results.append(False)

    passed = sum(results)
    total = len(results)

    logger.info(f"\n{'='*60}")
    logger.info("🏆 COMPREHENSIVE TEST RESULTS: {0}/{1} PASSED".format(passed, total))
    logger.info(f"{'='*60}")

    if passed == total:
        logger.info("🎉 ALL TESTS PASSED! Containerization approach validated!")
        logger.info("✨ Benefits demonstrated:")
        logger.info("   - Real service testing vs mocking")
        logger.info("   - Complex operations without fragile mocks")
        logger.info("   - Service integration testing")
        logger.info("   - Reproducible test environment")
        return True
    else:
        logger.error("❌ {0} tests failed".format(total - passed))
        return False


if __name__ == "__main__":
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)
