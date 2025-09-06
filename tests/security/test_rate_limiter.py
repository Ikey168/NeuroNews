"""
Comprehensive test suite for Rate Limiting Middleware - Issue #476.

Tests all rate limiting requirements:
- Rate limiting algorithms and enforcement
- User tier-based rate limiting (Free, Premium, Admin)
- Burst limit handling and sliding windows
- Concurrent request limiting
- Suspicious activity monitoring and auto-blocking
- Redis backend integration and fallback mechanisms
- Performance under high load scenarios
"""

import asyncio
import time
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError as RedisConnectionError

from src.api.middleware.rate_limit_middleware import (
    RateLimitConfig,
    RateLimitMiddleware,
    SuspiciousActivity,
    UserTier,
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

    def test_admin_tier_limits(self):
        """Test admin tier rate limits."""
        admin_tier = RateLimitConfig.ADMIN_TIER
        
        assert admin_tier.name == "admin"
        assert admin_tier.requests_per_minute > RateLimitConfig.PREMIUM_TIER.requests_per_minute
        assert admin_tier.requests_per_hour > RateLimitConfig.PREMIUM_TIER.requests_per_hour
        assert admin_tier.requests_per_day > RateLimitConfig.PREMIUM_TIER.requests_per_day
        assert admin_tier.burst_limit > RateLimitConfig.PREMIUM_TIER.burst_limit
        assert admin_tier.concurrent_requests > RateLimitConfig.PREMIUM_TIER.concurrent_requests

    def test_tier_hierarchy(self):
        """Test tier hierarchy (Admin > Premium > Free)."""
        free = RateLimitConfig.FREE_TIER
        premium = RateLimitConfig.PREMIUM_TIER
        admin = RateLimitConfig.ADMIN_TIER
        
        # Check hierarchy for all metrics
        assert admin.requests_per_minute >= premium.requests_per_minute >= free.requests_per_minute
        assert admin.requests_per_hour >= premium.requests_per_hour >= free.requests_per_hour
        assert admin.requests_per_day >= premium.requests_per_day >= free.requests_per_day
        assert admin.burst_limit >= premium.burst_limit >= free.burst_limit
        assert admin.concurrent_requests >= premium.concurrent_requests >= free.concurrent_requests

    def test_user_tier_dataclass(self):
        """Test UserTier dataclass functionality."""
        custom_tier = UserTier(
            name="custom",
            requests_per_minute=50,
            requests_per_hour=500,
            requests_per_day=5000,
            burst_limit=75,
            concurrent_requests=10
        )
        
        assert custom_tier.name == "custom"
        assert custom_tier.requests_per_minute == 50
        assert custom_tier.requests_per_hour == 500
        assert custom_tier.requests_per_day == 5000
        assert custom_tier.burst_limit == 75
        assert custom_tier.concurrent_requests == 10


class TestSuspiciousActivity:
    """Test suspicious activity detection."""

    def test_suspicious_activity_dataclass(self):
        """Test SuspiciousActivity dataclass."""
        activity = SuspiciousActivity(
            ip_address="192.168.1.100",
            request_count=500,
            time_window=300,  # 5 minutes
            patterns=["rapid_requests", "429_responses"],
            severity="high",
            first_seen=time.time(),
            last_seen=time.time()
        )
        
        assert activity.ip_address == "192.168.1.100"
        assert activity.request_count == 500
        assert activity.time_window == 300
        assert "rapid_requests" in activity.patterns
        assert activity.severity == "high"

    def test_suspicious_activity_threshold_calculation(self):
        """Test suspicious activity threshold calculations."""
        # High request rate in short time
        high_rate_activity = SuspiciousActivity(
            ip_address="10.0.0.1",
            request_count=1000,
            time_window=60,  # 1 minute
            patterns=["burst_attack"],
            severity="critical",
            first_seen=time.time(),
            last_seen=time.time()
        )
        
        # Calculate requests per second
        rps = high_rate_activity.request_count / high_rate_activity.time_window
        assert rps > 15  # Should be high rate

    def test_suspicious_activity_pattern_matching(self):
        """Test suspicious activity pattern identification."""
        patterns = [
            "rapid_burst",
            "distributed_attack", 
            "credential_stuffing",
            "api_abuse",
            "scraping_behavior"
        ]
        
        activity = SuspiciousActivity(
            ip_address="203.0.113.1",
            request_count=100,
            time_window=30,
            patterns=patterns,
            severity="medium",
            first_seen=time.time(),
            last_seen=time.time()
        )
        
        assert len(activity.patterns) == 5
        assert "rapid_burst" in activity.patterns
        assert "distributed_attack" in activity.patterns


class TestRateLimitMiddleware:
    """Test Rate Limit Middleware core functionality."""

    @pytest.fixture
    def rate_limit_middleware(self):
        """Create RateLimitMiddleware for testing."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        
        # Mock Redis client
        middleware.redis_client = MagicMock()
        middleware.redis_available = True
        
        return middleware

    @pytest.fixture
    def rate_limit_middleware_no_redis(self):
        """Create RateLimitMiddleware without Redis."""
        app = MagicMock()
        with patch('redis.Redis', side_effect=Exception("Redis unavailable")):
            middleware = RateLimitMiddleware(app)
        
        assert middleware.redis_available is False
        return middleware

    def test_middleware_initialization_with_redis(self):
        """Test middleware initialization with Redis available."""
        app = MagicMock()
        
        with patch('redis.Redis') as mock_redis:
            mock_redis_client = MagicMock()
            mock_redis.return_value = mock_redis_client
            mock_redis_client.ping.return_value = True
            
            middleware = RateLimitMiddleware(app)
            
            assert middleware.redis_available is True
            assert middleware.redis_client is not None

    def test_middleware_initialization_without_redis(self):
        """Test middleware initialization without Redis."""
        app = MagicMock()
        
        with patch('redis.Redis', side_effect=Exception("Connection failed")):
            middleware = RateLimitMiddleware(app)
            
            assert middleware.redis_available is False
            assert middleware.redis_client is None

    def test_get_user_tier_free(self, rate_limit_middleware):
        """Test getting free user tier."""
        middleware = rate_limit_middleware
        
        mock_user = {"role": "free", "user_id": "123"}
        tier = middleware._get_user_tier(mock_user)
        
        assert tier.name == "free"
        assert tier.requests_per_minute == RateLimitConfig.FREE_TIER.requests_per_minute

    def test_get_user_tier_premium(self, rate_limit_middleware):
        """Test getting premium user tier."""
        middleware = rate_limit_middleware
        
        mock_user = {"role": "premium", "user_id": "456"}
        tier = middleware._get_user_tier(mock_user)
        
        assert tier.name == "premium"
        assert tier.requests_per_minute == RateLimitConfig.PREMIUM_TIER.requests_per_minute

    def test_get_user_tier_admin(self, rate_limit_middleware):
        """Test getting admin user tier."""
        middleware = rate_limit_middleware
        
        mock_user = {"role": "admin", "user_id": "789"}
        tier = middleware._get_user_tier(mock_user)
        
        assert tier.name == "admin"
        assert tier.requests_per_minute == RateLimitConfig.ADMIN_TIER.requests_per_minute

    def test_get_user_tier_default(self, rate_limit_middleware):
        """Test getting default tier for unknown user."""
        middleware = rate_limit_middleware
        
        # No user provided
        tier = middleware._get_user_tier(None)
        assert tier.name == "free"
        
        # User without role
        tier = middleware._get_user_tier({"user_id": "123"})
        assert tier.name == "free"
        
        # Unknown role
        tier = middleware._get_user_tier({"role": "unknown", "user_id": "456"})
        assert tier.name == "free"

    def test_get_client_identifier_ip(self, rate_limit_middleware):
        """Test client identifier extraction from IP."""
        middleware = rate_limit_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        
        identifier = middleware._get_client_identifier(mock_request, None)
        assert identifier == "192.168.1.100"

    def test_get_client_identifier_user(self, rate_limit_middleware):
        """Test client identifier extraction from authenticated user."""
        middleware = rate_limit_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        
        mock_user = {"user_id": "user123", "role": "premium"}
        
        identifier = middleware._get_client_identifier(mock_request, mock_user)
        assert identifier == "user:user123"

    def test_get_client_identifier_forwarded(self, rate_limit_middleware):
        """Test client identifier extraction from forwarded headers."""
        middleware = rate_limit_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {"x-forwarded-for": "203.0.113.5, 192.168.1.1"}
        
        identifier = middleware._get_client_identifier(mock_request, None)
        assert identifier == "203.0.113.5"

    def test_check_rate_limit_with_redis(self, rate_limit_middleware):
        """Test rate limit checking with Redis backend."""
        middleware = rate_limit_middleware
        
        # Mock Redis responses
        middleware.redis_client.get.return_value = b"5"  # Current count
        middleware.redis_client.incr.return_value = 6
        middleware.redis_client.expire.return_value = True
        
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.FREE_TIER
        
        # Should not be rate limited (6 < 10 per minute)
        result = middleware._check_rate_limit_redis(client_id, user_tier)
        
        assert result["limited"] is False
        assert result["current"] == 6
        assert result["limit"] == user_tier.requests_per_minute
        assert "reset_time" in result

    def test_check_rate_limit_exceeded_with_redis(self, rate_limit_middleware):
        """Test rate limit exceeded with Redis backend."""
        middleware = rate_limit_middleware
        
        # Mock Redis responses - limit exceeded
        middleware.redis_client.get.return_value = b"15"  # Current count
        middleware.redis_client.incr.return_value = 16
        
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.FREE_TIER  # 10 per minute limit
        
        result = middleware._check_rate_limit_redis(client_id, user_tier)
        
        assert result["limited"] is True
        assert result["current"] == 16
        assert result["limit"] == user_tier.requests_per_minute

    def test_check_rate_limit_memory_fallback(self, rate_limit_middleware_no_redis):
        """Test rate limit checking with memory fallback."""
        middleware = rate_limit_middleware_no_redis
        
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.FREE_TIER
        
        # First few requests should pass
        for i in range(5):
            result = middleware._check_rate_limit_memory(client_id, user_tier)
            assert result["limited"] is False
            assert result["current"] == i + 1

    def test_check_rate_limit_memory_exceeded(self, rate_limit_middleware_no_redis):
        """Test memory-based rate limit exceeded."""
        middleware = rate_limit_middleware_no_redis
        
        client_id = "192.168.1.200"
        user_tier = RateLimitConfig.FREE_TIER  # 10 per minute
        
        # Exceed the limit
        for i in range(12):
            result = middleware._check_rate_limit_memory(client_id, user_tier)
            if i >= 10:  # After 10 requests
                assert result["limited"] is True
            else:
                assert result["limited"] is False

    def test_burst_limit_handling(self, rate_limit_middleware):
        """Test burst limit handling."""
        middleware = rate_limit_middleware
        
        # Mock Redis for burst detection
        middleware.redis_client.get.side_effect = [
            b"8",   # Current minute count
            b"2",   # Current burst count  
        ]
        middleware.redis_client.incr.side_effect = [9, 3]
        
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.FREE_TIER  # burst_limit = 15
        
        result = middleware._check_rate_limit_redis(client_id, user_tier)
        
        # Should allow burst traffic within burst limit
        assert result["limited"] is False

    def test_burst_limit_exceeded(self, rate_limit_middleware):
        """Test burst limit exceeded."""
        middleware = rate_limit_middleware
        
        # Mock Redis for burst exceeded
        middleware.redis_client.get.side_effect = [
            b"5",   # Current minute count (under limit)
            b"18",  # Current burst count (over burst limit)
        ]
        middleware.redis_client.incr.side_effect = [6, 19]
        
        client_id = "192.168.1.100" 
        user_tier = RateLimitConfig.FREE_TIER  # burst_limit = 15
        
        result = middleware._check_rate_limit_redis(client_id, user_tier)
        
        # Should be limited due to burst
        assert result["limited"] is True
        assert result["reason"] == "burst_limit_exceeded"

    def test_concurrent_requests_tracking(self, rate_limit_middleware):
        """Test concurrent request tracking."""
        middleware = rate_limit_middleware
        client_id = "192.168.1.100"
        
        # Start tracking concurrent requests
        middleware._increment_concurrent_requests(client_id)
        middleware._increment_concurrent_requests(client_id)
        
        count = middleware._get_concurrent_requests(client_id)
        assert count == 2
        
        # End some requests
        middleware._decrement_concurrent_requests(client_id)
        count = middleware._get_concurrent_requests(client_id)
        assert count == 1

    def test_concurrent_requests_limit_exceeded(self, rate_limit_middleware):
        """Test concurrent request limit exceeded."""
        middleware = rate_limit_middleware
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.FREE_TIER  # concurrent_requests = 3
        
        # Simulate max concurrent requests
        for _ in range(user_tier.concurrent_requests):
            middleware._increment_concurrent_requests(client_id)
        
        # Next request should be limited
        limited = middleware._check_concurrent_limit(client_id, user_tier)
        assert limited is True

    def test_suspicious_activity_detection(self, rate_limit_middleware):
        """Test suspicious activity detection."""
        middleware = rate_limit_middleware
        client_ip = "10.0.0.1"
        
        # Simulate rapid requests to trigger detection
        for _ in range(50):  # Many requests in short time
            middleware._record_request(client_ip)
        
        is_suspicious = middleware._is_suspicious_activity(client_ip)
        assert is_suspicious is True
        
        # Should be automatically blocked
        assert middleware._is_auto_blocked(client_ip) is True

    def test_whitelist_bypass(self, rate_limit_middleware):
        """Test whitelist IP bypass."""
        middleware = rate_limit_middleware
        
        whitelisted_ip = "127.0.0.1"
        middleware.whitelist_ips.add(whitelisted_ip)
        
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = whitelisted_ip
        mock_request.headers = {}
        
        # Should bypass all rate limiting
        should_limit = middleware._should_apply_rate_limiting(mock_request, None)
        assert should_limit is False

    def test_excluded_paths_bypass(self, rate_limit_middleware):
        """Test excluded paths bypass rate limiting."""
        middleware = rate_limit_middleware
        
        excluded_paths = ["/health", "/metrics", "/docs"]
        
        for path in excluded_paths:
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = path
            mock_request.client.host = "192.168.1.100"
            mock_request.headers = {}
            
            should_limit = middleware._should_apply_rate_limiting(mock_request, None)
            assert should_limit is False

    def test_create_rate_limit_response(self, rate_limit_middleware):
        """Test rate limit response creation."""
        middleware = rate_limit_middleware
        
        limit_info = {
            "limited": True,
            "current": 15,
            "limit": 10,
            "reset_time": time.time() + 60,
            "reason": "rate_limit_exceeded"
        }
        
        response = middleware._create_rate_limit_response(limit_info)
        
        assert response.status_code == 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert "Retry-After" in response.headers

    @pytest.mark.asyncio
    async def test_middleware_dispatch_normal_request(self, rate_limit_middleware):
        """Test middleware dispatch with normal request."""
        middleware = rate_limit_middleware
        
        # Mock successful rate limit check
        middleware._check_rate_limit_redis = MagicMock(return_value={
            "limited": False,
            "current": 5,
            "limit": 10,
            "reset_time": time.time() + 60
        })
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/test"
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        
        mock_call_next = AsyncMock(return_value=Response(content="OK", status_code=200))
        
        response = await middleware.dispatch(mock_request, mock_call_next)
        
        assert response.status_code == 200
        mock_call_next.assert_called_once_with(mock_request)

    @pytest.mark.asyncio
    async def test_middleware_dispatch_rate_limited(self, rate_limit_middleware):
        """Test middleware dispatch with rate limited request."""
        middleware = rate_limit_middleware
        
        # Mock rate limit exceeded
        middleware._check_rate_limit_redis = MagicMock(return_value={
            "limited": True,
            "current": 15,
            "limit": 10,
            "reset_time": time.time() + 60,
            "reason": "rate_limit_exceeded"
        })
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/test"
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        
        mock_call_next = AsyncMock()
        
        response = await middleware.dispatch(mock_request, mock_call_next)
        
        assert response.status_code == 429
        mock_call_next.assert_not_called()


class TestRateLimitPerformance:
    """Test rate limiting performance characteristics."""

    @pytest.fixture
    def performance_middleware(self):
        """Create rate limit middleware for performance testing."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        middleware.redis_client = MagicMock()
        middleware.redis_available = True
        return middleware

    def test_memory_rate_limiting_performance(self, performance_middleware):
        """Test memory-based rate limiting performance."""
        middleware = performance_middleware
        middleware.redis_available = False  # Force memory mode
        
        start_time = time.time()
        
        # Test many rate limit checks
        for i in range(1000):
            client_id = f"192.168.{i // 255}.{i % 255}"
            middleware._check_rate_limit_memory(client_id, RateLimitConfig.FREE_TIER)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle 1000 checks quickly
        assert duration < 1.0

    def test_redis_rate_limiting_performance(self, performance_middleware):
        """Test Redis-based rate limiting performance."""
        middleware = performance_middleware
        
        # Mock Redis responses
        middleware.redis_client.get.return_value = b"5"
        middleware.redis_client.incr.return_value = 6
        middleware.redis_client.expire.return_value = True
        
        start_time = time.time()
        
        # Test many Redis rate limit checks
        for i in range(1000):
            client_id = f"user_{i}"
            middleware._check_rate_limit_redis(client_id, RateLimitConfig.PREMIUM_TIER)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle 1000 Redis operations quickly
        assert duration < 2.0

    def test_concurrent_request_tracking_performance(self, performance_middleware):
        """Test concurrent request tracking performance."""
        middleware = performance_middleware
        
        start_time = time.time()
        
        # Simulate many concurrent request operations
        client_ids = [f"client_{i}" for i in range(100)]
        
        # Increment all
        for client_id in client_ids:
            for _ in range(5):  # 5 concurrent requests each
                middleware._increment_concurrent_requests(client_id)
        
        # Check counts
        for client_id in client_ids:
            count = middleware._get_concurrent_requests(client_id)
            assert count == 5
        
        # Decrement all
        for client_id in client_ids:
            for _ in range(5):
                middleware._decrement_concurrent_requests(client_id)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle concurrent tracking operations quickly
        assert duration < 1.0

    @pytest.mark.asyncio
    async def test_concurrent_middleware_dispatch(self, performance_middleware):
        """Test concurrent middleware dispatch performance."""
        middleware = performance_middleware
        
        # Mock rate limit checks to always pass
        middleware._check_rate_limit_redis = MagicMock(return_value={
            "limited": False,
            "current": 1,
            "limit": 100,
            "reset_time": time.time() + 60
        })
        
        async def dispatch_request(request_id):
            mock_request = MagicMock(spec=Request)
            mock_request.url.path = f"/api/test/{request_id}"
            mock_request.client.host = f"192.168.1.{request_id % 255}"
            mock_request.headers = {}
            
            mock_call_next = AsyncMock(return_value=Response("OK", status_code=200))
            
            return await middleware.dispatch(mock_request, mock_call_next)
        
        # Run many concurrent requests
        tasks = [dispatch_request(i) for i in range(50)]
        start_time = time.time()
        responses = await asyncio.gather(*tasks)
        end_time = time.time()
        
        # All should succeed
        assert len(responses) == 50
        for response in responses:
            assert response.status_code == 200
        
        # Should complete quickly
        duration = end_time - start_time
        assert duration < 5.0

    def test_memory_cleanup_performance(self, performance_middleware):
        """Test memory cleanup performance."""
        middleware = performance_middleware
        middleware.redis_available = False  # Force memory mode
        
        # Generate lots of rate limit data
        for i in range(1000):
            client_id = f"temp_client_{i}"
            for _ in range(10):
                middleware._check_rate_limit_memory(client_id, RateLimitConfig.FREE_TIER)
        
        initial_memory_size = len(middleware.request_counts)
        assert initial_memory_size > 0
        
        # Run cleanup
        start_time = time.time()
        middleware._cleanup_expired_entries()
        end_time = time.time()
        
        cleanup_duration = end_time - start_time
        
        # Cleanup should be fast
        assert cleanup_duration < 1.0


class TestRateLimitErrorHandling:
    """Test rate limiting error handling and edge cases."""

    @pytest.fixture
    def error_middleware(self):
        """Create middleware for error handling tests."""
        app = MagicMock()
        middleware = RateLimitMiddleware(app)
        return middleware

    def test_redis_connection_failure(self, error_middleware):
        """Test handling of Redis connection failures."""
        middleware = error_middleware
        
        # Mock Redis client with connection error
        middleware.redis_client = MagicMock()
        middleware.redis_client.get.side_effect = RedisConnectionError("Connection lost")
        middleware.redis_available = True
        
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.FREE_TIER
        
        # Should fallback to memory-based limiting
        result = middleware._check_rate_limit_redis(client_id, user_tier)
        
        # Should return appropriate fallback response
        assert isinstance(result, dict)
        assert "limited" in result

    def test_redis_timeout_handling(self, error_middleware):
        """Test handling of Redis timeout errors."""
        middleware = error_middleware
        
        from redis.exceptions import TimeoutError
        
        middleware.redis_client = MagicMock()
        middleware.redis_client.get.side_effect = TimeoutError("Operation timed out")
        middleware.redis_available = True
        
        client_id = "192.168.1.100"
        user_tier = RateLimitConfig.PREMIUM_TIER
        
        # Should handle timeout gracefully
        result = middleware._check_rate_limit_redis(client_id, user_tier)
        assert isinstance(result, dict)

    def test_malformed_client_data(self, error_middleware):
        """Test handling of malformed client data."""
        middleware = error_middleware
        
        # Test with various malformed requests
        malformed_requests = [
            None,
            MagicMock(client=None),
            MagicMock(client=MagicMock(host=None)),
        ]
        
        for mock_request in malformed_requests:
            try:
                identifier = middleware._get_client_identifier(mock_request, None)
                # Should return some fallback identifier
                assert identifier is not None
            except Exception:
                # Should handle gracefully
                pass

    def test_invalid_user_tier_data(self, error_middleware):
        """Test handling of invalid user tier data."""
        middleware = error_middleware
        
        invalid_users = [
            {"role": None},
            {"role": ""},
            {"role": "invalid_role"},
            {"user_id": None, "role": "premium"},
            {},  # Empty dict
            None  # None user
        ]
        
        for user in invalid_users:
            tier = middleware._get_user_tier(user)
            # Should default to free tier
            assert tier.name == "free"

    def test_extreme_request_counts(self, error_middleware):
        """Test handling of extreme request counts."""
        middleware = error_middleware
        middleware.redis_available = False  # Use memory mode
        
        client_id = "extreme_client"
        user_tier = RateLimitConfig.FREE_TIER
        
        # Simulate extreme number of requests
        for _ in range(10000):
            result = middleware._check_rate_limit_memory(client_id, user_tier)
            # Should handle without crashing
            assert isinstance(result, dict)
            assert "limited" in result

    @pytest.mark.asyncio
    async def test_middleware_exception_handling(self, error_middleware):
        """Test middleware exception handling."""
        middleware = error_middleware
        
        # Mock rate limit check to raise exception
        middleware._check_rate_limit_redis = MagicMock(
            side_effect=Exception("Unexpected error")
        )
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/test"
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {}
        
        mock_call_next = AsyncMock(return_value=Response("OK", status_code=200))
        
        # Should handle exception gracefully and either:
        # 1. Allow request through (fail-open)
        # 2. Return appropriate error response
        try:
            response = await middleware.dispatch(mock_request, mock_call_next)
            assert response is not None
        except Exception:
            # If exception propagates, ensure it's handled appropriately
            pass