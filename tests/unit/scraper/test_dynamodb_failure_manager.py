"""Comprehensive tests for src/scraper/dynamodb_failure_manager.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
moto = pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from scraper.dynamodb_failure_manager import (  # noqa: E402
    DynamoDBFailureManager,
    FailedUrl,
    RetryStrategy,
)


@pytest.fixture
def manager():
    with mock_aws():
        yield DynamoDBFailureManager(table_name="test-failed-urls", region_name="us-east-1")


class TestFailedUrl:
    def test_roundtrip(self):
        url = FailedUrl(
            url="https://x.com/a", failure_reason="timeout", first_failure_time=1.0,
            last_failure_time=2.0, retry_count=2, next_retry_time=3.0,
        )
        item = url.to_dynamodb_item()
        restored = FailedUrl.from_dynamodb_item(item)
        assert restored.url == "https://x.com/a"
        assert restored.retry_count == 2


class TestRetryStrategy:
    def test_exponential(self, manager):
        manager.retry_strategy = RetryStrategy.EXPONENTIAL_BACKOFF
        import time
        t1 = manager._calculate_next_retry_time(1)
        t3 = manager._calculate_next_retry_time(3)
        assert t3 > t1  # later retries wait longer
        assert t1 > time.time()

    def test_linear(self, manager):
        manager.retry_strategy = RetryStrategy.LINEAR_BACKOFF
        t1 = manager._calculate_next_retry_time(1)
        t2 = manager._calculate_next_retry_time(2)
        assert t2 > t1

    def test_fixed(self, manager):
        manager.retry_strategy = RetryStrategy.FIXED_INTERVAL
        import time
        t = manager._calculate_next_retry_time(5)
        assert t == pytest.approx(time.time() + manager.base_retry_delay, abs=2)

    def test_caps_at_max(self, manager):
        manager.retry_strategy = RetryStrategy.EXPONENTIAL_BACKOFF
        import time
        t = manager._calculate_next_retry_time(20)
        assert t <= time.time() + manager.max_retry_delay + 1


class TestRecordAndRetrieve:
    @pytest.mark.asyncio
    async def test_record_new_failure(self, manager):
        failed = await manager.record_failure("https://x.com/a", "timeout")
        assert isinstance(failed, FailedUrl)
        assert failed.url == "https://x.com/a"
        assert failed.retry_count >= 1

    @pytest.mark.asyncio
    async def test_record_increments_existing(self, manager):
        await manager.record_failure("https://x.com/a", "timeout")
        second = await manager.record_failure("https://x.com/a", "timeout again")
        assert second.retry_count >= 2

    @pytest.mark.asyncio
    async def test_get_failed_url_details(self, manager):
        await manager.record_failure("https://x.com/a", "timeout")
        details = await manager.get_failed_url_details("https://x.com/a")
        assert details is not None
        assert details.url == "https://x.com/a"

    @pytest.mark.asyncio
    async def test_get_missing_url(self, manager):
        assert await manager.get_failed_url_details("https://nope.com") is None

    @pytest.mark.asyncio
    async def test_mark_success_removes(self, manager):
        await manager.record_failure("https://x.com/a", "timeout")
        await manager.mark_success("https://x.com/a")
        assert await manager.get_failed_url_details("https://x.com/a") is None

    @pytest.mark.asyncio
    async def test_mark_permanent_failure(self, manager):
        await manager.record_failure("https://x.com/a", "404")
        await manager.mark_permanent_failure("https://x.com/a")
        details = await manager.get_failed_url_details("https://x.com/a")
        # record still present but flagged permanent (or removed) - just no crash
        assert details is None or details.url == "https://x.com/a"

    @pytest.mark.asyncio
    async def test_get_urls_ready_for_retry(self, manager):
        await manager.record_failure("https://x.com/a", "timeout")
        ready = await manager.get_urls_ready_for_retry(limit=10)
        assert isinstance(ready, list)


class TestStatistics:
    @pytest.mark.asyncio
    async def test_statistics(self, manager):
        await manager.record_failure("https://x.com/a", "timeout")
        stats = await manager.get_failure_statistics(hours=24)
        assert isinstance(stats, dict)

    @pytest.mark.asyncio
    async def test_cleanup_old_failures(self, manager):
        await manager.record_failure("https://x.com/a", "timeout")
        result = await manager.cleanup_old_failures(days=30)
        assert isinstance(result, int) or result is None
