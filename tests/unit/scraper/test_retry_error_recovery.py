"""
Tests for the enhanced retry / error-recovery subsystem in
``scraper.enhanced_retry_manager``.

The module provides ``RetryConfig`` (retry behaviour configuration),
``RetryReason`` (failure classification) and ``EnhancedRetryManager`` which
executes async callables with exponential backoff, permanent-failure detection
and a per-domain circuit breaker. These tests exercise that real API.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import aiohttp

# Import with proper path handling.
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

try:
    from scraper.enhanced_retry_manager import (
        EnhancedRetryManager,
        RetryConfig,
        RetryReason,
    )
except ImportError as _e:  # stale or optional dependency
    pytest.skip("module import failed: {0}".format(_e), allow_module_level=True)


class StatusError(Exception):
    """Exception carrying an HTTP-like ``status_code`` attribute."""

    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


class TestRetryConfig:
    def test_defaults(self):
        config = RetryConfig()
        assert config.max_retries == 5
        assert config.base_delay == 1.0
        assert config.max_delay == 300.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        # __post_init__ fills in the status-code lists.
        assert 429 in config.retry_on_status_codes
        assert 404 in config.permanent_failure_codes

    def test_custom_values(self):
        config = RetryConfig(max_retries=3, base_delay=0.5, jitter=False)
        assert config.max_retries == 3
        assert config.base_delay == 0.5
        assert config.jitter is False


class TestManagerInit:
    def test_uses_provided_config(self):
        config = RetryConfig(max_retries=2)
        manager = EnhancedRetryManager(retry_config=config)
        assert manager.retry_config is config
        assert manager.retry_config.max_retries == 2

    def test_default_config_when_none(self):
        manager = EnhancedRetryManager()
        assert isinstance(manager.retry_config, RetryConfig)
        assert manager.active_retries == {}
        assert manager.circuit_breaker_state == {}


class TestDelayCalculation:
    @pytest.fixture
    def manager(self):
        return EnhancedRetryManager(retry_config=RetryConfig(jitter=False))

    def test_exponential_growth(self, manager):
        config = manager.retry_config
        d0 = manager._calculate_delay(0, config, RetryReason.NETWORK_ERROR)
        d1 = manager._calculate_delay(1, config, RetryReason.NETWORK_ERROR)
        d2 = manager._calculate_delay(2, config, RetryReason.NETWORK_ERROR)
        assert d0 == pytest.approx(1.0)
        assert d1 == pytest.approx(2.0)
        assert d2 == pytest.approx(4.0)

    def test_max_delay_cap(self, manager):
        config = RetryConfig(jitter=False, max_delay=10.0)
        delay = manager._calculate_delay(20, config, RetryReason.NETWORK_ERROR)
        assert delay <= 10.0

    def test_rate_limited_gets_longer_delay(self, manager):
        config = manager.retry_config
        base = manager._calculate_delay(2, config, RetryReason.NETWORK_ERROR)
        rate_limited = manager._calculate_delay(2, config, RetryReason.RATE_LIMITED)
        assert rate_limited > base

    def test_jitter_produces_variation(self):
        manager = EnhancedRetryManager(retry_config=RetryConfig(jitter=True))
        config = manager.retry_config
        delays = {
            manager._calculate_delay(3, config, RetryReason.NETWORK_ERROR)
            for _ in range(20)
        }
        assert len(delays) > 1

    def test_minimum_delay_floor(self, manager):
        config = RetryConfig(jitter=False, base_delay=0.0)
        delay = manager._calculate_delay(0, config, RetryReason.NETWORK_ERROR)
        assert delay >= 0.1


class TestRetryReasonClassification:
    @pytest.fixture
    def manager(self):
        return EnhancedRetryManager()

    def test_timeout(self, manager):
        reason = manager._determine_retry_reason(Exception("Request timeout"), {})
        assert reason == RetryReason.TIMEOUT

    def test_rate_limited(self, manager):
        reason = manager._determine_retry_reason(Exception("rate limit exceeded"), {})
        assert reason == RetryReason.RATE_LIMITED

    def test_server_error_from_status(self, manager):
        reason = manager._determine_retry_reason(StatusError("bad", 500), {})
        assert reason == RetryReason.SERVER_ERROR

    def test_network_error(self, manager):
        reason = manager._determine_retry_reason(Exception("connection reset"), {})
        assert reason == RetryReason.NETWORK_ERROR

    def test_unknown(self, manager):
        reason = manager._determine_retry_reason(Exception("weird"), {})
        assert reason == RetryReason.UNKNOWN_ERROR


class TestPermanentFailure:
    @pytest.fixture
    def manager(self):
        return EnhancedRetryManager()

    def test_permanent_from_status_code(self, manager):
        assert manager._is_permanent_failure(StatusError("nope", 404), {}) is True

    def test_permanent_from_keyword(self, manager):
        assert manager._is_permanent_failure(Exception("403 Forbidden"), {}) is True

    def test_transient_not_permanent(self, manager):
        assert manager._is_permanent_failure(Exception("timeout"), {}) is False


@pytest.mark.asyncio
class TestRetryWithBackoff:
    async def test_success_first_try(self):
        manager = EnhancedRetryManager()
        func = AsyncMock(return_value="ok")
        result = await manager.retry_with_backoff(func, url="http://x.test")
        assert result == "ok"
        assert func.await_count == 1

    async def test_success_after_transient_failures(self):
        manager = EnhancedRetryManager(
            retry_config=RetryConfig(max_retries=5, jitter=False)
        )
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise Exception("connection error")
            return "recovered"

        with patch("asyncio.sleep", new=AsyncMock()) as sleep_mock:
            result = await manager.retry_with_backoff(flaky, url="http://y.test")

        assert result == "recovered"
        assert calls["n"] == 3
        # Two backoff sleeps between the three attempts.
        assert sleep_mock.await_count == 2

    async def test_exhausts_retries_and_raises(self):
        manager = EnhancedRetryManager(
            retry_config=RetryConfig(max_retries=2, jitter=False)
        )

        async def always_fail():
            raise Exception("connection error")

        with patch("asyncio.sleep", new=AsyncMock()):
            with pytest.raises(Exception, match="connection error"):
                await manager.retry_with_backoff(always_fail, url="http://z.test")

    async def test_permanent_failure_not_retried(self):
        manager = EnhancedRetryManager(
            retry_config=RetryConfig(max_retries=5, jitter=False)
        )
        func = AsyncMock(side_effect=StatusError("not found", 404))

        with patch("asyncio.sleep", new=AsyncMock()) as sleep_mock:
            with pytest.raises(StatusError):
                await manager.retry_with_backoff(func, url="http://p.test")

        # Permanent failure stops immediately: a single attempt, no sleeps.
        assert func.await_count == 1
        assert sleep_mock.await_count == 0

    async def test_success_clears_active_retries(self):
        manager = EnhancedRetryManager(
            retry_config=RetryConfig(max_retries=3, jitter=False)
        )
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise Exception("network glitch")
            return "done"

        with patch("asyncio.sleep", new=AsyncMock()):
            await manager.retry_with_backoff(flaky, url="http://clear.test")

        assert "http://clear.test" not in manager.active_retries


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_opens_after_threshold_failures(self):
        manager = EnhancedRetryManager(
            retry_config=RetryConfig(max_retries=0, jitter=False)
        )
        manager.circuit_breaker_failure_threshold = 3

        async def always_fail():
            raise Exception("network error")

        with patch("asyncio.sleep", new=AsyncMock()):
            for _ in range(3):
                with pytest.raises(Exception):
                    await manager.retry_with_backoff(
                        always_fail, url="http://cb.test/page"
                    )

        # Circuit is now open for the domain -> fast-fail with a distinct message.
        assert manager._is_circuit_breaker_open("http://cb.test/page") is True
        with pytest.raises(Exception, match="Circuit breaker is open"):
            await manager.retry_with_backoff(always_fail, url="http://cb.test/page")

    async def test_reset_after_success(self):
        manager = EnhancedRetryManager()
        manager._record_circuit_breaker_failure("http://reset.test/a")
        assert "reset.test" in manager.circuit_breaker_state

        manager._reset_circuit_breaker("http://reset.test/a")
        assert manager.circuit_breaker_state["reset.test"]["failure_count"] == 0
        assert manager.circuit_breaker_state["reset.test"]["state"] == "closed"


@pytest.mark.asyncio
class TestStatistics:
    async def test_statistics_report_active_and_breakers(self):
        manager = EnhancedRetryManager()
        manager._record_circuit_breaker_failure("http://s.test/x")

        stats = await manager.get_retry_statistics()
        assert "active_retries" in stats
        assert "circuit_breakers" in stats
        assert "s.test" in stats["circuit_breakers"]

    async def test_process_retry_queue_without_failure_manager(self):
        manager = EnhancedRetryManager()  # no failure_manager
        result = await manager.process_retry_queue()
        assert result == []
