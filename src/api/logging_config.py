"""
Logging configuration for the API.
"""

import logging
from datetime import datetime
from typing import Optional

import boto3
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class CloudWatchLogger(BaseHTTPMiddleware):
    """Middleware for logging API requests to CloudWatch."""

    def __init__(self, app, log_group: str, aws_region: Optional[str] = None):
        """Initialize the logger.

        Args:
            app: FastAPI application
            log_group: CloudWatch log group name
            aws_region: AWS region (defaults to environment variable)
        """
        super().__init__(app)
        self.log_group = log_group
        self.logs_client = boto3.client("logs", region_name=aws_region)
        self.log_stream = f"api-{datetime.now().strftime('%Y%m%d')}"

        # Create log stream if needed
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group, logStreamName=self.log_stream
            )
        except self.logs_client.exceptions.ResourceAlreadyExistsException:
            pass

        self.sequence_token = None

    async def dispatch(self, request: Request, call_next) -> Response:
        """Log request and response details to CloudWatch."""
        start_time = datetime.now()

        # Process the request
        try:
            response = await call_next(request)
            status_code = response.status_code
            error = None
        except Exception as e:
            status_code = 500
            error = str(e)
            raise
        finally:
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()

            # Prepare log entry
            log_entry = {
                "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S"),
                "request_id": request.headers.get("X-Request-ID", ""),
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration": "{0:.3f}s".format(duration),
            }

            if error:
                log_entry["error"] = error

            # Send to CloudWatch
            try:
                kwargs = {
                    "logGroupName": self.log_group,
                    "logStreamName": self.log_stream,
                    "logEvents": [
                        {
                            "timestamp": int(start_time.timestamp() * 1000),
                            "message": str(log_entry),
                        }
                    ],
                }

                if self.sequence_token:
                    kwargs["sequenceToken"] = self.sequence_token

                response = self.logs_client.put_log_events(**kwargs)
                self.sequence_token = response.get("nextSequenceToken")

            except Exception as e:
                logging.error("Failed to send logs to CloudWatch: {0}".format(e))

        if error:
            raise

        return response


def configure_logging(app, log_group: str, aws_region: Optional[str] = None):
    """Configure API logging middleware.

    Args:
        app: FastAPI application
        log_group: CloudWatch log group name
        aws_region: AWS region (optional)
    """
    app.add_middleware(CloudWatchLogger, log_group=log_group, aws_region=aws_region)
