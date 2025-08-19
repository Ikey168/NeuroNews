"""
DynamoDB integration for storing failed URLs and managing retry attempts.
Tracks failed scraping attempts and implements intelligent retry logic.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

import boto3


@dataclass
class FailedUrl:
    """Data class for failed URL tracking."""

    url: str
    failure_reason: str
    first_failure_time: float
    last_failure_time: float
    retry_count: int = 0
    max_retries: int = 3
    next_retry_time: float = 0.0
    error_details: Optional[str] = None
    proxy_used: Optional[str] = None
    user_agent_used: Optional[str] = None
    response_code: Optional[int] = None
    is_permanent_failure: bool = False

    def to_dynamodb_item(self) -> Dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "url": {"S": self.url},
            "failure_reason": {"S": self.failure_reason},
            "first_failure_time": {"N": str(self.first_failure_time)},
            "last_failure_time": {"N": str(self.last_failure_time)},
            "retry_count": {"N": str(self.retry_count)},
            "max_retries": {"N": str(self.max_retries)},
            "next_retry_time": {"N": str(self.next_retry_time)},
            "error_details": {"S": self.error_details or ""},
            "proxy_used": {"S": self.proxy_used or ""},
            "user_agent_used": {"S": self.user_agent_used or ""},
            "response_code": {"N": str(self.response_code or 0)},
            "is_permanent_failure": {"BOOL": self.is_permanent_failure},
        }

    @classmethod
    def from_dynamodb_item(cls, item: Dict[str, Any]) -> "FailedUrl":
        """Create from DynamoDB item format."""
        return cls(
            url=item["url"]["S"],
            failure_reason=item["failure_reason"]["S"],
            first_failure_time=float(item["first_failure_time"]["N"]),
            last_failure_time=float(item["last_failure_time"]["N"]),
            retry_count=int(item["retry_count"]["N"]),
            max_retries=int(item["max_retries"]["N"]),
            next_retry_time=float(item["next_retry_time"]["N"]),
            error_details=item.get("error_details", {}).get("S", ""),
            proxy_used=item.get("proxy_used", {}).get("S", ""),
            user_agent_used=item.get("user_agent_used", {}).get("S", ""),
            response_code=int(item.get("response_code", {}).get("N", "0")),
            is_permanent_failure=item.get("is_permanent_failure", {}).get(
                "BOOL", False
            ),
        )


class RetryStrategy(Enum):
    """Retry strategy types."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_INTERVAL = "fixed_interval"


class DynamoDBFailureManager:
    """DynamoDB integration for managing failed URLs and retry logic."""

    def __init__(
        self,
        table_name: str = "neuronews-failed-urls",
        region_name: str = "us-east-1",
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
    ):
        """
        Initialize DynamoDB failure manager.

        Args:
            table_name: DynamoDB table name for storing failed URLs
            region_name: AWS region for DynamoDB
            retry_strategy: Strategy for calculating retry delays
        """
        self.table_name = table_name
        self.region_name = region_name
        self.retry_strategy = retry_strategy

        # Initialize DynamoDB client
        self.dynamodb = boto3.client("dynamodb", region_name=region_name)

        # Setup logging
        self.logger = logging.getLogger(__name__)

        # Retry configuration
        self.base_retry_delay = 300  # 5 minutes
        self.max_retry_delay = 86400  # 24 hours
        self.max_retries = 5

        # Ensure table exists
        self._ensure_table_exists()

    def _ensure_table_exists(self):
        """Create DynamoDB table if it doesn't exist."""
        try:
            # Check if table exists
            self.dynamodb.describe_table(TableName=self.table_name)
            self.logger.debug(f"DynamoDB table exists: {self.table_name}")
        except self.dynamodb.exceptions.ResourceNotFoundException:
            # Create table
            self._create_table()
        except Exception as e:
            self.logger.error(f"Error checking table existence: {e}")

    def _create_table(self):
        """Create DynamoDB table for failed URLs."""
        try:
            self.dynamodb.create_table(
                TableName=self.table_name,
                KeySchema=[{"AttributeName": "url", "KeyType": "HASH"}],
                AttributeDefinitions=[
                    {"AttributeName": "url", "AttributeType": "S"},
                    {"AttributeName": "next_retry_time", "AttributeType": "N"},
                ],
                GlobalSecondaryIndexes=[
                    {
                        "IndexName": "retry-time-index",
                        "KeySchema": [
                            {"AttributeName": "next_retry_time", "KeyType": "HASH"}
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                        "BillingMode": "PAY_PER_REQUEST",
                    }
                ],
                BillingMode="PAY_PER_REQUEST",
            )

            # Wait for table to be created
            waiter = self.dynamodb.get_waiter("table_exists")
            waiter.wait(TableName=self.table_name)

            self.logger.info(f"Created DynamoDB table: {self.table_name}")

        except Exception as e:
            self.logger.error(f"Error creating DynamoDB table: {e}")

    async def record_failure(
        self,
        url: str,
        failure_reason: str,
        error_details: Optional[str] = None,
        proxy_used: Optional[str] = None,
        user_agent_used: Optional[str] = None,
        response_code: Optional[int] = None,
    ) -> FailedUrl:
        """
        Record a failed URL attempt.

        Args:
            url: The URL that failed
            failure_reason: Reason for failure
            error_details: Detailed error message
            proxy_used: Proxy that was used
            user_agent_used: User agent that was used
            response_code: HTTP response code

        Returns:
            FailedUrl object
        """
        current_time = time.time()

        try:
            # Check if URL already exists in table
            response = self.dynamodb.get_item(
                TableName=self.table_name, Key={"url": {"S": url}}
            )

            if "Item" in response:
                # Update existing record
                failed_url = FailedUrl.from_dynamodb_item(response["Item"])
                failed_url.last_failure_time = current_time
                failed_url.retry_count += 1
                failed_url.error_details = error_details
                failed_url.proxy_used = proxy_used
                failed_url.user_agent_used = user_agent_used
                failed_url.response_code = response_code

                # Check if we've exceeded max retries
                if failed_url.retry_count >= failed_url.max_retries:
                    failed_url.is_permanent_failure = True
                    failed_url.next_retry_time = 0  # No more retries
                else:
                    # Calculate next retry time
                    failed_url.next_retry_time = self._calculate_next_retry_time(
                        failed_url.retry_count
                    )
            else:
                # Create new record
                failed_url = FailedUrl(
                    url=url,
                    failure_reason=failure_reason,
                    first_failure_time=current_time,
                    last_failure_time=current_time,
                    retry_count=1,
                    max_retries=self.max_retries,
                    next_retry_time=self._calculate_next_retry_time(1),
                    error_details=error_details,
                    proxy_used=proxy_used,
                    user_agent_used=user_agent_used,
                    response_code=response_code,
                )

            # Store in DynamoDB
            self.dynamodb.put_item(
                TableName=self.table_name, Item=failed_url.to_dynamodb_item()
            )

            self.logger.info(
                f"Recorded failure for URL: {url} (attempt {failed_url.retry_count})"
            )
            return failed_url

        except Exception as e:
            self.logger.error(f"Error recording failure: {e}")
            # Return a basic failed URL object even if storage fails
            return FailedUrl(
                url=url,
                failure_reason=failure_reason,
                first_failure_time=current_time,
                last_failure_time=current_time,
                error_details=error_details,
            )

    def _calculate_next_retry_time(self, retry_count: int) -> float:
        """
        Calculate next retry time based on retry strategy.

        Args:
            retry_count: Current retry attempt number

        Returns:
            Unix timestamp for next retry
        """
        current_time = time.time()

        if self.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            # Exponential backoff: 5min, 10min, 20min, 40min, 80min...
            delay = min(
                self.base_retry_delay * (2 ** (retry_count - 1)), self.max_retry_delay
            )
        elif self.retry_strategy == RetryStrategy.LINEAR_BACKOFF:
            # Linear backoff: 5min, 10min, 15min, 20min, 25min...
            delay = min(self.base_retry_delay * retry_count, self.max_retry_delay)
        else:  # FIXED_INTERVAL
            # Fixed interval: 5min, 5min, 5min, 5min...
            delay = self.base_retry_delay

        return current_time + delay

    async def get_urls_ready_for_retry(self, limit: int = 50) -> List[FailedUrl]:
        """
        Get URLs that are ready for retry attempts.

        Args:
            limit: Maximum number of URLs to return

        Returns:
            List of FailedUrl objects ready for retry
        """
        try:
            current_time = time.time()

            # Query using GSI to find URLs ready for retry
            response = self.dynamodb.scan(
                TableName=self.table_name,
                FilterExpression="next_retry_time <= :current_time AND is_permanent_failure = :false",
                ExpressionAttributeValues={
                    ":current_time": {"N": str(current_time)},
                    ":false": {"BOOL": False},
                },
                Limit=limit,
            )

            failed_urls = []
            for item in response.get("Items", []):
                failed_url = FailedUrl.from_dynamodb_item(item)
                failed_urls.append(failed_url)

            self.logger.info(f"Found {len(failed_urls)} URLs ready for retry")
            return failed_urls

        except Exception as e:
            self.logger.error(f"Error getting URLs for retry: {e}")
            return []

    async def mark_success(self, url: str):
        """
        Mark a URL as successfully scraped and remove from failed table.

        Args:
            url: URL that was successfully scraped
        """
        try:
            self.dynamodb.delete_item(
                TableName=self.table_name, Key={"url": {"S": url}}
            )
            self.logger.info(f"Removed successfully scraped URL: {url}")

        except Exception as e:
            self.logger.error(f"Error marking success: {e}")

    async def mark_permanent_failure(self, url: str):
        """
        Mark a URL as permanently failed (no more retries).

        Args:
            url: URL to mark as permanently failed
        """
        try:
            self.dynamodb.update_item(
                TableName=self.table_name,
                Key={"url": {"S": url}},
                UpdateExpression="SET is_permanent_failure = :true, next_retry_time = :zero",
                ExpressionAttributeValues={
                    ":true": {"BOOL": True},
                    ":zero": {"N": "0"},
                },
            )
            self.logger.info(f"Marked URL as permanent failure: {url}")

        except Exception as e:
            self.logger.error(f"Error marking permanent failure: {e}")

    async def get_failure_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get failure statistics for the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            Dictionary with failure statistics
        """
        try:
            cutoff_time = time.time() - (hours * 3600)

            response = self.dynamodb.scan(
                TableName=self.table_name,
                FilterExpression="last_failure_time >= :cutoff_time",
                ExpressionAttributeValues={":cutoff_time": {"N": str(cutoff_time)}},
            )

            items = response.get("Items", [])

            # Calculate statistics
            total_failures = len(items)
            permanent_failures = sum(
                1
                for item in items
                if item.get("is_permanent_failure", {}).get("BOOL", False)
            )
            pending_retries = sum(
                1
                for item in items
                if not item.get("is_permanent_failure", {}).get("BOOL", False)
            )

            # Group by failure reason
            failure_reasons = {}
            for item in items:
                reason = item["failure_reason"]["S"]
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

            # Group by response code
            response_codes = {}
            for item in items:
                code = int(item.get("response_code", {}).get("N", "0"))
                if code > 0:
                    response_codes[code] = response_codes.get(code, 0) + 1

            return {
                "total_failures": total_failures,
                "permanent_failures": permanent_failures,
                "pending_retries": pending_retries,
                "failure_reasons": failure_reasons,
                "response_codes": response_codes,
                "time_period_hours": hours,
            }

        except Exception as e:
            self.logger.error(f"Error getting failure statistics: {e}")
            return {}

    async def cleanup_old_failures(self, days: int = 30):
        """
        Clean up old failure records to prevent table from growing indefinitely.

        Args:
            days: Number of days to keep records
        """
        try:
            cutoff_time = time.time() - (days * 24 * 3600)

            # Scan for old records
            response = self.dynamodb.scan(
                TableName=self.table_name,
                FilterExpression="first_failure_time < :cutoff_time",
                ExpressionAttributeValues={":cutoff_time": {"N": str(cutoff_time)}},
            )

            # Delete old records
            deleted_count = 0
            for item in response.get("Items", []):
                url = item["url"]["S"]
                self.dynamodb.delete_item(
                    TableName=self.table_name, Key={"url": {"S": url}}
                )
                deleted_count += 1

            self.logger.info(f"Cleaned up {deleted_count} old failure records")

        except Exception as e:
            self.logger.error(f"Error cleaning up old failures: {e}")

    async def get_failed_url_details(self, url: str) -> Optional[FailedUrl]:
        """
        Get details for a specific failed URL.

        Args:
            url: URL to get details for

        Returns:
            FailedUrl object or None if not found
        """
        try:
            response = self.dynamodb.get_item(
                TableName=self.table_name, Key={"url": {"S": url}}
            )

            if "Item" in response:
                return FailedUrl.from_dynamodb_item(response["Item"])
            else:
                return None

        except Exception as e:
            self.logger.error(f"Error getting failed URL details: {e}")
            return None
