"""
AWS WAF Security Monitoring Middleware for NeuroNews API - Issue #65.

This middleware provides real-time monitoring and response to security threats.
"""

import ipaddress
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.security.aws_waf_manager import (
    ActionType,
    SecurityEvent,
    ThreatType,
)

logger = logging.getLogger(__name__)


class WAFSecurityMiddleware(BaseHTTPMiddleware):
    """Middleware for WAF security monitoring and threat detection."""

    def __init__(self, app, excluded_paths: Optional[list] = None):
        """
        Initialize WAF security middleware.

        Args:
            app: FastAPI application
            excluded_paths: Paths to exclude from security monitoring
        """
        super().__init__(app)
        self.excluded_paths = excluded_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

        # Security patterns for threat detection
        self.sql_injection_patterns = [
            r"(?i)(union|select|insert|update|delete|drop|create|alter|exec|execute)",
            r"(?i)(\s*;\s*|\s*--|\s*/\*|\*/)",
            r"(?i)(or\s+1\s*=\s*1|and\s+1\s*=\s*1)",
            r"(?i)(information_schema|sys\.tables|sys\.columns)",
        ]

        self.xss_patterns = [
            r"(?i)<script[^>]*>.*?</script>",
            r"(?i)javascript:",
            r"(?i)on\w+\s*=",
            r"(?i)<iframe[^>]*>.*?</iframe>",
            r"(?i)eval\s*\(",
            r"(?i)alert\s*\(",
            r"(?i)document\.cookie",
        ]

        # Rate limiting tracking
        self.request_counts = {}
        self.blocked_ips = set()

        # Geofencing - blocked countries (ISO codes)
        # Example blocked countries
        self.blocked_countries = {"CN", "RU", "KP", "IR"}

    async def dispatch(self, request: Request, call_next):
        """
        Process request through WAF security monitoring.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response from next handler or security block response
        """
        start_time = time.time()

        # Skip monitoring for excluded paths
        if self._is_excluded_path(request.url.path):
            return await call_next(request)

        # Extract request information
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        request_path = request.url.path

        # Perform security checks
        security_check = await self._perform_security_checks(
            request, client_ip, user_agent
        )

        if security_check["blocked"]:
            # Log security event
            await self._log_security_event(
                threat_type=security_check["threat_type"],
                source_ip=client_ip,
                user_agent=user_agent,
                request_path=request_path,
                action_taken=ActionType.BLOCK,
                details=security_check["details"],
            )

            # Return blocked response
            return self._create_blocked_response(security_check)

        # Continue to application
        try:
            response = await call_next(request)

            # Add security headers
            self._add_security_headers(response)

            # Log successful request
            processing_time = time.time() - start_time
            await self._log_request_metrics(
                client_ip, request_path, processing_time, response.status_code
            )

            return response

        except Exception as e:
            logger.error("Error processing request: {0}".format(e))
            raise

    def _is_excluded_path(self, path: str) -> bool:
        """Check if path should be excluded from security monitoring."""
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return True
        return False

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address considering proxy headers."""
        # Check for forwarded IP headers (common in load balancers)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP if multiple are present
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct client IP
        return getattr(request.client, "host", "unknown")

    async def _perform_security_checks(
        self, request: Request, client_ip: str, user_agent: str
    ) -> Dict[str, Any]:
        """Perform comprehensive security checks on the request."""

        # Check 1: IP-based blocking
        if client_ip in self.blocked_ips:
            return {
                "blocked": True,
                "threat_type": ThreatType.MALICIOUS_IP,
                "details": {"reason": "IP address previously flagged as malicious"},
                "response_code": 403,
            }

        # Check 2: Rate limiting
        rate_limit_check = self._check_rate_limiting(client_ip)
        if rate_limit_check["exceeded"]:
            return {
                "blocked": True,
                "threat_type": ThreatType.RATE_LIMIT_EXCEEDED,
                "details": rate_limit_check,
                "response_code": 429,
            }

        # Check 3: Geofencing (simulate country detection)
        geo_check = await self._check_geofencing(client_ip)
        if geo_check["blocked"]:
            return {
                "blocked": True,
                "threat_type": ThreatType.GEO_BLOCKED,
                "details": geo_check,
                "response_code": 403,
            }

        # Check 4: SQL Injection detection
        sql_injection_check = await self._check_sql_injection(request)
        if sql_injection_check["detected"]:
            return {
                "blocked": True,
                "threat_type": ThreatType.SQL_INJECTION,
                "details": sql_injection_check,
                "response_code": 403,
            }

        # Check 5: XSS detection
        xss_check = await self._check_xss_attacks(request)
        if xss_check["detected"]:
            return {
                "blocked": True,
                "threat_type": ThreatType.XSS_ATTACK,
                "details": xss_check,
                "response_code": 403,
            }

        # Check 6: Bot detection
        bot_check = self._check_bot_traffic(user_agent)
        if bot_check["is_malicious_bot"]:
            return {
                "blocked": True,
                "threat_type": ThreatType.BOT_TRAFFIC,
                "details": bot_check,
                "response_code": 403,
            }

        return {"blocked": False}

    def _check_rate_limiting(self, client_ip: str) -> Dict[str, Any]:
        """Check rate limiting for client IP."""
        current_time = time.time()
        window_size = 300  # 5 minutes
        max_requests = 100  # requests per window

        # Clean old entries
        cutoff_time = current_time - window_size

        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []

        # Remove old requests
        self.request_counts[client_ip] = [
            timestamp
            for timestamp in self.request_counts[client_ip]
            if timestamp > cutoff_time
        ]

        # Add current request
        self.request_counts[client_ip].append(current_time)

        # Check if limit exceeded
        request_count = len(self.request_counts[client_ip])

        if request_count > max_requests:
            return {
                "exceeded": True,
                "request_count": request_count,
                "limit": max_requests,
                "window_seconds": window_size,
                "reset_time": current_time + window_size,
            }

        return {
            "exceeded": False,
            "request_count": request_count,
            "remaining": max_requests - request_count,
        }

    async def _check_geofencing(self, client_ip: str) -> Dict[str, Any]:
        """Check geofencing restrictions."""
        try:
            # In a real implementation, you would use a GeoIP service
            # For demo purposes, we'll simulate based on IP ranges

            # Example: Block certain IP ranges (this is simplified)
            ip_obj = ipaddress.ip_address(client_ip)

            # Simulate blocking certain IP ranges (example Chinese IP ranges)
            blocked_ranges = [
                ipaddress.ip_network("1.0.1.0/24"),  # Example range
                ipaddress.ip_network("223.255.255.0/24"),  # Example range
            ]

            for blocked_range in blocked_ranges:
                if ip_obj in blocked_range:
                    return {
                        "blocked": True,
                        "country": "Unknown",
                        "reason": "IP range blocked by geofencing policy",
                    }

            return {"blocked": False, "country": "Allowed"}

        except Exception as e:
            logger.warning("Error in geofencing check: {0}".format(e))
            return {"blocked": False, "error": str(e)}

    async def _check_sql_injection(self, request: Request) -> Dict[str, Any]:
        """Check for SQL injection attempts."""
        try:
            # Check query parameters
            query_string = str(request.url.query)

            # Check request body if present
            body_content = ""
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    body = await request.body()
                    body_content = body.decode("utf-8", errors="ignore")
                except Exception:
                    body_content = ""

            # Combine all content to check
            content_to_check = "{0} {1}".format(query_string, body_content).lower()

            # Check against SQL injection patterns
            for pattern in self.sql_injection_patterns:
                if re.search(pattern, content_to_check):
                    return {
                        "detected": True,
                        "pattern_matched": pattern,
                        # First 100 chars
                        "content_sample": content_to_check[:100],
                        "location": "query" if pattern in query_string else "body",
                    }

            return {"detected": False}

        except Exception as e:
            logger.error("Error in SQL injection check: {0}".format(e))
            return {"detected": False, "error": str(e)}

    async def _check_xss_attacks(self, request: Request) -> Dict[str, Any]:
        """Check for XSS attack attempts."""
        try:
            # Check query parameters
            query_string = str(request.url.query)

            # Check request headers
            headers_content = " ".join(
                "{0}:{1}".format(k, v) for k, v in request.headers.items()
            )

            # Check request body if present
            body_content = ""
            if request.method in ["POST", "PUT", "PATCH"]:
                try:
                    body = await request.body()
                    body_content = body.decode("utf-8", errors="ignore")
                except Exception:
                    body_content = ""

            # Combine all content to check
            content_to_check = "{0} {1} {2}".format(
                query_string, headers_content, body_content
            )

            # Check against XSS patterns
            for pattern in self.xss_patterns:
                if re.search(pattern, content_to_check):
                    return {
                        "detected": True,
                        "pattern_matched": pattern,
                        "content_sample": content_to_check[:100],
                        "threat_level": "high",
                    }

            return {"detected": False}

        except Exception as e:
            logger.error("Error in XSS check: {0}".format(e))
            return {"detected": False, "error": str(e)}

    def _check_bot_traffic(self, user_agent: str) -> Dict[str, Any]:
        """Check for malicious bot traffic."""
        # Known bad bot patterns
        malicious_bot_patterns = [
            r"(?i)(nikto|sqlmap|nessus|openvas|nmap)",
            r"(?i)(havij|sqlninja|pangolin)",
            r"(?i)(masscan|zmap|angry\s*ip)",
            r"(?i)(dirbuster|dirb|gobuster)",
            r"(?i)(wget|curl)(?!\s+\d)",  # Simple wget/curl without version
            r"(?i)(python-requests|python-urllib)",
            r"(?i)(bot|crawler|spider|scraper)(?!.*google|.*bing|.*facebook)",
        ]

        # Check for suspicious patterns
        for pattern in malicious_bot_patterns:
            if re.search(pattern, user_agent):
                return {
                    "is_malicious_bot": True,
                    "pattern_matched": pattern,
                    "user_agent": user_agent,
                    "confidence": "high",
                }

        # Check for empty or very short user agents
        if len(user_agent) < 10:
            return {
                "is_malicious_bot": True,
                "reason": "Suspicious user agent (too short)",
                "user_agent": user_agent,
                "confidence": "medium",
            }

        return {"is_malicious_bot": False}

    async def _log_security_event(
        self,
        threat_type: ThreatType,
        source_ip: str,
        user_agent: str,
        request_path: str,
        action_taken: ActionType,
        details: Dict[str, Any],
    ):
        """Log security event."""
        event = SecurityEvent(
            timestamp=datetime.now(timezone.utc),
            threat_type=threat_type,
            source_ip=source_ip,
            user_agent=user_agent,
            request_path=request_path,
            action_taken=action_taken,
            details=details,
        )

        # Log to application logger
        logger.warning(
            "SECURITY EVENT: {0} from {1} - Path: {2} - Action: {3}".format(
                threat_type.value, source_ip, request_path, action_taken.value
            )
        )

        # In production, you might also send to CloudWatch, SNS, etc.
        await self._send_security_alert(event)

    async def _send_security_alert(self, event: SecurityEvent):
        """Send security alert to monitoring systems."""
        try:
            # In production, this would send to SNS, Slack, PagerDuty, etc.
            alert_data = {
                "timestamp": event.timestamp.isoformat(),
                "threat_type": event.threat_type.value,
                "source_ip": event.source_ip,
                "severity": event.severity,
                "details": event.details,
            }

            # Log alert (in production, send to external system)
            logger.critical("SECURITY ALERT: {0}".format(json.dumps(alert_data)))

        except Exception as e:
            logger.error("Failed to send security alert: {0}".format(e))

    async def _log_request_metrics(
        self, client_ip: str, path: str, processing_time: float, status_code: int
    ):
        """Log request metrics for monitoring."""
        try:
            metrics = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "client_ip": client_ip,
                "path": path,
                "processing_time_ms": round(processing_time * 1000, 2),
                "status_code": status_code,
            }

            # In production, send to CloudWatch metrics
            logger.debug("REQUEST METRICS: {0}".format(json.dumps(metrics)))

        except Exception as e:
            logger.error("Failed to log request metrics: {0}".format(e))

    def _create_blocked_response(self, security_check: Dict[str, Any]) -> Response:
        """Create response for blocked requests."""
        response_data = {
            "error": "Access Denied",
            "message": "Your request has been blocked by our security system",
            "threat_type": security_check["threat_type"].value,
            "code": "WAF_BLOCKED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        response = Response(
            content=json.dumps(response_data),
            status_code=security_check.get("response_code", 403),
            media_type="application/json",
        )

        # Add security headers
        self._add_security_headers(response)

        return response

    def _add_security_headers(self, response: Response):
        """Add security headers to response."""
        security_headers = {
            "X-Content-Type-Options": "nosni",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'",
            "X-WAF-Protected": "true",
        }

        for header, value in security_headers.items():
            response.headers[header] = value


class WAFMetricsMiddleware(BaseHTTPMiddleware):
    """Middleware for collecting WAF metrics."""

    def __init__(self, app):
        """Initialize metrics middleware."""
        super().__init__(app)
        self.metrics = {
            "total_requests": 0,
            "blocked_requests": 0,
            "threat_types": {},
            "top_blocked_ips": {},
            "response_times": [],
        }

    async def dispatch(self, request: Request, call_next):
        """Collect metrics from requests."""
        start_time = time.time()

        response = await call_next(request)

        # Update metrics
        self.metrics["total_requests"] += 1

        # Track processing time
        processing_time = time.time() - start_time
        self.metrics["response_times"].append(processing_time)

        # Keep only last 1000 response times
        if len(self.metrics["response_times"]) > 1000:
            self.metrics["response_times"] = self.metrics["response_times"][-1000:]

        # Track blocked requests
        if response.status_code in [403, 429]:
            self.metrics["blocked_requests"] += 1

            # Track IP if blocked
            client_ip = request.headers.get(
                "X-Forwarded-For", request.client.host if request.client else "unknown"
            )
            if client_ip in self.metrics["top_blocked_ips"]:
                self.metrics["top_blocked_ips"][client_ip] += 1
            else:
                self.metrics["top_blocked_ips"][client_ip] = 1

        return response

    def get_metrics(self) -> Dict[str, Any]:
        """Get collected metrics."""
        avg_response_time = (
            sum(self.metrics["response_times"]) / len(self.metrics["response_times"])
            if self.metrics["response_times"]
            else 0
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_requests": self.metrics["total_requests"],
            "blocked_requests": self.metrics["blocked_requests"],
            "block_rate": (
                (self.metrics["blocked_requests"] / self.metrics["total_requests"])
                * 100
                if self.metrics["total_requests"] > 0
                else 0
            ),
            "average_response_time_ms": round(avg_response_time * 1000, 2),
            "top_blocked_ips": dict(
                sorted(
                    self.metrics["top_blocked_ips"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10]
            ),
            "threat_types": self.metrics["threat_types"],
        }


# Global metrics instance
waf_metrics = WAFMetricsMiddleware(None)
