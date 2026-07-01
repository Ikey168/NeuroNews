"""Coverage-focused tests for src/scraper/dynamodb_failure_manager.py.

Targets branches the existing ``test_dynamodb_failure_manager.py`` leaves
uncovered:

* ``_ensure_table_exists`` when the table already exists (debug branch) and when
  a generic exception is raised.
* ``_create_table`` error handling.
* ``record_failure`` incrementing an existing record up to a permanent failure
  (retry_count >= max_retries) and its top-level exception fallback.
* Exception branches of ``get_urls_ready_for_retry``, ``mark_success``,
  ``mark_permanent_failure``, ``get_failure_statistics``, ``cleanup_old_failures``
  (including actual deletes) and ``get_failed_url_details``.

boto3 and moto are guarded with ``importorskip``.
"""

import os
import sys
import time

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

boto3 = pytest.importorskip("boto3")
pytest.importorskip("moto")
from moto import mock_aws  # noqa: E402

from scraper.dynamodb_failure_manager import (  # noqa: E402
    DynamoDBFailureManager,
    FailedUrl,
)


@pytest.fixture
def manager():
    with mock_aws():
        yield DynamoDBFailureManager(
            table_name="cov-failed-urls", region_name="us-east-1"
        )


class TestEnsureTable:
    def test_table_already_exists_debug_branch(self, manager):
        # The fixture already created the table; a second ensure hits the
        # describe_table success (debug) branch without creating again.
        manager._ensure_table_exists()  # must not raise

    def test_generic_exception_branch(self, monkeypatch):
        with mock_aws():
            mgr = DynamoDBFailureManager(table_name="cov-x", region_name="us-east-1")

        # Replace client with one that raises a non-ResourceNotFound error.
        class BadClient:
            class exceptions:
                class ResourceNotFoundException(Exception):
                    pass

            def describe_table(self, TableName):
                raise RuntimeError("network down")

        mgr.dynamodb = BadClient()
        # Generic exception is caught + logged.
        mgr._ensure_table_exists()

    def test_create_table_error_branch(self):
        with mock_aws():
            mgr = DynamoDBFailureManager(table_name="cov-y", region_name="us-east-1")

        class FailingCreate:
            def create_table(self, **kwargs):
                raise RuntimeError("cannot create")

        mgr.dynamodb = FailingCreate()
        # Error is caught + logged, no raise.
        mgr._create_table()


class TestRecordFailure:
    @pytest.mark.asyncio
    async def test_increment_to_permanent_failure(self, manager):
        manager.max_retries = 2
        first = await manager.record_failure("https://p.com/a", "timeout")
        assert first.retry_count == 1
        assert first.is_permanent_failure is False
        # Second failure reaches retry_count == max_retries -> permanent.
        second = await manager.record_failure("https://p.com/a", "timeout")
        assert second.retry_count >= second.max_retries
        assert second.is_permanent_failure is True
        assert second.next_retry_time == 0

    @pytest.mark.asyncio
    async def test_record_failure_exception_fallback(self, monkeypatch):
        with mock_aws():
            mgr = DynamoDBFailureManager(table_name="cov-z", region_name="us-east-1")

        class BadClient:
            def get_item(self, **kwargs):
                raise RuntimeError("boom")

        mgr.dynamodb = BadClient()
        result = await mgr.record_failure("https://err.com/a", "network")
        # Returns a basic FailedUrl even though storage failed.
        assert isinstance(result, FailedUrl)
        assert result.url == "https://err.com/a"
        assert result.failure_reason == "network"


class TestOperationErrorBranches:
    def _bad_manager(self):
        with mock_aws():
            mgr = DynamoDBFailureManager(table_name="cov-bad", region_name="us-east-1")

        class BadClient:
            def scan(self, **kwargs):
                raise RuntimeError("scan failed")

            def delete_item(self, **kwargs):
                raise RuntimeError("delete failed")

            def update_item(self, **kwargs):
                raise RuntimeError("update failed")

            def get_item(self, **kwargs):
                raise RuntimeError("get failed")

        mgr.dynamodb = BadClient()
        return mgr

    @pytest.mark.asyncio
    async def test_get_urls_ready_error_returns_empty(self):
        mgr = self._bad_manager()
        assert await mgr.get_urls_ready_for_retry(limit=5) == []

    @pytest.mark.asyncio
    async def test_mark_success_error(self):
        mgr = self._bad_manager()
        await mgr.mark_success("https://x.com/a")  # caught, no raise

    @pytest.mark.asyncio
    async def test_mark_permanent_failure_error(self):
        mgr = self._bad_manager()
        await mgr.mark_permanent_failure("https://x.com/a")  # caught, no raise

    @pytest.mark.asyncio
    async def test_statistics_error_returns_empty(self):
        mgr = self._bad_manager()
        assert await mgr.get_failure_statistics(hours=24) == {}

    @pytest.mark.asyncio
    async def test_cleanup_error(self):
        mgr = self._bad_manager()
        await mgr.cleanup_old_failures(days=30)  # caught, no raise

    @pytest.mark.asyncio
    async def test_get_details_error_returns_none(self):
        mgr = self._bad_manager()
        assert await mgr.get_failed_url_details("https://x.com/a") is None


class TestStatisticsAndCleanupRealData:
    @pytest.mark.asyncio
    async def test_statistics_aggregates_reasons_and_codes(self, manager):
        await manager.record_failure(
            "https://s.com/a", "timeout", response_code=500
        )
        await manager.record_failure(
            "https://s.com/b", "timeout", response_code=503
        )
        await manager.mark_permanent_failure("https://s.com/a")
        stats = await manager.get_failure_statistics(hours=24)
        assert stats["total_failures"] == 2
        assert stats["failure_reasons"]["timeout"] == 2
        assert 500 in stats["response_codes"]
        assert stats["permanent_failures"] >= 1

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_records(self, manager, monkeypatch):
        await manager.record_failure("https://old.com/a", "timeout")
        # Force the stored record to look ancient so the cleanup filter matches.
        # Simplest: cleanup with days negative so cutoff is in the future ->
        # every record's first_failure_time < cutoff -> deleted.
        await manager.cleanup_old_failures(days=-1)
        assert await manager.get_failed_url_details("https://old.com/a") is None
