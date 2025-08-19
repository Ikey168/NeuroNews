"""
Suspicious Usage Pattern Monitoring Service (Issue #59)

Advanced monitoring and analysis of API usage patterns to detect abuse
and suspicious activities.
"""

import asyncio
import json
import logging
import re
import statistics
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SuspiciousPatternType(Enum):
    """Types of suspicious patterns."""

    RAPID_REQUESTS = "rapid_requests"
    UNUSUAL_HOURS = "unusual_hours"
    MULTIPLE_IPS = "multiple_ips"
    HIGH_ERROR_RATE = "high_error_rate"
    ENDPOINT_ABUSE = "endpoint_abuse"
    BOT_BEHAVIOR = "bot_behavior"
    CREDENTIAL_STUFFING = "credential_stuffing"
    DATA_SCRAPING = "data_scraping"
    DDOS_PATTERN = "ddos_pattern"
    UNUSUAL_USER_AGENT = "unusual_user_agent"


@dataclass
class SuspiciousActivity:
    """Represents a detected suspicious activity."""

    user_id: str
    pattern_type: SuspiciousPatternType
    alert_level: AlertLevel
    timestamp: datetime
    details: Dict[str, Any]
    ip_addresses: List[str]
    endpoints_accessed: List[str]
    request_count: int
    confidence_score: float  # 0.0 - 1.0


@dataclass
class UserBehaviorProfile:
    """Profile of a user's normal behavior patterns."""

    user_id: str
    typical_hours: List[int] = field(
        default_factory=list
    )  # Hours they usually access API
    typical_endpoints: Dict[str, int] = field(
        default_factory=dict
    )  # Endpoint usage frequency
    average_requests_per_hour: float = 0.0
    typical_ip_addresses: List[str] = field(default_factory=list)
    user_agent_patterns: List[str] = field(default_factory=list)
    last_updated: datetime = field(default_factory=datetime.now)


class AdvancedSuspiciousActivityDetector:
    """Advanced detector for sophisticated suspicious activity patterns."""

    def __init__(self):
        self.user_profiles: Dict[str, UserBehaviorProfile] = {}
        self.active_alerts: deque = deque(maxlen=1000)
        self.pattern_matchers = self._initialize_pattern_matchers()
        self.ml_threshold = 0.7  # Machine learning confidence threshold

        # Suspicious patterns configuration
        self.config = {
            "rapid_requests_threshold": 50,
            "unusual_hours_range": (2, 6),  # 2 AM - 6 AM
            "multiple_ip_threshold": 5,
            "error_rate_threshold": 0.5,
            "endpoint_abuse_threshold": 20,
            "bot_user_agents": [
                "bot",
                "crawler",
                "spider",
                "scraper",
                "curl",
                "wget",
                "automated",
                "headless",
                "phantom",
                "selenium",
            ],
        }

        logger.info("Advanced suspicious activity detector initialized")

    def _initialize_pattern_matchers(self) -> Dict[str, callable]:
        """Initialize pattern matching functions."""
        return {
            SuspiciousPatternType.RAPID_REQUESTS: self._detect_rapid_requests,
            SuspiciousPatternType.UNUSUAL_HOURS: self._detect_unusual_hours,
            SuspiciousPatternType.MULTIPLE_IPS: self._detect_multiple_ips,
            SuspiciousPatternType.HIGH_ERROR_RATE: self._detect_high_error_rate,
            SuspiciousPatternType.ENDPOINT_ABUSE: self._detect_endpoint_abuse,
            SuspiciousPatternType.BOT_BEHAVIOR: self._detect_bot_behavior,
            SuspiciousPatternType.CREDENTIAL_STUFFING: self._detect_credential_stuffing,
            SuspiciousPatternType.DATA_SCRAPING: self._detect_data_scraping,
            SuspiciousPatternType.DDOS_PATTERN: self._detect_ddos_pattern,
            SuspiciousPatternType.UNUSUAL_USER_AGENT: self._detect_unusual_user_agent,
        }

    async def analyze_user_activity(
        self, user_id: str, recent_requests: List[Dict]
    ) -> List[SuspiciousActivity]:
        """Analyze user activity for suspicious patterns."""
        if not recent_requests:
            return []

        suspicious_activities = []

        # Update user profile
        await self._update_user_profile(user_id, recent_requests)

        # Run all pattern detectors
        for pattern_type, detector_func in self.pattern_matchers.items():
            try:
                activity = await detector_func(user_id, recent_requests)
                if activity:
                    suspicious_activities.append(activity)
            except Exception as e:
                logger.error(f"Error in pattern detector {pattern_type}: {e}")

        # Store alerts
        for activity in suspicious_activities:
            self.active_alerts.append(activity)
            await self._log_suspicious_activity(activity)

        return suspicious_activities

    async def _update_user_profile(self, user_id: str, requests: List[Dict]):
        """Update user behavior profile based on recent activity."""
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = UserBehaviorProfile(user_id=user_id)

        profile = self.user_profiles[user_id]

        # Update typical hours
        hours = [req.get("timestamp", datetime.now()).hour for req in requests]
        profile.typical_hours = list(set(profile.typical_hours + hours))[
            -24:
        ]  # Keep last 24 unique hours

        # Update typical endpoints
        for req in requests:
            endpoint = req.get("endpoint", "")
            profile.typical_endpoints[endpoint] = (
                profile.typical_endpoints.get(endpoint, 0) + 1
            )

        # Calculate average requests per hour
        if len(requests) > 0:
            time_span = max(
                1,
                (
                    max(req.get("timestamp", datetime.now()) for req in requests)
                    - min(req.get("timestamp", datetime.now()) for req in requests)
                ).total_seconds()
                / 3600,
            )
            profile.average_requests_per_hour = len(requests) / time_span

        # Update IP addresses
        ips = [req.get("ip_address", "") for req in requests if req.get("ip_address")]
        profile.typical_ip_addresses = list(set(profile.typical_ip_addresses + ips))[
            -10:
        ]  # Keep last 10 IPs

        # Update user agents
        user_agents = [
            req.get("user_agent", "") for req in requests if req.get("user_agent")
        ]
        profile.user_agent_patterns = list(
            set(profile.user_agent_patterns + user_agents)
        )[
            -5:
        ]  # Keep last 5

        profile.last_updated = datetime.now()

    async def _detect_rapid_requests(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect rapid request patterns."""
        if len(requests) < self.config["rapid_requests_threshold"]:
            return None

        # Check requests in last minute
        now = datetime.now()
        recent_requests = [
            req
            for req in requests
            if (now - req.get("timestamp", now)).total_seconds() < 60
        ]

        if len(recent_requests) >= self.config["rapid_requests_threshold"]:
            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.RAPID_REQUESTS,
                alert_level=AlertLevel.HIGH,
                timestamp=now,
                details={
                    "requests_in_minute": len(recent_requests),
                    "threshold": self.config["rapid_requests_threshold"],
                },
                ip_addresses=list(
                    set(req.get("ip_address", "") for req in recent_requests)
                ),
                endpoints_accessed=list(
                    set(req.get("endpoint", "") for req in recent_requests)
                ),
                request_count=len(recent_requests),
                confidence_score=min(
                    1.0, len(recent_requests) / self.config["rapid_requests_threshold"]
                ),
            )

        return None

    async def _detect_unusual_hours(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect access during unusual hours."""
        profile = self.user_profiles.get(user_id)
        if not profile or len(profile.typical_hours) < 5:  # Need enough data
            return None

        unusual_requests = []
        start_hour, end_hour = self.config["unusual_hours_range"]

        for req in requests:
            hour = req.get("timestamp", datetime.now()).hour

            # Check if hour is unusual for this user AND in suspicious range
            if hour not in profile.typical_hours and start_hour <= hour <= end_hour:
                unusual_requests.append(req)

        if len(unusual_requests) > 5:  # More than 5 requests in unusual hours
            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.UNUSUAL_HOURS,
                alert_level=AlertLevel.MEDIUM,
                timestamp=datetime.now(),
                details={
                    "unusual_requests": len(unusual_requests),
                    "hours_accessed": list(
                        set(
                            req.get("timestamp", datetime.now()).hour
                            for req in unusual_requests
                        )
                    ),
                    "typical_hours": profile.typical_hours,
                },
                ip_addresses=list(
                    set(req.get("ip_address", "") for req in unusual_requests)
                ),
                endpoints_accessed=list(
                    set(req.get("endpoint", "") for req in unusual_requests)
                ),
                request_count=len(unusual_requests),
                confidence_score=0.6,
            )

        return None

    async def _detect_multiple_ips(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect access from multiple IP addresses."""
        # Get IPs from last hour
        now = datetime.now()
        recent_requests = [
            req
            for req in requests
            if (now - req.get("timestamp", now)).total_seconds() < 3600
        ]

        ips = set(
            req.get("ip_address", "")
            for req in recent_requests
            if req.get("ip_address")
        )
        ips.discard("")  # Remove empty strings

        if len(ips) >= self.config["multiple_ip_threshold"]:
            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.MULTIPLE_IPS,
                alert_level=AlertLevel.HIGH,
                timestamp=now,
                details={
                    "unique_ips": len(ips),
                    "threshold": self.config["multiple_ip_threshold"],
                    "time_window": "1 hour",
                },
                ip_addresses=list(ips),
                endpoints_accessed=list(
                    set(req.get("endpoint", "") for req in recent_requests)
                ),
                request_count=len(recent_requests),
                confidence_score=min(
                    1.0, len(ips) / (self.config["multiple_ip_threshold"] * 2)
                ),
            )

        return None

    async def _detect_high_error_rate(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect high error rates."""
        if len(requests) < 10:  # Need minimum requests to analyze
            return None

        # Calculate error rate for recent requests
        now = datetime.now()
        recent_requests = [
            req
            for req in requests
            if (now - req.get("timestamp", now)).total_seconds() < 300  # Last 5 minutes
        ]

        if not recent_requests:
            return None

        error_count = sum(
            1 for req in recent_requests if req.get("response_code", 200) >= 400
        )
        error_rate = error_count / len(recent_requests)

        if error_rate >= self.config["error_rate_threshold"]:
            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.HIGH_ERROR_RATE,
                alert_level=AlertLevel.MEDIUM,
                timestamp=now,
                details={
                    "error_rate": error_rate,
                    "error_count": error_count,
                    "total_requests": len(recent_requests),
                    "threshold": self.config["error_rate_threshold"],
                },
                ip_addresses=list(
                    set(req.get("ip_address", "") for req in recent_requests)
                ),
                endpoints_accessed=list(
                    set(req.get("endpoint", "") for req in recent_requests)
                ),
                request_count=len(recent_requests),
                confidence_score=error_rate,
            )

        return None

    async def _detect_endpoint_abuse(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect abuse of specific endpoints."""
        # Group requests by endpoint
        endpoint_counts = defaultdict(int)
        now = datetime.now()

        # Count requests to each endpoint in last minute
        for req in requests:
            if (now - req.get("timestamp", now)).total_seconds() < 60:
                endpoint_counts[req.get("endpoint", "")] += 1

        # Find abused endpoints
        abused_endpoints = [
            endpoint
            for endpoint, count in endpoint_counts.items()
            if count >= self.config["endpoint_abuse_threshold"]
        ]

        if abused_endpoints:
            total_abuse_requests = sum(
                endpoint_counts[endpoint] for endpoint in abused_endpoints
            )

            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.ENDPOINT_ABUSE,
                alert_level=AlertLevel.HIGH,
                timestamp=now,
                details={
                    "abused_endpoints": abused_endpoints,
                    "requests_per_endpoint": {
                        ep: endpoint_counts[ep] for ep in abused_endpoints
                    },
                    "threshold": self.config["endpoint_abuse_threshold"],
                },
                ip_addresses=list(
                    set(req.get("ip_address", "") for req in requests[-50:])
                ),
                endpoints_accessed=abused_endpoints,
                request_count=total_abuse_requests,
                confidence_score=min(
                    1.0,
                    total_abuse_requests
                    / (self.config["endpoint_abuse_threshold"] * 2),
                ),
            )

        return None

    async def _detect_bot_behavior(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect bot-like behavior patterns."""
        if len(requests) < 20:
            return None

        # Check for bot indicators
        bot_indicators = 0
        total_indicators = 0

        # 1. Regular timing patterns
        timestamps = [req.get("timestamp", datetime.now()) for req in requests[-20:]]
        intervals = []
        for i in range(1, len(timestamps)):
            interval = (timestamps[i] - timestamps[i - 1]).total_seconds()
            intervals.append(interval)

        if len(intervals) > 5:
            # Check if intervals are very regular (low variance)
            if statistics.stdev(intervals) < 1.0:  # Very regular timing
                bot_indicators += 1
            total_indicators += 1

        # 2. User agent analysis
        user_agents = [req.get("user_agent", "") for req in requests[-10:]]
        for ua in user_agents:
            if any(
                bot_term in ua.lower() for bot_term in self.config["bot_user_agents"]
            ):
                bot_indicators += 1
                break
        total_indicators += 1

        # 3. Sequential endpoint access
        endpoints = [req.get("endpoint", "") for req in requests[-10:]]
        if len(set(endpoints)) == 1 and len(endpoints) > 5:  # Same endpoint repeatedly
            bot_indicators += 1
        total_indicators += 1

        # 4. No variation in request patterns
        if len(requests) > 10:
            recent_ips = set(req.get("ip_address", "") for req in requests[-10:])
            if len(recent_ips) == 1:  # Always same IP
                bot_indicators += 1
            total_indicators += 1

        confidence = bot_indicators / total_indicators if total_indicators > 0 else 0

        if confidence >= 0.6:  # 60% confidence threshold
            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.BOT_BEHAVIOR,
                alert_level=AlertLevel.HIGH,
                timestamp=datetime.now(),
                details={
                    "bot_indicators": bot_indicators,
                    "total_indicators": total_indicators,
                    "confidence": confidence,
                    "patterns_detected": {
                        "regular_timing": len(intervals) > 5
                        and statistics.stdev(intervals) < 1.0,
                        "bot_user_agent": any(
                            bot_term in ua.lower()
                            for ua in user_agents
                            for bot_term in self.config["bot_user_agents"]
                        ),
                        "sequential_access": len(set(endpoints)) == 1
                        and len(endpoints) > 5,
                    },
                },
                ip_addresses=list(
                    set(req.get("ip_address", "") for req in requests[-20:])
                ),
                endpoints_accessed=list(
                    set(req.get("endpoint", "") for req in requests[-20:])
                ),
                request_count=len(requests),
                confidence_score=confidence,
            )

        return None

    async def _detect_credential_stuffing(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect credential stuffing attacks."""
        # Look for multiple failed login attempts
        auth_requests = [
            req
            for req in requests
            if "/auth/" in req.get("endpoint", "")
            and req.get("response_code", 200) == 401
        ]

        if len(auth_requests) >= 10:  # 10+ failed login attempts
            now = datetime.now()
            recent_auth_failures = [
                req
                for req in auth_requests
                if (now - req.get("timestamp", now)).total_seconds()
                < 300  # Last 5 minutes
            ]

            if len(recent_auth_failures) >= 5:
                return SuspiciousActivity(
                    user_id=user_id,
                    pattern_type=SuspiciousPatternType.CREDENTIAL_STUFFING,
                    alert_level=AlertLevel.CRITICAL,
                    timestamp=now,
                    details={
                        "failed_attempts": len(recent_auth_failures),
                        "time_window": "5 minutes",
                        "total_auth_failures": len(auth_requests),
                    },
                    ip_addresses=list(
                        set(req.get("ip_address", "") for req in recent_auth_failures)
                    ),
                    endpoints_accessed=list(
                        set(req.get("endpoint", "") for req in recent_auth_failures)
                    ),
                    request_count=len(recent_auth_failures),
                    confidence_score=min(1.0, len(recent_auth_failures) / 10),
                )

        return None

    async def _detect_data_scraping(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect data scraping patterns."""
        profile = self.user_profiles.get(user_id)
        if not profile:
            return None

        # Check for systematic endpoint access
        recent_requests = requests[-50:] if len(requests) >= 50 else requests

        # Look for patterns indicating systematic data access
        data_endpoints = [
            req
            for req in recent_requests
            if any(
                pattern in req.get("endpoint", "")
                for pattern in ["/articles", "/news", "/graph", "/entities"]
            )
        ]

        if len(data_endpoints) >= 30:  # High volume of data requests
            # Check if this is unusual for the user
            typical_data_requests = sum(
                count
                for endpoint, count in profile.typical_endpoints.items()
                if any(
                    pattern in endpoint
                    for pattern in ["/articles", "/news", "/graph", "/entities"]
                )
            )

            current_rate = len(data_endpoints)
            if current_rate > typical_data_requests * 3:  # 3x normal rate
                return SuspiciousActivity(
                    user_id=user_id,
                    pattern_type=SuspiciousPatternType.DATA_SCRAPING,
                    alert_level=AlertLevel.HIGH,
                    timestamp=datetime.now(),
                    details={
                        "data_requests": len(data_endpoints),
                        "typical_requests": typical_data_requests,
                        "rate_multiplier": current_rate / max(1, typical_data_requests),
                    },
                    ip_addresses=list(
                        set(req.get("ip_address", "") for req in data_endpoints)
                    ),
                    endpoints_accessed=list(
                        set(req.get("endpoint", "") for req in data_endpoints)
                    ),
                    request_count=len(data_endpoints),
                    confidence_score=min(
                        1.0, current_rate / (typical_data_requests * 5)
                    ),
                )

        return None

    async def _detect_ddos_pattern(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect distributed denial of service patterns."""
        # Look for high-volume, low-processing requests
        now = datetime.now()
        recent_requests = [
            req
            for req in requests
            if (now - req.get("timestamp", now)).total_seconds() < 60  # Last minute
        ]

        if len(recent_requests) >= 100:  # Very high volume
            # Check if requests are simple/fast (potential DDoS)
            fast_requests = [
                req
                for req in recent_requests
                if req.get("processing_time", 1.0) < 0.1  # Very fast processing
            ]

            if len(fast_requests) / len(recent_requests) > 0.8:  # 80% fast requests
                return SuspiciousActivity(
                    user_id=user_id,
                    pattern_type=SuspiciousPatternType.DDOS_PATTERN,
                    alert_level=AlertLevel.CRITICAL,
                    timestamp=now,
                    details={
                        "total_requests": len(recent_requests),
                        "fast_requests": len(fast_requests),
                        "fast_request_ratio": len(fast_requests) / len(recent_requests),
                        "time_window": "1 minute",
                    },
                    ip_addresses=list(
                        set(req.get("ip_address", "") for req in recent_requests)
                    ),
                    endpoints_accessed=list(
                        set(req.get("endpoint", "") for req in recent_requests)
                    ),
                    request_count=len(recent_requests),
                    confidence_score=0.9,
                )

        return None

    async def _detect_unusual_user_agent(
        self, user_id: str, requests: List[Dict]
    ) -> Optional[SuspiciousActivity]:
        """Detect unusual or suspicious user agents."""
        profile = self.user_profiles.get(user_id)
        if not profile:
            return None

        recent_user_agents = [req.get("user_agent", "") for req in requests[-10:]]
        unusual_agents = []

        for ua in recent_user_agents:
            if ua and ua not in profile.user_agent_patterns:
                # Check for suspicious patterns
                suspicious_terms = [
                    "bot",
                    "crawler",
                    "scraper",
                    "hack",
                    "test",
                    "curl",
                    "wget",
                ]
                if any(term in ua.lower() for term in suspicious_terms):
                    unusual_agents.append(ua)

        if unusual_agents:
            return SuspiciousActivity(
                user_id=user_id,
                pattern_type=SuspiciousPatternType.UNUSUAL_USER_AGENT,
                alert_level=AlertLevel.MEDIUM,
                timestamp=datetime.now(),
                details={
                    "unusual_user_agents": unusual_agents,
                    "typical_user_agents": profile.user_agent_patterns,
                },
                ip_addresses=list(
                    set(req.get("ip_address", "") for req in requests[-10:])
                ),
                endpoints_accessed=list(
                    set(req.get("endpoint", "") for req in requests[-10:])
                ),
                request_count=len(requests[-10:]),
                confidence_score=0.5,
            )

        return None

    async def _log_suspicious_activity(self, activity: SuspiciousActivity):
        """Log suspicious activity for monitoring."""
        log_data = {
            "user_id": activity.user_id,
            "pattern_type": activity.pattern_type.value,
            "alert_level": activity.alert_level.value,
            "timestamp": activity.timestamp.isoformat(),
            "confidence_score": activity.confidence_score,
            "request_count": activity.request_count,
            "ip_addresses": activity.ip_addresses,
            "endpoints_accessed": activity.endpoints_accessed,
            "details": activity.details,
        }

        if activity.alert_level in [AlertLevel.HIGH, AlertLevel.CRITICAL]:
            logger.warning(
                f"Suspicious activity detected: {activity.pattern_type.value}",
                extra=log_data,
            )
        else:
            logger.info(
                f"Potential suspicious activity: {activity.pattern_type.value}",
                extra=log_data,
            )

    def get_user_risk_score(self, user_id: str) -> float:
        """Calculate overall risk score for a user based on recent activities."""
        user_alerts = [
            alert
            for alert in self.active_alerts
            if alert.user_id == user_id
            and (datetime.now() - alert.timestamp).total_seconds() < 3600  # Last hour
        ]

        if not user_alerts:
            return 0.0

        # Weight by alert level
        level_weights = {
            AlertLevel.LOW: 0.2,
            AlertLevel.MEDIUM: 0.5,
            AlertLevel.HIGH: 0.8,
            AlertLevel.CRITICAL: 1.0,
        }

        total_score = sum(
            alert.confidence_score * level_weights[alert.alert_level]
            for alert in user_alerts
        )

        # Normalize to 0-1 range
        return min(1.0, total_score / len(user_alerts))

    def get_recent_alerts(
        self, hours: int = 24, min_alert_level: AlertLevel = AlertLevel.LOW
    ) -> List[SuspiciousActivity]:
        """Get recent suspicious activity alerts."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        return [
            alert
            for alert in self.active_alerts
            if alert.timestamp > cutoff_time
            and alert.alert_level.value >= min_alert_level.value
        ]
