"""
Comprehensive Test Suite for API Rate Limiting (Issue #59)

Tests all components of the rate limiting system including middleware,
routes, AWS integration, and suspicious activity detection.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.aws_rate_limiting import LocalUsagePlanManager

# Test imports
from src.api.middleware.rate_limit_middleware import (
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitStore,
    RequestMetrics,
    SuspiciousActivityDetector,
)
from src.api.monitoring.suspicious_activity_monitor import (
    AdvancedSuspiciousActivityDetector,
    AlertLevel,
    SuspiciousPatternType,
)
from src.api.auth.jwt_auth import require_auth
from src.api.routes.auth_routes import router as auth_router
from src.api.routes.rate_limit_routes import router as rate_limit_router

# Test configuration
TEST_CONFIG = RateLimitConfig()
TEST_CONFIG.FREE_TIER.requests_per_minute = 5  # Lower for testing
TEST_CONFIG.FREE_TIER.requests_per_hour = 20
TEST_CONFIG.FREE_TIER.concurrent_requests = 2


class TestRateLimitStore:
    """Test the rate limit storage backend."""

    @pytest.fixture
    def memory_store(self):
        """Create in-memory store for testing."""
        return RateLimitStore(use_redis=False)

    @pytest.fixture
    def redis_store(self):
        """Create Redis store for testing (if available)."""
        try:
            store = RateLimitStore(use_redis=True)
            if store.use_redis:
                return store
            else:
                pytest.skip("Redis not available")
        except Exception:
            pytest.skip("Redis not available")

    def test_memory_store_initialization(self, memory_store):
        """Test memory store initializes correctly."""
        assert not memory_store.use_redis
        assert memory_store.memory_store is not None

    @pytest.mark.asyncio
    async def test_record_and_get_requests_memory(self, memory_store):
        """Test recording and retrieving request counts in memory."""
        user_id = "test_user_123"

        # Create test metrics
        metrics = RequestMetrics(
            user_id=user_id,
            ip_address="192.168.1.1",
            endpoint="/test",
            timestamp=datetime.now(),
            response_code=200,
            processing_time=0.5,
        )

        # Record multiple requests
        for _ in range(3):
            await memory_store.record_request(user_id, metrics)

        # Get counts
        counts = await memory_store.get_request_counts(user_id)

        assert counts["minute"] == 3
        assert counts["hour"] == 3
        assert counts["day"] == 3

    @pytest.mark.asyncio
    async def test_concurrent_request_tracking(self, memory_store):
        """Test concurrent request tracking."""
        user_id = "test_user_concurrent"

        # Increment concurrent requests
        count1 = await memory_store.increment_concurrent(user_id)
        count2 = await memory_store.increment_concurrent(user_id)

        assert count1 == 1
        assert count2 == 2

        # Decrement
        await memory_store.decrement_concurrent(user_id)
        current_count = memory_store.memory_store[user_id]["concurrent"]
        assert current_count == 1


class TestRateLimitMiddleware:
    """Test the rate limiting middleware."""

    @pytest.fixture
    def test_app(self):
        """Create test FastAPI app with rate limiting."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, config=TEST_CONFIG)

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        @app.get("/protected")
        async def protected_endpoint():
            return {"message": "protected"}

        return app

    @pytest.fixture
    def test_client(self, test_app):
        """Create test client."""
        return TestClient(test_app)

    def test_normal_request_passes(self, test_client):
        """Test that normal requests pass through."""
        response = test_client.get("/test")
        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_rate_limit_headers_added(self, test_client):
        """Test that rate limit headers are added to responses."""
        response = test_client.get("/test")

        # Check for rate limit headers
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Limit-Hour" in response.headers
        assert "X-RateLimit-Limit-Day" in response.headers
        assert "X-RateLimit-Tier" in response.headers

    def test_rate_limit_enforcement(self, test_client):
        """Test that rate limits are enforced."""
        # Make requests up to the limit
        for i in range(TEST_CONFIG.FREE_TIER.requests_per_minute):
            response = test_client.get("/test")
            assert response.status_code == 200

        # Next request should be rate limited
        response = test_client.get("/test")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["error"]

    def test_excluded_paths_not_rate_limited(self, test_client):
        """Test that excluded paths bypass rate limiting."""
        # Make many requests to docs endpoint
        for _ in range(10):
            response = test_client.get("/docs")
            # Should not be rate limited (but may 404 since not actually set up)
            assert response.status_code != 429


class TestRateLimitRoutes:
    """Test the rate limiting API routes."""

    @pytest.fixture
    def test_app(self):
        """Create test app with rate limit routes."""
        app = FastAPI()
        app.include_router(rate_limit_router)
        app.include_router(auth_router)
        return app

    @pytest.fixture
    def test_client(self, test_app):
        """Create test client."""
        return TestClient(test_app)

    def test_get_api_limits_unauthorized(self, test_client):
        """Test API limits endpoint requires authentication."""
        response = test_client.get("/api/api_limits?user_id=test_user")
        # require_auth raises 401 when no bearer token is supplied
        assert response.status_code == 401

    def test_get_api_limits_success(self, test_app, test_client):
        """Test successful API limits retrieval."""
        # Override the auth dependency on the app so the request is treated as
        # authenticated. require_auth is the dependency object used in
        # Depends(...), so it is the correct override key.
        test_app.dependency_overrides[require_auth] = lambda: {
            "user_id": "test_user_123",
            "role": "user",
            "tier": "free",
        }
        try:
            response = test_client.get("/api/api_limits?user_id=test_user_123")
        finally:
            test_app.dependency_overrides.pop(require_auth, None)

        # Should get a response (may not be 200 due to mocking, but shouldn't be auth error)
        assert response.status_code != 401
        assert response.status_code != 403

    def test_health_check_endpoint(self, test_client):
        """Test rate limiting health check."""
        response = test_client.get("/api/api_limits/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "store_backend" in data
        assert "timestamp" in data


class TestSuspiciousActivityDetector:
    """Test the suspicious activity detection system."""

    @pytest.fixture
    def detector(self):
        """Create suspicious activity detector."""
        store = RateLimitStore(use_redis=False)
        config = RateLimitConfig()
        return SuspiciousActivityDetector(store, config)

    @pytest.fixture
    def advanced_detector(self):
        """Create advanced suspicious activity detector."""
        return AdvancedSuspiciousActivityDetector()

    def create_test_requests(self, count: int, user_id: str = "test_user") -> list:
        """Create test request data."""
        requests = []
        base_time = datetime.now() - timedelta(minutes=5)

        for i in range(count):
            requests.append(
                {
                    "user_id": user_id,
                    "ip_address": "192.168.1.{0}".format(i % 10 + 1),
                    "endpoint": "/test/endpoint/{0}".format(i % 3),
                    "timestamp": base_time + timedelta(seconds=i * 2),
                    "response_code": 200 if i % 10 != 0 else 500,
                    "processing_time": 0.1 + (i % 5) * 0.1,
                    "user_agent": "Mozilla/5.0 Test Browser",
                }
            )

        return requests

    @pytest.mark.asyncio
    async def test_rapid_requests_detection(self, advanced_detector):
        """Test detection of rapid request patterns."""
        user_id = "rapid_user"

        # Create rapid requests (all within 1 minute)
        rapid_requests = []
        now = datetime.now()
        for i in range(60):  # 60 requests in rapid succession
            rapid_requests.append(
                {
                    "user_id": user_id,
                    "timestamp": now - timedelta(seconds=i),
                    "ip_address": "192.168.1.1",
                    "endpoint": "/test",
                    "response_code": 200,
                    "processing_time": 0.1,
                    "user_agent": "Test Browser",
                }
            )

        activities = await advanced_detector.analyze_user_activity(user_id, rapid_requests)

        # Should detect rapid requests
        rapid_alerts = [
            a for a in activities if a.pattern_type == SuspiciousPatternType.RAPID_REQUESTS
        ]
        assert len(rapid_alerts) > 0
        assert rapid_alerts[0].alert_level == AlertLevel.HIGH

    @pytest.mark.asyncio
    async def test_multiple_ip_detection(self, advanced_detector):
        """Test detection of requests from multiple IPs."""
        user_id = "multi_ip_user"

        # Create requests from multiple IPs
        multi_ip_requests = []
        now = datetime.now()

        for i in range(20):
            multi_ip_requests.append(
                {
                    "user_id": user_id,
                    "timestamp": now - timedelta(minutes=i),
                    "ip_address": "192.168.{0}.1".format(i),  # Different IP for each request
                    "endpoint": "/test",
                    "response_code": 200,
                    "processing_time": 0.1,
                    "user_agent": "Test Browser",
                }
            )

        activities = await advanced_detector.analyze_user_activity(user_id, multi_ip_requests)

        # Should detect multiple IPs
        multi_ip_alerts = [
            a for a in activities if a.pattern_type == SuspiciousPatternType.MULTIPLE_IPS
        ]
        assert len(multi_ip_alerts) > 0

    @pytest.mark.asyncio
    async def test_bot_behavior_detection(self, advanced_detector):
        """Test detection of bot-like behavior."""
        user_id = "bot_user"

        # Create bot-like requests (regular intervals, bot user agent)
        bot_requests = []
        now = datetime.now()

        for i in range(25):  # Need enough requests for analysis
            bot_requests.append(
                {
                    "user_id": user_id,
                    "timestamp": now - timedelta(seconds=i * 10),  # Very regular intervals
                    "ip_address": "192.168.1.1",  # Same IP
                    "endpoint": "/api/data",  # Same endpoint
                    "response_code": 200,
                    "processing_time": 0.05,  # Very fast
                    "user_agent": "curl/7.68.0",  # Bot user agent
                }
            )

        activities = await advanced_detector.analyze_user_activity(user_id, bot_requests)

        # Should detect bot behavior
        bot_alerts = [a for a in activities if a.pattern_type == SuspiciousPatternType.BOT_BEHAVIOR]
        assert len(bot_alerts) > 0

    def test_user_risk_score_calculation(self, advanced_detector):
        """Test user risk score calculation."""
        user_id = "risk_user"

        # Add some suspicious activities
        from src.api.monitoring.suspicious_activity_monitor import SuspiciousActivity

        activity1 = SuspiciousActivity(
            user_id=user_id,
            pattern_type=SuspiciousPatternType.RAPID_REQUESTS,
            alert_level=AlertLevel.HIGH,
            timestamp=datetime.now(),
            details={},
            ip_addresses=["192.168.1.1"],
            endpoints_accessed=["/test"],
            request_count=50,
            confidence_score=0.8,
        )

        activity2 = SuspiciousActivity(
            user_id=user_id,
            pattern_type=SuspiciousPatternType.BOT_BEHAVIOR,
            alert_level=AlertLevel.HIGH,
            timestamp=datetime.now(),
            details={},
            ip_addresses=["192.168.1.1"],
            endpoints_accessed=["/api"],
            request_count=20,
            confidence_score=0.8,
        )

        advanced_detector.active_alerts.extend([activity1, activity2])

        # get_user_risk_score averages (confidence * level_weight) across the
        # user's recent alerts. Two HIGH alerts (0.8 weight, 0.8 confidence)
        # average to 0.64, which represents elevated risk.
        risk_score = advanced_detector.get_user_risk_score(user_id)
        assert 0.0 <= risk_score <= 1.0
        assert risk_score > 0.5  # Should be high due to two HIGH alerts


class TestAWSIntegration:
    """Test the local usage-plan manager (replaces the old AWS integration)."""

    @pytest.fixture
    def api_manager(self, tmp_path, monkeypatch):
        """Create a LocalUsagePlanManager backed by an isolated state dir.

        The manager keeps usage plans, API keys, and metrics in local JSON
        files under NEURONEWS_LOG_DIR (no AWS/boto3 client involved), so point
        it at a per-test temp directory.
        """
        monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
        return LocalUsagePlanManager()

    @pytest.mark.asyncio
    async def test_create_usage_plans(self, api_manager):
        """Test creation of usage plans for all tiers."""
        plans = await api_manager.create_usage_plans()

        # One plan per tier (free, premium, enterprise)
        assert isinstance(plans, dict)
        assert len(plans) == 3
        assert set(plans) == {"free_tier", "premium_tier", "enterprise_tier"}

    @pytest.mark.asyncio
    async def test_assign_user_to_plan(self, api_manager):
        """Test assigning a user to a usage plan."""
        # The plan must exist before a user can be assigned to it.
        await api_manager.create_usage_plans()

        result = await api_manager.assign_user_to_plan("user_123", "free", "api_key_789")

        assert result is True
        # The user's API key should now be associated with the free-tier plan.
        plans = await api_manager.get_usage_plans()
        free_plan_id = plans["free_tier"]
        key_id = "key-user_123"
        assert key_id in api_manager._state["plan_keys"][free_plan_id]

    @pytest.mark.asyncio
    async def test_get_usage_statistics(self, api_manager):
        """Test aggregating usage statistics from recorded metrics."""
        # Register a user/API key, then record RequestCount metrics for them.
        await api_manager.create_usage_plans()
        await api_manager.assign_user_to_plan("user_123", "free", "test_key")

        from src.api.aws_rate_limiting import LocalMetricsRecorder

        recorder = LocalMetricsRecorder()
        # value=requests_count, violations=0 -> two metric lines per call
        await recorder.put_rate_limit_metrics("user_123", "free", 150, 0)
        await recorder.put_rate_limit_metrics("user_123", "free", 100, 0)

        # The recorded timestamps are "now"; build a window covering today.
        today = datetime.now(timezone.utc).date().isoformat()
        stats = await api_manager.get_usage_statistics("test_key", today, today)

        assert "total_requests" in stats
        assert stats["total_requests"] == 250
        assert "daily_breakdown" in stats
        assert stats["daily_breakdown"][today] == 250


class TestIntegration:
    """Integration tests for the complete rate limiting system."""

    @pytest.fixture
    def full_app(self):
        """Create app with full rate limiting integration."""
        app = FastAPI()

        # Add rate limiting middleware
        app.add_middleware(RateLimitMiddleware, config=TEST_CONFIG)

        # Add routes
        app.include_router(rate_limit_router)

        @app.get("/api/test")
        async def test_endpoint():
            return {"message": "test successful"}

        @app.get("/api/data")
        async def data_endpoint():
            return {"data": "sensitive information"}

        return app

    @pytest.fixture
    def integration_client(self, full_app):
        """Create client for integration testing."""
        return TestClient(full_app)

    def test_end_to_end_rate_limiting(self, integration_client):
        """Test complete rate limiting flow."""
        # The middleware blocks once the recorded count reaches the limit
        # (counts["minute"] >= requests_per_minute), so the first
        # requests_per_minute requests succeed and the next one is blocked.
        for i in range(TEST_CONFIG.FREE_TIER.requests_per_minute):
            response = integration_client.get("/api/test")
            assert response.status_code == 200

            # Check rate limit headers
            assert "X-RateLimit-Limit-Minute" in response.headers
            assert "X-RateLimit-Tier" in response.headers

        # Next request should trigger rate limiting
        response = integration_client.get("/api/test")
        assert response.status_code == 429

        # Check rate limit error response
        error_data = response.json()
        assert "Rate limit exceeded" in error_data["error"]
        assert "limit" in error_data
        assert "reset_in_seconds" in error_data

    def test_different_endpoints_share_limits(self, integration_client):
        """Test that different endpoints share the same rate limit."""
        # Use up rate limit across different endpoints
        responses = []

        for i in range(TEST_CONFIG.FREE_TIER.requests_per_minute):
            if i % 2 == 0:
                response = integration_client.get("/api/test")
            else:
                response = integration_client.get("/api/data")
            responses.append(response)

        # All should succeed
        for response in responses:
            assert response.status_code == 200

        # Next request to either endpoint should be rate limited
        response = integration_client.get("/api/test")
        assert response.status_code == 429


# Utility functions for testing
def create_mock_request_metrics(user_id: str, count: int = 1) -> list:
    """Create mock request metrics for testing."""
    metrics = []
    base_time = datetime.now()

    for i in range(count):
        metrics.append(
            RequestMetrics(
                user_id=user_id,
                ip_address="192.168.1.{0}".format(i % 10 + 1),
                endpoint="/test/endpoint/{0}".format(i % 3),
                timestamp=base_time + timedelta(seconds=i),
                response_code=200,
                processing_time=0.1,
            )
        )

    return metrics


def run_rate_limit_tests():
    """Run all rate limiting tests."""
    pytest.main([__file__, "-v", "--tb=short", "--disable-warnings"])


if __name__ == "__main__":
    run_rate_limit_tests()
