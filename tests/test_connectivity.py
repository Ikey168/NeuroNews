#!/usr/bin/env python3
"""
Lightweight test runner for basic connectivity tests.
This version excludes heavy ML dependencies to test core functionality.
"""

import logging
import os
import sys
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def wait_for_service(host, port, timeout=30):
    """Wait for a service to become available."""
    import socket

    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                logger.info("✅ Service {0}:{1} is ready".format(host, port))
                return True

        except Exception as e:
            logger.debug("Waiting for {0}:{1} - {2}".format(host, port, e))

        time.sleep(1)

    logger.error(
        "❌ Service {0}:{1} did not become ready within {2}s".format(
            host, port, timeout
        )
    )
    return False


def test_database_basic():
    """Test basic database connectivity with psycopg2."""
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "test-postgres"),
            port=int(os.getenv("DB_PORT", 5432)),
            database=os.getenv("DB_NAME", "neuronews_test"),
            user=os.getenv("DB_USER", "test_user"),
            password=os.getenv("DB_PASSWORD", "test_password"),
        )

        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()

        cur.close()
        conn.close()

        assert result[0] == 1
        logger.info("✅ Database connection test passed")
        return True

    except Exception as e:
        logger.error("❌ Database connection test failed: {0}".format(e))
        return False


def test_redis_basic():
    """Test basic Redis connectivity."""
    try:
        import redis

        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "test-redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True,
        )

        # Test basic operations
        r.set("test_key", "test_value")
        value = r.get("test_key")
        r.delete("test_key")

        assert value == "test_value"
        logger.info("✅ Redis connection test passed")
        return True

    except Exception as e:
        logger.error("❌ Redis connection test failed: {0}".format(e))
        return False


def test_environment():
    """Test environment variables are set correctly."""
    required_vars = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD",
        "REDIS_HOST",
        "REDIS_PORT",
        "S3_ENDPOINT",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_BUCKET",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        logger.error("❌ Missing environment variables: {0}".format(missing_vars))
        return False

    logger.info("✅ All required environment variables are set")
    return True


def run_basic_tests():
    """Run basic connectivity tests."""
    logger.info("🚀 Starting lightweight connectivity tests...")

    # Test environment
    env_test = test_environment()

    # Wait for services
    db_ready = wait_for_service(
        os.getenv("DB_HOST", "test-postgres"), int(os.getenv("DB_PORT", 5432))
    )

    redis_ready = wait_for_service(
        os.getenv("REDIS_HOST", "test-redis"), int(os.getenv("REDIS_PORT", 6379))
    )

    # Run tests
    tests_passed = []
    if db_ready:
        tests_passed.append(test_database_basic())
    else:
        tests_passed.append(False)

    if redis_ready:
        tests_passed.append(test_redis_basic())
    else:
        tests_passed.append(False)

    # Results
    total_tests = len(tests_passed) + 1  # +1 for env test
    passed_tests = sum(tests_passed) + (1 if env_test else 0)

    logger.info("📊 Test Results: {0}/{1} passed".format(passed_tests, total_tests))

    if passed_tests == total_tests:
        logger.info("🎉 All basic tests passed!")
        return True
    else:
        logger.error("❌ {0} tests failed".format(total_tests - passed_tests))
        return False


def main():
    """Main test entry point."""
    success = run_basic_tests()

    if not success:
        sys.exit(1)

    logger.info("✅ Basic connectivity tests completed successfully")


if __name__ == "__main__":
    main()
