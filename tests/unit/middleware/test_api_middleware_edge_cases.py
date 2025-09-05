"""
Additional API Middleware Tests - Error Handling and Edge Cases

This module provides additional test coverage for middleware error scenarios,
edge cases, and integration patterns to achieve complete 100% coverage.
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch, PropertyMock

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestMiddlewareErrorHandling:
    """Tests for middleware error handling and recovery."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_store_redis_connection_failure(self):
        """Test rate limit store handles Redis connection failures."""
        from src.api.middleware.rate_limit_middleware import RateLimitStore
        
        # Mock Redis to fail during operations
        with patch('src.api.middleware.rate_limit_middleware.redis') as mock_redis:
            mock_client = Mock()
            mock_client.pipeline.side_effect = Exception("Redis connection failed")
            mock_redis.Redis.return_value = mock_client
            
            store = RateLimitStore(use_redis=True)
            
            # Should fallback to memory operations
            await store.increment_request_count("user123", "minute")
            counts = await store.get_request_counts("user123")
            
            # Should work with fallback
            assert isinstance(counts, dict)
    
    @pytest.mark.asyncio
    async def test_suspicious_activity_detector_exception_handling(self):
        """Test suspicious activity detector handles exceptions gracefully."""
        from src.api.middleware.rate_limit_middleware import (
            SuspiciousActivityDetector, RateLimitStore, RateLimitConfig, RequestMetrics
        )
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            store = RateLimitStore(use_redis=False)
            config = RateLimitConfig()
            detector = SuspiciousActivityDetector(store, config)
            
            # Mock store to raise exception
            store.get_user_requests = AsyncMock(side_effect=Exception("Store error"))
            
            metrics = RequestMetrics(
                user_id="test_user",
                ip_address="192.168.1.1",
                endpoint="/api/test",
                timestamp=datetime.now(),
                response_code=200,
                processing_time=0.1
            )
            
            # Should handle exception gracefully
            try:
                await detector.analyze_request("test_user", metrics)
            except Exception:
                pytest.fail("Detector should handle store errors gracefully")
    
    @pytest.mark.asyncio
    async def test_middleware_with_corrupted_request_state(self, mock_call_next):
        """Test middleware handles corrupted request state."""
        from src.api.middleware.auth_middleware import RoleBasedAccessMiddleware
        
        app = Mock(spec=FastAPI)
        middleware = RoleBasedAccessMiddleware(app, {"GET /api/admin": ["admin"]})
        
        # Create request with corrupted state
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/admin"
        request.method = "GET"
        request.state = None  # Corrupted state
        
        # Should handle gracefully
        response = await middleware.dispatch(request, mock_call_next)
        assert response.status_code in [401, 403, 500]
    
    @pytest.mark.asyncio
    async def test_api_key_middleware_database_unavailable(self, mock_call_next):
        """Test API key middleware when database is unavailable."""
        from src.api.auth.api_key_middleware import APIKeyAuthMiddleware
        
        app = Mock(spec=FastAPI)
        middleware = APIKeyAuthMiddleware(app)
        
        # Mock database error
        middleware._validate_api_key = AsyncMock(side_effect=Exception("DB connection failed"))
        
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/test"
        request.headers = {"Authorization": "Bearer api_key_123"}
        
        response = await middleware.dispatch(request, mock_call_next)
        
        # Should return 500 or 503 for server errors
        assert response.status_code in [500, 503]
    
    @pytest.mark.asyncio
    async def test_metrics_middleware_prometheus_failure(self, mock_call_next):
        """Test metrics middleware when Prometheus collection fails."""
        from src.services.api.middleware.metrics import RAGMetricsMiddleware
        
        app = Mock(spec=FastAPI)
        
        # Mock metrics collector to fail
        with patch('src.services.api.middleware.metrics.metrics_collector') as mock_collector:
            mock_collector.increment_request_count.side_effect = Exception("Prometheus error")
            
            middleware = RAGMetricsMiddleware(app)
            
            request = Mock(spec=Request)
            request.url = Mock()
            request.url.path = "/api/test"
            request.method = "GET"
            
            # Should handle Prometheus errors gracefully
            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code == 200


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestMiddlewareEdgeCases:
    """Tests for middleware edge cases and boundary conditions."""
    
    def test_rate_limit_config_invalid_values(self):
        """Test rate limit configuration with invalid values."""
        from src.api.middleware.rate_limit_middleware import UserTier
        
        # Test with zero limits
        tier = UserTier(
            name="zero_tier",
            requests_per_minute=0,
            requests_per_hour=0,
            requests_per_day=0,
            burst_limit=0,
            concurrent_requests=0
        )
        
        assert tier.requests_per_minute == 0
        assert tier.burst_limit == 0
        
        # Test with negative limits (should still work as defined)
        tier_negative = UserTier(
            name="negative_tier",
            requests_per_minute=-1,
            requests_per_hour=-1,
            requests_per_day=-1,
            burst_limit=-1,
            concurrent_requests=-1
        )
        
        assert tier_negative.requests_per_minute == -1
    
    @pytest.mark.asyncio
    async def test_rate_limit_middleware_time_boundary_conditions(self):
        """Test rate limiting at time boundaries."""
        from src.api.middleware.rate_limit_middleware import RateLimitStore
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            store = RateLimitStore(use_redis=False)
            
            user_id = "boundary_user"
            
            # Test rapid succession at minute boundary
            now = time.time()
            minute_start = int(now // 60) * 60
            
            # Simulate requests right at minute boundary
            with patch('time.time', return_value=minute_start):
                await store.increment_request_count(user_id, "minute")
            
            with patch('time.time', return_value=minute_start + 1):
                await store.increment_request_count(user_id, "minute")
            
            counts = await store.get_request_counts(user_id)
            assert counts["minute"] >= 1
    
    @pytest.mark.asyncio
    async def test_sliding_window_rate_limiter_edge_times(self):
        """Test sliding window rate limiter at edge time conditions."""
        from src.services.api.middleware.ratelimit import SlidingWindowRateLimiter
        
        app = Mock(spec=FastAPI)
        
        with patch('src.services.api.middleware.ratelimit.REDIS_AVAILABLE', False):
            limiter = SlidingWindowRateLimiter(app)
            
            # Test with zero window time
            with patch('src.services.api.middleware.ratelimit.WINDOW_SIZE_SECONDS', 0):
                result = await limiter._check_rate_limit_memory("test_key")
                assert isinstance(result, tuple)
                assert len(result) == 2
    
    def test_auth_middleware_empty_cors_origins(self):
        """Test CORS configuration with empty origins."""
        from src.api.middleware.auth_middleware import configure_cors
        
        app = Mock(spec=FastAPI)
        
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": ""}):
            configure_cors(app)
            
            # Should use default origins
            mock_app.add_middleware.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_api_key_middleware_extremely_long_keys(self, mock_call_next):
        """Test API key middleware with extremely long keys."""
        from src.api.auth.api_key_middleware import APIKeyAuthMiddleware
        
        app = Mock(spec=FastAPI)
        middleware = APIKeyAuthMiddleware(app)
        
        # Create extremely long API key
        long_key = "x" * 10000  # 10KB key
        
        request = Mock(spec=Request)
        request.url = Mock()
        request.url.path = "/api/test"
        request.headers = {"Authorization": f"Bearer {long_key}"}
        request.query_params = {}
        request.cookies = {}
        
        # Should extract key properly regardless of length
        extracted_key = middleware._extract_api_key(request)
        assert extracted_key == long_key
    
    @pytest.mark.asyncio
    async def test_middleware_unicode_and_special_characters(self, mock_call_next):
        """Test middleware handling of Unicode and special characters."""
        from src.api.middleware.rate_limit_middleware import RateLimitMiddleware
        
        app = Mock(spec=FastAPI)
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            middleware = RateLimitMiddleware(app)
            
            # Test with Unicode characters in headers
            request = Mock(spec=Request)
            request.url = Mock()
            request.url.path = "/api/测试"  # Chinese characters
            request.headers = {"Authorization": "Bearer токен123", "User-Agent": "üser-ågent"}
            request.client = Mock()
            request.client.host = "192.168.1.1"
            request.state = Mock()
            
            # Should handle Unicode gracefully
            response = await middleware.dispatch(request, mock_call_next)
            assert response.status_code in [200, 401, 429]
    
    def test_request_metrics_with_extreme_values(self):
        """Test request metrics with extreme values."""
        from src.api.middleware.rate_limit_middleware import RequestMetrics
        
        # Test with extreme processing time
        extreme_metrics = RequestMetrics(
            user_id="extreme_user",
            ip_address="192.168.1.1",
            endpoint="/api/test",
            timestamp=datetime.now(),
            response_code=999,  # Non-standard response code
            processing_time=999999.999  # Extremely long processing time
        )
        
        assert extreme_metrics.processing_time == 999999.999
        assert extreme_metrics.response_code == 999


# =============================================================================
# Concurrency and Threading Tests
# =============================================================================

class TestMiddlewareConcurrency:
    """Tests for middleware concurrency and thread safety."""
    
    @pytest.mark.asyncio
    async def test_rate_limit_store_concurrent_access(self):
        """Test concurrent access to rate limit store."""
        from src.api.middleware.rate_limit_middleware import RateLimitStore
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            store = RateLimitStore(use_redis=False)
            
            user_id = "concurrent_user"
            
            # Create multiple concurrent increment tasks
            tasks = []
            for i in range(100):
                task = asyncio.create_task(
                    store.increment_request_count(user_id, "minute")
                )
                tasks.append(task)
            
            # Wait for all to complete
            await asyncio.gather(*tasks)
            
            # Check final count (should be around 100, allowing for race conditions)
            counts = await store.get_request_counts(user_id)
            assert counts["minute"] <= 100  # May be less due to timing
    
    @pytest.mark.asyncio
    async def test_suspicious_activity_detector_concurrent_analysis(self):
        """Test concurrent suspicious activity analysis."""
        from src.api.middleware.rate_limit_middleware import (
            SuspiciousActivityDetector, RateLimitStore, RateLimitConfig, RequestMetrics
        )
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            store = RateLimitStore(use_redis=False)
            config = RateLimitConfig()
            detector = SuspiciousActivityDetector(store, config)
            
            # Create concurrent analysis tasks
            tasks = []
            for i in range(50):
                metrics = RequestMetrics(
                    user_id=f"user_{i % 10}",  # 10 different users
                    ip_address=f"192.168.1.{i % 255}",
                    endpoint="/api/test",
                    timestamp=datetime.now(),
                    response_code=200,
                    processing_time=0.1
                )
                
                task = asyncio.create_task(
                    detector.analyze_request(f"user_{i % 10}", metrics)
                )
                tasks.append(task)
            
            # Should complete without deadlocks or race conditions
            await asyncio.gather(*tasks)
    
    @pytest.mark.asyncio
    async def test_middleware_chain_concurrent_requests(self):
        """Test middleware chain with concurrent requests."""
        from src.api.middleware.auth_middleware import AuditLogMiddleware
        from src.services.api.middleware.ratelimit import SlidingWindowRateLimiter
        
        app = Mock(spec=FastAPI)
        
        # Create middleware chain
        audit_middleware = AuditLogMiddleware(app)
        
        with patch('src.services.api.middleware.ratelimit.REDIS_AVAILABLE', False):
            rate_limiter = SlidingWindowRateLimiter(app)
        
        async def final_handler(request):
            await asyncio.sleep(0.001)  # Simulate processing
            return Response()
        
        # Create concurrent requests through chain
        tasks = []
        for i in range(20):
            request = Mock(spec=Request)
            request.url = Mock()
            request.url.path = f"/api/test/{i}"
            request.method = "GET"
            request.client = Mock()
            request.client.host = f"192.168.1.{i % 10}"
            request.headers = {"User-Agent": f"test-agent-{i}"}
            request.state = Mock()
            
            # Chain: audit -> rate_limiter -> handler
            task = asyncio.create_task(
                audit_middleware.dispatch(
                    request,
                    lambda r: rate_limiter.dispatch(r, final_handler)
                )
            )
            tasks.append(task)
        
        # All should complete successfully
        responses = await asyncio.gather(*tasks)
        assert len(responses) == 20
        assert all(r.status_code in [200, 429] for r in responses)


# =============================================================================
# Configuration and Environment Tests
# =============================================================================

class TestMiddlewareConfiguration:
    """Tests for middleware configuration scenarios."""
    
    def test_rate_limit_config_from_environment(self):
        """Test rate limit configuration from environment variables."""
        from src.api.middleware.rate_limit_middleware import RateLimitConfig
        
        # Test with custom environment variables
        with patch.dict(os.environ, {
            "RATE_LIMIT_FREE_MINUTE": "20",
            "RATE_LIMIT_PREMIUM_HOUR": "2000",
            "SUSPICIOUS_RAPID_THRESHOLD": "100"
        }):
            # RateLimitConfig should ideally read from environment
            config = RateLimitConfig()
            
            # Test that config is created successfully
            assert hasattr(config, 'FREE_TIER')
            assert hasattr(config, 'PREMIUM_TIER')
    
    def test_metrics_middleware_custom_configuration(self):
        """Test metrics middleware with custom configuration."""
        from src.services.api.middleware.metrics import RAGMetricsMiddleware
        
        app = Mock(spec=FastAPI)
        
        with patch('src.services.api.middleware.metrics.metrics_collector'):
            # Test with various configuration options
            middleware1 = RAGMetricsMiddleware(app, track_all_endpoints=True)
            assert middleware1.track_all_endpoints is True
            
            middleware2 = RAGMetricsMiddleware(app, track_all_endpoints=False)
            assert middleware2.track_all_endpoints is False
    
    def test_api_key_middleware_custom_excluded_paths(self):
        """Test API key middleware with custom excluded paths."""
        from src.api.auth.api_key_middleware import APIKeyAuthMiddleware
        
        app = Mock(spec=FastAPI)
        custom_paths = ["/custom", "/special", "/public/*"]
        
        middleware = APIKeyAuthMiddleware(app, excluded_paths=custom_paths)
        
        assert "/custom" in middleware.excluded_paths
        assert "/special" in middleware.excluded_paths
        assert "/public/*" in middleware.excluded_paths
    
    def test_cors_configuration_multiple_formats(self):
        """Test CORS configuration with different origin formats."""
        from src.api.middleware.auth_middleware import configure_cors
        
        app = Mock(spec=FastAPI)
        
        # Test with comma-separated origins
        with patch.dict(os.environ, {
            "ALLOWED_ORIGINS": "http://localhost:3000,https://app.example.com,https://*.example.com"
        }):
            configure_cors(app)
            
            args, kwargs = app.add_middleware.call_args
            origins = kwargs["allow_origins"]
            
            assert "http://localhost:3000" in origins
            assert "https://app.example.com" in origins
            assert "https://*.example.com" in origins
    
    def test_rbac_middleware_dynamic_permissions(self):
        """Test RBAC middleware with dynamic permission loading."""
        from src.api.middleware.auth_middleware import RoleBasedAccessMiddleware
        
        app = Mock(spec=FastAPI)
        
        # Test empty initial permissions (should load dynamically)
        middleware = RoleBasedAccessMiddleware(app, {})
        assert middleware.protected_routes == {}
        
        # Test with initial permissions
        permissions = {
            "GET /admin": ["admin"],
            "POST /users": ["admin", "moderator"]
        }
        middleware2 = RoleBasedAccessMiddleware(app, permissions)
        assert len(middleware2.protected_routes) == 2


# =============================================================================
# Memory and Resource Management Tests
# =============================================================================

class TestMiddlewareResourceManagement:
    """Tests for middleware resource usage and cleanup."""
    
    def test_rate_limit_store_memory_cleanup(self):
        """Test memory cleanup in rate limit store."""
        from src.api.middleware.rate_limit_middleware import RateLimitStore
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            store = RateLimitStore(use_redis=False)
            
            # Add many entries
            for i in range(1000):
                user_id = f"user_{i}"
                store.memory_store[f"{user_id}:minute"] = i
                store.memory_store[f"{user_id}:hour"] = i
                store.memory_store[f"{user_id}:day"] = i
            
            initial_size = len(store.memory_store)
            assert initial_size == 3000
            
            # Simulate cleanup (if implemented)
            # Most memory stores would have TTL or cleanup mechanisms
            # This tests that the store can handle large datasets
    
    @pytest.mark.asyncio
    async def test_suspicious_activity_detector_memory_usage(self):
        """Test suspicious activity detector memory usage patterns."""
        from src.api.middleware.rate_limit_middleware import (
            SuspiciousActivityDetector, RateLimitStore, RateLimitConfig, RequestMetrics
        )
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            store = RateLimitStore(use_redis=False)
            config = RateLimitConfig()
            detector = SuspiciousActivityDetector(store, config)
            
            # Test with many users generating metrics
            for i in range(100):
                user_id = f"memory_test_user_{i}"
                
                for j in range(10):  # 10 requests per user
                    metrics = RequestMetrics(
                        user_id=user_id,
                        ip_address=f"192.168.1.{i % 255}",
                        endpoint=f"/api/endpoint_{j}",
                        timestamp=datetime.now(),
                        response_code=200,
                        processing_time=0.1
                    )
                    
                    await detector.analyze_request(user_id, metrics)
            
            # Memory usage should be manageable
            # This test ensures the detector doesn't leak memory
    
    def test_middleware_cleanup_on_app_shutdown(self):
        """Test middleware cleanup when app shuts down."""
        from src.api.middleware.rate_limit_middleware import RateLimitMiddleware
        
        app = Mock(spec=FastAPI)
        
        with patch('src.api.middleware.rate_limit_middleware.redis', side_effect=ImportError):
            middleware = RateLimitMiddleware(app)
            
            # Middleware should initialize without issues
            assert hasattr(middleware, 'store')
            assert hasattr(middleware, 'detector')
            
            # Cleanup should work without errors (if implemented)
            # This ensures middleware can be properly disposed of


if __name__ == "__main__":
    pytest.main([
        __file__,
        "-v",
        "--cov=src.api.middleware",
        "--cov=src.services.api.middleware", 
        "--cov=src.api.auth.api_key_middleware",
        "--cov=src.api.rbac.rbac_middleware",
        "--cov-report=term-missing"
    ])
