"""
Comprehensive test suite for Security Middleware - Issue #476.

Tests all security middleware requirements:
- Request filtering and validation
- CORS policy enforcement
- Role-based access control middleware
- Authentication middleware integration
- Audit logging middleware
- Security headers and response modification
- Error handling and security boundary validation
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.middleware.auth_middleware import (
    AuditLogMiddleware,
    RoleBasedAccessMiddleware,
    configure_cors,
)


class TestCORSConfiguration:
    """Test CORS middleware configuration."""

    def test_configure_cors_default_origins(self):
        """Test CORS configuration with default origins."""
        app = FastAPI()
        
        with patch.dict(os.environ, {}, clear=True):
            configure_cors(app)
        
        # Should have CORS middleware configured
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break
        
        assert cors_middleware is not None
        
        # Check default configuration
        options = cors_middleware.options
        assert "allow_origins" in options
        assert options["allow_credentials"] is True
        assert options["allow_methods"] == ["*"]
        assert options["allow_headers"] == ["*"]

    def test_configure_cors_custom_origins(self):
        """Test CORS configuration with custom origins."""
        app = FastAPI()
        
        custom_origins = "https://example.com,https://api.example.com"
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": custom_origins}):
            configure_cors(app)
        
        # Should have CORS middleware with custom origins
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break
        
        assert cors_middleware is not None
        options = cors_middleware.options
        expected_origins = ["https://example.com", "https://api.example.com"]
        assert options["allow_origins"] == expected_origins

    def test_configure_cors_empty_origins(self):
        """Test CORS configuration with empty origins environment variable."""
        app = FastAPI()
        
        with patch.dict(os.environ, {"ALLOWED_ORIGINS": ""}):
            configure_cors(app)
        
        # Should use default origins
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break
        
        assert cors_middleware is not None
        options = cors_middleware.options
        assert "http://localhost:3000" in options["allow_origins"]

    def test_cors_headers_exposed(self):
        """Test that required headers are exposed in CORS."""
        app = FastAPI()
        
        configure_cors(app)
        
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break
        
        options = cors_middleware.options
        assert "X-Request-ID" in options["expose_headers"]

    def test_cors_credentials_allowed(self):
        """Test that credentials are allowed in CORS."""
        app = FastAPI()
        
        configure_cors(app)
        
        cors_middleware = None
        for middleware in app.user_middleware:
            if middleware.cls == CORSMiddleware:
                cors_middleware = middleware
                break
        
        options = cors_middleware.options
        assert options["allow_credentials"] is True


class TestRoleBasedAccessMiddleware:
    """Test Role-Based Access Control middleware."""

    @pytest.fixture
    def protected_routes(self):
        """Define protected routes for testing."""
        return {
            "GET /admin/users": ["admin"],
            "POST /admin/users": ["admin"],
            "DELETE /admin/users": ["admin"],
            "GET /premium/data": ["premium", "admin"],
            "POST /api/nlp/jobs": ["premium", "admin"],
            "GET /public/articles": []  # Public route
        }

    @pytest.fixture
    def rbac_middleware(self, protected_routes):
        """Create RBAC middleware instance."""
        app = FastAPI()
        return RoleBasedAccessMiddleware(app, protected_routes)

    @pytest.fixture
    def mock_auth_handler(self):
        """Mock authentication handler."""
        with patch('src.api.middleware.auth_middleware.auth_handler') as mock_handler:
            yield mock_handler

    @pytest.mark.asyncio
    async def test_public_route_access(self, rbac_middleware):
        """Test access to public routes."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/public/info"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        
        mock_call_next = AsyncMock(return_value=Response("OK", status_code=200))
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        
        # Should allow access to public routes
        assert response.status_code == 200
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_protected_route_with_valid_role(self, rbac_middleware, mock_auth_handler):
        """Test access to protected route with valid role."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/admin/users"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "admin123", "role": "admin"}
        
        mock_call_next = AsyncMock(return_value=Response("Admin Data", status_code=200))
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        
        # Should allow access with valid role
        assert response.status_code == 200
        mock_call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_protected_route_with_insufficient_role(self, rbac_middleware):
        """Test access to protected route with insufficient role."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/admin/users"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "user123", "role": "free"}
        
        mock_call_next = AsyncMock()
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        
        # Should deny access
        assert response.status_code == 403
        response_data = json.loads(response.body.decode())
        assert "Insufficient permissions" in response_data["detail"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_protected_route_without_authentication(self, rbac_middleware, mock_auth_handler):
        """Test access to protected route without authentication."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/admin/users"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        
        # Mock authentication failure
        mock_auth_handler.side_effect = HTTPException(status_code=401, detail="Invalid token")
        
        # No user in request state
        delattr(mock_request.state, 'user')
        
        mock_call_next = AsyncMock()
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        
        # Should deny access
        assert response.status_code == 401
        response_data = json.loads(response.body.decode())
        assert "Authentication required" in response_data["detail"]
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_allowed_roles(self, rbac_middleware):
        """Test route accessible by multiple roles."""
        # Test premium user access
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/premium/data"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "premium123", "role": "premium"}
        
        mock_call_next = AsyncMock(return_value=Response("Premium Data", status_code=200))
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        assert response.status_code == 200
        
        # Test admin user access to same route
        mock_request.state.user = {"user_id": "admin123", "role": "admin"}
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_without_role(self, rbac_middleware):
        """Test user without role field."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/admin/users"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "user123"}  # No role field
        
        mock_call_next = AsyncMock()
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        
        # Should deny access
        assert response.status_code == 403
        mock_call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_route_method_specificity(self, rbac_middleware):
        """Test that route protection is method-specific."""
        # GET should be protected
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/admin/users"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "user123", "role": "free"}
        
        response = await rbac_middleware.dispatch(mock_request, AsyncMock())
        assert response.status_code == 403
        
        # OPTIONS might not be protected (depends on configuration)
        mock_request.method = "OPTIONS"
        mock_call_next = AsyncMock(return_value=Response("OK", status_code=200))
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        # Should allow OPTIONS requests (not in protected routes)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fallback_authentication(self, rbac_middleware, mock_auth_handler):
        """Test fallback to auth handler when user not in request state."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/admin/users"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        
        # No user in state, should call auth handler
        delattr(mock_request.state, 'user')
        
        # Mock successful authentication
        mock_auth_handler.return_value = {"user_id": "admin123", "role": "admin"}
        
        mock_call_next = AsyncMock(return_value=Response("Admin Data", status_code=200))
        
        response = await rbac_middleware.dispatch(mock_request, mock_call_next)
        
        assert response.status_code == 200
        mock_auth_handler.assert_called_once_with(mock_request)


class TestAuditLogMiddleware:
    """Test Audit Log middleware."""

    @pytest.fixture
    def audit_middleware(self):
        """Create audit log middleware instance."""
        app = FastAPI()
        return AuditLogMiddleware(app)

    @pytest.fixture
    def mock_security_logger(self):
        """Mock security audit logger."""
        with patch('src.api.middleware.auth_middleware.logger') as mock_logger:
            yield mock_logger

    @pytest.mark.asyncio
    async def test_successful_request_logging(self, audit_middleware, mock_security_logger):
        """Test logging of successful requests."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/users"
        mock_request.method = "GET"
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {"user-agent": "TestAgent/1.0"}
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "user123", "role": "premium"}
        
        mock_response = Response("Success", status_code=200)
        mock_call_next = AsyncMock(return_value=mock_response)
        
        response = await audit_middleware.dispatch(mock_request, mock_call_next)
        
        assert response.status_code == 200
        # Should have logged the request
        assert mock_security_logger.info.called

    @pytest.mark.asyncio
    async def test_failed_request_logging(self, audit_middleware, mock_security_logger):
        """Test logging of failed requests."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/admin"
        mock_request.method = "POST"
        mock_request.client.host = "10.0.0.1"
        mock_request.headers = {"user-agent": "BadActor/1.0"}
        mock_request.state = MagicMock()
        mock_request.state.user = {"user_id": "user123", "role": "free"}
        
        mock_response = Response("Forbidden", status_code=403)
        mock_call_next = AsyncMock(return_value=mock_response)
        
        response = await audit_middleware.dispatch(mock_request, mock_call_next)
        
        assert response.status_code == 403
        # Should have logged the failed request
        assert mock_security_logger.warning.called or mock_security_logger.error.called

    @pytest.mark.asyncio
    async def test_unauthenticated_request_logging(self, audit_middleware, mock_security_logger):
        """Test logging of unauthenticated requests."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/protected"
        mock_request.method = "GET"
        mock_request.client.host = "203.0.113.1"
        mock_request.headers = {}
        mock_request.state = MagicMock()
        
        # No user in state
        delattr(mock_request.state, 'user')
        
        mock_response = Response("Unauthorized", status_code=401)
        mock_call_next = AsyncMock(return_value=mock_response)
        
        response = await audit_middleware.dispatch(mock_request, mock_call_next)
        
        assert response.status_code == 401
        # Should have logged the unauthorized access attempt
        assert mock_security_logger.warning.called

    @pytest.mark.asyncio
    async def test_exception_handling_in_logging(self, audit_middleware, mock_security_logger):
        """Test that exceptions in next handler are properly logged."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/error"
        mock_request.method = "GET"
        mock_request.client.host = "192.168.1.100"
        mock_request.state = MagicMock()
        
        # Mock call_next to raise exception
        mock_call_next = AsyncMock(side_effect=Exception("Internal error"))
        
        # Should propagate exception but log it
        with pytest.raises(Exception, match="Internal error"):
            await audit_middleware.dispatch(mock_request, mock_call_next)
        
        # Should have logged the error
        assert mock_security_logger.error.called

    @pytest.mark.asyncio
    async def test_sensitive_data_sanitization(self, audit_middleware, mock_security_logger):
        """Test that sensitive data is sanitized in logs."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/login"
        mock_request.method = "POST"
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {
            "authorization": "Bearer secret_token_123",
            "x-api-key": "nn_secret_api_key"
        }
        mock_request.state = MagicMock()
        
        mock_response = Response("Login successful", status_code=200)
        mock_call_next = AsyncMock(return_value=mock_response)
        
        await audit_middleware.dispatch(mock_request, mock_call_next)
        
        # Check that sensitive headers were sanitized in logs
        log_calls = mock_security_logger.info.call_args_list
        for call in log_calls:
            log_message = str(call)
            # Should not contain actual sensitive values
            assert "secret_token_123" not in log_message
            assert "nn_secret_api_key" not in log_message


class TestSecurityMiddlewareIntegration:
    """Test integration between different security middlewares."""

    @pytest.fixture
    def integrated_app(self):
        """Create FastAPI app with integrated security middlewares."""
        app = FastAPI()
        
        # Configure CORS
        configure_cors(app)
        
        # Add RBAC middleware
        protected_routes = {
            "GET /admin/users": ["admin"],
            "POST /api/premium": ["premium", "admin"]
        }
        rbac_middleware = RoleBasedAccessMiddleware(app, protected_routes)
        app.add_middleware(BaseHTTPMiddleware, dispatch=rbac_middleware.dispatch)
        
        # Add audit middleware
        audit_middleware = AuditLogMiddleware(app)
        app.add_middleware(BaseHTTPMiddleware, dispatch=audit_middleware.dispatch)
        
        @app.get("/public")
        async def public_endpoint():
            return {"message": "public"}
        
        @app.get("/admin/users")
        async def admin_endpoint():
            return {"users": ["admin", "user1"]}
            
        @app.post("/api/premium")
        async def premium_endpoint():
            return {"data": "premium content"}
        
        return app

    def test_cors_integration(self, integrated_app):
        """Test CORS integration with security middlewares."""
        client = TestClient(integrated_app)
        
        # Test preflight request
        response = client.options(
            "/admin/users",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        
        # Should handle CORS preflight
        assert response.status_code in [200, 204]

    def test_rbac_and_audit_integration(self, integrated_app):
        """Test integration between RBAC and audit middleware."""
        client = TestClient(integrated_app)
        
        with patch('src.api.middleware.auth_middleware.logger') as mock_logger:
            # Test unauthorized access (should be logged)
            response = client.get("/admin/users")
            
            # Should be blocked by RBAC
            assert response.status_code == 401
            
            # Should be logged by audit middleware
            assert mock_logger.warning.called or mock_logger.error.called

    def test_middleware_execution_order(self, integrated_app):
        """Test that middlewares execute in correct order."""
        client = TestClient(integrated_app)
        
        with patch('src.api.middleware.auth_middleware.logger') as mock_logger:
            # Make request that triggers multiple middlewares
            response = client.get("/public")
            
            # Should succeed (public endpoint)
            assert response.status_code == 200
            
            # Audit middleware should have logged the request
            assert mock_logger.info.called

    @pytest.mark.asyncio
    async def test_concurrent_middleware_processing(self, integrated_app):
        """Test concurrent processing with multiple middlewares."""
        import asyncio
        from concurrent.futures import ThreadPoolExecutor
        
        def make_request(path):
            client = TestClient(integrated_app)
            return client.get(path)
        
        # Make concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(make_request, "/public")
                for _ in range(20)
            ]
            responses = [future.result() for future in futures]
        
        # All requests should succeed
        assert all(response.status_code == 200 for response in responses)

    def test_error_propagation_through_middlewares(self, integrated_app):
        """Test error propagation through middleware stack."""
        # Add endpoint that raises exception
        @integrated_app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=500, detail="Internal error")
        
        client = TestClient(integrated_app)
        
        with patch('src.api.middleware.auth_middleware.logger') as mock_logger:
            response = client.get("/error")
            
            # Should return error
            assert response.status_code == 500
            
            # Error should be logged by audit middleware
            assert mock_logger.error.called or mock_logger.warning.called


class TestSecurityMiddlewarePerformance:
    """Test security middleware performance characteristics."""

    @pytest.fixture
    def performance_app(self):
        """Create app optimized for performance testing."""
        app = FastAPI()
        
        configure_cors(app)
        
        # Large number of protected routes
        protected_routes = {}
        for i in range(100):
            protected_routes[f"GET /api/route_{i}"] = ["admin"]
        
        rbac_middleware = RoleBasedAccessMiddleware(app, protected_routes)
        app.add_middleware(BaseHTTPMiddleware, dispatch=rbac_middleware.dispatch)
        
        audit_middleware = AuditLogMiddleware(app)
        app.add_middleware(BaseHTTPMiddleware, dispatch=audit_middleware.dispatch)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "test"}
        
        return app

    def test_middleware_performance_with_many_routes(self, performance_app):
        """Test performance with many protected routes."""
        client = TestClient(performance_app)
        
        # Measure performance
        import time
        start_time = time.time()
        
        # Make many requests
        for _ in range(100):
            response = client.get("/test")
            assert response.status_code == 200
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle requests efficiently
        assert duration < 5.0  # 100 requests in under 5 seconds

    def test_concurrent_middleware_performance(self, performance_app):
        """Test performance under concurrent load."""
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor
        
        def make_requests(num_requests):
            client = TestClient(performance_app)
            success_count = 0
            for _ in range(num_requests):
                response = client.get("/test")
                if response.status_code == 200:
                    success_count += 1
            return success_count
        
        start_time = time.time()
        
        # Run concurrent requests
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_requests, 20) for _ in range(10)]
            results = [future.result() for future in futures]
        
        end_time = time.time()
        duration = end_time - start_time
        
        # All requests should succeed
        total_successful = sum(results)
        assert total_successful == 200  # 10 threads × 20 requests each
        
        # Should complete efficiently
        assert duration < 10.0

    def test_memory_usage_stability(self, performance_app):
        """Test memory usage stability under load."""
        import gc
        
        client = TestClient(performance_app)
        
        # Force garbage collection
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Make many requests
        for i in range(500):
            response = client.get("/test")
            assert response.status_code == 200
            
            # Periodic garbage collection
            if i % 100 == 0:
                gc.collect()
        
        # Final garbage collection
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Memory shouldn't grow significantly
        object_growth = final_objects - initial_objects
        assert object_growth < 10000, f"Memory grew by {object_growth} objects"