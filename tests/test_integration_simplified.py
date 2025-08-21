#!/usr/bin/env python3
"""
Simplified test runner for containerized environment.
Replaces complex mocking with real service integration.
"""

import asyncio
import logging
import os
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_database_connection():
    """Test basic database connectivity."""
    try:
        from src.database.setup import get_async_connection

        async with get_async_connection(testing=True) as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1
            logger.info(" Database connection test passed")
            return True
    except Exception as e:
        logger.error("❌ Database connection test failed: {0}".format(e))
        return False


async def test_redis_connection():
    """Test Redis connectivity."""
    try:
        import redis.asyncio as redis

        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "test-redis"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            decode_responses=True,
        )

        await redis_client.set("test_key", "test_value")
        value = await redis_client.get("test_key")
        assert value == "test_value"
        await redis_client.delete("test_key")
        await redis_client.close()

        logger.info(" Redis connection test passed")
        return True
    except Exception as e:
        logger.error("❌ Redis connection test failed: {0}".format(e))
        return False


async def test_s3_connection():
    """Test S3/MinIO connectivity."""
    try:
        import boto3
        from botocore.config import Config

        s3_client = boto3.client(
            "s3",
            endpoint_url=os.getenv("S3_ENDPOINT", "http://test-minio:9000"),
            aws_access_key_id=os.getenv("S3_ACCESS_KEY", "testuser"),
            aws_secret_access_key=os.getenv("S3_SECRET_KEY", "testpassword"),
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )

        # Test bucket operations
        bucket_name = os.getenv("S3_BUCKET", "test-bucket")

        # Create bucket if it doesn't exist
        try:
            s3_client.head_bucket(Bucket=bucket_name)
        except BaseException:
            s3_client.create_bucket(Bucket=bucket_name)

        # Test put/get object
        s3_client.put_object(Bucket=bucket_name, Key="test_object.txt", Body=b"test content")

        response = s3_client.get_object(Bucket=bucket_name, Key="test_object.txt")
        content = response["Body"].read()
        assert content == b"test content"

        # Clean up
        s3_client.delete_object(Bucket=bucket_name, Key="test_object.txt")

        logger.info(" S3/MinIO connection test passed")
        return True
    except Exception as e:
        logger.error("❌ S3/MinIO connection test failed: {0}".format(e))
        return False


async def run_simplified_tests():
    """Run simplified integration tests without complex mocking."""
    logger.info(" Starting simplified integration tests...")

    # Test all service connections
    db_test = await test_database_connection()
    redis_test = await test_redis_connection()
    s3_test = await test_s3_connection()

    success_count = sum([db_test, redis_test, s3_test])
    total_tests = 3

    logger.info(" Test Results: {0}/{1} passed".format(success_count, total_tests))

    if success_count == total_tests:
        logger.info(" All integration tests passed!")
        return True
    else:
        logger.error("❌ Some integration tests failed")
        return False


def main():
    """Main test runner entry point."""
    # Set testing environment
    os.environ["TESTING"] = "true"

    # Run tests
    success = asyncio.run(run_simplified_tests())

    if not success:
        sys.exit(1)

    logger.info(" All tests completed successfully")


if __name__ == "__main__":
    main()
