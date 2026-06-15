"""Comprehensive tests for src/scraper/enhanced_retry_manager.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.enhanced_retry_manager import (  # noqa: E402
    EnhancedRetryManager,
    RetryAttempt,
    RetryConfig,
    RetryReason,
)


class StatusError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


@pytest.fixture
def manager():
    # All AWS deps default to None -> pure-logic + no-op recording paths
    return EnhancedRetryManager(retry_config=RetryConfig(jitter=False, base_delay=1.0))


class TestConfig:
    def test_defaults(self):
        cfg = RetryConfig()
        assert cfg.max_retries == 5
        assert 429 in cfg.retry_on_status_codes
        assert 404 in cfg.permanent_failure_codes

    def test_custom_lists_preserved(self):
        cfg = RetryConfig(retry_on_status_codes=[500], permanent_failure_codes=[400])
        assert cfg.retry_on_status_codes == [500]
        assert cfg.permanent_failure_codes == [400]


class TestRetryAttempt:
    def test_fields(self):
        a = RetryAttempt(attempt_number=1, delay=2.0, reason=RetryReason.TIMEOUT,
                         timestamp=123.0)
        assert a.error is None
        assert a.proxy_used is None


class TestDetermineRetryReason:
    def test_timeout(self, manager):
        assert manager._determine_retry_reason(Exception("Connection timeout"), {}) == RetryReason.TIMEOUT

    def test_captcha(self, manager):
        assert manager._determine_retry_reason(Exception("captcha challenge"), {}) == RetryReason.CAPTCHA_FAILED

    def test_proxy(self, manager):
        assert manager._determine_retry_reason(Exception("proxy refused"), {}) == RetryReason.PROXY_FAILED

    def test_rate_limited_text(self, manager):
        assert manager._determine_retry_reason(Exception("too many requests"), {}) == RetryReason.RATE_LIMITED

    def test_server_error_status(self, manager):
        assert manager._determine_retry_reason(StatusError("x", 503), {}) == RetryReason.SERVER_ERROR

    def test_rate_limited_status(self, manager):
        assert manager._determine_retry_reason(StatusError("x", 429), {}) == RetryReason.RATE_LIMITED

    def test_http_error_status(self, manager):
        assert manager._determine_retry_reason(StatusError("x", 418), {}) == RetryReason.HTTP_ERROR

    def test_network(self, manager):
        assert manager._determine_retry_reason(Exception("network unreachable"), {}) == RetryReason.NETWORK_ERROR

    def test_unknown(self, manager):
        assert manager._determine_retry_reason(Exception("weird"), {}) == RetryReason.UNKNOWN_ERROR


class TestPermanentFailure:
    def test_permanent_status(self, manager):
        assert manager._is_permanent_failure(StatusError("x", 404), {}) is True

    def test_non_permanent_status(self, manager):
        assert manager._is_permanent_failure(StatusError("x", 500), {}) is False

    def test_permanent_keyword(self, manager):
        assert manager._is_permanent_failure(Exception("403 Forbidden"), {}) is True

    def test_not_permanent_keyword(self, manager):
        assert manager._is_permanent_failure(Exception("temporary glitch"), {}) is False


class TestCalculateDelay:
    def test_exponential_growth(self, manager):
        cfg = RetryConfig(jitter=False, base_delay=1.0, exponential_base=2.0)
        d0 = manager._calculate_delay(0, cfg, RetryReason.UNKNOWN_ERROR)
        d2 = manager._calculate_delay(2, cfg, RetryReason.UNKNOWN_ERROR)
        assert d2 > d0

    def test_capped_at_max(self, manager):
        cfg = RetryConfig(jitter=False, base_delay=1.0, max_delay=5.0)
        d = manager._calculate_delay(10, cfg, RetryReason.UNKNOWN_ERROR)
        assert d <= 5.0

    def test_rate_limited_longer(self, manager):
        cfg = RetryConfig(jitter=False)
        rl = manager._calculate_delay(1, cfg, RetryReason.RATE_LIMITED)
        normal = manager._calculate_delay(1, cfg, RetryReason.UNKNOWN_ERROR)
        assert rl > normal

    def test_proxy_shorter(self, manager):
        cfg = RetryConfig(jitter=False)
        proxy = manager._calculate_delay(1, cfg, RetryReason.PROXY_FAILED)
        normal = manager._calculate_delay(1, cfg, RetryReason.UNKNOWN_ERROR)
        assert proxy < normal

    def test_minimum_floor(self, manager):
        cfg = RetryConfig(jitter=False, base_delay=0.0)
        assert manager._calculate_delay(0, cfg, RetryReason.UNKNOWN_ERROR) >= 0.1


class TestCircuitBreaker:
    def test_closed_by_default(self, manager):
        assert manager._is_circuit_breaker_open("https://x.com/a") is False

    def test_opens_after_threshold(self, manager):
        url = "https://flaky.com/a"
        for _ in range(manager.circuit_breaker_failure_threshold):
            manager._record_circuit_breaker_failure(url)
        assert manager._is_circuit_breaker_open(url) is True

    def test_reset(self, manager):
        url = "https://flaky.com/a"
        for _ in range(manager.circuit_breaker_failure_threshold):
            manager._record_circuit_breaker_failure(url)
        manager._reset_circuit_breaker(url)
        assert manager._is_circuit_breaker_open(url) is False

    def test_half_open_after_timeout(self, manager):
        url = "https://flaky.com/a"
        manager.circuit_breaker_timeout = -1  # already elapsed
        for _ in range(manager.circuit_breaker_failure_threshold):
            manager._record_circuit_breaker_failure(url)
        # open_until is in the past -> transitions to half-open and returns False
        assert manager._is_circuit_breaker_open(url) is False

    def test_domain_extraction(self, manager):
        assert manager._get_domain_from_url("https://news.example.com/path") == "news.example.com"


class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_success_first_try(self, manager):
        async def ok():
            return "result"
        assert await manager.retry_with_backoff(ok, url="https://x.com") == "result"

    @pytest.mark.asyncio
    async def test_succeeds_after_failures(self, manager):
        manager.retry_config = RetryConfig(max_retries=3, base_delay=0.0, jitter=False)
        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise Exception("network error")
            return "ok"

        result = await manager.retry_with_backoff(flaky, url="https://x.com/p")
        assert result == "ok"
        assert calls["n"] == 3

    @pytest.mark.asyncio
    async def test_permanent_failure_not_retried(self, manager):
        manager.retry_config = RetryConfig(max_retries=5, base_delay=0.0, jitter=False)
        calls = {"n": 0}

        async def forbidden():
            calls["n"] += 1
            raise StatusError("denied", 403)

        with pytest.raises(StatusError):
            await manager.retry_with_backoff(forbidden, url="https://x.com/p")
        assert calls["n"] == 1  # not retried

    @pytest.mark.asyncio
    async def test_exhausts_retries(self, manager):
        manager.retry_config = RetryConfig(max_retries=2, base_delay=0.0, jitter=False)

        async def always_fail():
            raise Exception("server error 500")

        with pytest.raises(Exception):
            await manager.retry_with_backoff(always_fail, url="https://x.com/p")


class TestStatistics:
    @pytest.mark.asyncio
    async def test_get_retry_statistics(self, manager):
        stats = await manager.get_retry_statistics()
        assert isinstance(stats, dict)
