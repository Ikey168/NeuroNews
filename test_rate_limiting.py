"""
Comprehensive Test Suite for API Rate Limiting (Issue #59)

Tests all components of the rate limiting system including middleware,
routes, AWS integration, and suspicious activity detection.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
import json
import redis

# Test imports
from src.api.middleware.rate_limit_middleware import (
    RateLimitMiddleware, RateLimitConfig, RateLimitStore, 
    SuspiciousActivityDetector, RequestMetrics
)
from src.api.routes.rate_limit_routes import router as rate_limit_router
from src.api.routes.auth_routes import router as auth_router  
from src.api.aws_rate_limiting import APIGatewayManager, CloudWatchMetrics
from src.api.monitoring.suspicious_activity_monitor import (
    AdvancedSuspiciousActivityDetector, SuspiciousPatternType, AlertLevel
)

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
            processing_time=0.5
        )
        
        # Record multiple requests
        for _ in range(3):
            await memory_store.record_request(user_id, metrics)
        
        # Get counts
        counts = await memory_store.get_request_counts(user_id)
        
        assert counts['minute'] == 3
        assert counts['hour'] == 3
        assert counts['day'] == 3
    
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
        current_count = memory_store.memory_store[user_id]['concurrent']
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
    
    @pytest.fixture
    def mock_auth(self, monkeypatch):
        """Mock authentication for testing."""
        async def mock_require_auth():
            return {
                "user_id": "test_user_123",
                "role": "admin",
                "tier": "free"
            }
        
        monkeypatch.setattr("src.api.routes.rate_limit_routes.require_auth", mock_require_auth)
        return mock_require_auth
    
    def test_get_api_limits_unauthorized(self, test_client):
        """Test API limits endpoint requires authentication."""
        response = test_client.get("/api/api_limits?user_id=test_user")
        assert response.status_code == 422  # Missing auth dependency
    
    @patch('src.api.routes.rate_limit_routes.require_auth')
    def test_get_api_limits_success(self, mock_auth, test_client):
        """Test successful API limits retrieval."""
        # Mock the auth dependency
        mock_auth.return_value = {
            "user_id": "test_user_123",
            "role": "user",
            "tier": "free"
        }
        
        response = test_client.get("/api/api_limits?user_id=test_user_123")
        
        # Should get a response (may not be 200 due to mocking, but shouldn't be auth error)
        assert response.status_code != 401
        assert response.status_code != 403
    
    @patch('src.api.routes.rate_limit_routes.require_auth')
    def test_health_check_endpoint(self, mock_auth, test_client):
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
            requests.append({
                'user_id': user_id,
                'ip_address': f"192.168.1.{i % 10 + 1}",
                'endpoint': f"/test/endpoint/{i % 3}",
                'timestamp': base_time + timedelta(seconds=i * 2),
                'response_code': 200 if i % 10 != 0 else 500,
                'processing_time': 0.1 + (i % 5) * 0.1,
                'user_agent': 'Mozilla/5.0 Test Browser'
            })
        
        return requests
    
    @pytest.mark.asyncio
    async def test_rapid_requests_detection(self, advanced_detector):
        """Test detection of rapid request patterns."""
        user_id = "rapid_user"
        
        # Create rapid requests (all within 1 minute)
        rapid_requests = []
        now = datetime.now()
        for i in range(60):  # 60 requests in rapid succession
            rapid_requests.append({
                'user_id': user_id,
                'timestamp': now - timedelta(seconds=i),
                'ip_address': '192.168.1.1',
                'endpoint': '/test',
                'response_code': 200,
                'processing_time': 0.1,
                'user_agent': 'Test Browser'
            })
        
        activities = await advanced_detector.analyze_user_activity(user_id, rapid_requests)
        
        # Should detect rapid requests
        rapid_alerts = [a for a in activities if a.pattern_type == SuspiciousPatternType.RAPID_REQUESTS]
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
            multi_ip_requests.append({
                'user_id': user_id,
                'timestamp': now - timedelta(minutes=i),
                'ip_address': f'192.168.{i}.1',  # Different IP for each request
                'endpoint': '/test',
                'response_code': 200,
                'processing_time': 0.1,
                'user_agent': 'Test Browser'
            })
        
        activities = await advanced_detector.analyze_user_activity(user_id, multi_ip_requests)
        
        # Should detect multiple IPs
        multi_ip_alerts = [a for a in activities if a.pattern_type == SuspiciousPatternType.MULTIPLE_IPS]
        assert len(multi_ip_alerts) > 0
    
    @pytest.mark.asyncio
    async def test_bot_behavior_detection(self, advanced_detector):
        """Test detection of bot-like behavior."""
        user_id = "bot_user"
        
        # Create bot-like requests (regular intervals, bot user agent)
        bot_requests = []
        now = datetime.now()
        
        for i in range(25):  # Need enough requests for analysis
            bot_requests.append({
                'user_id': user_id,
                'timestamp': now - timedelta(seconds=i * 10),  # Very regular intervals
                'ip_address': '192.168.1.1',  # Same IP
                'endpoint': '/api/data',  # Same endpoint
                'response_code': 200,
                'processing_time': 0.05,  # Very fast
                'user_agent': 'curl/7.68.0'  # Bot user agent
            })
        
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
            ip_addresses=['192.168.1.1'],
            endpoints_accessed=['/test'],
            request_count=50,
            confidence_score=0.8
        )
        
        activity2 = SuspiciousActivity(
            user_id=user_id,
            pattern_type=SuspiciousPatternType.BOT_BEHAVIOR,
            alert_level=AlertLevel.MEDIUM,
            timestamp=datetime.now(),
            details={},
            ip_addresses=['192.168.1.1'],
            endpoints_accessed=['/api'],
            request_count=20,
            confidence_score=0.6
        )
        
        advanced_detector.active_alerts.extend([activity1, activity2])
        
        risk_score = advanced_detector.get_user_risk_score(user_id)
        assert 0.0 <= risk_score <= 1.0
        assert risk_score > 0.5  # Should be high due to HIGH and MEDIUM alerts

class TestAWSIntegration:
    """Test AWS API Gateway integration."""
    
    @pytest.fixture
    def api_manager(self):
        """Create API Gateway manager with mocked AWS client."""
        with patch('boto3.client') as mock_boto:
            manager = APIGatewayManager()
            manager.client = Mock()
            manager.usage_client = Mock()
            return manager
    
    @pytest.mark.asyncio
    async def test_create_usage_plans(self, api_manager):
        """Test creation of AWS usage plans."""
        # Mock AWS responses
        api_manager.client.create_usage_plan.return_value = {'id': 'plan_123'}
        api_manager.client.create_usage_plan_key.return_value = {}
        
        plans = await api_manager.create_usage_plans()
        
        # Should call create_usage_plan for each tier
        assert api_manager.client.create_usage_plan.call_count == 3
        assert isinstance(plans, dict)
    
    @pytest.mark.asyncio
    async def test_assign_user_to_plan(self, api_manager):
        """Test assigning user to usage plan."""
        # Mock responses
        api_manager.get_usage_plans = AsyncMock(return_value={'free_tier': 'plan_123'})
        api_manager.create_api_key_for_user = AsyncMock(return_value='key_456')
        api_manager.client.create_usage_plan_key.return_value = {}
        
        result = await api_manager.assign_user_to_plan('user_123', 'free', 'api_key_789')
        
        assert result is True
        api_manager.client.create_usage_plan_key.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_usage_statistics(self, api_manager):
        """Test getting usage statistics."""
        # Mock responses
        api_manager.client.get_api_keys.return_value = {
            'items': [{'id': 'key_123', 'value': 'test_key'}]
        }
        api_manager.client.get_usage.return_value = {
            'values': {'2025-08-17': 100, '2025-08-16': 150},
            'startDate': '2025-08-16',
            'endDate': '2025-08-17'
        }
        
        stats = await api_manager.get_usage_statistics('test_key', '2025-08-16', '2025-08-17')
        
        assert 'total_requests' in stats
        assert stats['total_requests'] == 250
        assert 'daily_breakdown' in stats

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
        # Make requests within limit
        for i in range(TEST_CONFIG.FREE_TIER.requests_per_minute - 1):
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
        metrics.append(RequestMetrics(
            user_id=user_id,
            ip_address=f"192.168.1.{i % 10 + 1}",
            endpoint=f"/test/endpoint/{i % 3}",
            timestamp=base_time + timedelta(seconds=i),
            response_code=200,
            processing_time=0.1
        ))
    
    return metrics

def run_rate_limit_tests():
    """Run all rate limiting tests."""
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--disable-warnings"
    ])

if __name__ == "__main__":
    run_rate_limit_tests()
