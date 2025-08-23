"""
AWS API Gateway Rate Limiting Integration (Issue #59)

Provides configuration and utilities for integrating with AWS API Gateway
throttling and usage plans.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import boto3

logger = logging.getLogger(__name__)


@dataclass
class APIGatewayUsagePlan:
    """Configuration for AWS API Gateway usage plans."""

    plan_id: str
    name: str
    description: str
    throttle_burst_limit: int
    throttle_rate_limit: float
    quota_limit: int
    quota_period: str  # DAY, WEEK, MONTH


@dataclass
class APIGatewayConfiguration:
    """AWS API Gateway configuration for rate limiting."""

    # Usage Plans for different tiers
    FREE_PLAN = APIGatewayUsagePlan(
        plan_id="free-tier-plan",
        name="Free Tier",
        description="Free tier with basic rate limits",
        throttle_burst_limit=15,
        throttle_rate_limit=0.17,  # ~10 requests per minute
        quota_limit=1000,
        quota_period="DAY",
    )

    PREMIUM_PLAN = APIGatewayUsagePlan(
        plan_id="premium-tier-plan",
        name="Premium Tier",
        description="Premium tier with enhanced rate limits",
        throttle_burst_limit=150,
        throttle_rate_limit=1.67,  # ~100 requests per minute
        quota_limit=20000,
        quota_period="DAY",
    )

    ENTERPRISE_PLAN = APIGatewayUsagePlan(
        plan_id="enterprise-tier-plan",
        name="Enterprise Tier",
        description="Enterprise tier with high rate limits",
        throttle_burst_limit=1500,
        throttle_rate_limit=16.67,  # ~1000 requests per minute
        quota_limit=500000,
        quota_period="DAY",
    )


class APIGatewayManager:
    """Manager for AWS API Gateway rate limiting operations."""

    def __init__(self, region: str = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.api_id = os.getenv("API_GATEWAY_ID")
        self.stage_name = os.getenv("API_GATEWAY_STAGE", "prod")

        try:
            self.client = boto3.client("apigateway", region_name=self.region)
            self.usage_client = boto3.client(
                "apigatewaymanagementapi", region_name=self.region
            )
            logger.info(
                "AWS API Gateway client initialized for region {0}".format(self.region)
            )
        except Exception as e:
            logger.error("Failed to initialize AWS API Gateway client: {0}".format(e))
            self.client = None
            self.usage_client = None

    async def create_usage_plans(self) -> Dict[str, str]:
        """Create usage plans for different user tiers."""
        if not self.client:
            logger.error("API Gateway client not available")
            return {}

        config = APIGatewayConfiguration()
        plans = [config.FREE_PLAN, config.PREMIUM_PLAN, config.ENTERPRISE_PLAN]
        created_plans = {}

        for plan in plans:
            try:
                response = self.client.create_usage_plan(
                    name=plan.name,
                    description=plan.description,
                    throttle={
                        "burstLimit": plan.throttle_burst_limit,
                        "rateLimit": plan.throttle_rate_limit,
                    },
                    quota={"limit": plan.quota_limit, "period": plan.quota_period},
                )

                plan_id = response["id"]
                created_plans[plan.name.lower().replace(" ", "_")] = plan_id

                # Associate with API stage
                if self.api_id:
                    self.client.create_usage_plan_key(
                        usagePlanId=plan_id, keyId=self.api_id, keyType="API_KEY"
                    )

                logger.info(
                    "Created usage plan: {0} (ID: {1})".format(plan.name, plan_id)
                )

            except Exception as e:
                logger.error(
                    "Failed to create usage plan {0}: {1}".format(plan.name, e)
                )

        return created_plans

    async def assign_user_to_plan(self, user_id: str, tier: str, api_key: str) -> bool:
        """Assign a user to a specific usage plan."""
        if not self.client:
            return False

        plan_mapping = {
            "free": "free_tier",
            "premium": "premium_tier",
            "enterprise": "enterprise_tier",
        }

        plan_name = plan_mapping.get(tier)
        if not plan_name:
            logger.error("Unknown tier: {0}".format(tier))
            return False

        try:
            # Get usage plan ID (in production, this would be cached/stored)
            usage_plans = await self.get_usage_plans()
            plan_id = usage_plans.get(plan_name)

            if not plan_id:
                logger.error("Usage plan not found for tier: {0}".format(tier))
                return False

            # Create or get API key for user
            key_id = await self.create_api_key_for_user(user_id, api_key)

            if not key_id:
                return False

            # Associate key with usage plan
            self.client.create_usage_plan_key(
                usagePlanId=plan_id, keyId=key_id, keyType="API_KEY"
            )

            logger.info(
                "Assigned user {0} to {1} tier (plan: {2})".format(
                    user_id, tier, plan_id
                )
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to assign user {0} to plan {1}: {2}".format(user_id, tier, e)
            )
            return False

    async def create_api_key_for_user(
        self, user_id: str, api_key_value: str
    ) -> Optional[str]:
        """Create an API key for a user."""
        if not self.client:
            return None

        try:
            response = self.client.create_api_key(
                name="neuronews-user-{0}".format(user_id),
                description="API key for NeuroNews user {0}".format(user_id),
                enabled=True,
                value=api_key_value,
                tags={
                    "user_id": user_id,
                    "service": "neuronews",
                    "created": datetime.now().isoformat(),
                },
            )

            key_id = response["id"]
            logger.info("Created API key for user {0}: {1}".format(user_id, key_id))
            return key_id

        except Exception as e:
            logger.error(
                "Failed to create API key for user {0}: {1}".format(user_id, e)
            )
            return None

    async def get_usage_plans(self) -> Dict[str, str]:
        """Get existing usage plans."""
        if not self.client:
            return {}

        try:
            response = self.client.get_usage_plans()
            plans = {}

            for plan in response["items"]:
                plan_name = plan["name"].lower().replace(" ", "_")
                plans[plan_name] = plan["id"]

            return plans

        except Exception as e:
            logger.error("Failed to get usage plans: {0}".format(e))
            return {}

    async def get_usage_statistics(
        self, user_api_key: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Get usage statistics for a user's API key."""
        if not self.client:
            return {}

        try:
            # Get API key ID from value
            api_keys = self.client.get_api_keys()
            key_id = None

            for key in api_keys["items"]:
                if key.get("value") == user_api_key:
                    key_id = key["id"]
                    break

            if not key_id:
                logger.error("API key not found: {0}".format(user_api_key))
                return {}

            # Get usage data
            response = self.client.get_usage(
                usagePlanId=key_id, startDate=start_date, endDate=end_date
            )

            return {
                "period": "{0} to {1}".format(start_date, end_date),
                "total_requests": (
                    sum(response["values"].values()) if "values" in response else 0
                ),
                "daily_breakdown": response.get("values", {}),
                "position": response.get("position"),
                "start_date": response.get("startDate"),
                "end_date": response.get("endDate"),
            }

        except Exception as e:
            logger.error("Failed to get usage statistics: {0}".format(e))
            return {}

    async def update_user_tier(
        self, user_id: str, old_tier: str, new_tier: str
    ) -> bool:
        """Update a user's tier by moving them to a different usage plan."""
        if not self.client:
            return False

        try:
            # Get user's current API key
            api_keys = self.client.get_api_keys()
            user_key = None

            for key in api_keys["items"]:
                if key.get("tags", {}).get("user_id") == user_id:
                    user_key = key
                    break

            if not user_key:
                logger.error("API key not found for user: {0}".format(user_id))
                return False

            # Remove from old usage plan
            old_plans = await self.get_usage_plans()
            old_plan_id = old_plans.get("{0}_tier".format(old_tier))

            if old_plan_id:
                try:
                    self.client.delete_usage_plan_key(
                        usagePlanId=old_plan_id, keyId=user_key["id"]
                    )
                except Exception as e:
                    logger.warning("Could not remove from old plan: {0}".format(e))

            # Add to new usage plan
            return await self.assign_user_to_plan(user_id, new_tier, user_key["value"])

        except Exception as e:
            logger.error("Failed to update user tier: {0}".format(e))
            return False

    async def monitor_throttling_events(self) -> List[Dict[str, Any]]:
        """Monitor API Gateway throttling events."""
        if not self.client:
            return []

        try:
            # In production, this would integrate with CloudWatch
            # For now, return a mock implementation
            return [
                {
                    "timestamp": datetime.now().isoformat(),
                    "api_id": self.api_id,
                    "stage": self.stage_name,
                    "throttled_requests": 0,
                    "total_requests": 0,
                    "throttle_rate": 0.0,
                }
            ]

        except Exception as e:
            logger.error("Failed to monitor throttling events: {0}".format(e))
            return []


class CloudWatchMetrics:
    """CloudWatch metrics integration for rate limiting monitoring."""

    def __init__(self, region: str = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")

        try:
            self.cloudwatch = boto3.client("cloudwatch", region_name=self.region)
            logger.info("CloudWatch client initialized")
        except Exception as e:
            logger.error("Failed to initialize CloudWatch client: {0}".format(e))
            self.cloudwatch = None

    async def put_rate_limit_metrics(
        self, user_id: str, tier: str, requests_count: int, violations: int
    ):
        """Send rate limiting metrics to CloudWatch."""
        if not self.cloudwatch:
            return

        try:
            self.cloudwatch.put_metric_data(
                Namespace="NeuroNews/RateLimiting",
                MetricData=[
                    {
                        "MetricName": "RequestCount",
                        "Dimensions": [
                            {"Name": "UserId", "Value": user_id},
                            {"Name": "Tier", "Value": tier},
                        ],
                        "Value": requests_count,
                        "Unit": "Count",
                        "Timestamp": datetime.now(),
                    },
                    {
                        "MetricName": "RateLimitViolations",
                        "Dimensions": [
                            {"Name": "UserId", "Value": user_id},
                            {"Name": "Tier", "Value": tier},
                        ],
                        "Value": violations,
                        "Unit": "Count",
                        "Timestamp": datetime.now(),
                    },
                ],
            )

            logger.debug("Sent metrics to CloudWatch for user {0}".format(user_id))

        except Exception as e:
            logger.error("Failed to send metrics to CloudWatch: {0}".format(e))

    async def create_rate_limit_alarms(self):
        """Create CloudWatch alarms for rate limiting violations."""
        if not self.cloudwatch:
            return

        try:
            # Alarm for high rate limit violations
            self.cloudwatch.put_metric_alarm(
                AlarmName="NeuroNews-HighRateLimitViolations",
                ComparisonOperator="GreaterThanThreshold",
                EvaluationPeriods=2,
                MetricName="RateLimitViolations",
                Namespace="NeuroNews/RateLimiting",
                Period=300,  # 5 minutes
                Statistic="Sum",
                Threshold=100.0,
                ActionsEnabled=True,
                AlarmActions=[
                    os.getenv(
                        "SNS_ALERT_TOPIC",
                        "arn:aws:sns:us-east-1:123456789012:neuronews-alerts",
                    )
                ],
                AlarmDescription="High rate limit violations detected",
                Dimensions=[],
                Unit="Count",
            )

            logger.info("Created CloudWatch alarms for rate limiting")

        except Exception as e:
            logger.error("Failed to create CloudWatch alarms: {0}".format(e))


# Utility functions for integration
def get_api_gateway_manager() -> APIGatewayManager:
    """Get configured API Gateway manager instance."""
    return APIGatewayManager()


def get_cloudwatch_metrics() -> CloudWatchMetrics:
    """Get configured CloudWatch metrics instance."""
    return CloudWatchMetrics()


async def setup_aws_rate_limiting() -> bool:
    """Set up AWS API Gateway rate limiting infrastructure."""
    try:
        # Initialize managers
        api_manager = get_api_gateway_manager()
        cloudwatch = get_cloudwatch_metrics()

        # Create usage plans
        plans = await api_manager.create_usage_plans()
        logger.info("Created usage plans: {0}".format(plans))

        # Set up monitoring
        await cloudwatch.create_rate_limit_alarms()

        logger.info("AWS rate limiting setup completed successfully")
        return True

    except Exception as e:
        logger.error("Failed to set up AWS rate limiting: {0}".format(e))
        return False
