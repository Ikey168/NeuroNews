"""
Test suite for the rate limiting middleware in
src/api/middleware/rate_limit_middleware.py.

Tests the actual rate-limiting API shipped in this codebase:
- RateLimitConfig user tiers (FREE / PREMIUM / ENTERPRISE) and UserTier dataclass
- RequestMetrics dataclass
- RateLimitStore in-memory backend (record_request / get_request_counts /
  concurrent counters), with Redis forced off for determinism
- SuspiciousActivityDetector pattern analysis
- RateLimitMiddleware dispatch, tier resolution, client IP extraction,
  excluded-path bypass and 429 responses
"""

import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from src.api.middleware.rate_limit_middleware import (
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitStore,
    RequestMetrics,
    SuspiciousActivityDetector,
    UserTier,
)


# Force the in-memory backend for every RateLimitStore created in this module.
@pytest.fixture(autouse=True)
def _force_memory_backend():
    with patch.object(RateLimitStore, "_redis_available", return_value=False):
        yield


def _make_metrics(user_id="u1", ip="192.168.1.100", endpoint="/api/test",
                  code=200, ts=None):
    return RequestMetrics(
        user_id=user_id,
        ip_address=ip,
        endpoint=endpoint,
        timestamp=ts or datetime.now(),
        response_code=code,
        processing_time=0.01,
    )


class TestUserTierConfiguration:
    """Test user tier configurations."""

    def test_free_tier_limits(self):
        """Test free tier rate limits."""
        free_tier = RateLimitConfig.FREE_TIER

        assert free_tier.name == "free"
        assert free_tier.requests_per_minute == 10
        assert free_tier.requests_per_hour == 100
        assert free_tier.requests_per_day == 1000
        assert free_tier.burst_limit == 15
        assert free_tier.concurrent_requests == 3

    def test_premium_tier_limits(self):
        """Test premium tier rate limits."""
        premium_tier = RateLimitConfig.PREMIUM_TIER

        assert premium_tier.name == "premium"
        assert premium_tier.requests_per_minute > RateLimitConfig.FREE_TIER.requests_per_minute
        assert premium_tier.requests_per_hour > RateLimitConfig.FREE_TIER.requests_per_hour
        assert premium_tier.requests_per_day > RateLimitConfig.FREE_TIER.requests_per_day
        assert premium_tier.burst_limit > RateLimitConfig.FREE_TIER.burst_limit
        assert premium_tier.concurrent_requests > RateLimitConfig.FREE_TIER.concurrent_requests

    def test_enterprise_tier_limits(self):
        """Test enterprise tier rate limits."""
        enterprise_tier = RateLimitConfig.ENTERPRISE_TIER

        assert enterprise_tier.name == "enterprise"
        assert enterprise_tier.requests_per_minute > RateLimitConfig.PREMIUM_TIER.requests_per_minute
        assert enterprise_tier.requests_per_hour > RateLimitConfig.PREMIUM_TIER.requests_per_hour
        assert enterprise_tier.requests_per_day > RateLimitConfig.PREMIUM_TIER.requests_per_day
        assert enterprise_tier.burst_limit > RateLimitConfig.PREMIUM_TIER.burst_limit
        assert enterprise_tier.concurrent_requests > RateLimitConfig.PREMIUM_TIER.concurrent_requests

    def test_tier_hierarchy(self):
        """Test tier hierarchy (Enterprise > Premium > Free)."""
        free = RateLimitConfig.FREE_TIER
        premium = RateLimitConfig.PREMIUM_TIER
        enterprise = RateLimitConfig.ENTERPRISE_TIER

        assert enterprise.requests_per_minute >= premium.requests_per_minute >= free.requests_per_minute
        assert enterprise.requests_per_hour >= premium.requests_per_hour >= free.requests_per_hour
        assert enterprise.requests_per_day >= premium.requests_per_day >= free.requests_per_day
        assert enterprise.burst_limit >= premium.burst_limit >= free.burst_limit
        assert enterprise.concurrent_requests >= premium.concurrent_requests >= free.concurrent_requests

    def test_user_tier_dataclass(self):
        """Test UserTier dataclass functionality."""
        custom_tier = UserTier(
            name="custom",
            requests_per_minute=50,
            requests_per_hour=500,
            requests_per_day=5000,
            burst_limit=75,
            concurrent_requests=10,
        )

        assert custom_tier.name == "custom"
        assert custom_tier.requests_per_minute == 50
        assert custom_tier.requests_per_hour == 500
        assert custom_tier.requests_per_day == 5000
        assert custom_tier.burst_limit == 75
        assert custom_tier.concurrent_requests == 10


class TestRequestMetrics:
    """Test the RequestMetrics dataclass."""

    def test_request_metrics_fields(self):
        """Test that RequestMetrics stores its fields."""
        now = datetime.now()
        metrics = RequestMetrics(
            user_id="user123",
            ip_address="10.0.0.1",
            endpoint="/api/articles",
            timestamp=now,
            response_code=200,
            processing_time=0.05,
        )
        assert metrics.user_id == "user123"
        assert metrics.ip_address == "10.0.0.1"
        assert metrics.endpoint == "/api/articles"
        assert metrics.timestamp == now
        assert metrics.response_code == 200
        assert metrics.processing_time == 0.05


class TestRateLimitStoreMemory:
    """Test the in-memory backend of RateLimitStore."""

    @pytest.fixture
    def store(self):
        store = RateLimitStore()
        assert store.use_redis is False  # forced by autouse fixture
        return store

    @pytest.mark.asyncio
    async def test_record_and_count_requests(self, store):
        """Recorded requests are reflected in the time-window counts."""
        counts = await store.get_request_counts("u1")
        assert counts == {"minute": 0, "hour": 0, "day": 0}

        for _ in range(5):
            await store.record_request("u1", _make_metrics(user_id="u1"))

        counts = await store.get_request_counts("u1")
        assert counts["minute"] == 5
        assert counts["hour"] == 5
        assert counts["day"] == 5

    @pytest.mark.asyncio
    async def test_counts_are_per_user(self, store):
        """Counts are isolated per user id."""
        await store.record_request("a", _make_metrics(user_id="a"))
        await store.record_request("a", _make_metrics(user_id="a"))
        await store.record_request("b", _make_metrics(user_id="b"))

        assert (await store.get_request_counts("a"))["minute"] == 2
        assert (await store.get_request_counts("b"))["minute"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_counter(self, store):
        """Concurrent counters increment and decrement correctly."""
        assert await store.increment_concurrent("u1") == 1
        assert await store.increment_concurrent("u1") == 2
        await store.decrement_concurrent("u1")
        assert store.memory_store["u1"]["concurrent"] == 1

    @pytest.mark.asyncio
    async def test_concurrent_counter_never_negative(self, store):
        """Decrementing below zero is clamped at zero."""
        await store.decrement_concurrent("u1")
        assert store.memory_store["u1"]["concurrent"] == 0


class TestSuspiciousActivityDetector:
    """Test suspicious activity detection."""

    @pytest.fixture
    def detector(self):
        store = RateLimitStore()
        return SuspiciousActivityDetector(store, RateLimitConfig())

    def test_unusual_hours_detection(self, detector):
        """Requests during 2-6 AM are flagged as unusual hours."""
        night = datetime.now().replace(hour=3, minute=0, second=0, microsecond=0)
        day = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
        assert detector._check_unusual_hours(night) is True
        assert detector._check_unusual_hours(day) is False

    @pytest.mark.asyncio
    async def test_rapid_requests_detection(self, detector):
        """Exceeding the rapid_requests threshold is flagged."""
        threshold = detector.config.SUSPICIOUS_PATTERNS["rapid_requests"]
        now = datetime.now()
        metrics = [_make_metrics(ts=now) for _ in range(threshold + 5)]
        assert await detector._check_rapid_requests(metrics) is True

        # Below threshold: not flagged
        few = [_make_metrics(ts=now) for _ in range(threshold - 1)]
        assert await detector._check_rapid_requests(few) is False

    @pytest.mark.asyncio
    async def test_high_error_rate_detection(self, detector):
        """A high proportion of error responses is flagged."""
        now = datetime.now()
        metrics = [_make_metrics(code=500, ts=now) for _ in range(15)]
        assert await detector._check_error_rate(metrics) is True

        ok = [_make_metrics(code=200, ts=now) for _ in range(15)]
        assert await detector._check_error_rate(ok) is False

    @pytest.mark.asyncio
    async def test_multiple_ips_detection(self, detector):
        """Many distinct IPs for one user is flagged."""
        now = datetime.now()
        limit = detector.config.SUSPICIOUS_PATTERNS["multiple_ips"]
        metrics = [
            _make_metrics(ip=f"10.0.0.{i}", ts=now) for i in range(limit + 5)
        ]
        assert await detector._check_multiple_ips(metrics) is True

    @pytest.mark.asyncio
    async def test_analyze_request_aggregates_alerts(self, detector):
        """analyze_request returns alert strings for suspicious traffic.

        The stored metrics are timestamped 'now' so the sliding-minute checks
        (rapid_requests, error_rate, multiple_ips) fire deterministically
        regardless of wall-clock time, while the trigger metric carries a
        3 AM timestamp so the unusual_hours check also fires.
        """
        now = datetime.now()
        for i in range(60):
            m = _make_metrics(user_id="attacker", ip=f"10.0.0.{i % 20}",
                              code=500, ts=now)
            detector.store.memory_store["attacker"]["metrics"].append(m)

        night = now.replace(hour=3, minute=0, second=0, microsecond=0)
        trigger = _make_metrics(user_id="attacker", ip="10.0.0.1", code=500, ts=night)
        alerts = await detector.analyze_request("attacker", trigger)

        assert isinstance(alerts, list)
        assert "unusual_hours" in alerts
        assert "rapid_requests" in alerts
        assert "high_error_rate" in alerts
        assert "multiple_ips" in alerts


class TestRateLimitMiddleware:
    """Test the RateLimitMiddleware core behaviour."""

    @pytest.fixture
    def middleware(self):
        app = MagicMock()
        mw = RateLimitMiddleware(app)
        assert mw.store.use_redis is False
        return mw

    @pytest.mark.asyncio
    async def test_get_user_info_free_default(self, middleware):
        """Anonymous requests resolve to the free tier."""
        request = MagicMock(spec=Request)
        request.state = MagicMock(spec=[])  # no `user` attribute
        request.headers = {}
        user_id, tier = await middleware._get_user_info(request)
        assert tier.name == "free"
        assert user_id == "anonymous"

    @pytest.mark.asyncio
    async def test_get_user_info_premium_from_state(self, middleware):
        """A premium user in request.state resolves to the premium tier."""
        request = MagicMock(spec=Request)
        request.state.user = {"user_id": "456", "tier": "premium"}
        request.headers = {}
        user_id, tier = await middleware._get_user_info(request)
        assert user_id == "456"
        assert tier.name == "premium"

    @pytest.mark.asyncio
    async def test_get_user_info_unknown_tier_falls_back(self, middleware):
        """An unknown tier name falls back to free."""
        request = MagicMock(spec=Request)
        request.state.user = {"user_id": "789", "tier": "bogus"}
        request.headers = {}
        _, tier = await middleware._get_user_info(request)
        assert tier.name == "free"

    def test_get_client_ip_direct(self, middleware):
        """Client IP falls back to the socket peer."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client.host = "192.168.1.50"
        assert middleware._get_client_ip(request) == "192.168.1.50"

    def test_get_client_ip_forwarded(self, middleware):
        """X-Forwarded-For takes precedence and uses the first hop."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "203.0.113.5, 192.168.1.1"}
        request.client.host = "192.168.1.50"
        assert middleware._get_client_ip(request) == "203.0.113.5"

    def test_get_client_ip_real_ip(self, middleware):
        """X-Real-IP is honoured when present."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Real-IP": "198.51.100.7"}
        request.client.host = "192.168.1.50"
        assert middleware._get_client_ip(request) == "198.51.100.7"

    @pytest.mark.asyncio
    async def test_check_rate_limits_under_limit(self, middleware):
        """No response returned while under the per-minute limit."""
        result = await middleware._check_rate_limits("u1", RateLimitConfig.FREE_TIER)
        assert result is None

    @pytest.mark.asyncio
    async def test_check_rate_limits_minute_exceeded(self, middleware):
        """A 429 JSONResponse is returned once the per-minute limit is hit."""
        tier = RateLimitConfig.FREE_TIER
        for _ in range(tier.requests_per_minute):
            await middleware.store.record_request("u1", _make_metrics(user_id="u1"))

        result = await middleware._check_rate_limits("u1", tier)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 429

    def test_create_rate_limit_response_headers(self, middleware):
        """The 429 response carries standard rate-limit headers."""
        response = middleware._create_rate_limit_response("Rate limit exceeded", 10, 60)
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Limit"] == "10"
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert "X-RateLimit-Reset" in response.headers
        assert response.headers["Retry-After"] == "60"

    def test_excluded_paths_configured(self, middleware):
        """Public dashboard/health paths are excluded from limiting."""
        assert "/health" in middleware.excluded_paths
        assert "/docs" in middleware.excluded_paths
        assert "/openapi.json" in middleware.excluded_paths

    @pytest.mark.asyncio
    async def test_dispatch_excluded_path_bypasses(self, middleware):
        """Requests to excluded paths skip rate limiting entirely."""
        request = MagicMock(spec=Request)
        request.url.path = "/health"
        sentinel = Response(content="OK", status_code=200)
        call_next = AsyncMock(return_value=sentinel)

        response = await middleware.dispatch(request, call_next)
        assert response is sentinel
        call_next.assert_awaited_once_with(request)

    @pytest.mark.asyncio
    async def test_dispatch_normal_request_passes(self, middleware):
        """A normal request under limits is forwarded to the app."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.state = MagicMock(spec=[])
        request.headers = {}
        request.client.host = "192.168.1.100"

        call_next = AsyncMock(return_value=Response(content="OK", status_code=200))
        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 200
        call_next.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dispatch_rate_limited_returns_429(self, middleware):
        """When the per-minute limit is exceeded, dispatch returns 429 and
        does not call the downstream app."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.state.user = {"user_id": "hammer", "tier": "free"}
        request.headers = {}
        request.client.host = "192.168.1.100"

        # Pre-fill the minute window to the free-tier ceiling.
        for _ in range(RateLimitConfig.FREE_TIER.requests_per_minute):
            await middleware.store.record_request("hammer", _make_metrics(user_id="hammer"))

        call_next = AsyncMock()
        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 429
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_concurrent_limit_returns_429(self, middleware):
        """Exceeding the concurrent-request ceiling returns 429."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.state.user = {"user_id": "conc", "tier": "free"}
        request.headers = {}
        request.client.host = "192.168.1.100"

        tier = RateLimitConfig.FREE_TIER
        # Occupy the concurrent slots so the next request trips the limit.
        for _ in range(tier.concurrent_requests):
            await middleware.store.increment_concurrent("conc")

        call_next = AsyncMock()
        response = await middleware.dispatch(request, call_next)

        assert response.status_code == 429
        call_next.assert_not_called()


class TestRateLimitMiddlewarePerformance:
    """Basic performance characteristics of the in-memory path."""

    @pytest.fixture
    def store(self):
        return RateLimitStore()

    @pytest.mark.asyncio
    async def test_memory_recording_is_fast(self, store):
        """Recording many requests stays well under a second."""
        start = time.time()
        for i in range(1000):
            await store.record_request(f"u{i % 50}", _make_metrics(user_id=f"u{i % 50}"))
        assert time.time() - start < 2.0

    @pytest.mark.asyncio
    async def test_count_queries_are_fast(self, store):
        """Querying counts for many users stays fast."""
        for i in range(50):
            await store.record_request(f"u{i}", _make_metrics(user_id=f"u{i}"))
        start = time.time()
        for i in range(1000):
            await store.get_request_counts(f"u{i % 50}")
        assert time.time() - start < 2.0
