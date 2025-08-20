"""
SNS integration for sending alerts when scrapers fail multiple times.
Provides intelligent alerting with rate limiting and escalation.
"""

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import boto3


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class AlertType(Enum):
    """Types of alerts."""

    SCRAPER_FAILURE = "scraper_failure"
    HIGH_FAILURE_RATE = "high_failure_rate"
    CAPTCHA_BLOCKING = "captcha_blocking"
    IP_BLOCKING = "ip_blocking"
    SYSTEM_ERROR = "system_error"
    PERFORMANCE_DEGRADATION = "performance_degradation"


@dataclass
class Alert:
    """Data class for alert information."""

    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    timestamp: float
    metadata: Dict[str, Any]

    def to_sns_message(self) -> str:
        """Convert alert to SNS message format."""
        alert_data = {
            "timestamp": datetime.fromtimestamp(
                self.timestamp, tz=timezone.utc
            ).isoformat(),
            "severity": self.severity.value,
            "alert_type": self.alert_type.value,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
        }
        return json.dumps(alert_data, indent=2)


class SNSAlertManager:
    """SNS integration for scraper failure alerts and notifications."""

    def __init__(
        self,
        topic_arn: str,
        region_name: str = "us-east-1",
        rate_limit_window: int = 3600,
        max_alerts_per_window: int = 10,
    ):
        """
        Initialize SNS alert manager.

        Args:
            topic_arn: SNS topic ARN for sending alerts
            region_name: AWS region for SNS
            rate_limit_window: Time window for rate limiting (seconds)
            max_alerts_per_window: Maximum alerts per window
        """
        self.topic_arn = topic_arn
        self.region_name = region_name
        self.rate_limit_window = rate_limit_window
        self.max_alerts_per_window = max_alerts_per_window

        # Initialize SNS client
        self.sns = boto3.client("sns", region_name=region_name)

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Rate limiting tracking
        self.alert_history: List[float] = []
        self.muted_until: float = 0.0

        # Alert thresholds
        self.failure_rate_threshold = 50.0  # 50% failure rate
        self.consecutive_failure_threshold = 5
        self.response_time_threshold = 30000  # 30 seconds

    async def send_alert(self, alert: Alert, force: bool = False) -> bool:
        """
        Send an alert via SNS with rate limiting.

        Args:
            alert: Alert object to send
            force: Force send even if rate limited

        Returns:
            True if alert was sent, False if rate limited
        """
        current_time = time.time()

        # Check if we're in a mute period
        if current_time < self.muted_until and not force:
            self.logger.debug("Alert muted due to rate limiting")
            return False

        # Check rate limiting
        if not force and not self._is_within_rate_limit():
            # Mute alerts for the next hour if we've exceeded the limit
            self.muted_until = current_time + self.rate_limit_window
            self.logger.warning("Alert rate limit exceeded, muting alerts for 1 hour")

            # Send a rate limit notification
            await self._send_rate_limit_notification()
            return False

        try:
            # Prepare SNS message
            subject = "[{0}] NeuroNews Scraper Alert: {1}".format(alert.severity.value, alert.title)
            message = alert.to_sns_message()

            # Add message attributes for filtering
            message_attributes = {
                "severity": {"DataType": "String", "StringValue": alert.severity.value},
                "alert_type": {
                    "DataType": "String",
                    "StringValue": alert.alert_type.value,
                },
                "timestamp": {
                    "DataType": "Number",
                    "StringValue": str(alert.timestamp),
                },
            }

            # Send to SNS
            response = self.sns.publish(
                TopicArn=self.topic_arn,
                Subject=subject,
                Message=message,
                MessageAttributes=message_attributes,
            )

            # Track alert for rate limiting
            self.alert_history.append(current_time)
            self._cleanup_old_alerts()

            self.logger.info(
                "Sent alert: {0} (MessageId: {1})".format(
                    alert.title, response['MessageId']
                ])
            )
            return True

        except Exception as e:
            self.logger.error("Error sending alert: {0}".format(e))
            return False

    def _is_within_rate_limit(self) -> bool:
        """Check if we're within the rate limit."""
        current_time = time.time()
        cutoff_time = current_time - self.rate_limit_window

        # Count alerts in the current window
        recent_alerts = [t for t in self.alert_history if t > cutoff_time]
        return len(recent_alerts) < self.max_alerts_per_window

    def _cleanup_old_alerts(self):
        """Remove old alerts from history to prevent memory growth."""
        current_time = time.time()
        cutoff_time = current_time - self.rate_limit_window
        self.alert_history = [t for t in self.alert_history if t > cutoff_time]

    async def _send_rate_limit_notification(self):
        """Send a notification that alerts are being rate limited."""
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.WARNING,
            title="Alert Rate Limit Exceeded",
            message="Too many alerts have been sent in a short period. Alerts will be muted for 1 hour.",
            timestamp=time.time(),
            metadata={
                "rate_limit_window": self.rate_limit_window,
                "max_alerts_per_window": self.max_alerts_per_window,
            },
        )

        # Send without rate limiting
        try:
            subject = "[{0}] NeuroNews Scraper Alert: {1}".format(alert.severity.value, alert.title)
            message = alert.to_sns_message()

            self.sns.publish(TopicArn=self.topic_arn, Subject=subject, Message=message)
        except Exception as e:
            self.logger.error("Error sending rate limit notification: {0}".format(e))

    async def alert_scraper_failure(
        self,
        url: str,
        failure_reason: str,
        retry_count: int = 0,
        error_details: Optional[str] = None,
    ):
        """
        Send alert for scraper failure.

        Args:
            url: URL that failed
            failure_reason: Reason for failure
            retry_count: Number of retry attempts
            error_details: Detailed error information
        """
        # Determine severity based on retry count
        if retry_count >= self.consecutive_failure_threshold:
            severity = AlertSeverity.ERROR
        elif retry_count >= 2:
            severity = AlertSeverity.WARNING
        else:
            severity = AlertSeverity.INFO

        alert = Alert(
            alert_type=AlertType.SCRAPER_FAILURE,
            severity=severity,
            title="Scraper Failure - {0} Attempts".format(retry_count + 1),
            message="Failed to scrape URL: {0}\nReason: {1}\nRetry Count: {2}".format(url, failure_reason, retry_count),
            timestamp=time.time(),
            metadata={
                "url": url,
                "failure_reason": failure_reason,
                "retry_count": retry_count,
                "error_details": error_details,
            },
        )

        await self.send_alert(alert)

    async def alert_high_failure_rate(
        self, failure_rate: float, time_period: int, failed_count: int, total_count: int
    ):
        """
        Send alert for high failure rate.

        Args:
            failure_rate: Failure rate percentage
            time_period: Time period in hours
            failed_count: Number of failed attempts
            total_count: Total number of attempts
        """
        severity = AlertSeverity.CRITICAL if failure_rate >= 80 else AlertSeverity.ERROR

        alert = Alert(
            alert_type=AlertType.HIGH_FAILURE_RATE,
            severity=severity,
            title="High Failure Rate Detected: {0:.1f}%".format(failure_rate),
            message="Scraper failure rate is {0:.1f}% over the last {1} hours.\n".format(failure_rate, time_period)
            "Failed: {0}/{1} attempts".format(failed_count, total_count),
            timestamp=time.time(),
            metadata={
                "failure_rate": failure_rate,
                "time_period_hours": time_period,
                "failed_count": failed_count,
                "total_count": total_count,
            },
        )

        await self.send_alert(alert)

    async def alert_captcha_blocking(
        self, url: str, captcha_count: int, time_period: int
    ):
        """
        Send alert for CAPTCHA blocking issues.

        Args:
            url: URL experiencing CAPTCHA issues
            captcha_count: Number of CAPTCHA encounters
            time_period: Time period in hours
        """
        alert = Alert(
            alert_type=AlertType.CAPTCHA_BLOCKING,
            severity=AlertSeverity.WARNING,
            title="Frequent CAPTCHA Encounters",
            message="Encountered {0} CAPTCHAs for {1} in the last {2} hours.\n".format(captcha_count, url, time_period)
            "This may indicate detection by anti-bot systems.",
            timestamp=time.time(),
            metadata={
                "url": url,
                "captcha_count": captcha_count,
                "time_period_hours": time_period,
            },
        )

        await self.send_alert(alert)

    async def alert_ip_blocking(
        self, url: str, blocked_ips: List[str], time_period: int
    ):
        """
        Send alert for IP blocking issues.

        Args:
            url: URL experiencing IP blocking
            blocked_ips: List of blocked IP addresses
            time_period: Time period in hours
        """
        alert = Alert(
            alert_type=AlertType.IP_BLOCKING,
            severity=AlertSeverity.ERROR,
            title="IP Blocking Detected",
            message="Multiple IPs blocked for {0} in the last {1} hours.\nBlocked IPs: {2}{3}".format(url, time_period, ', '.join(blocked_ips[:5]]), '...' if len(blocked_ips) > 5 else ''
            ),
            timestamp=time.time(),
            metadata={
                "url": url,
                "blocked_ips": blocked_ips,
                "time_period_hours": time_period,
            },
        )

        await self.send_alert(alert)

    async def alert_performance_degradation(
        self, avg_response_time: float, threshold: float, time_period: int
    ):
        """
        Send alert for performance degradation.

        Args:
            avg_response_time: Average response time in milliseconds
            threshold: Response time threshold
            time_period: Time period in hours
        """
        alert = Alert(
            alert_type=AlertType.PERFORMANCE_DEGRADATION,
            severity=AlertSeverity.WARNING,
            title="Performance Degradation Detected",
            message="Average response time ({0:.0f}ms) exceeds threshold ({1:.0f}ms) ".format(avg_response_time, threshold)
            "over the last {0} hours.".format(time_period),
            timestamp=time.time(),
            metadata={
                "avg_response_time_ms": avg_response_time,
                "threshold_ms": threshold,
                "time_period_hours": time_period,
            },
        )

        await self.send_alert(alert)

    async def alert_system_error(
        self, error_type: str, error_message: str, component: str
    ):
        """
        Send alert for system errors.

        Args:
            error_type: Type of error
            error_message: Error message
            component: Component that experienced the error
        """
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.ERROR,
            title="System Error in {0}".format(component),
            message="Error Type: {0}\nMessage: {1}\nComponent: {2}".format(error_type, error_message, component),
            timestamp=time.time(),
            metadata={
                "error_type": error_type,
                "error_message": error_message,
                "component": component,
            },
        )

        await self.send_alert(alert)

    async def test_alert_system(self):
        """Send a test alert to verify the system is working."""
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.INFO,
            title="Test Alert",
            message="This is a test alert to verify the SNS alert system is working properly.",
            timestamp=time.time(),
            metadata={"test": True},
        )

        return await self.send_alert(alert, force=True)

    def set_failure_rate_threshold(self, threshold: float):
        """Set the failure rate threshold for alerts."""
        self.failure_rate_threshold = threshold
        self.logger.info("Set failure rate threshold to {0}%".format(threshold))

    def set_consecutive_failure_threshold(self, threshold: int):
        """Set the consecutive failure threshold for alerts."""
        self.consecutive_failure_threshold = threshold
        self.logger.info("Set consecutive failure threshold to {0}".format(threshold))

    def set_response_time_threshold(self, threshold: float):
        """Set the response time threshold for alerts."""
        self.response_time_threshold = threshold
        self.logger.info("Set response time threshold to {0}ms".format(threshold))
