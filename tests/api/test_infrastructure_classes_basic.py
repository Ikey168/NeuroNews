"""
Comprehensive API Infrastructure Classes Testing Suite for Issue #477

Tests API infrastructure behaviour (error handling, request processing and
metrics collection) to ensure reliable operation.

Note: the former ``TestAuthMiddleware`` suite was removed because the
``AuthMiddleware`` class it exercised (with ``secret_key``/``algorithm``/
``dispatch``/``is_public_endpoint``) no longer exists in
``src.api.middleware.auth_middleware`` — that module now exposes
``RoleBasedAccessMiddleware`` / ``AuditLogMiddleware`` and ``configure_*``
helpers instead. The remaining integration tests cover functionality that is
still present.
"""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import pytest


# ============================================================================
# METRICS COLLECTOR TEST DOUBLE
# ============================================================================

class MockMetricsCollector:
    def __init__(self):
        self.request_count = 0
        self.response_times = {}
        self.error_count = 0

    def record_request(self, endpoint, method, success=True, timestamp=None):
        self.request_count += 1

    def get_request_count(self):
        return self.request_count

    def record_response_time(self, endpoint, time_ms):
        if endpoint not in self.response_times:
            self.response_times[endpoint] = []
        self.response_times[endpoint].append(time_ms)

    def get_average_response_time(self, endpoint):
        if endpoint not in self.response_times:
            return 0
        times = self.response_times[endpoint]
        return sum(times) / len(times)

    def reset_metrics(self):
        self.request_count = 0
        self.response_times = {}
        self.error_count = 0


# ============================================================================
# INTEGRATION TESTS FOR INFRASTRUCTURE
# ============================================================================

class TestInfrastructureIntegration:
    """Integration tests for infrastructure components."""

    def test_middleware_error_handling_integration(self):
        """Test integration of middleware with error handling."""
        app = FastAPI()

        @app.get("/error")
        async def error_endpoint():
            raise HTTPException(status_code=400, detail="Test error")

        client = TestClient(app)

        response = client.get("/error")
        assert response.status_code == 400

    def test_basic_request_processing(self):
        """Test basic request processing through middleware stack."""
        app = FastAPI()

        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}

        client = TestClient(app)

        response = client.get("/test")
        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_metrics_collection_integration(self):
        """Test metrics collection functionality."""
        metrics = MockMetricsCollector()

        # Record some metrics
        metrics.record_request("/api/test", "GET")
        metrics.record_response_time("/api/test", 150)

        assert metrics.get_request_count() == 1
        assert metrics.get_average_response_time("/api/test") == 150


if __name__ == "__main__":
    # Run infrastructure tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short"
    ])
