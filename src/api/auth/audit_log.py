"""
Security audit logging for authentication and authorization events.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3
from fastapi import Request

# Configure logger
logger = logging.getLogger("security_audit")
logger.setLevel(logging.INFO)


class SecurityAuditLogger:
    """Handle security event logging and monitoring."""

    def __init__(self, log_group: str = "/aws/neuronews/security"):
        """
        Initialize security logger.

        Args:
            log_group: CloudWatch log group name
        """
        self.log_group = log_group
        aws_region = os.getenv("AWS_DEFAULT_REGION")
        if aws_region:
            self.cloudwatch = boto3.client("cloudwatch", region_name=aws_region)
            self.logs = boto3.client("logs", region_name=aws_region)
        else:
            # Fallback to no-op clients when region not configured (e.g. tests)
            self.cloudwatch = None
            self.logs = None

        if self.logs:
            try:
                self.logs.create_log_group(logGroupName=log_group)
            except self.logs.exceptions.ResourceAlreadyExistsException:
                pass

        self.stream_name = datetime.now(timezone.utc).strftime("%Y/%m/%d/security")
        if self.logs:
            try:
                self.logs.create_log_stream(
                    logGroupName=log_group, logStreamName=self.stream_name
                )
            except self.logs.exceptions.ResourceAlreadyExistsException:
                pass

        self.sequence_token = None

    def _format_log_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        request: Optional[Request] = None,
        user: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Format event data for logging.

        Args:
            event_type: Type of security event
            event_data: Event details
            request: Optional FastAPI request object
            user: Optional user data

        Returns:
            Formatted log event
        """
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "event_data": event_data,
        }

        if request:
            log_entry.update(
                {
                    "client_ip": request.client.host,
                    "method": request.method,
                    "path": str(request.url),
                    "user_agent": request.headers.get("user-agent"),
                    "request_id": request.headers.get("x-request-id"),
                }
            )

        if user:
            log_entry["user"] = {
                "id": user.get("sub"),
                "email": user.get("email"),
                "role": user.get("role"),
            }

        return log_entry

    async def log_security_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        request: Optional[Request] = None,
        user: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Log a security event to CloudWatch.

        Args:
            event_type: Type of security event
            event_data: Event details
            request: Optional FastAPI request object
            user: Optional user data
        """
        log_entry = self._format_log_event(event_type, event_data, request, user)

        try:
            kwargs = {
                "logGroupName": self.log_group,
                "logStreamName": self.stream_name,
                "logEvents": [
                    {
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        "message": json.dumps(log_entry),
                    }
                ],
            }

            if self.sequence_token:
                kwargs["sequenceToken"] = self.sequence_token

            if self.logs:
                response = self.logs.put_log_events(**kwargs)
                self.sequence_token = response.get("nextSequenceToken")

            # Emit CloudWatch metrics
            if self.cloudwatch:
                self.cloudwatch.put_metric_data(
                    Namespace="NeuroNews/Security",
                    MetricData=[
                        {
                            "MetricName": f"SecurityEvent{event_type}",
                            "Value": 1,
                            "Unit": "Count",
                            "Dimensions": [
                                {"Name": "Environment", "Value": "production"}
                            ],
                        }
                    ],
                )

        except Exception as e:
            logger.error(f"Failed to log security event: {e}", extra=log_entry)

    async def log_auth_failure(
        self, reason: str, request: Request, user: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log authentication/authorization failure.

        Args:
            reason: Reason for failure
            request: FastAPI request
            user: Optional user data
        """
        await self.log_security_event("AUTH_FAILURE", {"reason": reason}, request, user)

    async def log_auth_success(self, request: Request, user: Dict[str, Any]) -> None:
        """
        Log successful authentication.

        Args:
            request: FastAPI request
            user: User data
        """
        await self.log_security_event("AUTH_SUCCESS", {}, request, user)

    async def log_permission_denied(
        self, permission: str, request: Request, user: Dict[str, Any]
    ) -> None:
        """
        Log permission denial.

        Args:
            permission: Required permission that was missing
            request: FastAPI request
            user: User data
        """
        await self.log_security_event(
            "PERMISSION_DENIED", {"required_permission": permission}, request, user
        )


# Global security logger instance
security_logger = SecurityAuditLogger()
