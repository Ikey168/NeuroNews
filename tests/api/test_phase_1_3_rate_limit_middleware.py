"""
Comprehensive Test Suite for Rate Limiting Middleware (Issue #445)

Tests for achieving 4% → 60% coverage of src/api/middleware/rate_limit_middleware.py
Covers all major functionality including user tiers, storage backends, suspicious activity detection.
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock
from typing import Dict, List

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Import the components we need to test
from src.api.middleware.rate_limit_middleware import (
    RateLimitConfig,
    RateLimitMiddleware, 
    RateLimitStore,
    RequestMetrics,
    SuspiciousActivityDetector,
    UserTier,
)


@pytest.fixture
def sample_user_tier():
    """Create a sample user tier for testing."""
    return UserTier(
        name="test",
        requests_per_minute=10,
        requests_per_hour=100, 
        requests_per_day=1000,
        burst_limit=15,
        concurrent_requests=3
    )


@pytest.fixture
def rate_limit_config():
    """Create rate limit config for testing."""
    return RateLimitConfig()


@pytest.fixture
def request_metrics():
    """Create sample request metrics."""
    return RequestMetrics(
        user_id="test_user_123",
        ip_address="192.168.1.1",
        endpoint="/api/test",
        timestamp=datetime.now(),
        response_code=200,
        processing_time=0.5
    )


class TestUserTier:
    """Test UserTier dataclass functionality."""
    
    def test_user_tier_creation(self, sample_user_tier):
        """Test UserTier can be created with all fields."""
        assert sample_user_tier.name == "test"
        assert sample_user_tier.requests_per_minute == 10
        assert sample_user_tier.requests_per_hour == 100
        assert sample_user_tier.requests_per_day == 1000
        assert sample_user_tier.burst_limit == 15
        assert sample_user_tier.concurrent_requests == 3


class TestRateLimitConfig:
    """Test rate limit configuration."""
    
    def test_config_default_tiers(self, rate_limit_config):
        """Test default tier configurations exist."""
        assert rate_limit_config.FREE_TIER.name == "free"
        assert rate_limit_config.PREMIUM_TIER.name == "premium"
        assert rate_limit_config.ENTERPRISE_TIER.name == "enterprise"
        
        # Test tier limits are sensible
        assert rate_limit_config.FREE_TIER.requests_per_minute < rate_limit_config.PREMIUM_TIER.requests_per_minute
        assert rate_limit_config.PREMIUM_TIER.requests_per_minute < rate_limit_config.ENTERPRISE_TIER.requests_per_minute
    
    def test_suspicious_patterns_config(self, rate_limit_config):
        """Test suspicious activity patterns are configured."""
        patterns = rate_limit_config.SUSPICIOUS_PATTERNS
        assert "rapid_requests" in patterns
        assert "unusual_hours" in patterns
        assert "multiple_ips" in patterns
        assert "error_rate" in patterns
        assert "endpoint_abuse" in patterns


class TestRequestMetrics:
    """Test RequestMetrics dataclass."""
    
    def test_request_metrics_creation(self, request_metrics):
        """Test RequestMetrics can be created with all fields."""
        assert request_metrics.user_id == "test_user_123"
        assert request_metrics.ip_address == "192.168.1.1"
        assert request_metrics.endpoint == "/api/test"
        assert isinstance(request_metrics.timestamp, datetime)
        assert request_metrics.response_code == 200
        assert request_metrics.processing_time == 0.5


class TestRateLimitStore:
    """Test rate limit storage backend."""
    
    @pytest.fixture
    def memory_store(self):
        """Create in-memory store for testing."""
        return RateLimitStore(use_redis=False)
    
    @pytest.fixture
    def mock_redis_store(self):
        """Create mock Redis store for testing."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            store.use_redis = True
            return store, mock_client
    
    def test_memory_store_initialization(self, memory_store):
        """Test memory store initializes correctly."""
        assert not memory_store.use_redis
        assert memory_store.memory_store is not None
        assert isinstance(memory_store.memory_store, defaultdict)
    
    def test_redis_available_check(self):
        """Test Redis availability checking."""
        store = RateLimitStore()
        # Should return True since redis is importable
        assert store._redis_available() is True
    
    def test_get_redis_client_success(self):
        """Test Redis client creation with environment variables."""
        with patch.dict('os.environ', {
            'REDIS_HOST': 'test-host',
            'REDIS_PORT': '6380', 
            'REDIS_DB': '1'
        }):
            with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
                store = RateLimitStore(use_redis=False)  # Avoid double call
                store._get_redis_client()
                
                mock_redis.assert_called_with(
                    host='test-host',
                    port=6380,
                    db=1,
                    decode_responses=True
                )
    
    def test_get_redis_client_fallback(self):
        """Test Redis client fallback on connection error."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_redis.side_effect = Exception("Connection failed")
            
            store = RateLimitStore()
            client = store._get_redis_client()
            
            assert client is None
            assert store.use_redis is False
    
    @pytest.mark.asyncio
    async def test_record_request_memory(self, memory_store, request_metrics):
        """Test recording requests in memory store."""
        user_id = "test_user"
        
        # Record a request
        await memory_store.record_request(user_id, request_metrics)
        
        # Check it was stored
        user_data = memory_store.memory_store[user_id]
        assert len(user_data["requests"]) == 1
        assert len(user_data["metrics"]) == 1
        
        stored_request = user_data["requests"][0]
        assert stored_request["ip"] == request_metrics.ip_address
        assert stored_request["endpoint"] == request_metrics.endpoint
    
    @pytest.mark.asyncio
    async def test_record_request_redis(self, request_metrics):
        """Test recording requests in Redis store."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_pipeline = Mock()
            mock_client.pipeline.return_value = mock_pipeline
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            
            # Mock asyncio executor
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock()
                
                await store.record_request("test_user", request_metrics)
                
                # Verify pipeline operations were called
                mock_client.pipeline.assert_called_once()
                mock_pipeline.incr.assert_called()
                mock_pipeline.expire.assert_called()
                mock_pipeline.lpush.assert_called()
                mock_pipeline.ltrim.assert_called()
    
    @pytest.mark.asyncio
    async def test_get_request_counts_memory(self, memory_store, request_metrics):
        """Test getting request counts from memory store."""
        user_id = "test_user"
        
        # Record multiple requests at different times
        now = time.time()
        
        # Record current request
        await memory_store.record_request(user_id, request_metrics)
        
        # Record old request (older than 24 hours)
        old_request_data = {
            "timestamp": now - 90000,  # > 24 hours ago
            "ip": "192.168.1.2",
            "endpoint": "/old"
        }
        memory_store.memory_store[user_id]["requests"].append(old_request_data)
        
        counts = await memory_store.get_request_counts(user_id)
        
        # Should only count recent requests
        assert counts["minute"] == 1
        assert counts["hour"] == 1 
        assert counts["day"] == 1
    
    @pytest.mark.asyncio
    async def test_get_request_counts_redis(self):
        """Test getting request counts from Redis store."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_pipeline = Mock()
            mock_client.pipeline.return_value = mock_pipeline
            mock_pipeline.execute.return_value = [5, 50, 500]  # minute, hour, day
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=[5, 50, 500])
                
                counts = await store.get_request_counts("test_user")
                
                assert counts["minute"] == 5
                assert counts["hour"] == 50
                assert counts["day"] == 500
    
    @pytest.mark.asyncio
    async def test_concurrent_request_tracking_memory(self, memory_store):
        """Test concurrent request tracking in memory."""
        user_id = "test_user"
        
        # Increment concurrent requests
        count1 = await memory_store.increment_concurrent(user_id)
        count2 = await memory_store.increment_concurrent(user_id)
        
        assert count1 == 1
        assert count2 == 2
        
        # Decrement
        await memory_store.decrement_concurrent(user_id)
        assert memory_store.memory_store[user_id]["concurrent"] == 1
        
        # Don't go below 0
        await memory_store.decrement_concurrent(user_id)
        await memory_store.decrement_concurrent(user_id)
        assert memory_store.memory_store[user_id]["concurrent"] == 0
    
    @pytest.mark.asyncio
    async def test_concurrent_request_tracking_redis(self):
        """Test concurrent request tracking in Redis."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=5)
                
                count = await store.increment_concurrent("test_user")
                assert count == 5
                
                # Test decrement
                await store.decrement_concurrent("test_user")
                
                # Verify Redis operations were called (increment + expire + decrement)
                assert mock_loop.return_value.run_in_executor.call_count >= 2


class TestSuspiciousActivityDetector:
    """Test suspicious activity detection."""
    
    @pytest.fixture
    def detector(self, rate_limit_config):
        """Create detector with memory store."""
        store = RateLimitStore(use_redis=False)
        return SuspiciousActivityDetector(store, rate_limit_config)
    
    @pytest.fixture
    def recent_metrics(self):
        """Create list of recent metrics for testing."""
        now = datetime.now()
        metrics = []
        
        for i in range(60):  # 60 requests for rapid request testing
            metrics.append(RequestMetrics(
                user_id="test_user",
                ip_address=f"192.168.1.{i % 5}",  # Multiple IPs
                endpoint="/api/test",
                timestamp=now - timedelta(seconds=i),
                response_code=200 if i % 3 != 0 else 500,  # Some errors
                processing_time=0.5
            ))
        
        return metrics
    
    @pytest.mark.asyncio
    async def test_analyze_request_with_all_alerts(self, detector):
        """Test analyze_request with all alert conditions triggered.""" 
        # Create a custom request metric for unusual hours
        unusual_time_metric = RequestMetrics(
            user_id="test_user",
            ip_address="192.168.1.1",
            endpoint="/api/abused",
            timestamp=datetime.now().replace(hour=3, minute=0, second=0),  # Unusual hour
            response_code=400,
            processing_time=0.5
        )
        
        # Create metrics that trigger various suspicious patterns
        now = datetime.now()
        suspicious_metrics = []
        
        # Create 60 requests with multiple suspicious patterns
        for i in range(60):
            metric = RequestMetrics(
                user_id="test_user",
                ip_address=f"192.168.1.{i % 6}",  # Multiple IPs
                endpoint="/api/abused",  # Same endpoint for abuse
                timestamp=now - timedelta(seconds=i),  # Recent rapid requests
                response_code=400 if i < 35 else 200,  # >50% error rate
                processing_time=0.5
            )
            suspicious_metrics.append(metric)
        
        with patch.object(detector, '_get_recent_metrics_memory', return_value=suspicious_metrics):
            alerts = await detector.analyze_request("test_user", unusual_time_metric)
            
            # Should trigger multiple alert types
            assert len(alerts) >= 4  # Most patterns should be detected
            assert "rapid_requests" in alerts
            assert "unusual_hours" in alerts
    
    @pytest.mark.asyncio
    async def test_analyze_request_redis_backend(self, rate_limit_config, request_metrics):
        """Test analyze_request with Redis backend."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            detector = SuspiciousActivityDetector(store, rate_limit_config)
            
            # Mock Redis metrics response
            with patch.object(detector, '_get_recent_metrics_redis', return_value=[]):
                alerts = await detector.analyze_request("test_user", request_metrics)
                assert alerts == []
    
    @pytest.mark.asyncio
    async def test_rapid_requests_detection(self, detector, recent_metrics):
        """Test rapid requests pattern detection."""
        # Mock recent metrics to return many requests
        with patch.object(detector, '_get_recent_metrics_memory', return_value=recent_metrics):
            result = await detector._check_rapid_requests(recent_metrics)
            assert result is True  # Should detect rapid requests
    
    def test_unusual_hours_detection(self, detector):
        """Test unusual hours detection."""
        # Test 3 AM (should be flagged)
        early_morning = datetime.now().replace(hour=3, minute=0, second=0)
        assert detector._check_unusual_hours(early_morning) is True
        
        # Test 2 PM (should not be flagged)
        afternoon = datetime.now().replace(hour=14, minute=0, second=0)
        assert detector._check_unusual_hours(afternoon) is False
    
    def test_unusual_hours_detection_disabled(self, rate_limit_config):
        """Test unusual hours detection when disabled."""
        # Temporarily modify the config
        original_value = rate_limit_config.SUSPICIOUS_PATTERNS["unusual_hours"]
        rate_limit_config.SUSPICIOUS_PATTERNS["unusual_hours"] = False
        
        try:
            store = RateLimitStore(use_redis=False)
            detector = SuspiciousActivityDetector(store, rate_limit_config)
            
            # Test 3 AM (should NOT be flagged when disabled)
            early_morning = datetime.now().replace(hour=3, minute=0, second=0)
            result = detector._check_unusual_hours(early_morning)
            assert result is False
        finally:
            # Restore original value
            rate_limit_config.SUSPICIOUS_PATTERNS["unusual_hours"] = original_value
    
    @pytest.mark.asyncio
    async def test_multiple_ips_detection(self, detector):
        """Test multiple IPs detection."""
        # Create metrics with multiple IPs (within last hour)
        now = datetime.now()
        multi_ip_metrics = []
        
        for i in range(15):  # Enough data (>10)
            metric = RequestMetrics(
                user_id="test_user",
                ip_address=f"192.168.1.{i % 7}",  # 7 different IPs (> 5 threshold)
                endpoint="/test",
                timestamp=now - timedelta(minutes=30),  # Within last hour
                response_code=200,
                processing_time=0.5
            )
            multi_ip_metrics.append(metric)
        
        result = await detector._check_multiple_ips(multi_ip_metrics)
        assert result is True  # Should detect multiple IPs
        
        # Test with single IP
        single_ip_metrics = []
        for i in range(15):
            metric = RequestMetrics(
                user_id="test_user",
                ip_address="192.168.1.1",  # Same IP
                endpoint="/test",
                timestamp=now - timedelta(minutes=30),
                response_code=200,
                processing_time=0.5
            )
            single_ip_metrics.append(metric)
        
        result = await detector._check_multiple_ips(single_ip_metrics)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_multiple_ips_detection_insufficient_data(self, detector):
        """Test multiple IPs detection with insufficient data."""
        # Test with less than 10 metrics
        few_metrics = [RequestMetrics(
            user_id="test_user",
            ip_address="192.168.1.1",
            endpoint="/test",
            timestamp=datetime.now(),
            response_code=200,
            processing_time=0.5
        ) for _ in range(5)]
        
        result = await detector._check_multiple_ips(few_metrics)
        assert result is False  # Should return False with insufficient data
    
    @pytest.mark.asyncio
    async def test_error_rate_detection(self, detector):
        """Test high error rate detection."""
        # Create metrics with high error rate within the 5-minute window
        error_metrics = []
        now = datetime.now()
        for i in range(20):
            metric = RequestMetrics(
                user_id="test_user",
                ip_address="192.168.1.1",
                endpoint="/api/test",
                timestamp=now - timedelta(seconds=30 + i),  # Within last 5 minutes
                response_code=400 if i < 12 else 200,  # 60% error rate (>50% threshold)
                processing_time=0.5
            )
            error_metrics.append(metric)
        
        result = await detector._check_error_rate(error_metrics)
        assert result is True  # Should detect high error rate (60% > 50% threshold)
    
    @pytest.mark.asyncio
    async def test_error_rate_detection_insufficient_data(self, detector):
        """Test error rate detection with insufficient data."""
        # Test with less than 10 metrics
        few_metrics = [RequestMetrics(
            user_id="test_user",
            ip_address="192.168.1.1",
            endpoint="/test",
            timestamp=datetime.now(),
            response_code=500,
            processing_time=0.5
        ) for _ in range(5)]
        
        result = await detector._check_error_rate(few_metrics)
        assert result is False  # Should return False with insufficient data
    
    @pytest.mark.asyncio
    async def test_error_rate_detection_no_recent_data(self, detector):
        """Test error rate detection with no recent data."""
        # Create metrics that are all old (older than 5 minutes)
        old_metrics = []
        old_time = datetime.now() - timedelta(minutes=10)
        for i in range(20):
            metric = RequestMetrics(
                user_id="test_user",
                ip_address="192.168.1.1",
                endpoint="/api/test",
                timestamp=old_time,
                response_code=500,
                processing_time=0.5
            )
            old_metrics.append(metric)
        
        result = await detector._check_error_rate(old_metrics)
        assert result is False  # Should return False when no recent metrics
    
    @pytest.mark.asyncio
    async def test_endpoint_abuse_detection(self, detector, recent_metrics):
        """Test endpoint abuse detection."""
        # All requests to same endpoint in short time
        for metric in recent_metrics[:25]:
            metric.endpoint = "/api/abused"
            metric.timestamp = datetime.now() - timedelta(seconds=10)
        
        result = await detector._check_endpoint_abuse(recent_metrics[:25], "/api/abused")
        assert result is True  # Should detect endpoint abuse
    
    def test_log_suspicious_activity(self, detector, request_metrics):
        """Test suspicious activity logging."""
        alerts = ["rapid_requests", "unusual_hours"]
        
        detector._log_suspicious_activity("test_user", request_metrics, alerts)
        
        # Check alert was stored
        assert len(detector.alerts) == 1
        alert_data = detector.alerts[0]
        assert alert_data["user_id"] == "test_user"
        assert alert_data["alerts"] == alerts
    
    @pytest.mark.asyncio
    async def test_get_recent_metrics_redis_success(self, rate_limit_config):
        """Test getting recent metrics from Redis successfully."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_client.lrange.return_value = [
                json.dumps({
                    "ip": "192.168.1.1",
                    "endpoint": "/test",
                    "timestamp": "2023-01-01T10:00:00",
                    "response_code": 200,
                    "processing_time": 0.5
                })
            ]
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            detector = SuspiciousActivityDetector(store, rate_limit_config)
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(return_value=[
                    json.dumps({
                        "ip": "192.168.1.1",
                        "endpoint": "/test", 
                        "timestamp": "2023-01-01T10:00:00",
                        "response_code": 200,
                        "processing_time": 0.5
                    })
                ])
                
                metrics = await detector._get_recent_metrics_redis("test_user")
                
                assert len(metrics) == 1
                assert metrics[0].ip_address == "192.168.1.1"
    
    @pytest.mark.asyncio 
    async def test_get_recent_metrics_redis_error(self, rate_limit_config):
        """Test getting recent metrics from Redis with error."""
        with patch('src.api.middleware.rate_limit_middleware.redis.Redis') as mock_redis:
            mock_client = Mock()
            mock_redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            store.redis_client = mock_client
            detector = SuspiciousActivityDetector(store, rate_limit_config)
            
            with patch('asyncio.get_event_loop') as mock_loop:
                mock_loop.return_value.run_in_executor = AsyncMock(side_effect=Exception("Redis error"))
                
                metrics = await detector._get_recent_metrics_redis("test_user")
                
                assert metrics == []  # Should return empty list on error


class TestRateLimitMiddleware:
    """Test the main rate limiting middleware."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI app for testing."""
        return FastAPI()
    
    @pytest.fixture
    def middleware(self, app, rate_limit_config):
        """Create rate limit middleware."""
        return RateLimitMiddleware(app, rate_limit_config)
    
    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = Mock(spec=Request)
        request.url.path = "/api/test"
        request.headers = {}
        request.client.host = "192.168.1.1"
        request.state = Mock()
        request.state.user = None
        return request
    
    def test_middleware_initialization(self, middleware):
        """Test middleware initializes correctly."""
        assert middleware.config is not None
        assert middleware.store is not None
        assert middleware.detector is not None
        assert "/docs" in middleware.excluded_paths
        assert "/health" in middleware.excluded_paths
    
    @pytest.mark.asyncio
    async def test_dispatch_excluded_path(self, middleware, mock_request):
        """Test dispatch skips rate limiting for excluded paths."""
        mock_request.url.path = "/docs"
        
        async def call_next(request):
            return Response("OK", status_code=200)
        
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_get_user_info_anonymous(self, middleware, mock_request):
        """Test getting user info for anonymous user."""
        user_id, user_tier = await middleware._get_user_info(mock_request)
        
        assert user_id == "anonymous"
        assert user_tier.name == "free"
    
    @pytest.mark.asyncio
    async def test_get_user_info_from_state(self, middleware, mock_request):
        """Test getting user info from request state."""
        mock_request.state.user = {
            "user_id": "user123",
            "tier": "premium"
        }
        
        user_id, user_tier = await middleware._get_user_info(mock_request)
        
        assert user_id == "user123"
        assert user_tier.name == "premium"
    
    @pytest.mark.asyncio
    async def test_get_user_info_from_auth_header(self, middleware, mock_request):
        """Test getting user info from Authorization header."""
        mock_request.headers = {"Authorization": "Bearer test_token_123"}
        
        user_id, user_tier = await middleware._get_user_info(mock_request)
        
        assert user_id != "anonymous"  # Should extract from token
        assert user_tier.name == "free"  # Default tier
    
    @pytest.mark.asyncio
    async def test_get_user_info_exception_handling(self, middleware):
        """Test getting user info with exception during processing."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer test_token"}
        mock_request.state = Mock()
        
        # Make request.state.user raise an exception
        type(mock_request.state).user = PropertyMock(side_effect=Exception("State error"))
        
        user_id, user_tier = await middleware._get_user_info(mock_request)
        
        assert user_id == "anonymous"
        assert user_tier.name == "free"
    
    def test_extract_user_from_token(self, middleware):
        """Test extracting user ID from token."""
        token = "Bearer test_token_123"
        user_id = middleware._extract_user_from_token(token)
        
        assert user_id != "anonymous"
        assert len(user_id) == 12  # MD5 hash truncated
    
    def test_extract_user_from_token_exception(self, middleware):
        """Test extracting user ID from token with exception."""
        # Test with invalid token that causes exception
        with patch('hashlib.md5', side_effect=Exception("Hash error")):
            user_id = middleware._extract_user_from_token("Bearer invalid_token")
            assert user_id == "anonymous"
    
    def test_get_client_ip_forwarded(self, middleware, mock_request):
        """Test getting client IP from X-Forwarded-For header."""
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.1"
    
    def test_get_client_ip_real_ip(self, middleware, mock_request):
        """Test getting client IP from X-Real-IP header."""
        mock_request.headers = {"X-Real-IP": "10.0.0.2"}
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.2"
    
    def test_get_client_ip_direct(self, middleware, mock_request):
        """Test getting client IP directly from request."""
        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.1"
    
    def test_get_client_ip_no_client(self, middleware):
        """Test getting client IP when request.client is None."""
        mock_request = Mock(spec=Request)
        mock_request.headers = {}
        mock_request.client = None
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "unknown"
    
    @pytest.mark.asyncio
    async def test_check_rate_limits_exceeded_minute(self, middleware):
        """Test rate limit check when minute limit exceeded."""
        with patch.object(middleware.store, 'get_request_counts', 
                         return_value={"minute": 100, "hour": 100, "day": 100}):
            
            user_tier = UserTier("test", 10, 100, 1000, 15, 3)
            response = await middleware._check_rate_limits("test_user", user_tier)
            
            assert response is not None
            assert response.status_code == 429
    
    @pytest.mark.asyncio
    async def test_check_rate_limits_exceeded_hour(self, middleware):
        """Test rate limit check when hour limit exceeded."""
        with patch.object(middleware.store, 'get_request_counts',
                         return_value={"minute": 5, "hour": 150, "day": 150}):
            
            user_tier = UserTier("test", 10, 100, 1000, 15, 3)
            response = await middleware._check_rate_limits("test_user", user_tier)
            
            assert response is not None
            assert response.status_code == 429
    
    @pytest.mark.asyncio
    async def test_check_rate_limits_exceeded_day(self, middleware):
        """Test rate limit check when day limit exceeded."""
        with patch.object(middleware.store, 'get_request_counts',
                         return_value={"minute": 5, "hour": 50, "day": 1500}):
            
            user_tier = UserTier("test", 10, 100, 1000, 15, 3)
            response = await middleware._check_rate_limits("test_user", user_tier)
            
            assert response is not None
            assert response.status_code == 429
    
    @pytest.mark.asyncio
    async def test_check_rate_limits_within_limits(self, middleware):
        """Test rate limit check when within limits."""
        with patch.object(middleware.store, 'get_request_counts',
                         return_value={"minute": 5, "hour": 50, "day": 500}):
            
            user_tier = UserTier("test", 10, 100, 1000, 15, 3)
            response = await middleware._check_rate_limits("test_user", user_tier)
            
            assert response is None  # No rate limit exceeded
    
    def test_create_rate_limit_response(self, middleware):
        """Test creating rate limit response."""
        response = middleware._create_rate_limit_response(
            "Rate limit exceeded", 100, 60
        )
        
        assert response.status_code == 429
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers
        assert "X-RateLimit-Reset" in response.headers
        assert "Retry-After" in response.headers
    
    def test_add_rate_limit_headers(self, middleware, sample_user_tier):
        """Test adding rate limit headers to response."""
        response = Response("OK")
        
        middleware._add_rate_limit_headers(response, "test_user", sample_user_tier)
        
        assert "X-RateLimit-Limit-Minute" in response.headers
        assert "X-RateLimit-Limit-Hour" in response.headers  
        assert "X-RateLimit-Limit-Day" in response.headers
        assert "X-RateLimit-Tier" in response.headers
        assert response.headers["X-RateLimit-Tier"] == "test"
    
    @pytest.mark.asyncio
    async def test_dispatch_concurrent_limit_exceeded(self, middleware, mock_request):
        """Test dispatch when concurrent limit exceeded."""
        # Mock store methods
        with patch.object(middleware.store, 'get_request_counts',
                         return_value={"minute": 1, "hour": 1, "day": 1}):
            with patch.object(middleware.store, 'increment_concurrent',
                             return_value=10):  # Exceeds limit
                with patch.object(middleware.store, 'decrement_concurrent'):
                    
                    async def call_next(request):
                        return Response("OK", status_code=200)
                    
                    response = await middleware.dispatch(mock_request, call_next)
                    
                    assert response.status_code == 429
    
    @pytest.mark.asyncio
    async def test_dispatch_successful_request(self, middleware, mock_request):
        """Test successful request dispatch."""
        # Mock all the necessary components
        with patch.object(middleware.store, 'get_request_counts',
                         return_value={"minute": 1, "hour": 1, "day": 1}):
            with patch.object(middleware.store, 'increment_concurrent', return_value=1):
                with patch.object(middleware.store, 'decrement_concurrent'):
                    with patch.object(middleware.store, 'record_request'):
                        with patch.object(middleware.detector, 'analyze_request', return_value=[]):
                            
                            async def call_next(request):
                                return Response("OK", status_code=200)
                            
                            response = await middleware.dispatch(mock_request, call_next)
                            
                            assert response.status_code == 200
                            # Verify rate limit headers were added
                            assert "X-RateLimit-Tier" in response.headers
    
    @pytest.mark.asyncio
    async def test_dispatch_exception_handling(self, middleware, mock_request):
        """Test dispatch handles exceptions properly."""
        with patch.object(middleware.store, 'get_request_counts',
                         return_value={"minute": 1, "hour": 1, "day": 1}):
            with patch.object(middleware.store, 'increment_concurrent', return_value=1):
                with patch.object(middleware.store, 'decrement_concurrent') as mock_decrement:
                    
                    async def call_next(request):
                        raise Exception("Test exception")
                    
                    with pytest.raises(Exception, match="Test exception"):
                        await middleware.dispatch(mock_request, call_next)
                    
                    # Verify decrement_concurrent was called in finally block
                    mock_decrement.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_dispatch_rate_limit_hit_returns_early(self, middleware, mock_request):
        """Test dispatch returns rate limit response without processing."""
        # Mock rate limits exceeded to trigger line 477 (return rate_limit_result)
        rate_limit_response = JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded"}
        )
        
        with patch.object(middleware, '_check_rate_limits', return_value=rate_limit_response):
            response = await middleware.dispatch(mock_request, lambda req: Response("Should not reach"))
            
            assert response.status_code == 429
            # Verify we returned early and didn't process the request
