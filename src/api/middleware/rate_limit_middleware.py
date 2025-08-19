"""
Rate Limiting Middleware for API Access Control (Issue #59)

Implements comprehensive rate limiting with user tiers and suspicious activity monitoring.
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import redis
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


@dataclass
class UserTier:
    """User tier configuration for rate limiting."""

    name: str
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_limit: int
    concurrent_requests: int


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    # User tiers
    FREE_TIER = UserTier(
        name="free",
        requests_per_minute=10,
        requests_per_hour=100,
        requests_per_day=1000,
        burst_limit=15,
        concurrent_requests=3,
    )

    PREMIUM_TIER = UserTier(
        name="premium",
        requests_per_minute=100,
        requests_per_hour=2000,
        requests_per_day=20000,
        burst_limit=150,
        concurrent_requests=10,
    )

    ENTERPRISE_TIER = UserTier(
        name="enterprise",
        requests_per_minute=1000,
        requests_per_hour=50000,
        requests_per_day=500000,
        burst_limit=1500,
        concurrent_requests=50,
    )

    # Suspicious activity thresholds
    SUSPICIOUS_PATTERNS = {
        "rapid_requests": 50,  # More than 50 requests in 1 minute
        "unusual_hours": True,  # Requests during 2-6 AM
        "multiple_ips": 5,  # Same user from 5+ different IPs in 1 hour
        "error_rate": 0.5,  # More than 50% error rate
        "endpoint_abuse": 20,  # More than 20 requests to same endpoint/minute
    }


@dataclass
class RequestMetrics:
    """Metrics for tracking request patterns."""

    user_id: str
    ip_address: str
    endpoint: str
    timestamp: datetime
    response_code: int
    processing_time: float


class RateLimitStore:
    """Storage backend for rate limiting data."""

    def __init__(self, use_redis: bool = True):
        self.use_redis = use_redis and self._redis_available()

        if self.use_redis:
            self.redis_client = self._get_redis_client()
            logger.info("Rate limiting using Redis backend")
        else:
            # In-memory fallback
            self.memory_store = defaultdict(
                lambda: {
                    "requests": deque(),
                    "concurrent": 0,
                    "metrics": deque(maxlen=1000),
                }
            )
            logger.info("Rate limiting using in-memory backend")

    def _redis_available(self) -> bool:
        """Check if Redis is available."""
        try:
            pass

            return True
        except ImportError:
            return False

    def _get_redis_client(self):
        """Get Redis client."""
        try:
            return redis.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", 6379)),
                db=int(os.getenv("REDIS_DB", 0)),
                decode_responses=True,
            )
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}, falling back to memory")
            self.use_redis = False
            return None

    async def record_request(self, user_id: str, metrics: RequestMetrics):
        """Record a request for rate limiting."""
        if self.use_redis:
            await self._record_request_redis(user_id, metrics)
        else:
            self._record_request_memory(user_id, metrics)

    async def _record_request_redis(self, user_id: str, metrics: RequestMetrics):
        """Record request in Redis."""
        pipe = self.redis_client.pipeline()
        now = time.time()

        # Store in time-based windows
        minute_key = f"rate_limit:{user_id}:minute:{int(now // 60)}"
        hour_key = f"rate_limit:{user_id}:hour:{int(now // 3600)}"
        day_key = f"rate_limit:{user_id}:day:{int(now // 86400)}"

        # Increment counters with expiration
        pipe.incr(minute_key)
        pipe.expire(minute_key, 120)  # Keep for 2 minutes

        pipe.incr(hour_key)
        pipe.expire(hour_key, 7200)  # Keep for 2 hours

        pipe.incr(day_key)
        pipe.expire(day_key, 172800)  # Keep for 2 days

        # Store detailed metrics
        metrics_key = f"metrics:{user_id}"
        metrics_data = {
            "ip": metrics.ip_address,
            "endpoint": metrics.endpoint,
            "timestamp": metrics.timestamp.isoformat(),
            "response_code": metrics.response_code,
            "processing_time": metrics.processing_time,
        }

        pipe.lpush(metrics_key, json.dumps(metrics_data))
        pipe.ltrim(metrics_key, 0, 999)  # Keep last 1000 entries
        pipe.expire(metrics_key, 86400)  # Keep for 1 day

        await asyncio.get_event_loop().run_in_executor(None, pipe.execute)

    def _record_request_memory(self, user_id: str, metrics: RequestMetrics):
        """Record request in memory."""
        user_data = self.memory_store[user_id]
        now = time.time()

        # Clean old requests (older than 24 hours)
        user_data["requests"] = deque(
            [req for req in user_data["requests"] if now - req["timestamp"] < 86400]
        )

        # Add new request
        user_data["requests"].append(
            {"timestamp": now, "ip": metrics.ip_address, "endpoint": metrics.endpoint}
        )

        # Add metrics
        user_data["metrics"].append(metrics)

    async def get_request_counts(self, user_id: str) -> Dict[str, int]:
        """Get request counts for different time windows."""
        if self.use_redis:
            return await self._get_request_counts_redis(user_id)
        else:
            return self._get_request_counts_memory(user_id)

    async def _get_request_counts_redis(self, user_id: str) -> Dict[str, int]:
        """Get request counts from Redis."""
        now = time.time()

        minute_key = f"rate_limit:{user_id}:minute:{int(now // 60)}"
        hour_key = f"rate_limit:{user_id}:hour:{int(now // 3600)}"
        day_key = f"rate_limit:{user_id}:day:{int(now // 86400)}"

        pipe = self.redis_client.pipeline()
        pipe.get(minute_key)
        pipe.get(hour_key)
        pipe.get(day_key)

        results = await asyncio.get_event_loop().run_in_executor(None, pipe.execute)

        return {
            "minute": int(results[0] or 0),
            "hour": int(results[1] or 0),
            "day": int(results[2] or 0),
        }

    def _get_request_counts_memory(self, user_id: str) -> Dict[str, int]:
        """Get request counts from memory."""
        user_data = self.memory_store[user_id]
        now = time.time()

        requests = user_data["requests"]

        # Count requests in different windows
        minute_count = sum(1 for req in requests if now - req["timestamp"] < 60)
        hour_count = sum(1 for req in requests if now - req["timestamp"] < 3600)
        day_count = sum(1 for req in requests if now - req["timestamp"] < 86400)

        return {"minute": minute_count, "hour": hour_count, "day": day_count}

    async def increment_concurrent(self, user_id: str) -> int:
        """Increment concurrent request counter."""
        if self.use_redis:
            return await self._increment_concurrent_redis(user_id)
        else:
            return self._increment_concurrent_memory(user_id)

    async def decrement_concurrent(self, user_id: str):
        """Decrement concurrent request counter."""
        if self.use_redis:
            await self._decrement_concurrent_redis(user_id)
        else:
            self._decrement_concurrent_memory(user_id)

    async def _increment_concurrent_redis(self, user_id: str) -> int:
        """Increment concurrent counter in Redis."""
        key = f"concurrent:{user_id}"
        new_count = await asyncio.get_event_loop().run_in_executor(
            None, self.redis_client.incr, key
        )
        await asyncio.get_event_loop().run_in_executor(
            None, self.redis_client.expire, key, 300
        )
        return new_count

    async def _decrement_concurrent_redis(self, user_id: str):
        """Decrement concurrent counter in Redis."""
        key = f"concurrent:{user_id}"
        await asyncio.get_event_loop().run_in_executor(
            None, self.redis_client.decr, key
        )

    def _increment_concurrent_memory(self, user_id: str) -> int:
        """Increment concurrent counter in memory."""
        self.memory_store[user_id]["concurrent"] += 1
        return self.memory_store[user_id]["concurrent"]

    def _decrement_concurrent_memory(self, user_id: str):
        """Decrement concurrent counter in memory."""
        if self.memory_store[user_id]["concurrent"] > 0:
            self.memory_store[user_id]["concurrent"] -= 1


class SuspiciousActivityDetector:
    """Detect suspicious usage patterns."""

    def __init__(self, store: RateLimitStore, config: RateLimitConfig):
        self.store = store
        self.config = config
        self.alerts = deque(maxlen=100)

    async def analyze_request(self, user_id: str, metrics: RequestMetrics) -> List[str]:
        """Analyze request for suspicious patterns."""
        alerts = []

        # Get recent metrics
        if self.store.use_redis:
            recent_metrics = await self._get_recent_metrics_redis(user_id)
        else:
            recent_metrics = self._get_recent_metrics_memory(user_id)

        # Check for rapid requests
        if await self._check_rapid_requests(recent_metrics):
            alerts.append("rapid_requests")

        # Check for unusual hours
        if self._check_unusual_hours(metrics.timestamp):
            alerts.append("unusual_hours")

        # Check for multiple IPs
        if await self._check_multiple_ips(recent_metrics):
            alerts.append("multiple_ips")

        # Check error rate
        if await self._check_error_rate(recent_metrics):
            alerts.append("high_error_rate")

        # Check endpoint abuse
        if await self._check_endpoint_abuse(recent_metrics, metrics.endpoint):
            alerts.append("endpoint_abuse")

        # Log alerts
        if alerts:
            self._log_suspicious_activity(user_id, metrics, alerts)

        return alerts

    async def _get_recent_metrics_redis(self, user_id: str) -> List[RequestMetrics]:
        """Get recent metrics from Redis."""
        metrics_key = f"metrics:{user_id}"
        try:
            raw_metrics = await asyncio.get_event_loop().run_in_executor(
                None, self.store.redis_client.lrange, metrics_key, 0, 100
            )

            metrics = []
            for raw in raw_metrics:
                data = json.loads(raw)
                metrics.append(
                    RequestMetrics(
                        user_id=user_id,
                        ip_address=data["ip"],
                        endpoint=data["endpoint"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        response_code=data["response_code"],
                        processing_time=data["processing_time"],
                    )
                )
            return metrics
        except Exception as e:
            logger.error(f"Error getting metrics from Redis: {e}")
            return []

    def _get_recent_metrics_memory(self, user_id: str) -> List[RequestMetrics]:
        """Get recent metrics from memory."""
        return list(self.store.memory_store[user_id]["metrics"])

    async def _check_rapid_requests(self, metrics: List[RequestMetrics]) -> bool:
        """Check for rapid request patterns."""
        if len(metrics) < self.config.SUSPICIOUS_PATTERNS["rapid_requests"]:
            return False

        # Check if we have more than threshold requests in last minute
        now = datetime.now()
        recent = [m for m in metrics if (now - m.timestamp).total_seconds() < 60]

        return len(recent) > self.config.SUSPICIOUS_PATTERNS["rapid_requests"]

    def _check_unusual_hours(self, timestamp: datetime) -> bool:
        """Check if request is during unusual hours (2-6 AM)."""
        if not self.config.SUSPICIOUS_PATTERNS["unusual_hours"]:
            return False

        hour = timestamp.hour
        return 2 <= hour <= 6

    async def _check_multiple_ips(self, metrics: List[RequestMetrics]) -> bool:
        """Check for requests from multiple IPs."""
        if len(metrics) < 10:  # Need some requests to analyze
            return False

        # Get IPs from last hour
        now = datetime.now()
        recent = [m for m in metrics if (now - m.timestamp).total_seconds() < 3600]

        unique_ips = set(m.ip_address for m in recent)
        return len(unique_ips) > self.config.SUSPICIOUS_PATTERNS["multiple_ips"]

    async def _check_error_rate(self, metrics: List[RequestMetrics]) -> bool:
        """Check for high error rates."""
        if len(metrics) < 10:
            return False

        # Calculate error rate for recent requests
        now = datetime.now()
        recent = [
            m for m in metrics if (now - m.timestamp).total_seconds() < 300
        ]  # Last 5 minutes

        if not recent:
            return False

        error_count = sum(1 for m in recent if m.response_code >= 400)
        error_rate = error_count / len(recent)

        return error_rate > self.config.SUSPICIOUS_PATTERNS["error_rate"]

    async def _check_endpoint_abuse(
        self, metrics: List[RequestMetrics], endpoint: str
    ) -> bool:
        """Check for endpoint abuse."""
        if len(metrics) < 10:
            return False

        # Count requests to same endpoint in last minute
        now = datetime.now()
        recent_same_endpoint = [
            m
            for m in metrics
            if m.endpoint == endpoint and (now - m.timestamp).total_seconds() < 60
        ]

        return (
            len(recent_same_endpoint)
            > self.config.SUSPICIOUS_PATTERNS["endpoint_abuse"]
        )

    def _log_suspicious_activity(
        self, user_id: str, metrics: RequestMetrics, alerts: List[str]
    ):
        """Log suspicious activity."""
        alert_data = {
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "ip_address": metrics.ip_address,
            "endpoint": metrics.endpoint,
            "alerts": alerts,
        }

        self.alerts.append(alert_data)

        logger.warning(
            f"Suspicious activity detected for user {user_id}: {
                ', '.join(alerts)}",
            extra=alert_data,
        )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Main rate limiting middleware."""

    def __init__(self, app, config: RateLimitConfig = None):
        super().__init__(app)
        self.config = config or RateLimitConfig()
        self.store = RateLimitStore()
        self.detector = SuspiciousActivityDetector(self.store, self.config)

        # Excluded paths (no rate limiting)
        self.excluded_paths = {"/docs", "/redoc", "/openapi.json", "/health"}

        logger.info("Rate limit middleware initialized")

    async def dispatch(self, request: Request, call_next):
        """Main middleware dispatch method."""
        # Skip rate limiting for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Extract user information
        user_id, user_tier = await self._get_user_info(request)

        # Get client IP
        client_ip = self._get_client_ip(request)

        # Check rate limits
        rate_limit_result = await self._check_rate_limits(user_id, user_tier)
        if rate_limit_result:
            return rate_limit_result

        # Increment concurrent counter
        concurrent_count = await self.store.increment_concurrent(user_id)

        # Check concurrent limit
        if concurrent_count > user_tier.concurrent_requests:
            await self.store.decrement_concurrent(user_id)
            return self._create_rate_limit_response(
                "Too many concurrent requests", user_tier.concurrent_requests
            )

        try:
            # Process request
            start_time = time.time()
            response = await call_next(request)
            processing_time = time.time() - start_time

            # Record metrics
            metrics = RequestMetrics(
                user_id=user_id,
                ip_address=client_ip,
                endpoint=request.url.path,
                timestamp=datetime.now(),
                response_code=response.status_code,
                processing_time=processing_time,
            )

            await self.store.record_request(user_id, metrics)

            # Check for suspicious activity
            await self.detector.analyze_request(user_id, metrics)

            # Add rate limit headers
            self._add_rate_limit_headers(response, user_id, user_tier)

            return response

        except Exception as e:
            logger.error(f"Error in rate limit middleware: {e}")
            raise
        finally:
            # Always decrement concurrent counter
            await self.store.decrement_concurrent(user_id)

    async def _get_user_info(self, request: Request) -> Tuple[str, UserTier]:
        """Extract user ID and tier from request."""
        # Try to get user from JWT token
        try:
            if hasattr(request.state, "user") and request.state.user:
                user = request.state.user
                user_id = user.get("user_id", user.get("id", "anonymous"))
                tier_name = user.get("tier", "free")
            else:
                # Try to get from Authorization header
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    # For demo purposes, extract user info from token
                    # In production, this would decode the JWT
                    user_id = self._extract_user_from_token(auth_header)
                    tier_name = "free"  # Default tier
                else:
                    user_id = "anonymous"
                    tier_name = "free"
        except Exception:
            user_id = "anonymous"
            tier_name = "free"

        # Get user tier configuration
        tier_map = {
            "free": self.config.FREE_TIER,
            "premium": self.config.PREMIUM_TIER,
            "enterprise": self.config.ENTERPRISE_TIER,
        }

        user_tier = tier_map.get(tier_name, self.config.FREE_TIER)

        return user_id, user_tier

    def _extract_user_from_token(self, auth_header: str) -> str:
        """Extract user ID from JWT token (simplified for demo)."""
        try:
            # In production, this would properly decode the JWT
            # For now, create a hash-based user ID
            token = auth_header.replace("Bearer ", "")
            return hashlib.md5(token.encode()).hexdigest()[:12]
        except Exception:
            return "anonymous"

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address."""
        # Check for forwarded headers first
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"

    async def _check_rate_limits(
        self, user_id: str, user_tier: UserTier
    ) -> Optional[JSONResponse]:
        """Check if user has exceeded rate limits."""
        counts = await self.store.get_request_counts(user_id)

        # Check different time windows
        if counts["minute"] >= user_tier.requests_per_minute:
            return self._create_rate_limit_response(
                "Rate limit exceeded for requests per minute",
                user_tier.requests_per_minute,
                reset_time=60,
            )

        if counts["hour"] >= user_tier.requests_per_hour:
            return self._create_rate_limit_response(
                "Rate limit exceeded for requests per hour",
                user_tier.requests_per_hour,
                reset_time=3600,
            )

        if counts["day"] >= user_tier.requests_per_day:
            return self._create_rate_limit_response(
                "Rate limit exceeded for requests per day",
                user_tier.requests_per_day,
                reset_time=86400,
            )

        return None

    def _create_rate_limit_response(
        self, message: str, limit: int, reset_time: int = 60
    ) -> JSONResponse:
        """Create rate limit exceeded response."""
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": message,
                "limit": limit,
                "reset_in_seconds": reset_time,
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + reset_time),
                "Retry-After": str(reset_time),
            },
        )

    def _add_rate_limit_headers(self, response, user_id: str, user_tier: UserTier):
        """Add rate limit headers to response."""
        # These would be calculated based on current usage
        # For simplicity, showing basic implementation
        response.headers["X-RateLimit-Limit-Minute"] = str(
            user_tier.requests_per_minute
        )
        response.headers["X-RateLimit-Limit-Hour"] = str(user_tier.requests_per_hour)
        response.headers["X-RateLimit-Limit-Day"] = str(user_tier.requests_per_day)
        response.headers["X-RateLimit-Tier"] = user_tier.name
