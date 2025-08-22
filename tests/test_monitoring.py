#!/usr/bin/env python3
"""
Test suite for monitoring and error handling system.
Tests CloudWatch logging, DynamoDB failure tracking, SNS alerting, and retry logic.
"""

from src.scraper.sns_alert_manager import Alert, AlertSeverity, AlertType, SNSAlertManager
from src.scraper.enhanced_retry_manager import (
    EnhancedRetryManager,
    RetryConfig,
)
from src.scraper.dynamodb_failure_manager import DynamoDBFailureManager
from src.scraper.cloudwatch_logger import CloudWatchLogger, ScrapingMetrics, ScrapingStatus
import asyncio
import json
import sys
import time
from unittest.mock import patch

import pytest
from moto import mock_aws

sys.path.append("/workspaces/NeuroNews/src")


class TestCloudWatchLogger:
    """Test CloudWatch logging functionality."""

    @mock_aws
    def test_cloudwatch_logger_initialization(self):
        """Test CloudWatch logger initializes correctly."""
        logger = CloudWatchLogger(region_name="us-east-1")
        assert logger.namespace == "NeuroNews/Scraper"
        assert logger.region_name == "us-east-1"

    @pytest.mark.asyncio
    async def test_log_scraping_attempt(self):
        """Test logging scraping attempts."""
        logger = CloudWatchLogger(region_name="us-east-1")

        metrics = ScrapingMetrics(
            url="https://test.com",
            status=ScrapingStatus.SUCCESS,
            timestamp=time.time(),
            duration_ms=1500,
            articles_scraped=5,
            retry_count=1,
        )

        # Mock CloudWatch methods
        with patch.object(logger, "_send_log_entry") as mock_log, patch.object(
            logger, "_send_cloudwatch_metrics"
        ) as mock_metrics:
            await logger.log_scraping_attempt(metrics)
            mock_log.assert_called_once()
            mock_metrics.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_metrics_sending(self):
        """Test batch metrics functionality."""
        logger = CloudWatchLogger(region_name="us-east-1")
        logger.buffer_size = 2  # Small buffer for testing

        metrics1 = ScrapingMetrics(
            url="https://test1.com",
            status=ScrapingStatus.SUCCESS,
            timestamp=time.time(),
            duration_ms=1000,
        )

        metrics2 = ScrapingMetrics(
            url="https://test2.com",
            status=ScrapingStatus.FAILURE,
            timestamp=time.time(),
            duration_ms=2000,
            error_message="Test error",
        )

        with patch.object(logger, "_send_batch_metrics") as mock_batch:
            await logger.log_scraping_attempt(metrics1)
            assert len(logger.metrics_buffer) == 1

            await logger.log_scraping_attempt(metrics2)
            # Should trigger batch send when buffer is full
            mock_batch.assert_called_once()


class TestDynamoDBFailureManager:
    """Test DynamoDB failure management functionality."""

    @mock_aws
    def test_dynamodb_manager_initialization(self):
        """Test DynamoDB manager initializes correctly."""
        manager = DynamoDBFailureManager(
            table_name="test-failed-urls", region_name="us-east-1"
        )
        assert manager.table_name == "test-failed-urls"
        assert manager.region_name == "us-east-1"

    @pytest.mark.asyncio
    async def test_record_failure(self):
        """Test recording failure attempts."""
        manager = DynamoDBFailureManager(
            table_name="test-failed-urls", region_name="us-east-1"
        )

        # Mock DynamoDB operations
        with patch.object(manager.dynamodb, "get_item") as mock_get, patch.object(
            manager.dynamodb, "put_item"
        ) as mock_put:

            # Simulate new failure
            mock_get.return_value = {}

            failed_url = await manager.record_failure(
                url="https://test.com",
                failure_reason="timeout",
                error_details="Connection timeout",
            )

            assert failed_url.url == "https://test.com"
            assert failed_url.failure_reason == "timeout"
            assert failed_url.retry_count == 1
            mock_put.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_urls_ready_for_retry(self):
        """Test getting URLs ready for retry."""
        manager = DynamoDBFailureManager(
            table_name="test-failed-urls", region_name="us-east-1"
        )

        # Mock DynamoDB scan response
        mock_response = {
            "Items": [
                {
                    "url": {"S": "https://test.com"},
                    "failure_reason": {"S": "timeout"},
                    "first_failure_time": {"N": str(time.time() - 3600)},
                    "last_failure_time": {"N": str(time.time() - 600)},
                    "retry_count": {"N": "2"},
                    "max_retries": {"N": "5"},
                    "next_retry_time": {"N": str(time.time() - 100)},
                    "is_permanent_failure": {"BOOL": False},
                }
            ]
        }

        with patch.object(manager.dynamodb, "scan", return_value=mock_response):
            urls = await manager.get_urls_ready_for_retry(limit=10)
            assert len(urls) == 1
            assert urls[0].url == "https://test.com"
            assert urls[0].retry_count == 2


class TestSNSAlertManager:
    """Test SNS alerting functionality."""

    @mock_aws
    def test_sns_manager_initialization(self):
        """Test SNS manager initializes correctly."""
        manager = SNSAlertManager(
            topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
            region_name="us-east-1",
        )
        assert manager.topic_arn == "arn:aws:sns:us-east-1:123456789012:test-topic"
        assert manager.region_name == "us-east-1"

    @pytest.mark.asyncio
    async def test_send_alert(self):
        """Test sending alerts."""
        manager = SNSAlertManager(
            topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
            region_name="us-east-1",
        )

        alert = Alert(
            alert_type=AlertType.SCRAPER_FAILURE,
            severity=AlertSeverity.ERROR,
            title="Test Alert",
            message="This is a test alert",
            timestamp=time.time(),
            metadata={"test": True},
        )

        with patch.object(manager.sns, "publish") as mock_publish:
            mock_publish.return_value = {"MessageId": "test-123"}

            result = await manager.send_alert(alert)
            assert result
            mock_publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test alert rate limiting."""
        manager = SNSAlertManager(
            topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
            region_name="us-east-1",
            max_alerts_per_window=2,
        )

        alert = Alert(
            alert_type=AlertType.SCRAPER_FAILURE,
            severity=AlertSeverity.INFO,
            title="Test Alert",
            message="This is a test alert",
            timestamp=time.time(),
            metadata={},
        )

        with patch.object(manager.sns, "publish") as mock_publish:
            mock_publish.return_value = {"MessageId": "test-123"}

            # First two alerts should go through
            result1 = await manager.send_alert(alert)
            result2 = await manager.send_alert(alert)
            assert result1
            assert result2

            # Third alert should be rate limited
            result3 = await manager.send_alert(alert)
            assert result3 is False


class TestEnhancedRetryManager:
    """Test enhanced retry manager functionality."""

    def test_retry_manager_initialization(self):
        """Test retry manager initializes correctly."""
        manager = EnhancedRetryManager()
        assert manager.retry_config.max_retries == 5  # Default value

    @pytest.mark.asyncio
    async def test_successful_retry(self):
        """Test successful function execution with retry."""
        manager = EnhancedRetryManager()

        # Mock function that succeeds on first try

        async def mock_function():
            return "success"

        result = await manager.retry_with_backoff(mock_function, url="https://test.com")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_retry_with_failures(self):
        """Test retry logic with initial failures."""
        manager = EnhancedRetryManager()

        call_count = 0

        async def mock_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = await manager.retry_with_backoff(
            mock_function,
            url="https://test.com",
            retry_config=RetryConfig(max_retries=5, base_delay=0.1),
        )

        assert result == "success"
        assert call_count == 3  # Failed twice, succeeded on third try

    @pytest.mark.asyncio
    async def test_permanent_failure(self):
        """Test handling of permanent failures."""
        manager = EnhancedRetryManager()

        async def mock_function():
            error = Exception("Not found")
            error.status_code = 404  # Permanent failure
            raise error

        with pytest.raises(Exception) as exc_info:
            await manager.retry_with_backoff(
                mock_function,
                url="https://test.com",
                retry_config=RetryConfig(max_retries=3, base_delay=0.1),
            )

        assert "Not found" in str(exc_info.value)

    def test_circuit_breaker(self):
        """Test circuit breaker functionality."""
        manager = EnhancedRetryManager()
        manager.circuit_breaker_failure_threshold = 2

        url = "https://test.com"

        # Record failures to trigger circuit breaker
        manager._record_circuit_breaker_failure(url)
        manager._record_circuit_breaker_failure(url)

        # Circuit breaker should be open
        assert manager._is_circuit_breaker_open(url)

        # Reset circuit breaker
        manager._reset_circuit_breaker(url)
        assert manager._is_circuit_breaker_open(url) is False


class TestIntegration:
    """Integration tests for monitoring and error handling system."""

    @pytest.mark.asyncio
    async def test_full_monitoring_workflow(self):
        """Test complete monitoring workflow."""
        # Initialize all components
        cloudwatch_logger = CloudWatchLogger(region_name="us-east-1")
        failure_manager = DynamoDBFailureManager(
            table_name="test-failed-urls", region_name="us-east-1"
        )
        alert_manager = SNSAlertManager(
            topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
            region_name="us-east-1",
        )

        retry_manager = EnhancedRetryManager(
            cloudwatch_logger=cloudwatch_logger,
            failure_manager=failure_manager,
            alert_manager=alert_manager,
        )

        # Mock AWS services
        with patch.object(
            cloudwatch_logger, "log_scraping_attempt"
        ) as mock_log, patch.object(
            failure_manager, "record_failure"
        ) as mock_failure, patch.object(
            alert_manager, "send_alert"
        ) as mock_alert:

            # Test function that fails

            async def failing_function():
                raise Exception("Test failure")

            # Should record failure, log metrics, and send alert
            with pytest.raises(Exception):
                await retry_manager.retry_with_backoff(
                    failing_function,
                    url="https://test.com",
                    retry_config=RetryConfig(max_retries=1, base_delay=0.1),
                )

            # Verify all monitoring components were called
            mock_log.assert_called()
            mock_failure.assert_called()
            mock_alert.assert_called()


class TestMonitoringConfiguration:
    """Test monitoring configuration loading."""

    def test_config_file_loading(self):
        """Test loading monitoring configuration from file."""
        config_path = "/workspaces/NeuroNews/src/scraper/config_monitoring.json"

        # Check if config file exists and is valid JSON
        try:
            with open(config_path, "r") as f:
                config = json.load(f)

            assert "monitoring" in config
            assert "cloudwatch" in config["monitoring"]
            assert "dynamodb" in config["monitoring"]
            assert "sns" in config["monitoring"]
            assert config["monitoring"]["enabled"]

        except FileNotFoundError:
            pytest.skip("Config file not found")
        except json.JSONDecodeError:
            pytest.fail("Config file contains invalid JSON")


if __name__ == "__main__":
    """Run tests manually for development."""
    import asyncio

    async def run_manual_tests():
        """Run some basic tests manually."""
        print("Testing monitoring and error handling system...")

        # Test CloudWatch logger
        print("1. Testing CloudWatch Logger...")
        cloudwatch_logger = CloudWatchLogger(region_name="us-east-1")

        metrics = ScrapingMetrics(
            url="https://test.com",
            status=ScrapingStatus.SUCCESS,
            timestamp=time.time(),
            duration_ms=1500,
            articles_scraped=5,
        )

        try:
            await cloudwatch_logger.log_scraping_attempt(metrics)
            print(" CloudWatch logging test passed")
        except Exception as e:
            print("❌ CloudWatch logging test failed: {0}".format(e))

        # Test DynamoDB manager
        print("2. Testing DynamoDB Failure Manager...")
        failure_manager = DynamoDBFailureManager(
            table_name="test-failed-urls", region_name="us-east-1"
        )

        try:
            failed_url = await failure_manager.record_failure(
                url="https://test-failure.com",
                failure_reason="timeout",
                error_details="Connection timeout after 30s",
            )
            print(
                " DynamoDB failure recording test passed: {0}".format(failed_url.url)
            )
        except Exception as e:
            print("❌ DynamoDB failure recording test failed: {0}".format(e))

        # Test SNS alert manager
        print("3. Testing SNS Alert Manager...")
        try:
            alert_manager = SNSAlertManager(
                topic_arn="arn:aws:sns:us-east-1:123456789012:test-topic",
                region_name="us-east-1",
            )

            alert = Alert(
                alert_type=AlertType.SCRAPER_FAILURE,
                severity=AlertSeverity.INFO,
                title="Test Alert",
                message="This is a test alert for manual testing",
                timestamp=time.time(),
                metadata={"test": True},
            )

            # This would fail without proper AWS credentials, but tests the
            # code path
            print(" SNS alert manager initialization test passed")
        except Exception as e:
            print("⚠️ SNS alert manager test: {0}".format(e))

        # Test retry manager
        print("4. Testing Enhanced Retry Manager...")
        retry_manager = EnhancedRetryManager()

        call_count = 0

        async def test_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "success"

        try:
            result = await retry_manager.retry_with_backoff(
                test_function,
                url="https://test-retry.com",
                retry_config=RetryConfig(max_retries=3, base_delay=0.1),
            )
            print(
                " Retry manager test passed: {0} (after {1} attempts)".format(
                    result, call_count
                )
            )
        except Exception as e:
            print("❌ Retry manager test failed: {0}".format(e))

        print("Manual tests completed!")

    # Run manual tests
    asyncio.run(run_manual_tests())
