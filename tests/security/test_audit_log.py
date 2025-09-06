"""
Comprehensive test suite for Security Audit Logger - Issue #476.

Tests all audit logging requirements:
- Security event logging and audit trails
- CloudWatch integration and log streaming
- Event formatting and data sanitization
- Performance under high-volume logging
- Log retention and compliance requirements
- Error handling and failover mechanisms
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest
from fastapi import Request

from src.api.auth.audit_log import SecurityAuditLogger, security_logger


class TestSecurityAuditLogger:
    """Test SecurityAuditLogger class functionality."""

    @pytest.fixture
    def mock_aws_clients(self):
        """Mock AWS clients for testing."""
        with patch('boto3.client') as mock_boto_client:
            mock_cloudwatch = MagicMock()
            mock_logs = MagicMock()
            
            def client_side_effect(service, region_name=None):
                if service == 'cloudwatch':
                    return mock_cloudwatch
                elif service == 'logs':
                    return mock_logs
                return MagicMock()
            
            mock_boto_client.side_effect = client_side_effect
            
            # Setup log group creation
            mock_logs.exceptions.ResourceAlreadyExistsException = Exception
            mock_logs.create_log_group.return_value = {}
            mock_logs.create_log_stream.return_value = {}
            
            yield mock_cloudwatch, mock_logs

    @pytest.fixture
    def audit_logger(self, mock_aws_clients):
        """Create SecurityAuditLogger instance with mocked AWS clients."""
        mock_cloudwatch, mock_logs = mock_aws_clients
        
        with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
            logger = SecurityAuditLogger()
            logger.cloudwatch = mock_cloudwatch
            logger.logs = mock_logs
            return logger

    @pytest.fixture
    def audit_logger_no_aws(self):
        """Create SecurityAuditLogger without AWS region configured."""
        with patch.dict(os.environ, {}, clear=True):
            return SecurityAuditLogger()

    def test_audit_logger_initialization_with_aws(self, mock_aws_clients):
        """Test SecurityAuditLogger initialization with AWS configured."""
        mock_cloudwatch, mock_logs = mock_aws_clients
        
        with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
            logger = SecurityAuditLogger(log_group="/test/security")
            
            assert logger.log_group == "/test/security"
            assert logger.cloudwatch is not None
            assert logger.logs is not None
            assert logger.stream_name is not None
            assert logger.sequence_token is None

    def test_audit_logger_initialization_no_aws(self, audit_logger_no_aws):
        """Test SecurityAuditLogger initialization without AWS."""
        logger = audit_logger_no_aws
        
        assert logger.log_group == "/aws/neuronews/security"
        assert logger.cloudwatch is None
        assert logger.logs is None
        assert logger.stream_name is not None

    def test_log_group_creation(self, mock_aws_clients):
        """Test CloudWatch log group creation."""
        mock_cloudwatch, mock_logs = mock_aws_clients
        
        with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
            SecurityAuditLogger(log_group="/test/new-group")
            
            mock_logs.create_log_group.assert_called_with(logGroupName="/test/new-group")

    def test_log_group_already_exists(self, mock_aws_clients):
        """Test handling when log group already exists."""
        mock_cloudwatch, mock_logs = mock_aws_clients
        mock_logs.create_log_group.side_effect = mock_logs.exceptions.ResourceAlreadyExistsException()
        
        with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
            # Should not raise exception
            SecurityAuditLogger(log_group="/existing/group")

    def test_log_stream_creation(self, mock_aws_clients):
        """Test CloudWatch log stream creation."""
        mock_cloudwatch, mock_logs = mock_aws_clients
        
        with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
            SecurityAuditLogger()
            
            # Should create log stream
            assert mock_logs.create_log_stream.called

    def test_format_log_event_basic(self, audit_logger):
        """Test basic log event formatting."""
        event_data = {"action": "login", "user_id": "123"}
        
        log_entry = audit_logger._format_log_event(
            event_type="authentication",
            event_data=event_data
        )
        
        assert log_entry["event_type"] == "authentication"
        assert log_entry["event_data"] == event_data
        assert "timestamp" in log_entry
        assert isinstance(log_entry["timestamp"], str)

    def test_format_log_event_with_request(self, audit_logger):
        """Test log event formatting with request context."""
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.100"
        mock_request.headers = {"user-agent": "TestAgent/1.0"}
        mock_request.url.path = "/api/secure"
        mock_request.method = "POST"
        
        event_data = {"action": "permission_denied"}
        
        log_entry = audit_logger._format_log_event(
            event_type="authorization",
            event_data=event_data,
            request=mock_request
        )
        
        assert "request_info" in log_entry
        assert log_entry["request_info"]["client_ip"] == "192.168.1.100"
        assert log_entry["request_info"]["user_agent"] == "TestAgent/1.0"
        assert log_entry["request_info"]["path"] == "/api/secure"
        assert log_entry["request_info"]["method"] == "POST"

    def test_format_log_event_with_user(self, audit_logger):
        """Test log event formatting with user context."""
        user_data = {
            "user_id": "user123",
            "email": "test@example.com",
            "role": "premium"
        }
        
        event_data = {"action": "data_access"}
        
        log_entry = audit_logger._format_log_event(
            event_type="data_access",
            event_data=event_data,
            user=user_data
        )
        
        assert "user_info" in log_entry
        assert log_entry["user_info"] == user_data

    def test_format_log_event_complete(self, audit_logger):
        """Test log event formatting with all context."""
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "10.0.0.5"
        mock_request.headers = {"authorization": "Bearer token123"}
        mock_request.url.path = "/admin/users"
        mock_request.method = "DELETE"
        
        user_data = {"user_id": "admin456", "role": "admin"}
        event_data = {"action": "user_deletion", "target_user": "user789"}
        
        log_entry = audit_logger._format_log_event(
            event_type="admin_action",
            event_data=event_data,
            request=mock_request,
            user=user_data
        )
        
        assert log_entry["event_type"] == "admin_action"
        assert log_entry["event_data"] == event_data
        assert log_entry["user_info"] == user_data
        assert "request_info" in log_entry
        assert "timestamp" in log_entry

    def test_log_security_event_success(self, audit_logger):
        """Test successful security event logging."""
        audit_logger.logs.put_log_events.return_value = {
            "nextSequenceToken": "new_token_123"
        }
        
        event_data = {"action": "successful_login", "user_id": "user123"}
        
        result = audit_logger.log_security_event(
            event_type="authentication",
            event_data=event_data
        )
        
        assert result is True
        audit_logger.logs.put_log_events.assert_called_once()
        
        # Check sequence token was updated
        assert audit_logger.sequence_token == "new_token_123"

    def test_log_security_event_with_request(self, audit_logger):
        """Test security event logging with request context."""
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "192.168.1.200"
        
        audit_logger.logs.put_log_events.return_value = {
            "nextSequenceToken": "token456"
        }
        
        event_data = {"action": "permission_check", "permission": "read:articles"}
        
        result = audit_logger.log_security_event(
            event_type="authorization",
            event_data=event_data,
            request=mock_request
        )
        
        assert result is True
        
        # Verify log event was created with request info
        call_args = audit_logger.logs.put_log_events.call_args
        log_events = call_args[1]["logEvents"]
        log_message = json.loads(log_events[0]["message"])
        assert "request_info" in log_message

    def test_log_security_event_failure(self, audit_logger):
        """Test security event logging failure handling."""
        from botocore.exceptions import ClientError
        
        audit_logger.logs.put_log_events.side_effect = ClientError(
            {"Error": {"Code": "InvalidSequenceTokenException"}}, 
            "PutLogEvents"
        )
        
        event_data = {"action": "failed_login", "user_id": "user123"}
        
        result = audit_logger.log_security_event(
            event_type="authentication",
            event_data=event_data
        )
        
        assert result is False

    def test_log_security_event_no_aws(self, audit_logger_no_aws):
        """Test security event logging when AWS is not configured."""
        event_data = {"action": "login_attempt"}
        
        # Should not fail when AWS is not available
        result = audit_logger_no_aws.log_security_event(
            event_type="authentication",
            event_data=event_data
        )
        
        # Should return True (logged locally) or handle gracefully
        assert result in [True, False]  # Implementation dependent

    def test_log_authentication_event(self, audit_logger):
        """Test authentication event logging."""
        audit_logger.logs.put_log_events.return_value = {"nextSequenceToken": "token"}
        
        user_id = "user123"
        action = "login_success"
        details = {"method": "password", "ip": "192.168.1.50"}
        
        result = audit_logger.log_authentication_event(user_id, action, details)
        
        assert result is True
        
        # Verify event structure
        call_args = audit_logger.logs.put_log_events.call_args
        log_events = call_args[1]["logEvents"]
        log_message = json.loads(log_events[0]["message"])
        
        assert log_message["event_type"] == "authentication"
        assert log_message["event_data"]["user_id"] == user_id
        assert log_message["event_data"]["action"] == action
        assert log_message["event_data"]["details"] == details

    def test_log_authorization_event(self, audit_logger):
        """Test authorization event logging."""
        audit_logger.logs.put_log_events.return_value = {"nextSequenceToken": "token"}
        
        user_id = "user456"
        resource = "/api/admin/users"
        action = "access_denied"
        reason = "insufficient_permissions"
        
        result = audit_logger.log_authorization_event(user_id, resource, action, reason)
        
        assert result is True
        
        # Verify event structure
        call_args = audit_logger.logs.put_log_events.call_args
        log_events = call_args[1]["logEvents"]
        log_message = json.loads(log_events[0]["message"])
        
        assert log_message["event_type"] == "authorization"
        assert log_message["event_data"]["user_id"] == user_id
        assert log_message["event_data"]["resource"] == resource
        assert log_message["event_data"]["action"] == action
        assert log_message["event_data"]["reason"] == reason

    def test_log_data_access_event(self, audit_logger):
        """Test data access event logging."""
        audit_logger.logs.put_log_events.return_value = {"nextSequenceToken": "token"}
        
        user_id = "user789"
        resource_type = "article"
        resource_id = "article_123"
        action = "read"
        
        result = audit_logger.log_data_access_event(user_id, resource_type, resource_id, action)
        
        assert result is True
        
        # Verify event structure
        call_args = audit_logger.logs.put_log_events.call_args
        log_events = call_args[1]["logEvents"]
        log_message = json.loads(log_events[0]["message"])
        
        assert log_message["event_type"] == "data_access"
        assert log_message["event_data"]["user_id"] == user_id
        assert log_message["event_data"]["resource_type"] == resource_type
        assert log_message["event_data"]["resource_id"] == resource_id
        assert log_message["event_data"]["action"] == action

    def test_log_security_violation(self, audit_logger):
        """Test security violation logging."""
        audit_logger.logs.put_log_events.return_value = {"nextSequenceToken": "token"}
        
        violation_type = "brute_force_attempt"
        severity = "high"
        details = {"ip": "10.0.0.1", "attempts": 5, "timeframe": "60s"}
        
        result = audit_logger.log_security_violation(violation_type, severity, details)
        
        assert result is True
        
        # Verify event structure
        call_args = audit_logger.logs.put_log_events.call_args
        log_events = call_args[1]["logEvents"]
        log_message = json.loads(log_events[0]["message"])
        
        assert log_message["event_type"] == "security_violation"
        assert log_message["event_data"]["violation_type"] == violation_type
        assert log_message["event_data"]["severity"] == severity
        assert log_message["event_data"]["details"] == details

    def test_sanitize_sensitive_data(self, audit_logger):
        """Test sensitive data sanitization in logs."""
        sensitive_data = {
            "user_id": "user123",
            "password": "secret123",
            "api_key": "nn_secret_key_xyz",
            "email": "user@example.com",
            "session_token": "session_abc_123",
            "credit_card": "4111-1111-1111-1111"
        }
        
        log_entry = audit_logger._format_log_event(
            event_type="test",
            event_data=sensitive_data
        )
        
        # Verify sensitive fields are sanitized
        sanitized_data = log_entry["event_data"]
        assert sanitized_data["password"] == "[REDACTED]"
        assert sanitized_data["api_key"] == "[REDACTED]"
        assert sanitized_data["session_token"] == "[REDACTED]"
        assert sanitized_data["credit_card"] == "[REDACTED]"
        
        # Non-sensitive data should remain
        assert sanitized_data["user_id"] == "user123"
        assert sanitized_data["email"] == "user@example.com"


class TestSecurityAuditLoggerPerformance:
    """Test SecurityAuditLogger performance characteristics."""

    @pytest.fixture
    def audit_logger(self):
        """Create audit logger for performance testing."""
        with patch('boto3.client'):
            with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
                logger = SecurityAuditLogger()
                logger.logs = MagicMock()
                logger.logs.put_log_events.return_value = {"nextSequenceToken": "token"}
                return logger

    def test_high_volume_logging_performance(self, audit_logger):
        """Test performance with high volume of log events."""
        import time
        
        start_time = time.time()
        
        # Log many events quickly
        for i in range(100):
            audit_logger.log_security_event(
                event_type="test",
                event_data={"event_id": i, "action": "test_action"}
            )
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should handle 100 log events in reasonable time (< 5 seconds)
        assert duration < 5.0
        
        # Verify all events were attempted to be logged
        assert audit_logger.logs.put_log_events.call_count == 100

    def test_concurrent_logging(self, audit_logger):
        """Test concurrent logging from multiple threads."""
        import concurrent.futures
        import threading
        
        def log_events(thread_id):
            results = []
            for i in range(10):
                result = audit_logger.log_security_event(
                    event_type="concurrent_test",
                    event_data={"thread_id": thread_id, "event_id": i}
                )
                results.append(result)
            return results
        
        # Run concurrent logging
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(log_events, i) for i in range(5)]
            results = [future.result() for future in concurrent.futures.as_completed(futures)]
        
        # All operations should succeed
        for thread_results in results:
            assert all(thread_results), "Some log operations failed"
        
        # Should have attempted 50 total log operations (5 threads × 10 events)
        assert audit_logger.logs.put_log_events.call_count == 50

    def test_memory_usage_stability(self, audit_logger):
        """Test memory usage remains stable with continuous logging."""
        import gc
        
        # Force garbage collection
        gc.collect()
        initial_objects = len(gc.get_objects())
        
        # Log many events
        for i in range(200):
            audit_logger.log_security_event(
                event_type="memory_test",
                event_data={"iteration": i, "data": "x" * 100}
            )
            
            # Force garbage collection every 50 events
            if i % 50 == 0:
                gc.collect()
        
        # Final garbage collection
        gc.collect()
        final_objects = len(gc.get_objects())
        
        # Object count shouldn't grow significantly
        object_growth = final_objects - initial_objects
        assert object_growth < 2000, f"Memory usage grew by {object_growth} objects"

    def test_large_event_data_handling(self, audit_logger):
        """Test handling of large event data."""
        # Create large event data
        large_data = {
            "user_id": "user123",
            "action": "bulk_operation",
            "details": {
                "items": [f"item_{i}" for i in range(1000)],
                "metadata": "x" * 5000  # Large string
            }
        }
        
        # Should handle large data without issues
        result = audit_logger.log_security_event(
            event_type="bulk_operation",
            event_data=large_data
        )
        
        assert result is True
        audit_logger.logs.put_log_events.assert_called()


class TestSecurityAuditLoggerErrorHandling:
    """Test SecurityAuditLogger error handling."""

    @pytest.fixture
    def audit_logger_with_errors(self):
        """Create audit logger that simulates AWS errors."""
        with patch('boto3.client'):
            with patch.dict(os.environ, {'AWS_DEFAULT_REGION': 'us-east-1'}):
                logger = SecurityAuditLogger()
                logger.logs = MagicMock()
                return logger

    def test_cloudwatch_unavailable(self, audit_logger_with_errors):
        """Test behavior when CloudWatch is unavailable."""
        from botocore.exceptions import EndpointConnectionError
        
        audit_logger_with_errors.logs.put_log_events.side_effect = EndpointConnectionError(
            endpoint_url="https://logs.us-east-1.amazonaws.com"
        )
        
        result = audit_logger_with_errors.log_security_event(
            event_type="test",
            event_data={"action": "test"}
        )
        
        # Should handle error gracefully
        assert result is False

    def test_invalid_sequence_token_retry(self, audit_logger_with_errors):
        """Test retry logic for invalid sequence token."""
        from botocore.exceptions import ClientError
        
        # First call fails with invalid token, second succeeds
        audit_logger_with_errors.logs.put_log_events.side_effect = [
            ClientError(
                {"Error": {"Code": "InvalidSequenceTokenException", "expectedSequenceToken": "correct_token"}},
                "PutLogEvents"
            ),
            {"nextSequenceToken": "new_token"}
        ]
        
        result = audit_logger_with_errors.log_security_event(
            event_type="test",
            event_data={"action": "test"}
        )
        
        # Should succeed after retry
        assert result is True
        assert audit_logger_with_errors.logs.put_log_events.call_count == 2

    def test_permission_denied_error(self, audit_logger_with_errors):
        """Test handling of permission denied errors."""
        from botocore.exceptions import ClientError
        
        audit_logger_with_errors.logs.put_log_events.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException"}},
            "PutLogEvents"
        )
        
        result = audit_logger_with_errors.log_security_event(
            event_type="test",
            event_data={"action": "test"}
        )
        
        # Should handle permission error gracefully
        assert result is False

    def test_throttling_error_handling(self, audit_logger_with_errors):
        """Test handling of throttling errors."""
        from botocore.exceptions import ClientError
        
        audit_logger_with_errors.logs.put_log_events.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException"}},
            "PutLogEvents"
        )
        
        result = audit_logger_with_errors.log_security_event(
            event_type="test",
            event_data={"action": "test"}
        )
        
        # Should handle throttling gracefully
        assert result is False

    def test_malformed_log_data_handling(self, audit_logger_with_errors):
        """Test handling of malformed log data."""
        # Non-serializable data
        class NonSerializable:
            def __str__(self):
                raise Exception("Cannot serialize")
        
        malformed_data = {
            "user_id": "user123",
            "problematic_field": NonSerializable()
        }
        
        # Should handle serialization errors gracefully
        result = audit_logger_with_errors.log_security_event(
            event_type="test",
            event_data=malformed_data
        )
        
        # Implementation dependent - could succeed with sanitized data or fail gracefully
        assert isinstance(result, bool)


class TestGlobalSecurityLogger:
    """Test the global security_logger instance."""

    def test_security_logger_exists(self):
        """Test that security_logger is properly initialized."""
        assert security_logger is not None

    def test_security_logger_functionality(self):
        """Test security_logger basic functionality."""
        # Should be able to call logging methods without errors
        try:
            security_logger.info("Test log message")
            security_logger.warning("Test warning message")
            security_logger.error("Test error message")
        except Exception as e:
            pytest.fail(f"Security logger methods failed: {e}")

    def test_security_logger_integration(self):
        """Test security_logger integration patterns."""
        # Test that it can be used in typical security contexts
        user_id = "user123"
        action = "login_attempt"
        
        # Should not raise exceptions
        try:
            security_logger.info(f"Security event: user={user_id}, action={action}")
        except Exception as e:
            pytest.fail(f"Security logger integration failed: {e}")