"""
AWS WAF (Web Application Firewall) Security System for NeuroNews API - Issue #65.

This module implements comprehensive API protection:
1. Deploy AWS WAF (Web Application Firewall) for API protection
2. Block SQL injection & cross-site scripting (XSS) attacks
3. Enable geofencing (limit access by country)
4. Monitor real-time attack attempts
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

logger = logging.getLogger(__name__)


class ThreatType(Enum):
    """Types of security threats."""

    SQL_INJECTION = "sql_injection"
    XSS_ATTACK = "xss_attack"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    GEO_BLOCKED = "geo_blocked"
    MALICIOUS_IP = "malicious_ip"
    BOT_TRAFFIC = "bot_traffic"
    DDOS_ATTEMPT = "ddos_attempt"


class ActionType(Enum):
    """WAF action types."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    COUNT = "COUNT"
    CAPTCHA = "CAPTCHA"


@dataclass
class WAFRule:
    """WAF rule configuration."""

    name: str
    priority: int
    action: ActionType
    rule_type: str
    description: str
    enabled: bool = True
    metric_name: Optional[str] = None


@dataclass
class SecurityEvent:
    """Security event data structure."""

    timestamp: datetime
    threat_type: ThreatType
    source_ip: str
    user_agent: str
    request_path: str
    action_taken: ActionType
    details: Dict[str, Any]
    severity: str = "medium"


class AWSWAFManager:
    """Manages AWS WAF configuration and monitoring."""

    def __init__(self):
        """Initialize AWS WAF manager."""
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.web_acl_name = os.getenv("WAF_WEB_ACL_NAME", "NeuroNewsAPIProtection")
        self.api_gateway_arn = os.getenv("API_GATEWAY_ARN", "")

        # Allowed countries for geofencing
        self.allowed_countries = os.getenv(
            "WAF_ALLOWED_COUNTRIES", "US,CA,GB,AU,DE,FR,JP"
        ).split(",")

        # Rate limiting configuration
        self.rate_limit_requests = int(
            os.getenv("WAF_RATE_LIMIT", "2000")
        )  # requests per 5 minutes

        # Initialize AWS clients
        self.wafv2_client = None
        self.cloudwatch_client = None
        self.logs_client = None

        if BOTO3_AVAILABLE:
            try:
                self.wafv2_client = boto3.client("wafv2", region_name=self.region)
                self.cloudwatch_client = boto3.client(
                    "cloudwatch", region_name=self.region
                )
                self.logs_client = boto3.client("logs", region_name=self.region)
                logger.info("AWS WAF clients initialized successfully")
            except (NoCredentialsError, Exception) as e:
                logger.warning("Failed to initialize AWS clients: {0}".format(e))
                self.wafv2_client = None
                self.cloudwatch_client = None
                self.logs_client = None
        else:
            logger.warning("boto3 not available - AWS WAF features disabled")

    def create_web_acl(self) -> bool:
        """Create AWS WAF Web ACL with comprehensive rules."""
        if not self.wafv2_client:
            logger.warning("AWS WAF client not available")
            return False

        try:
            # Define WAF rules
            rules = self._get_waf_rules()

            # Create Web ACL
            response = self.wafv2_client.create_web_acl(
                Name=self.web_acl_name,
                Scope="REGIONAL",  # For API Gateway
                DefaultAction={"Allow": {}},
                Description=(
                    "NeuroNews API Protection - Blocks SQL injection, XSS, "
                    "and implements geofencing"
                ),
                Rules=rules,
                Tags=[
                    {"Key": "Application", "Value": "NeuroNews"},
                    {"Key": "Purpose", "Value": "APIProtection"},
                    {"Key": "Issue", "Value": "65"},
                ],
                CustomResponseBodies={
                    "BlockedResponse": {
                        "ContentType": "APPLICATION_JSON",
                        "Content": json.dumps(
                            {
                                "error": "Access Denied",
                                "message": "Your request has been blocked by our security system",
                                "code": "WAF_BLOCKED",
                            }
                        ),
                    }
                },
            )

            self.web_acl_arn = response["Summary"]["ARN"]
            logger.info(
                "Created Web ACL: {0} with ARN: {1}".format(
                    self.web_acl_name, self.web_acl_arn
                )
            )
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "WAFDuplicateItemException":
                logger.info("Web ACL {0} already exists".format(self.web_acl_name))
                return self._get_existing_web_acl()
            else:
                logger.error("Failed to create Web ACL: {0}".format(e))
                return False
        except Exception as e:
            logger.error("Unexpected error creating Web ACL: {0}".format(e))
            return False

    def _get_waf_rules(self) -> List[Dict[str, Any]]:
        """Define comprehensive WAF rules."""
        rules = []

        # Rule 1: Block SQL Injection attacks
        rules.append(
            {
                "Name": "SQLInjectionProtection",
                "Priority": 1,
                "Statement": {
                    "SqliMatchStatement": {
                        "FieldToMatch": {"AllQueryArguments": {}},
                        "TextTransformations": [
                            {"Priority": 0, "Type": "URL_DECODE"},
                            {"Priority": 1, "Type": "HTML_ENTITY_DECODE"},
                        ],
                    }
                },
                "Action": {"Block": {"CustomResponse": {"ResponseCode": 403}}},
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "SQLInjectionBlocked",
                },
            }
        )

        # Rule 2: Block XSS attacks
        rules.append(
            {
                "Name": "XSSProtection",
                "Priority": 2,
                "Statement": {
                    "XssMatchStatement": {
                        "FieldToMatch": {"AllQueryArguments": {}},
                        "TextTransformations": [
                            {"Priority": 0, "Type": "URL_DECODE"},
                            {"Priority": 1, "Type": "HTML_ENTITY_DECODE"},
                        ],
                    }
                },
                "Action": {"Block": {"CustomResponse": {"ResponseCode": 403}}},
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "XSSBlocked",
                },
            }
        )

        # Rule 3: Geofencing - Allow only specific countries
        if self.allowed_countries:
            rules.append(
                {
                    "Name": "GeofencingRule",
                    "Priority": 3,
                    "Statement": {
                        "NotStatement": {
                            "Statement": {
                                "GeoMatchStatement": {
                                    "CountryCodes": self.allowed_countries
                                }
                            }
                        }
                    },
                    "Action": {"Block": {"CustomResponse": {"ResponseCode": 403}}},
                    "VisibilityConfig": {
                        "SampledRequestsEnabled": True,
                        "CloudWatchMetricsEnabled": True,
                        "MetricName": "GeoBlocked",
                    },
                }
            )

        # Rule 4: Rate limiting
        rules.append(
            {
                "Name": "RateLimitingRule",
                "Priority": 4,
                "Statement": {
                    "RateBasedStatement": {
                        "Limit": self.rate_limit_requests,
                        "AggregateKeyType": "IP",
                    }
                },
                "Action": {"Block": {"CustomResponse": {"ResponseCode": 429}}},
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "RateLimitExceeded",
                },
            }
        )

        # Rule 5: Known malicious IPs (AWS managed rule)
        rules.append(
            {
                "Name": "AWSManagedRulesKnownBadInputsRuleSet",
                "Priority": 5,
                "OverrideAction": {"None": {}},
                "Statement": {
                    "ManagedRuleGroupStatement": {
                        "VendorName": "AWS",
                        "Name": "AWSManagedRulesKnownBadInputsRuleSet",
                    }
                },
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "KnownBadInputsBlocked",
                },
            }
        )

        # Rule 6: Core Rule Set (OWASP)
        rules.append(
            {
                "Name": "AWSManagedRulesCommonRuleSet",
                "Priority": 6,
                "OverrideAction": {"None": {}},
                "Statement": {
                    "ManagedRuleGroupStatement": {
                        "VendorName": "AWS",
                        "Name": "AWSManagedRulesCommonRuleSet",
                        "ExcludedRules": [
                            # Exclude rules that might be too restrictive for
                            # API
                            {"Name": "SizeRestrictions_BODY"},
                            {"Name": "SizeRestrictions_QUERYSTRING"},
                        ],
                    }
                },
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "CoreRuleSetBlocked",
                },
            }
        )

        # Rule 7: Bot control
        rules.append(
            {
                "Name": "AWSManagedRulesBotControlRuleSet",
                "Priority": 7,
                "OverrideAction": {"None": {}},
                "Statement": {
                    "ManagedRuleGroupStatement": {
                        "VendorName": "AWS",
                        "Name": "AWSManagedRulesBotControlRuleSet",
                    }
                },
                "VisibilityConfig": {
                    "SampledRequestsEnabled": True,
                    "CloudWatchMetricsEnabled": True,
                    "MetricName": "BotControlBlocked",
                },
            }
        )

        return rules

    def _get_existing_web_acl(self) -> bool:
        """Get existing Web ACL ARN."""
        try:
            response = self.wafv2_client.list_web_acls(Scope="REGIONAL")

            for web_acl in response["WebACLs"]:
                if web_acl["Name"] == self.web_acl_name:
                    self.web_acl_arn = web_acl["ARN"]
                    logger.info("Found existing Web ACL: {0}".format(self.web_acl_arn))
                    return True

            logger.warning("Web ACL {0} not found".format(self.web_acl_name))
            return False

        except Exception as e:
            logger.error("Error finding existing Web ACL: {0}".format(e))
            return False

    def associate_with_api_gateway(self, api_gateway_arn: str = None) -> bool:
        """Associate Web ACL with API Gateway."""
        if not self.wafv2_client:
            logger.warning("AWS WAF client not available")
            return False

        target_arn = api_gateway_arn or self.api_gateway_arn
        if not target_arn:
            logger.error("API Gateway ARN not provided")
            return False

        if not hasattr(self, "web_acl_arn") or not self.web_acl_arn:
            if not self.create_web_acl():
                return False

        try:
            self.wafv2_client.associate_web_acl(
                WebACLArn=self.web_acl_arn, ResourceArn=target_arn
            )

            logger.info("Associated Web ACL with API Gateway: {0}".format(target_arn))
            return True

        except ClientError as e:
            if e.response["Error"]["Code"] == "WAFAssociatedItemException":
                logger.info("Web ACL already associated with API Gateway")
                return True
            else:
                logger.error(
                    "Failed to associate Web ACL with API Gateway: {0}".format(e)
                )
                return False
        except Exception as e:
            logger.error("Unexpected error associating Web ACL: {0}".format(e))
            return False

    def get_security_metrics(self) -> Dict[str, Any]:
        """Get WAF security metrics from CloudWatch."""
        if not self.cloudwatch_client:
            return {"error": "CloudWatch client not available"}

        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time.replace(hour=end_time.hour - 1)  # Last hour

            metrics = {}

            # Define metrics to collect
            metric_names = [
                "SQLInjectionBlocked",
                "XSSBlocked",
                "GeoBlocked",
                "RateLimitExceeded",
                "KnownBadInputsBlocked",
                "CoreRuleSetBlocked",
                "BotControlBlocked",
            ]

            for metric_name in metric_names:
                try:
                    response = self.cloudwatch_client.get_metric_statistics(
                        Namespace="AWS/WAFV2",
                        MetricName=metric_name,
                        Dimensions=[
                            {"Name": "WebACL", "Value": self.web_acl_name},
                            {"Name": "Region", "Value": self.region},
                        ],
                        StartTime=start_time,
                        EndTime=end_time,
                        Period=300,  # 5 minutes
                        Statistics=["Sum"],
                    )

                    total_blocked = sum(
                        point["Sum"] for point in response["Datapoints"]
                    )
                    metrics[metric_name] = {
                        "blocked_requests": total_blocked,
                        "datapoints": len(response["Datapoints"]),
                    }

                except Exception as e:
                    logger.warning(
                        "Failed to get metric {0}: {1}".format(metric_name, e)
                    )
                    metrics[metric_name] = {"blocked_requests": 0, "error": str(e)}

            return {
                "timestamp": end_time.isoformat(),
                "web_acl_name": self.web_acl_name,
                "metrics": metrics,
                "time_range": {
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                },
            }

        except Exception as e:
            logger.error("Error getting security metrics: {0}".format(e))
            return {"error": str(e)}

    def get_blocked_requests(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent blocked requests for analysis."""
        if not self.wafv2_client:
            return []

        try:
            # Get sampled requests that were blocked
            response = self.wafv2_client.get_sampled_requests(
                WebAclArn=self.web_acl_arn,
                RuleMetricName="SQLInjectionBlocked",  # Example rule
                Scope="REGIONAL",
                TimeWindow={
                    "StartTime": datetime.now(timezone.utc).replace(
                        hour=datetime.now(timezone.utc).hour - 1
                    ),
                    "EndTime": datetime.now(timezone.utc),
                },
                MaxItems=limit,
            )

            blocked_requests = []
            for sample in response["SampledRequests"]:
                request_data = sample["Request"]
                blocked_requests.append(
                    {
                        "timestamp": sample["Timestamp"].isoformat(),
                        "client_ip": request_data.get("ClientIP", "unknown"),
                        "country": request_data.get("Country", "unknown"),
                        "uri": request_data.get("URI", "unknown"),
                        "method": request_data.get("Method", "unknown"),
                        "headers": request_data.get("Headers", []),
                        "action": sample["Action"],
                        "weight": sample.get("Weight", 1),
                    }
                )

            return blocked_requests

        except Exception as e:
            logger.error("Error getting blocked requests: {0}".format(e))
            return []

    def create_security_dashboard(self) -> bool:
        """Create CloudWatch dashboard for WAF monitoring."""
        if not self.cloudwatch_client:
            logger.warning("CloudWatch client not available")
            return False

        try:
            dashboard_body = {
                "widgets": [
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 0,
                        "width": 12,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                [
                                    "AWS/WAFV2",
                                    "BlockedRequests",
                                    "WebACL",
                                    self.web_acl_name,
                                    "Region",
                                    self.region,
                                ],
                                [
                                    "AWS/WAFV2",
                                    "AllowedRequests",
                                    "WebACL",
                                    self.web_acl_name,
                                    "Region",
                                    self.region,
                                ],
                            ],
                            "period": 300,
                            "stat": "Sum",
                            "region": self.region,
                            "title": "WAF Requests Overview",
                        },
                    },
                    {
                        "type": "metric",
                        "x": 0,
                        "y": 6,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                [
                                    "AWS/WAFV2",
                                    "SQLInjectionBlocked",
                                    "WebACL",
                                    self.web_acl_name,
                                    "Region",
                                    self.region,
                                ],
                                [
                                    "AWS/WAFV2",
                                    "XSSBlocked",
                                    "WebACL",
                                    self.web_acl_name,
                                    "Region",
                                    self.region,
                                ],
                            ],
                            "period": 300,
                            "stat": "Sum",
                            "region": self.region,
                            "title": "Attack Types Blocked",
                        },
                    },
                    {
                        "type": "metric",
                        "x": 6,
                        "y": 6,
                        "width": 6,
                        "height": 6,
                        "properties": {
                            "metrics": [
                                [
                                    "AWS/WAFV2",
                                    "GeoBlocked",
                                    "WebACL",
                                    self.web_acl_name,
                                    "Region",
                                    self.region,
                                ],
                                [
                                    "AWS/WAFV2",
                                    "RateLimitExceeded",
                                    "WebACL",
                                    self.web_acl_name,
                                    "Region",
                                    self.region,
                                ],
                            ],
                            "period": 300,
                            "stat": "Sum",
                            "region": self.region,
                            "title": "Geo & Rate Limiting",
                        },
                    },
                ]
            }

            dashboard_name = "NeuroNews-WAF-Security-{0}".format(self.region)

            self.cloudwatch_client.put_dashboard(
                DashboardName=dashboard_name, DashboardBody=json.dumps(dashboard_body)
            )

            logger.info("Created CloudWatch dashboard: {0}".format(dashboard_name))
            return True

        except Exception as e:
            logger.error("Error creating security dashboard: {0}".format(e))
            return False

    def setup_logging(self) -> bool:
        """Set up WAF logging to CloudWatch."""
        if not self.logs_client or not self.wafv2_client:
            logger.warning("Required AWS clients not available")
            return False

        try:
            log_group_name = "/aws/wafv2/{0}".format(self.web_acl_name)

            # Create log group
            try:
                self.logs_client.create_log_group(
                    logGroupName=log_group_name,
                    tags={"Application": "NeuroNews", "Purpose": "WAFLogging"},
                )
                logger.info("Created CloudWatch log group: {0}".format(log_group_name))
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceAlreadyExistsException":
                    logger.info("Log group {0} already exists".format(log_group_name))
                else:
                    raise

            # Set retention policy
            self.logs_client.put_retention_policy(
                logGroupName=log_group_name, retentionInDays=30
            )

            # Enable WAF logging
            log_destination_arn = "arn:aws:logs:{0}:{1}:log-group:{2}".format(
                self.region, self._get_account_id(), log_group_name
            )

            self.wafv2_client.put_logging_configuration(
                LoggingConfiguration={
                    "ResourceArn": self.web_acl_arn,
                    "LogDestinationConfigs": [log_destination_arn],
                    "RedactedFields": [
                        {"SingleHeader": {"Name": "authorization"}},
                        {"SingleHeader": {"Name": "cookie"}},
                    ],
                }
            )

            logger.info("WAF logging configured successfully")
            return True

        except Exception as e:
            logger.error("Error setting up WAF logging: {0}".format(e))
            return False

    def _get_account_id(self) -> str:
        """Get AWS account ID."""
        try:
            sts_client = boto3.client("sts", region_name=self.region)
            return sts_client.get_caller_identity()["Account"]
        except Exception:
            return "123456789012"  # Fallback for testing

    def health_check(self) -> Dict[str, Any]:
        """Check WAF system health."""
        health_status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "components": {},
            "overall_status": "healthy",
        }

        # Check AWS clients
        health_status["components"]["waf_client"] = (
            "operational" if self.wafv2_client else "unavailable"
        )
        health_status["components"]["cloudwatch_client"] = (
            "operational" if self.cloudwatch_client else "unavailable"
        )
        health_status["components"]["logs_client"] = (
            "operational" if self.logs_client else "unavailable"
        )

        # Check Web ACL existence
        if self.wafv2_client:
            try:
                self._get_existing_web_acl()
                health_status["components"]["web_acl"] = "operational"
            except Exception:
                health_status["components"]["web_acl"] = "error"
                health_status["overall_status"] = "degraded"
        else:
            health_status["components"]["web_acl"] = "unavailable"
            health_status["overall_status"] = "degraded"

        return health_status

    def detect_sql_injection(self, content: str) -> bool:
        """
        Detect SQL injection patterns in content.

        Args:
            content: Content to analyze

        Returns:
            True if SQL injection detected
        """
        return self._detect_sql_injection(content)

    def detect_xss(self, content: str) -> bool:
        """
        Detect XSS patterns in content.

        Args:
            content: Content to analyze

        Returns:
            True if XSS detected
        """
        return self._detect_xss(content)


# Global WAF manager instance
waf_manager = AWSWAFManager()
