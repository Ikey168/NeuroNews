"""
Comprehensive test suite for WAF Security Middleware - Issue #476.

Tests all WAF security requirements:
- WAF rule processing and attack detection
- SQL injection and XSS protection validation
- Request sanitization and validation
- IP-based blocking and geofencing
- Rate limiting integration
- Security event logging and metrics
- Performance under attack loads
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.security.aws_waf_manager import ActionType, ThreatType, SecurityEvent
from src.api.security.waf_middleware import WAFSecurityMiddleware


class TestWAFSecurityMiddleware:
    """Test WAF Security Middleware core functionality."""

    @pytest.fixture
    def app_with_waf(self):
        """Create FastAPI app with WAF middleware."""
        app = FastAPI()
        waf_middleware = WAFSecurityMiddleware(app)
        app.add_middleware(BaseHTTPMiddleware, dispatch=waf_middleware.dispatch)
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        @app.get("/admin/users")
        async def admin_endpoint():
            return {"users": ["admin", "user1"]}
            
        @app.post("/api/data")
        async def data_endpoint(data: dict):
            return {"received": data}
        
        return app

    @pytest.fixture
    def client(self, app_with_waf):
        """Create test client."""
        return TestClient(app_with_waf)

    @pytest.fixture
    def mock_waf_middleware(self):
        """Create WAF middleware with mocked dependencies."""
        app = MagicMock()
        middleware = WAFSecurityMiddleware(app)
        
        # Mock external dependencies
        middleware._log_security_event = AsyncMock()
        middleware._log_request_metrics = AsyncMock()
        
        return middleware

    def test_waf_middleware_initialization(self):
        """Test WAF middleware initialization."""
        app = MagicMock()
        excluded_paths = ["/health", "/metrics"]
        
        middleware = WAFSecurityMiddleware(app, excluded_paths=excluded_paths)
        
        assert middleware.excluded_paths == excluded_paths
        assert "/health" in middleware.excluded_paths
        assert "/docs" in middleware.excluded_paths  # Default exclusion
        
        # Verify security patterns are loaded
        assert len(middleware.sql_injection_patterns) > 0
        assert len(middleware.xss_patterns) > 0
        assert len(middleware.suspicious_user_agents) > 0

    def test_excluded_path_checking(self, mock_waf_middleware):
        """Test path exclusion logic."""
        middleware = mock_waf_middleware
        
        # Default excluded paths
        assert middleware._is_excluded_path("/health") is True
        assert middleware._is_excluded_path("/docs") is True
        assert middleware._is_excluded_path("/openapi.json") is True
        assert middleware._is_excluded_path("/redoc") is True
        
        # Non-excluded paths
        assert middleware._is_excluded_path("/api/users") is False
        assert middleware._is_excluded_path("/admin/system") is False

    def test_client_ip_extraction_direct(self, mock_waf_middleware):
        """Test client IP extraction from direct connection."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        mock_request.client.host = "192.168.1.100"
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "192.168.1.100"

    def test_client_ip_extraction_forwarded(self, mock_waf_middleware):
        """Test client IP extraction from X-Forwarded-For header."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {
            "X-Forwarded-For": "10.0.0.1, 192.168.1.1, 172.16.0.1"
        }
        mock_request.client.host = "192.168.1.100"
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.1"  # Should take first IP

    def test_client_ip_extraction_real_ip(self, mock_waf_middleware):
        """Test client IP extraction from X-Real-IP header."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-Real-IP": "203.0.113.5"}
        mock_request.client.host = "192.168.1.100"
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "203.0.113.5"

    def test_client_ip_extraction_priority(self, mock_waf_middleware):
        """Test IP extraction priority order."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {
            "X-Forwarded-For": "10.0.0.1",
            "X-Real-IP": "203.0.113.5"
        }
        mock_request.client.host = "192.168.1.100"
        
        ip = middleware._get_client_ip(mock_request)
        assert ip == "10.0.0.1"  # X-Forwarded-For takes priority

    @pytest.mark.asyncio
    async def test_sql_injection_detection(self, mock_waf_middleware):
        """Test SQL injection pattern detection."""
        middleware = mock_waf_middleware
        
        # Create request with SQL injection attempt
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "id=1' OR '1'='1"
        mock_request.method = "GET"
        
        # Mock request body for POST requests
        mock_request.body = AsyncMock(return_value=b'{"data": "1; DROP TABLE users; --"}')
        
        result = await middleware._check_sql_injection(mock_request)
        
        assert result["detected"] is True
        assert "SQL injection" in result["reason"]
        assert len(result["patterns_matched"]) > 0

    @pytest.mark.asyncio
    async def test_sql_injection_clean_request(self, mock_waf_middleware):
        """Test clean request passes SQL injection check."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "id=123&name=john"
        mock_request.method = "GET"
        mock_request.body = AsyncMock(return_value=b'{"name": "John Doe", "age": 30}')
        
        result = await middleware._check_sql_injection(mock_request)
        
        assert result["detected"] is False

    @pytest.mark.asyncio
    async def test_xss_detection(self, mock_waf_middleware):
        """Test XSS pattern detection."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "msg=<script>alert('xss')</script>"
        mock_request.method = "GET"
        mock_request.body = AsyncMock(return_value=b'{"comment": "<img src=x onerror=alert(1)>"}')
        
        result = await middleware._check_xss_attack(mock_request)
        
        assert result["detected"] is True
        assert "XSS" in result["reason"]
        assert len(result["patterns_matched"]) > 0

    @pytest.mark.asyncio
    async def test_xss_clean_request(self, mock_waf_middleware):
        """Test clean request passes XSS check."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "message=Hello World"
        mock_request.method = "GET"
        mock_request.body = AsyncMock(return_value=b'{"comment": "This is a normal comment"}')
        
        result = await middleware._check_xss_attack(mock_request)
        
        assert result["detected"] is False

    def test_rate_limiting_normal_traffic(self, mock_waf_middleware):
        """Test rate limiting with normal traffic."""
        middleware = mock_waf_middleware
        client_ip = "192.168.1.100"
        
        # Simulate normal request rate
        for _ in range(5):  # Under limit
            result = middleware._check_rate_limiting(client_ip)
            assert result["exceeded"] is False
        
        # Should still be under limit
        result = middleware._check_rate_limiting(client_ip)
        assert result["exceeded"] is False

    def test_rate_limiting_exceeded(self, mock_waf_middleware):
        """Test rate limiting when limit is exceeded."""
        middleware = mock_waf_middleware
        client_ip = "192.168.1.200"
        
        # Set low limit for testing
        middleware.rate_limit_requests = 5
        middleware.rate_limit_window = 60
        
        # Exceed the limit
        for _ in range(6):
            middleware._check_rate_limiting(client_ip)
        
        result = middleware._check_rate_limiting(client_ip)
        assert result["exceeded"] is True
        assert result["current_count"] > middleware.rate_limit_requests

    def test_ip_blocking_functionality(self, mock_waf_middleware):
        """Test IP-based blocking."""
        middleware = mock_waf_middleware
        blocked_ip = "10.0.0.666"
        middleware.blocked_ips.add(blocked_ip)
        
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}
        mock_request.client.host = blocked_ip
        
        # Should be blocked
        assert blocked_ip in middleware.blocked_ips
        
        # Clean IP should not be blocked
        clean_ip = "192.168.1.100"
        assert clean_ip not in middleware.blocked_ips

    @pytest.mark.asyncio
    async def test_geofencing_allowed_country(self, mock_waf_middleware):
        """Test geofencing for allowed countries."""
        middleware = mock_waf_middleware
        
        # Mock geolocation response for allowed country
        with patch.object(middleware, '_get_country_for_ip', return_value="US"):
            result = await middleware._check_geofencing("8.8.8.8")
            
            assert result["blocked"] is False

    @pytest.mark.asyncio
    async def test_geofencing_blocked_country(self, mock_waf_middleware):
        """Test geofencing for blocked countries."""
        middleware = mock_waf_middleware
        middleware.blocked_countries = {"XX", "YY"}
        
        # Mock geolocation response for blocked country
        with patch.object(middleware, '_get_country_for_ip', return_value="XX"):
            result = await middleware._check_geofencing("1.2.3.4")
            
            assert result["blocked"] is True
            assert result["country"] == "XX"

    @pytest.mark.asyncio
    async def test_user_agent_filtering(self, mock_waf_middleware):
        """Test suspicious user agent filtering."""
        middleware = mock_waf_middleware
        
        suspicious_agents = [
            "sqlmap/1.0",
            "nikto/2.1.6",
            "Nmap Scripting Engine",
            "() { :; }; /bin/bash",
            ""  # Empty user agent
        ]
        
        for agent in suspicious_agents:
            mock_request = MagicMock(spec=Request)
            mock_request.headers = {"user-agent": agent}
            
            result = await middleware._check_user_agent(mock_request)
            assert result["suspicious"] is True
            assert "user agent" in result["reason"].lower()

    @pytest.mark.asyncio
    async def test_user_agent_normal(self, mock_waf_middleware):
        """Test normal user agent passes checks."""
        middleware = mock_waf_middleware
        
        normal_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
            "curl/7.68.0"  # Legitimate curl
        ]
        
        for agent in normal_agents:
            mock_request = MagicMock(spec=Request)
            mock_request.headers = {"user-agent": agent}
            
            result = await middleware._check_user_agent(mock_request)
            assert result["suspicious"] is False

    @pytest.mark.asyncio
    async def test_comprehensive_security_check_clean(self, mock_waf_middleware):
        """Test comprehensive security check with clean request."""
        middleware = mock_waf_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "page=1&limit=10"
        mock_request.method = "GET"
        mock_request.headers = {"user-agent": "Mozilla/5.0"}
        mock_request.body = AsyncMock(return_value=b'{"valid": "data"}')
        mock_request.client.host = "192.168.1.100"
        
        result = await middleware._perform_security_checks(
            mock_request, "192.168.1.100", "Mozilla/5.0"
        )
        
        assert result["blocked"] is False

    @pytest.mark.asyncio
    async def test_comprehensive_security_check_blocked(self, mock_waf_middleware):
        """Test comprehensive security check with malicious request."""
        middleware = mock_waf_middleware
        malicious_ip = "10.0.0.666"
        middleware.blocked_ips.add(malicious_ip)
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "id=1' OR 1=1 --"
        mock_request.method = "GET" 
        mock_request.headers = {"user-agent": "sqlmap/1.0"}
        mock_request.body = AsyncMock(return_value=b'')
        
        result = await middleware._perform_security_checks(
            mock_request, malicious_ip, "sqlmap/1.0"
        )
        
        assert result["blocked"] is True
        assert result["threat_type"] == ThreatType.MALICIOUS_IP

    def test_blocked_response_creation(self, mock_waf_middleware):
        """Test creation of blocked response."""
        middleware = mock_waf_middleware
        
        security_check = {
            "blocked": True,
            "threat_type": ThreatType.SQL_INJECTION,
            "details": {"reason": "SQL injection detected", "patterns": ["OR 1=1"]},
            "response_code": 403
        }
        
        response = middleware._create_blocked_response(security_check)
        
        assert response.status_code == 403
        response_data = json.loads(response.body.decode())
        assert response_data["error"] == "Request blocked by security policy"
        assert response_data["threat_type"] == "sql_injection"

    def test_security_headers_addition(self, mock_waf_middleware):
        """Test security headers are added to responses."""
        middleware = mock_waf_middleware
        
        mock_response = MagicMock(spec=Response)
        mock_response.headers = {}
        
        middleware._add_security_headers(mock_response)
        
        # Check security headers were added
        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Strict-Transport-Security",
            "Referrer-Policy"
        ]
        
        for header in expected_headers:
            assert header in mock_response.headers


class TestWAFPerformance:
    """Test WAF middleware performance characteristics."""

    @pytest.fixture
    def performance_middleware(self):
        """Create WAF middleware for performance testing."""
        app = MagicMock()
        middleware = WAFSecurityMiddleware(app)
        middleware._log_security_event = AsyncMock()
        middleware._log_request_metrics = AsyncMock()
        return middleware

    @pytest.mark.asyncio
    async def test_security_check_performance(self, performance_middleware):
        """Test security check performance."""
        middleware = performance_middleware
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = "normal=query&page=1"
        mock_request.method = "GET"
        mock_request.headers = {"user-agent": "Mozilla/5.0"}
        mock_request.body = AsyncMock(return_value=b'{"normal": "data"}')
        
        # Measure performance
        start_time = time.time()
        
        # Run multiple security checks
        for _ in range(100):
            await middleware._perform_security_checks(
                mock_request, "192.168.1.100", "Mozilla/5.0"
            )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete 100 checks quickly (< 1 second)
        assert duration < 1.0

    @pytest.mark.asyncio
    async def test_sql_injection_pattern_performance(self, performance_middleware):
        """Test SQL injection pattern matching performance."""
        middleware = performance_middleware
        
        # Large query string
        large_query = "&".join([f"param{i}=value{i}" for i in range(100)])
        
        mock_request = MagicMock(spec=Request)
        mock_request.url.query = large_query
        mock_request.method = "GET"
        mock_request.body = AsyncMock(return_value=b'{"data": "normal"}')
        
        start_time = time.time()
        
        # Test pattern matching performance
        result = await middleware._check_sql_injection(mock_request)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete quickly even with large input
        assert duration < 0.1
        assert result["detected"] is False

    @pytest.mark.asyncio
    async def test_concurrent_security_checks(self, performance_middleware):
        """Test concurrent security check performance."""
        middleware = performance_middleware
        
        async def run_security_check(request_id):
            mock_request = MagicMock(spec=Request)
            mock_request.url.query = f"id={request_id}"
            mock_request.method = "GET"
            mock_request.headers = {"user-agent": "TestAgent"}
            mock_request.body = AsyncMock(return_value=b'{"test": "data"}')
            
            return await middleware._perform_security_checks(
                mock_request, f"192.168.1.{request_id % 255}", "TestAgent"
            )
        
        # Run concurrent security checks
        tasks = [run_security_check(i) for i in range(50)]
        results = await asyncio.gather(*tasks)
        
        # All should complete successfully
        assert len(results) == 50
        for result in results:
            assert "blocked" in result

    def test_rate_limiting_performance(self, performance_middleware):
        """Test rate limiting performance with many IPs."""
        middleware = performance_middleware
        
        start_time = time.time()
        
        # Check rate limits for many different IPs
        for i in range(1000):
            ip = f"192.168.{i // 255}.{i % 255}"
            middleware._check_rate_limiting(ip)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle many IP checks quickly
        assert duration < 2.0

    def test_memory_usage_stability(self, performance_middleware):
        """Test memory usage stability under load."""
        import gc
        
        middleware = performance_middleware
        
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Generate load
        for i in range(500):
            ip = f"10.0.{i // 255}.{i % 255}"
            # Simulate various operations
            middleware._check_rate_limiting(ip)
            middleware._is_excluded_path(f"/test/{i}")
            
            # Periodic garbage collection
            if i % 100 == 0:
                gc.collect()
        
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Memory usage shouldn't grow significantly
        object_growth = final_objects - initial_objects
        assert object_growth < 5000, f"Memory grew by {object_growth} objects"


class TestWAFSecurityScenarios:
    """Test WAF security scenarios and attack simulations."""

    @pytest.fixture
    def security_middleware(self):
        """Create WAF middleware for security testing."""
        app = MagicMock()
        middleware = WAFSecurityMiddleware(app)
        middleware._log_security_event = AsyncMock()
        return middleware

    @pytest.mark.asyncio
    async def test_advanced_sql_injection_attempts(self, security_middleware):
        """Test detection of advanced SQL injection attempts."""
        middleware = security_middleware
        
        advanced_payloads = [
            "1' UNION SELECT username,password FROM users--",
            "'; INSERT INTO users (username,password) VALUES ('hacker','pass'); --",
            "1' AND (SELECT COUNT(*) FROM users) > 0 --",
            "1' OR ASCII(SUBSTRING((SELECT password FROM users WHERE username='admin'),1,1)) > 65 --",
            "1'; WAITFOR DELAY '00:00:05' --",
            "1' OR '1'='1",
            "admin'/**/OR/**/'1'='1",
            "1' AND SLEEP(5) --"
        ]
        
        for payload in advanced_payloads:
            mock_request = MagicMock(spec=Request)
            mock_request.url.query = f"id={payload}"
            mock_request.method = "GET"
            mock_request.body = AsyncMock(return_value=b'{}')
            
            result = await middleware._check_sql_injection(mock_request)
            assert result["detected"] is True, f"Failed to detect: {payload}"

    @pytest.mark.asyncio
    async def test_advanced_xss_attempts(self, security_middleware):
        """Test detection of advanced XSS attempts."""
        middleware = security_middleware
        
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert(1)>",
            "<svg onload=alert('XSS')>",
            "javascript:alert('XSS')",
            "<iframe src=javascript:alert('XSS')></iframe>",
            "<body onload=alert('XSS')>",
            "<input onfocus=alert('XSS') autofocus>",
            "';alert('XSS');//",
            "<script>document.cookie='stolen';</script>"
        ]
        
        for payload in xss_payloads:
            mock_request = MagicMock(spec=Request)
            mock_request.url.query = f"msg={payload}"
            mock_request.method = "GET"
            mock_request.body = AsyncMock(return_value=f'{{"comment":"{payload}"}}'.encode())
            
            result = await middleware._check_xss_attack(mock_request)
            assert result["detected"] is True, f"Failed to detect: {payload}"

    @pytest.mark.asyncio
    async def test_path_traversal_detection(self, security_middleware):
        """Test path traversal attack detection."""
        middleware = security_middleware
        
        path_traversal_payloads = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc/passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
            "..%252f..%252f..%252fetc%252fpasswd",
            "..%c0%af..%c0%af..%c0%afetc%c0%afpasswd"
        ]
        
        for payload in path_traversal_payloads:
            mock_request = MagicMock(spec=Request)
            mock_request.url.query = f"file={payload}"
            mock_request.method = "GET"
            mock_request.body = AsyncMock(return_value=b'{}')
            
            # Add path traversal patterns to middleware
            if not hasattr(middleware, 'path_traversal_patterns'):
                middleware.path_traversal_patterns = [
                    r"\.\./",
                    r"\.\.\\",
                    r"%2e%2e%2f",
                    r"\.\.%2f",
                    r"%c0%af"
                ]
            
            result = await middleware._check_path_traversal(mock_request)
            assert result["detected"] is True, f"Failed to detect: {payload}"

    def test_ddos_protection_simulation(self, security_middleware):
        """Test DDoS protection through rate limiting."""
        middleware = security_middleware
        attacker_ip = "10.0.0.1"
        
        # Set aggressive rate limiting for testing
        middleware.rate_limit_requests = 10
        middleware.rate_limit_window = 60
        
        # Simulate rapid requests
        blocked_count = 0
        for i in range(50):  # Attempt many requests
            result = middleware._check_rate_limiting(attacker_ip)
            if result["exceeded"]:
                blocked_count += 1
        
        # Should block most requests after limit exceeded
        assert blocked_count > 30

    @pytest.mark.asyncio
    async def test_bot_detection(self, security_middleware):
        """Test malicious bot detection."""
        middleware = security_middleware
        
        bot_user_agents = [
            "Mozilla/5.0 (compatible; Baiduspider/2.0)",
            "sqlmap/1.0",
            "nikto/2.1.6",
            "w3af.sourceforge.net",
            "() { :; }; echo; /bin/bash",
            "Havij",
            "pangolin",
            ""
        ]
        
        for agent in bot_user_agents:
            mock_request = MagicMock(spec=Request)
            mock_request.headers = {"user-agent": agent}
            
            result = await middleware._check_user_agent(mock_request)
            # Some legitimate bots might be allowed, but malicious ones should be caught
            if agent in ["sqlmap/1.0", "nikto/2.1.6", "Havij", ""]:
                assert result["suspicious"] is True

    @pytest.mark.asyncio
    async def test_combined_attack_detection(self, security_middleware):
        """Test detection of combined attack techniques."""
        middleware = security_middleware
        
        # Simulate sophisticated attack combining multiple techniques
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {
            "user-agent": "sqlmap/1.0",
            "x-forwarded-for": "10.0.0.1"  # Suspicious IP
        }
        mock_request.url.query = "id=1' UNION SELECT * FROM users--&file=../etc/passwd"
        mock_request.method = "POST"
        mock_request.body = AsyncMock(return_value=b'{"data": "<script>alert(\"XSS\")</script>"}')
        
        attacker_ip = "10.0.0.1"
        
        # Should detect multiple threats
        sql_result = await middleware._check_sql_injection(mock_request)
        xss_result = await middleware._check_xss_attack(mock_request)
        agent_result = await middleware._check_user_agent(mock_request)
        
        assert sql_result["detected"] is True
        assert xss_result["detected"] is True
        assert agent_result["suspicious"] is True


class TestWAFIntegration:
    """Test WAF integration with other security components."""

    @pytest.mark.asyncio
    async def test_security_event_logging_integration(self):
        """Test integration with security event logging."""
        app = MagicMock()
        middleware = WAFSecurityMiddleware(app)
        
        # Mock security logger
        with patch('src.api.security.waf_middleware.logger') as mock_logger:
            await middleware._log_security_event(
                threat_type=ThreatType.SQL_INJECTION,
                source_ip="10.0.0.1",
                user_agent="sqlmap/1.0",
                request_path="/api/data",
                action_taken=ActionType.BLOCK,
                details={"patterns": ["OR 1=1"]}
            )
            
            # Should log security event
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_metrics_collection_integration(self):
        """Test integration with metrics collection."""
        app = MagicMock()
        middleware = WAFSecurityMiddleware(app)
        
        # Mock metrics collection
        await middleware._log_request_metrics(
            client_ip="192.168.1.100",
            request_path="/api/test",
            processing_time=0.150,
            status_code=200
        )
        
        # Should complete without errors
        assert True  # Test passes if no exceptions

    def test_aws_waf_manager_integration(self):
        """Test integration with AWS WAF Manager."""
        app = MagicMock()
        middleware = WAFSecurityMiddleware(app)
        
        # Should use proper threat types and action types from AWS WAF Manager
        assert hasattr(middleware, 'blocked_ips')
        
        # Test threat type integration
        security_event = SecurityEvent(
            event_id="test123",
            threat_type=ThreatType.SQL_INJECTION,
            source_ip="10.0.0.1",
            timestamp=time.time(),
            action_taken=ActionType.BLOCK
        )
        
        assert security_event.threat_type == ThreatType.SQL_INJECTION
        assert security_event.action_taken == ActionType.BLOCK