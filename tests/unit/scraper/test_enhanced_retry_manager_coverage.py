"""Coverage-focused tests for src/scraper/enhanced_retry_manager.py.

The existing ``test_enhanced_retry_manager.py`` runs the manager with all AWS
collaborators set to ``None`` (no-op recording paths). This file wires in mocked
collaborators (CloudWatch logger, DynamoDB failure manager, SNS alert manager) so
the recording branches actually execute:

* ``_record_success`` -> cloudwatch log + failure_manager.mark_success
* ``_record_retry_attempt`` -> cloudwatch log
* ``_record_final_failure`` -> cloudwatch + failure_manager.record_failure + alert
* ``_record_permanent_failure`` -> cloudwatch + failure_manager.record_failure +
  mark_permanent_failure
* ``process_retry_queue`` (no manager, populated queue, circuit-breaker skip, and
  per-URL error handling)
* ``get_retry_statistics`` with a failure manager (success + error paths)
* ``_get_domain_from_url`` exception fallback.

No real AWS; collaborators are ``AsyncMock``/``MagicMock``.
"""

import os
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.enhanced_retry_manager import (  # noqa: E402
    EnhancedRetryManager,
    RetryConfig,
    RetryReason,
)


class StatusError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


def make_manager(**collaborators):
    cfg = RetryConfig(jitter=False, base_delay=0.0, max_retries=2)
    return EnhancedRetryManager(retry_config=cfg, **collaborators)


class TestRecordingCollaborators:
    @pytest.mark.asyncio
    async def test_success_records_cloudwatch_and_marks_success(self):
        cw = MagicMock()
        cw.log_scraping_attempt = AsyncMock()
        fm = MagicMock()
        fm.mark_success = AsyncMock()
        mgr = make_manager(cloudwatch_logger=cw, failure_manager=fm)

        async def ok():
            return "value"

        result = await mgr.retry_with_backoff(
            ok, url="https://ok.com/a", context={"articles_scraped": 2}
        )
        assert result == "value"
        cw.log_scraping_attempt.assert_awaited()
        fm.mark_success.assert_awaited_once_with("https://ok.com/a")

    @pytest.mark.asyncio
    async def test_retry_then_final_failure_records_all(self):
        cw = MagicMock()
        cw.log_scraping_attempt = AsyncMock()
        fm = MagicMock()
        fm.record_failure = AsyncMock()
        fm.mark_success = AsyncMock()
        alert = MagicMock()
        alert.alert_scraper_failure = AsyncMock()
        mgr = make_manager(
            cloudwatch_logger=cw, failure_manager=fm, alert_manager=alert
        )

        async def always_fail():
            raise Exception("server error 500")

        with pytest.raises(Exception):
            await mgr.retry_with_backoff(always_fail, url="https://f.com/a")

        # At least one retry attempt was logged, plus the final failure recorded.
        assert cw.log_scraping_attempt.await_count >= 1
        fm.record_failure.assert_awaited()
        alert.alert_scraper_failure.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_permanent_failure_records_and_marks_permanent(self):
        cw = MagicMock()
        cw.log_scraping_attempt = AsyncMock()
        fm = MagicMock()
        fm.record_failure = AsyncMock()
        fm.mark_permanent_failure = AsyncMock()
        mgr = make_manager(cloudwatch_logger=cw, failure_manager=fm)

        async def forbidden():
            raise StatusError("access denied", 403)

        with pytest.raises(StatusError):
            await mgr.retry_with_backoff(forbidden, url="https://perm.com/a")

        cw.log_scraping_attempt.assert_awaited()
        fm.record_failure.assert_awaited_once()
        fm.mark_permanent_failure.assert_awaited_once_with("https://perm.com/a")


class TestProcessRetryQueue:
    @pytest.mark.asyncio
    async def test_no_failure_manager_returns_empty(self):
        mgr = make_manager()
        assert await mgr.process_retry_queue(limit=10) == []

    @pytest.mark.asyncio
    async def test_processes_ready_urls(self):
        fm = MagicMock()
        ready = [
            MagicMock(url="https://a.com/1", retry_count=1),
            MagicMock(url="https://b.com/2", retry_count=2),
        ]
        fm.get_urls_ready_for_retry = AsyncMock(return_value=ready)
        mgr = make_manager(failure_manager=fm)
        processed = await mgr.process_retry_queue(limit=10)
        assert processed == ["https://a.com/1", "https://b.com/2"]

    @pytest.mark.asyncio
    async def test_skips_circuit_broken_url(self):
        fm = MagicMock()
        ready = [MagicMock(url="https://broken.com/1", retry_count=1)]
        fm.get_urls_ready_for_retry = AsyncMock(return_value=ready)
        mgr = make_manager(failure_manager=fm)
        # Open the circuit breaker for that domain.
        for _ in range(mgr.circuit_breaker_failure_threshold):
            mgr._record_circuit_breaker_failure("https://broken.com/1")
        processed = await mgr.process_retry_queue(limit=10)
        assert processed == []

    @pytest.mark.asyncio
    async def test_queue_level_error_returns_empty(self):
        fm = MagicMock()
        fm.get_urls_ready_for_retry = AsyncMock(side_effect=RuntimeError("boom"))
        mgr = make_manager(failure_manager=fm)
        assert await mgr.process_retry_queue(limit=10) == []

    @pytest.mark.asyncio
    async def test_per_url_error_is_caught(self, monkeypatch):
        fm = MagicMock()
        ready = [MagicMock(url="https://c.com/1", retry_count=1)]
        fm.get_urls_ready_for_retry = AsyncMock(return_value=ready)
        mgr = make_manager(failure_manager=fm)

        # Make the per-URL circuit-breaker check raise so the inner
        # try/except (per-URL error handling) executes.
        def boom(url):
            raise RuntimeError("cb check failed")

        monkeypatch.setattr(mgr, "_is_circuit_breaker_open", boom)
        # Inner errors are swallowed; nothing is appended to processed.
        assert await mgr.process_retry_queue(limit=10) == []


class TestCircuitBreakerOpenRaises:
    @pytest.mark.asyncio
    async def test_open_circuit_raises_before_calling_func(self):
        mgr = make_manager()
        url = "https://open.com/a"
        for _ in range(mgr.circuit_breaker_failure_threshold):
            mgr._record_circuit_breaker_failure(url)
        called = {"n": 0}

        async def should_not_run():
            called["n"] += 1
            return "x"

        with pytest.raises(Exception) as exc:
            await mgr.retry_with_backoff(should_not_run, url=url)
        assert "Circuit breaker is open" in str(exc.value)
        assert called["n"] == 0


class TestGetRetryStatistics:
    @pytest.mark.asyncio
    async def test_includes_circuit_breaker_and_failure_stats(self):
        fm = MagicMock()
        fm.get_failure_statistics = AsyncMock(return_value={"total_failures": 3})
        mgr = make_manager(failure_manager=fm)
        # Create a circuit-breaker entry to exercise the stats loop.
        mgr._record_circuit_breaker_failure("https://cb.com/a")
        stats = await mgr.get_retry_statistics()
        assert "cb.com" in stats["circuit_breakers"]
        assert stats["circuit_breakers"]["cb.com"]["failure_count"] == 1
        assert stats["failure_stats"] == {"total_failures": 3}

    @pytest.mark.asyncio
    async def test_failure_stats_error_is_handled(self):
        fm = MagicMock()
        fm.get_failure_statistics = AsyncMock(side_effect=RuntimeError("stat fail"))
        mgr = make_manager(failure_manager=fm)
        stats = await mgr.get_retry_statistics()
        # Error branch swallows the exception; failure_stats key absent.
        assert "failure_stats" not in stats
        assert isinstance(stats["active_retries"], int)


class TestDomainExtraction:
    def test_exception_fallback(self, monkeypatch):
        mgr = make_manager()
        monkeypatch.setattr(
            "urllib.parse.urlparse",
            lambda url: (_ for _ in ()).throw(RuntimeError("bad url")),
        )
        assert mgr._get_domain_from_url("https://x.com") == "unknown"


class TestActiveRetriesTracking:
    @pytest.mark.asyncio
    async def test_active_retries_cleared_on_eventual_success(self):
        mgr = make_manager()
        mgr.retry_config = RetryConfig(jitter=False, base_delay=0.0, max_retries=3)
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise Exception("network error")
            return "ok"

        result = await mgr.retry_with_backoff(flaky, url="https://track.com/a")
        assert result == "ok"
        # Success path removes the URL from active retry tracking.
        assert "https://track.com/a" not in mgr.active_retries
