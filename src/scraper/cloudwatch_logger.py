"""
CloudWatch monitoring integration for NeuroNews scraper.
Tracks execution success/failure rates, performance metrics, and sends alerts.
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

import boto3


class ScrapingStatus(Enum):
    """Enumeration for scraping status types."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    CAPTCHA_BLOCKED = "captcha_blocked"
    IP_BLOCKED = "ip_blocked"


@dataclass
class ScrapingMetrics:
    """Data class for scraping execution metrics."""

    url: str
    status: ScrapingStatus
    timestamp: float
    duration_ms: int
    articles_scraped: int = 0
    error_message: Optional[str] = None
    retry_count: int = 0
    proxy_used: Optional[str] = None
    user_agent: Optional[str] = None
    response_code: Optional[int] = None
    captcha_encountered: bool = False
    ip_blocked: bool = False


class CloudWatchLogger:
    """CloudWatch integration for scraper monitoring and alerting."""

    def __init__(
        self,
        region_name: str = "us-east-1",
        namespace: str = "NeuroNews/Scraper",
        log_group: str = "/aws/lambda/neuronews-scraper",
    ):
        """
        Initialize CloudWatch logger.

        Args:
            region_name: AWS region for CloudWatch
            namespace: CloudWatch namespace for metrics
            log_group: CloudWatch log group name
        """
        self.region_name = region_name
        self.namespace = namespace
        self.log_group = log_group

        # Initialize AWS clients
        self.cloudwatch = boto3.client("cloudwatch", region_name=region_name)
        self.logs_client = boto3.client("logs", region_name=region_name)

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Metrics buffer for batch sending
        self.metrics_buffer: List[ScrapingMetrics] = []
        self.buffer_size = 10

        # Ensure log group exists
        self._ensure_log_group_exists()

    def _ensure_log_group_exists(self):
        """Create CloudWatch log group if it doesn't exist."""
        try:
            self.logs_client.create_log_group(logGroupName=self.log_group)
            self.logger.info(f"Created CloudWatch log group: {self.log_group}")
        except self.logs_client.exceptions.ResourceAlreadyExistsException:
            self.logger.debug(f"Log group already exists: {self.log_group}")
        except Exception as e:
            self.logger.error(f"Error creating log group: {e}")

    async def log_scraping_attempt(self, metrics: ScrapingMetrics):
        """
        Log a scraping attempt with detailed metrics.

        Args:
            metrics: ScrapingMetrics object with execution details
        """
        # Add to buffer
        self.metrics_buffer.append(metrics)

        # Send to CloudWatch Logs
        await self._send_log_entry(metrics)

        # Send metrics to CloudWatch
        await self._send_cloudwatch_metrics(metrics)

        # Check if buffer is full and send batch metrics
        if len(self.metrics_buffer) >= self.buffer_size:
            await self._send_batch_metrics()
            self.metrics_buffer.clear()

    async def _send_log_entry(self, metrics: ScrapingMetrics):
        """Send detailed log entry to CloudWatch Logs."""
        try:
            log_entry = {
                "timestamp": datetime.fromtimestamp(
                    metrics.timestamp, tz=timezone.utc
                ).isoformat(),
                "url": metrics.url,
                "status": metrics.status.value,
                "duration_ms": metrics.duration_ms,
                "articles_scraped": metrics.articles_scraped,
                "retry_count": metrics.retry_count,
                "proxy_used": metrics.proxy_used,
                "response_code": metrics.response_code,
                "captcha_encountered": metrics.captcha_encountered,
                "ip_blocked": metrics.ip_blocked,
                "error_message": metrics.error_message,
            }

            # Create log stream name with date
            log_stream = f"scraper-{datetime.now().strftime('%Y-%m-%d')}"

            # Ensure log stream exists
            try:
                self.logs_client.create_log_stream(
                    logGroupName=self.log_group, logStreamName=log_stream
                )
            except self.logs_client.exceptions.ResourceAlreadyExistsException:
                pass

            # Send log event
            self.logs_client.put_log_events(
                logGroupName=self.log_group,
                logStreamName=log_stream,
                logEvents=[
                    {
                        "timestamp": int(metrics.timestamp * 1000),
                        "message": json.dumps(log_entry),
                    }
                ],
            )

        except Exception as e:
            self.logger.error(f"Error sending log entry to CloudWatch: {e}")

    async def _send_cloudwatch_metrics(self, metrics: ScrapingMetrics):
        """Send metrics to CloudWatch for monitoring and alerting."""
        try:
            metric_data = []

            # Success/Failure metric
            metric_data.append(
                {
                    "MetricName": "ScrapingAttempts",
                    "Dimensions": [
                        {"Name": "Status", "Value": metrics.status.value},
                        {
                            "Name": "URL",
                            "Value": self._get_domain_from_url(metrics.url),
                        },
                    ],
                    "Value": 1,
                    "Unit": "Count",
                    "Timestamp": datetime.fromtimestamp(
                        metrics.timestamp, tz=timezone.utc
                    ),
                }
            )

            # Duration metric
            metric_data.append(
                {
                    "MetricName": "ScrapingDuration",
                    "Dimensions": [
                        {"Name": "URL", "Value": self._get_domain_from_url(metrics.url)}
                    ],
                    "Value": metrics.duration_ms,
                    "Unit": "Milliseconds",
                    "Timestamp": datetime.fromtimestamp(
                        metrics.timestamp, tz=timezone.utc
                    ),
                }
            )

            # Articles scraped metric
            if metrics.articles_scraped > 0:
                metric_data.append(
                    {
                        "MetricName": "ArticlesScraped",
                        "Dimensions": [
                            {
                                "Name": "URL",
                                "Value": self._get_domain_from_url(metrics.url),
                            }
                        ],
                        "Value": metrics.articles_scraped,
                        "Unit": "Count",
                        "Timestamp": datetime.fromtimestamp(
                            metrics.timestamp, tz=timezone.utc
                        ),
                    }
                )

            # Retry count metric
            if metrics.retry_count > 0:
                metric_data.append(
                    {
                        "MetricName": "RetryCount",
                        "Dimensions": [
                            {
                                "Name": "URL",
                                "Value": self._get_domain_from_url(metrics.url),
                            }
                        ],
                        "Value": metrics.retry_count,
                        "Unit": "Count",
                        "Timestamp": datetime.fromtimestamp(
                            metrics.timestamp, tz=timezone.utc
                        ),
                    }
                )

            # CAPTCHA encounters
            if metrics.captcha_encountered:
                metric_data.append(
                    {
                        "MetricName": "CaptchaEncounters",
                        "Dimensions": [
                            {
                                "Name": "URL",
                                "Value": self._get_domain_from_url(metrics.url),
                            }
                        ],
                        "Value": 1,
                        "Unit": "Count",
                        "Timestamp": datetime.fromtimestamp(
                            metrics.timestamp, tz=timezone.utc
                        ),
                    }
                )

            # IP blocks
            if metrics.ip_blocked:
                metric_data.append(
                    {
                        "MetricName": "IPBlocks",
                        "Dimensions": [
                            {
                                "Name": "URL",
                                "Value": self._get_domain_from_url(metrics.url),
                            }
                        ],
                        "Value": 1,
                        "Unit": "Count",
                        "Timestamp": datetime.fromtimestamp(
                            metrics.timestamp, tz=timezone.utc
                        ),
                    }
                )

            # Send metrics to CloudWatch
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace, MetricData=metric_data
            )

        except Exception as e:
            self.logger.error(f"Error sending metrics to CloudWatch: {e}")

    async def _send_batch_metrics(self):
        """Send aggregated metrics from buffer."""
        if not self.metrics_buffer:
            return

        try:
            # Calculate aggregate metrics
            total_attempts = len(self.metrics_buffer)
            successful_attempts = sum(
                1 for m in self.metrics_buffer if m.status == ScrapingStatus.SUCCESS
            )
            total_attempts - successful_attempts
            avg_duration = (
                sum(m.duration_ms for m in self.metrics_buffer) / total_attempts
            )
            total_articles = sum(m.articles_scraped for m in self.metrics_buffer)

            # Success rate metric
            success_rate = (successful_attempts / total_attempts) * 100

            metric_data = [
                {
                    "MetricName": "SuccessRate",
                    "Value": success_rate,
                    "Unit": "Percent",
                    "Timestamp": datetime.now(tz=timezone.utc),
                },
                {
                    "MetricName": "AverageDuration",
                    "Value": avg_duration,
                    "Unit": "Milliseconds",
                    "Timestamp": datetime.now(tz=timezone.utc),
                },
                {
                    "MetricName": "TotalArticlesScraped",
                    "Value": total_articles,
                    "Unit": "Count",
                    "Timestamp": datetime.now(tz=timezone.utc),
                },
            ]

            self.cloudwatch.put_metric_data(
                Namespace=self.namespace, MetricData=metric_data
            )

        except Exception as e:
            self.logger.error(f"Error sending batch metrics: {e}")

    def _get_domain_from_url(self, url: str) -> str:
        """Extract domain from URL for grouping metrics."""
        try:
            from urllib.parse import urlparse

            return urlparse(url).netloc
        except Exception:
            return "unknown"

    async def get_success_rate(self, hours: int = 24) -> float:
        """
        Get success rate for the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Success rate as percentage
        """
        try:
            end_time = datetime.now(tz=timezone.utc)
            start_time = end_time.replace(hour=end_time.hour - hours)

            # Query CloudWatch for success rate
            response = self.cloudwatch.get_metric_statistics(
                Namespace=self.namespace,
                MetricName="SuccessRate",
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,  # 1 hour periods
                Statistics=["Average"],
            )

            if response["Datapoints"]:
                # Return average success rate
                return sum(dp["Average"] for dp in response["Datapoints"]) / len(
                    response["Datapoints"]
                )
            else:
                return 0.0

        except Exception as e:
            self.logger.error(f"Error getting success rate: {e}")
            return 0.0

    async def get_failure_count(self, hours: int = 1) -> int:
        """
        Get failure count for the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Number of failures
        """
        try:
            end_time = datetime.now(tz=timezone.utc)
            start_time = end_time.replace(hour=end_time.hour - hours)

            response = self.cloudwatch.get_metric_statistics(
                Namespace=self.namespace,
                MetricName="ScrapingAttempts",
                Dimensions=[{"Name": "Status", "Value": "failure"}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=["Sum"],
            )

            if response["Datapoints"]:
                return int(sum(dp["Sum"] for dp in response["Datapoints"]))
            else:
                return 0

        except Exception as e:
            self.logger.error(f"Error getting failure count: {e}")
            return 0

    async def create_alarm(
        self,
        alarm_name: str,
        metric_name: str,
        threshold: float,
        comparison_operator: str = "GreaterThanThreshold",
        sns_topic_arn: Optional[str] = None,
    ):
        """
        Create CloudWatch alarm for monitoring.

        Args:
            alarm_name: Name of the alarm
            metric_name: CloudWatch metric to monitor
            threshold: Threshold value for alarm
            comparison_operator: Comparison operator for threshold
            sns_topic_arn: SNS topic ARN for notifications
        """
        try:
            alarm_actions = [sns_topic_arn] if sns_topic_arn else []

            self.cloudwatch.put_metric_alarm(
                AlarmName=alarm_name,
                ComparisonOperator=comparison_operator,
                EvaluationPeriods=2,
                MetricName=metric_name,
                Namespace=self.namespace,
                Period=300,  # 5 minutes
                Statistic="Average",
                Threshold=threshold,
                ActionsEnabled=True,
                AlarmActions=alarm_actions,
                AlarmDescription=f"Alarm for {metric_name} in NeuroNews scraper",
                Unit="Count",
            )

            self.logger.info(f"Created CloudWatch alarm: {alarm_name}")

        except Exception as e:
            self.logger.error(f"Error creating alarm: {e}")

    async def flush_metrics(self):
        """Flush any remaining metrics in buffer."""
        if self.metrics_buffer:
            await self._send_batch_metrics()
            self.metrics_buffer.clear()
