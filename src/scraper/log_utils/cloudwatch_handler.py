"""
CloudWatch logging handler for NeuroNews scrapers.
"""

import json
import logging
import os
from datetime import datetime

import boto3
from botocore.exceptions import ClientError


class CloudWatchLoggingHandler(logging.Handler):
    """
    A logging handler that sends logs to AWS CloudWatch Logs.
    """

    def __init__(
        self,
        log_group_name,
        log_stream_name=None,
        aws_access_key_id=None,
        aws_secret_access_key=None,
        aws_region=None,
    ):
        """
        Initialize the CloudWatch logging handler.

        Args:
            log_group_name (str): CloudWatch Logs group name
            log_stream_name (str, optional): CloudWatch Logs stream name.
                                            If not provided, a name will be generated.
            aws_access_key_id (str, optional): AWS access key ID
            aws_secret_access_key (str, optional): AWS secret access key
            aws_region (str, optional): AWS region
        """
        super().__init__()
        self.log_group_name = log_group_name
        self.log_stream_name = (
            log_stream_name or f"scraper-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )

        # Initialize CloudWatch Logs client
        self.logs_client = boto3.client(
            "logs",
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region or "us-east-1",
        )

        self.sequence_token = None
        self._create_log_group_and_stream()

    def _create_log_group_and_stream(self):
        """Create the log group and stream if they don't exist."""
        # Create log group if it doesn't exist
        try:
            self.logs_client.create_log_group(logGroupName=self.log_group_name)
        except ClientError as e:
            # ResourceAlreadyExistsException is expected if the log group already exists
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

        # Create log stream if it doesn't exist
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group_name, logStreamName=self.log_stream_name
            )
        except ClientError as e:
            # ResourceAlreadyExistsException is expected if the log stream already exists
            if e.response["Error"]["Code"] != "ResourceAlreadyExistsException":
                raise

    def emit(self, record):
        """
        Send a log record to CloudWatch Logs.

        Args:
            record: The log record to send
        """
        try:
            # Format the log message
            log_message = self.format(record)

            # Prepare the log event
            log_event = {
                "timestamp": int(
                    record.created * 1000
                ),  # CloudWatch expects milliseconds
                "message": log_message,
            }

            # Add the log event to CloudWatch Logs
            kwargs = {
                "logGroupName": self.log_group_name,
                "logStreamName": self.log_stream_name,
                "logEvents": [log_event],
            }

            # Include sequence token if we have one
            if self.sequence_token:
                kwargs["sequenceToken"] = self.sequence_token

            # Put the log event
            response = self.logs_client.put_log_events(**kwargs)

            # Update the sequence token for the next call
            self.sequence_token = response.get("nextSequenceToken")

        except Exception as e:
            # Don't raise exceptions from the logging handler
            self.handleError(record)


def configure_cloudwatch_logging(settings, spider_name):
    """
    Configure CloudWatch logging for a Scrapy spider.

    Args:
        settings: Scrapy settings object
        spider_name: Name of the spider

    Returns:
        CloudWatchLoggingHandler: The configured handler, or None if CloudWatch logging is disabled
    """
    # Check if CloudWatch logging is enabled
    if not settings.getbool("CLOUDWATCH_LOGGING_ENABLED", False):
        return None

    # Get CloudWatch settings
    aws_access_key_id = settings.get("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = settings.get("AWS_SECRET_ACCESS_KEY")
    aws_region = settings.get("AWS_REGION", "us-east-1")
    log_group_name = settings.get("CLOUDWATCH_LOG_GROUP", "NeuroNews-Scraper")
    log_stream_prefix = settings.get("CLOUDWATCH_LOG_STREAM_PREFIX", "scraper")

    # Generate a log stream name
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_stream_name = f"{log_stream_prefix}-{spider_name}-{timestamp}"

    # Create and configure the handler
    handler = CloudWatchLoggingHandler(
        log_group_name=log_group_name,
        log_stream_name=log_stream_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_region=aws_region,
    )

    # Set the formatter
    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)

    # Set the log level
    log_level = settings.get("CLOUDWATCH_LOG_LEVEL", "INFO")
    handler.setLevel(getattr(logging, log_level))

    return handler
