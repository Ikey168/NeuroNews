#!/usr/bin/env python3
"""
Local WAF (Web Application Firewall) security tests - Issue #65 (fixed variant).

The WAF implementation migrated from AWS WAF to a fully in-process, local
implementation:

- ``src/api/security/local_waf_manager.py`` -> ``LocalWAFManager`` / ``waf_manager``
- ``src/api/security/waf_middleware.py``    -> ``WAFSecurityMiddleware`` / ``WAFMetricsMiddleware``
- ``src/api/routes/waf_security_routes.py`` -> ``router`` (prefix ``/api/security``)

No boto3 / AWS access is required. These tests exercise the real source with
concrete assertions and are fully self-contained (no reliance on state leaked
by other test files).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request


class TestWAFImports:
    """The local WAF components import with their expected public symbols."""

    def test_waf_manager_import(self):
        from src.api.security.local_waf_manager import (
            ActionType,
            ThreatType,
            waf_manager,
        )

        assert ThreatType.XSS_ATTACK.value == "xss_attack"
        assert ActionType.ALLOW.value == "ALLOW"
        assert hasattr(waf_manager, "detect_xss")

    def test_waf_middleware_import(self):
        from starlette.middleware.base import BaseHTTPMiddleware

        from src.api.security.waf_middleware import (
            WAFMetricsMiddleware,
            WAFSecurityMiddleware,
        )

        assert issubclass(WAFSecurityMiddleware, BaseHTTPMiddleware)
        assert issubclass(WAFMetricsMiddleware, BaseHTTPMiddleware)

    def test_waf_routes_import(self):
        from src.api.routes.waf_security_routes import router

        assert router.prefix == "/api/security"
        assert len(router.routes) > 0


class TestFastAPIIntegration:
    """WAF availability flag and router mounting."""

    def test_waf_security_available_flag(self):
        from src.api.app import WAF_SECURITY_AVAILABLE

        assert isinstance(WAF_SECURITY_AVAILABLE, bool)

    def test_router_mounts_expected_paths(self):
        from src.api.routes.waf_security_routes import router

        app = FastAPI()
        app.include_router(router)

        # OpenAPI schema is the authoritative list of exposed paths.
        paths = app.openapi()["paths"]
        sec_paths = [p for p in paths if "/api/security" in p]
        assert sec_paths
        assert any("/waf/status" in p for p in sec_paths)
        assert any("/attacks/sql-injection" in p for p in sec_paths)


class TestManagerFunctionality:
    """LocalWAFManager health, detection and metrics."""

    @pytest.fixture
    def manager(self):
        from src.api.security.local_waf_manager import LocalWAFManager

        return LocalWAFManager()

    def test_health_check(self, manager):
        health = manager.health_check()
        assert health["overall_status"] == "healthy"

    def test_sql_injection_detection(self, manager):
        assert manager.detect_sql_injection("'; DROP TABLE users; --") is True
        assert manager.detect_sql_injection("normal input") is False

    def test_xss_detection(self, manager):
        assert manager.detect_xss("<script>alert('xss')</script>") is True
        assert manager.detect_xss("normal input") is False

    def test_metrics_have_timestamp(self, manager):
        metrics = manager.get_security_metrics()
        assert isinstance(metrics, dict)
        assert "timestamp" in metrics


class TestMiddlewareMethods:
    """WAFSecurityMiddleware exposes and implements its security checks."""

    @pytest.fixture
    def middleware(self):
        from src.api.security.waf_middleware import WAFSecurityMiddleware

        mw = WAFSecurityMiddleware(FastAPI())
        mw._log_security_event = AsyncMock()
        mw._log_request_metrics = AsyncMock()
        return mw

    def test_sql_and_xss_methods_exist(self, middleware):
        assert hasattr(middleware, "_check_sql_injection")
        assert hasattr(middleware, "_check_xss_attacks")

    def test_geofencing_method_exists(self, middleware):
        assert hasattr(middleware, "_check_geofencing")

    def test_rate_limiting_method_exists(self, middleware):
        assert hasattr(middleware, "_check_rate_limiting")

    def test_sql_injection_check_positive(self, middleware):
        request = MagicMock(spec=Request)
        request.url.query = "id=1' OR 1=1 --"
        request.method = "GET"
        request.body = AsyncMock(return_value=b"")
        result = asyncio.run(middleware._check_sql_injection(request))
        assert result["detected"] is True

    def test_xss_check_positive(self, middleware):
        request = MagicMock(spec=Request)
        request.url.query = "q=<script>alert(1)</script>"
        request.method = "GET"
        request.body = AsyncMock(return_value=b"")
        result = asyncio.run(middleware._check_xss_attacks(request))
        assert result["detected"] is True

    def test_bot_traffic_detection(self, middleware):
        assert middleware._check_bot_traffic("sqlmap/1.0")["is_malicious_bot"] is True
        normal = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        assert middleware._check_bot_traffic(normal)["is_malicious_bot"] is False


class TestAttackSimulation:
    """Attack payloads are consistently detected by the WAF manager."""

    @pytest.fixture
    def manager(self):
        from src.api.security.local_waf_manager import LocalWAFManager

        return LocalWAFManager()

    def test_sql_payloads(self, manager):
        for payload in [
            "' OR 1=1--",
            "'; DROP TABLE users;--",
            "UNION SELECT password FROM users",
            "1' AND 1=1#",
        ]:
            assert manager.detect_sql_injection(payload) is True, payload

    def test_xss_payloads(self, manager):
        for payload in [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(document.cookie)",
            "<svg/onload=alert(1)>",
        ]:
            assert manager.detect_xss(payload) is True, payload


class TestMetricsMonitoring:
    """WAF metrics collection (local replacement for CloudWatch)."""

    def test_metrics_middleware_initial_state(self):
        from src.api.security.waf_middleware import WAFMetricsMiddleware

        report = WAFMetricsMiddleware(FastAPI()).get_metrics()
        assert report["total_requests"] == 0
        assert report["blocked_requests"] == 0
        assert "timestamp" in report
