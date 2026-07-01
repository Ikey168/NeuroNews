#!/usr/bin/env python3
"""
Local WAF (Web Application Firewall) security tests - Issue #65.

The WAF implementation migrated from AWS WAF to a fully in-process, local
implementation:

- ``src/api/security/local_waf_manager.py`` -> ``LocalWAFManager`` / ``waf_manager``
- ``src/api/security/waf_middleware.py``    -> ``WAFSecurityMiddleware`` / ``WAFMetricsMiddleware``
- ``src/api/routes/waf_security_routes.py`` -> ``router`` (prefix ``/api/security``)

No boto3 / AWS access is required. These tests exercise the real source with
concrete assertions. Every test sets up its own objects and does not rely on
state leaked from other test files.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request


class TestWAFComponentImports:
    """The local WAF components import with their expected public symbols."""

    def test_waf_manager_import(self):
        from src.api.security.local_waf_manager import (
            ActionType,
            ThreatType,
            waf_manager,
        )

        # ThreatType / ActionType are the local enums; waf_manager is the
        # singleton LocalWAFManager instance.
        assert ThreatType.SQL_INJECTION.value == "sql_injection"
        assert ActionType.BLOCK.value == "BLOCK"
        assert waf_manager is not None
        assert hasattr(waf_manager, "detect_sql_injection")

    def test_waf_middleware_import(self):
        from starlette.middleware.base import BaseHTTPMiddleware

        from src.api.security.waf_middleware import (
            WAFMetricsMiddleware,
            WAFSecurityMiddleware,
        )

        # Both are Starlette HTTP middleware and constructible with a FastAPI app.
        assert issubclass(WAFSecurityMiddleware, BaseHTTPMiddleware)
        assert issubclass(WAFMetricsMiddleware, BaseHTTPMiddleware)
        assert WAFSecurityMiddleware(FastAPI()) is not None
        assert WAFMetricsMiddleware(FastAPI()) is not None

    def test_waf_routes_import(self):
        from src.api.routes.waf_security_routes import router

        # The router carries the /api/security prefix.
        assert router.prefix == "/api/security"
        assert len(router.routes) > 0

    def test_no_boto3_dependency(self):
        """The migrated local WAF manager must not import boto3."""
        import ast
        import inspect

        import src.api.security.local_waf_manager as mod

        tree = ast.parse(inspect.getsource(mod))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        assert "boto3" not in imported
        assert "botocore" not in imported


class TestWAFFastAPIIntegration:
    """WAF routes integrate with a FastAPI application."""

    def test_waf_security_available_flag_exposed(self):
        # The app module exposes the availability flag used to wire the WAF.
        from src.api.app import WAF_SECURITY_AVAILABLE

        assert isinstance(WAF_SECURITY_AVAILABLE, bool)

    def test_waf_router_mounts_on_app(self):
        """Including the real WAF router exposes /api/security routes.

        A fresh app is built here (rather than relying on the module-level
        ``app``, which is minimal under the test ``TESTING`` flag) so the check
        is deterministic and self-contained.
        """
        from src.api.routes.waf_security_routes import router

        app = FastAPI()
        app.include_router(router)

        # Use the generated OpenAPI schema to enumerate the effectively mounted
        # paths (newer FastAPI lazily wraps included routers, so iterating
        # ``app.routes`` does not flatten sub-paths).
        paths = app.openapi()["paths"]
        waf_routes = [p for p in paths if "/api/security" in p]
        assert waf_routes, "No /api/security routes mounted"
        assert any("/waf/health" in p for p in waf_routes)


class TestWAFManagerFunctionality:
    """LocalWAFManager threat detection and reporting behaviour."""

    @pytest.fixture
    def manager(self):
        from src.api.security.local_waf_manager import LocalWAFManager

        return LocalWAFManager()

    def test_health_check_reports_healthy(self, manager):
        health = manager.health_check()
        assert health["overall_status"] == "healthy"
        assert health["components"]["waf_engine"] == "operational"

    def test_detect_sql_injection_positive(self, manager):
        # Payloads carrying injection markers must be detected.
        assert manager.detect_sql_injection("' OR 1=1 --") is True
        assert manager.detect_sql_injection("'; DROP TABLE users;--") is True
        assert manager.detect_sql_injection("UNION SELECT password FROM users") is True

    def test_detect_sql_injection_negative(self, manager):
        assert manager.detect_sql_injection("hello world") is False
        assert manager.detect_sql_injection("") is False

    def test_detect_xss_positive(self, manager):
        assert manager.detect_xss("<script>alert('xss')</script>") is True
        assert manager.detect_xss("<img src=x onerror=alert(1)>") is True
        assert manager.detect_xss("javascript:alert(document.cookie)") is True

    def test_detect_xss_negative(self, manager):
        assert manager.detect_xss("just a normal comment") is False
        assert manager.detect_xss("") is False

    def test_security_metrics_structure(self, manager):
        metrics = manager.get_security_metrics()
        assert isinstance(metrics, dict)
        assert "timestamp" in metrics
        assert "metrics" in metrics
        # Every tracked metric name is present.
        for name in manager.METRIC_NAMES:
            assert name in metrics["metrics"]


class TestWAFMiddlewareThreatDetection:
    """WAFSecurityMiddleware request-level threat detection."""

    @pytest.fixture
    def middleware(self):
        from src.api.security.waf_middleware import WAFSecurityMiddleware

        mw = WAFSecurityMiddleware(FastAPI())
        # Avoid touching the real logging / alerting paths.
        mw._log_security_event = AsyncMock()
        mw._log_request_metrics = AsyncMock()
        return mw

    def test_detection_methods_exist(self, middleware):
        for method in (
            "_check_sql_injection",
            "_check_xss_attacks",
            "_check_geofencing",
            "_check_rate_limiting",
            "_check_bot_traffic",
        ):
            assert hasattr(middleware, method)

    def test_sql_injection_detected_in_query(self, middleware):
        request = MagicMock(spec=Request)
        request.url.query = "id=1 UNION SELECT username,password FROM users"
        request.method = "GET"
        request.body = AsyncMock(return_value=b"")

        result = asyncio.run(middleware._check_sql_injection(request))
        assert result["detected"] is True
        assert result["pattern_matched"]

    def test_sql_injection_clean_request(self, middleware):
        request = MagicMock(spec=Request)
        request.url.query = "id=123&name=john"
        request.method = "GET"
        request.body = AsyncMock(return_value=b'{"name": "John"}')

        result = asyncio.run(middleware._check_sql_injection(request))
        assert result["detected"] is False

    def test_xss_detected_in_query(self, middleware):
        request = MagicMock(spec=Request)
        request.url.query = "msg=<script>alert('xss')</script>"
        request.method = "GET"
        request.body = AsyncMock(return_value=b"")

        result = asyncio.run(middleware._check_xss_attacks(request))
        assert result["detected"] is True
        assert result["threat_level"] == "high"


class TestWAFGeofencing:
    """Geofencing behaviour of the middleware."""

    @pytest.fixture
    def middleware(self):
        from src.api.security.waf_middleware import WAFSecurityMiddleware

        return WAFSecurityMiddleware(FastAPI())

    def test_ip_in_blocked_range_is_blocked(self, middleware):
        # 1.0.1.0/24 is a geofenced range in the middleware.
        result = asyncio.run(middleware._check_geofencing("1.0.1.5"))
        assert result["blocked"] is True

    def test_allowed_ip_not_blocked(self, middleware):
        result = asyncio.run(middleware._check_geofencing("8.8.8.8"))
        assert result["blocked"] is False


class TestWAFRateLimiting:
    """Rate limiting integration of the middleware."""

    @pytest.fixture
    def middleware(self):
        from src.api.security.waf_middleware import WAFSecurityMiddleware

        return WAFSecurityMiddleware(FastAPI())

    def test_rate_limiting_method_available(self, middleware):
        assert hasattr(middleware, "_check_rate_limiting")

    def test_normal_traffic_not_limited(self, middleware):
        for _ in range(5):
            result = middleware._check_rate_limiting("192.168.1.10")
            assert result["exceeded"] is False

    def test_limit_exceeded_after_burst(self, middleware):
        ip = "192.168.1.200"
        # The middleware uses a hardcoded window limit of 100 requests.
        for _ in range(101):
            middleware._check_rate_limiting(ip)
        result = middleware._check_rate_limiting(ip)
        assert result["exceeded"] is True
        assert result["request_count"] > 100


class TestWAFSecuritySimulation:
    """Simulate attacks end-to-end against the local WAF manager."""

    @pytest.fixture
    def manager(self):
        from src.api.security.local_waf_manager import LocalWAFManager

        return LocalWAFManager()

    def test_all_sql_payloads_detected(self, manager):
        sql_payloads = [
            "' OR 1=1--",
            "'; DROP TABLE users;--",
            "UNION SELECT password FROM users",
            "1' AND 1=1#",
        ]
        for payload in sql_payloads:
            assert manager.detect_sql_injection(payload) is True, payload

    def test_all_xss_payloads_detected(self, manager):
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(document.cookie)",
            "<svg/onload=alert(1)>",
        ]
        for payload in xss_payloads:
            assert manager.detect_xss(payload) is True, payload


class TestWAFMetricsMonitoring:
    """WAF metrics collection (replaces the former CloudWatch integration)."""

    def test_manager_metrics_collection(self):
        from src.api.security.local_waf_manager import LocalWAFManager

        metrics = LocalWAFManager().get_security_metrics()
        assert isinstance(metrics, dict)
        assert "timestamp" in metrics

    def test_metrics_middleware_reports(self):
        from src.api.security.waf_middleware import WAFMetricsMiddleware

        mw = WAFMetricsMiddleware(FastAPI())
        report = mw.get_metrics()
        assert "total_requests" in report
        assert "blocked_requests" in report
        assert report["total_requests"] == 0
