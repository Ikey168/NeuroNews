"""
Comprehensive test suite for Security Audit Logger - Issue #476.

NOTE: The audit logger was rewritten to drop the AWS CloudWatch / CloudWatch
Logs integration in favour of local newline-delimited JSON files written under
NEURONEWS_LOG_DIR (default ./logs). These tests target that current,
local-file implementation:

- Security event logging and audit trails (async, file-backed)
- Event formatting (request and user context)
- Local audit-log and metric record writing
- Performance under high-volume logging
- Error handling for write/serialization failures
"""

import asyncio
import json
import os
import tempfile

import pytest
from unittest.mock import MagicMock, patch

from fastapi import Request

from src.api.auth.audit_log import SecurityAuditLogger, security_logger


def _make_request(
    host="192.168.1.100",
    headers=None,
    url="http://testserver/api/secure",
    method="POST",
):
    """Build a truthy MagicMock that quacks like a FastAPI/Starlette Request.

    A real Request is truthy (its __len__ reflects header count); a bare
    MagicMock(spec=Request) is falsy because __len__ defaults to 0, which would
    cause the source's ``if request:`` guard to skip request context. We force
    it truthy to mirror real-request behaviour.
    """
    request = MagicMock(spec=Request)
    request.__len__.return_value = 1
    request.client.host = host
    request.headers = headers if headers is not None else {}
    request.url = url
    request.method = method
    return request


@pytest.fixture
def tmp_log_dir():
    """Isolate audit-log output in a temp directory for each test."""
    with tempfile.TemporaryDirectory() as d:
        with patch.dict(os.environ, {"NEURONEWS_LOG_DIR": d}):
            yield d


class TestSecurityAuditLogger:
    """Test SecurityAuditLogger class functionality."""

    @pytest.fixture
    def audit_logger(self, tmp_log_dir):
        """Create a SecurityAuditLogger writing to an isolated temp dir."""
        return SecurityAuditLogger()

    def test_audit_logger_initialization_with_group(self, tmp_log_dir):
        """Test SecurityAuditLogger initialization with an explicit log group."""
        logger = SecurityAuditLogger(log_group="/test/security")

        assert logger.log_group == "/test/security"
        assert logger.stream_name is not None
        assert logger.events_file.endswith("audit_log.jsonl")
        assert logger.metrics_file.endswith("audit_metrics.jsonl")
        assert logger.log_dir == tmp_log_dir

    def test_audit_logger_initialization_default(self, tmp_log_dir):
        """Test SecurityAuditLogger initialization with default log group."""
        logger = SecurityAuditLogger()

        assert logger.log_group == "neuronews-security"
        assert logger.stream_name is not None
        assert os.path.isdir(logger.log_dir)

    def test_log_dir_created(self, tmp_log_dir):
        """Local log directory is created on initialization."""
        SecurityAuditLogger()

        assert os.path.isdir(tmp_log_dir)

    def test_stream_name_format(self, audit_logger):
        """Stream name encodes a date-based path ending in 'security'."""
        assert audit_logger.stream_name.endswith("/security")
        # YYYY/MM/DD/security -> four slash-separated parts
        assert len(audit_logger.stream_name.split("/")) == 4

    def test_format_log_event_basic(self, audit_logger):
        """Test basic log event formatting."""
        event_data = {"action": "login", "user_id": "123"}

        log_entry = audit_logger._format_log_event(
            event_type="authentication",
            event_data=event_data,
        )

        assert log_entry["event_type"] == "authentication"
        assert log_entry["event_data"] == event_data
        assert "timestamp" in log_entry
        assert isinstance(log_entry["timestamp"], str)

    def test_format_log_event_with_request(self, audit_logger):
        """Test log event formatting with request context."""
        mock_request = _make_request(
            host="192.168.1.100",
            headers={"user-agent": "TestAgent/1.0", "x-request-id": "rid-1"},
            url="http://testserver/api/secure",
            method="POST",
        )

        event_data = {"action": "permission_denied"}

        log_entry = audit_logger._format_log_event(
            event_type="authorization",
            event_data=event_data,
            request=mock_request,
        )

        assert log_entry["client_ip"] == "192.168.1.100"
        assert log_entry["user_agent"] == "TestAgent/1.0"
        assert log_entry["path"] == "http://testserver/api/secure"
        assert log_entry["method"] == "POST"
        assert log_entry["request_id"] == "rid-1"

    def test_format_log_event_with_user(self, audit_logger):
        """Test log event formatting with user context."""
        user_data = {
            "sub": "user123",
            "email": "test@example.com",
            "role": "premium",
        }

        event_data = {"action": "data_access"}

        log_entry = audit_logger._format_log_event(
            event_type="data_access",
            event_data=event_data,
            user=user_data,
        )

        assert "user" in log_entry
        assert log_entry["user"] == {
            "id": "user123",
            "email": "test@example.com",
            "role": "premium",
        }

    def test_format_log_event_complete(self, audit_logger):
        """Test log event formatting with all context."""
        mock_request = _make_request(
            host="10.0.0.5",
            headers={"authorization": "Bearer token123"},
            url="http://testserver/admin/users",
            method="DELETE",
        )

        user_data = {"sub": "admin456", "role": "admin"}
        event_data = {"action": "user_deletion", "target_user": "user789"}

        log_entry = audit_logger._format_log_event(
            event_type="admin_action",
            event_data=event_data,
            request=mock_request,
            user=user_data,
        )

        assert log_entry["event_type"] == "admin_action"
        assert log_entry["event_data"] == event_data
        assert log_entry["user"] == {
            "id": "admin456",
            "email": None,
            "role": "admin",
        }
        assert log_entry["client_ip"] == "10.0.0.5"
        assert "timestamp" in log_entry

    def test_log_security_event_writes_record(self, audit_logger):
        """A security event is appended to the local audit log file."""
        event_data = {"action": "successful_login", "user_id": "user123"}

        result = asyncio.run(
            audit_logger.log_security_event(
                event_type="authentication",
                event_data=event_data,
            )
        )

        # Current implementation logs locally and returns None.
        assert result is None

        assert os.path.exists(audit_logger.events_file)
        with open(audit_logger.events_file) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event_type"] == "authentication"
        assert record["event_data"] == event_data
        assert record["log_group"] == audit_logger.log_group
        assert record["log_stream"] == audit_logger.stream_name

    def test_log_security_event_emits_metric(self, audit_logger):
        """A security event also records a local metric."""
        asyncio.run(
            audit_logger.log_security_event(
                event_type="authentication",
                event_data={"action": "login"},
            )
        )

        assert os.path.exists(audit_logger.metrics_file)
        with open(audit_logger.metrics_file) as f:
            metric_lines = [line for line in f if line.strip()]
        assert len(metric_lines) == 1
        metric = json.loads(metric_lines[0])
        assert metric["Namespace"] == "NeuroNews/Security"
        assert metric["MetricName"] == "SecurityEventauthentication"
        assert metric["Value"] == 1
        assert metric["Unit"] == "Count"

    def test_log_security_event_with_request(self, audit_logger):
        """Test security event logging with request context."""
        mock_request = _make_request(
            host="192.168.1.200",
            headers={"user-agent": "agent"},
            url="http://testserver/api/x",
            method="GET",
        )

        event_data = {"action": "permission_check", "permission": "read:articles"}

        asyncio.run(
            audit_logger.log_security_event(
                event_type="authorization",
                event_data=event_data,
                request=mock_request,
            )
        )

        with open(audit_logger.events_file) as f:
            record = json.loads([line for line in f if line.strip()][0])
        assert record["client_ip"] == "192.168.1.200"
        assert record["method"] == "GET"

    def test_log_security_event_failure_is_swallowed(self, audit_logger):
        """Write failures are caught and do not propagate."""
        with patch.object(
            audit_logger, "_write_record", side_effect=OSError("disk full")
        ):
            # Should not raise even though writing fails.
            result = asyncio.run(
                audit_logger.log_security_event(
                    event_type="authentication",
                    event_data={"action": "failed_login"},
                )
            )

        assert result is None

    def test_log_auth_success(self, audit_logger):
        """Test successful authentication convenience method."""
        request = _make_request(headers={"user-agent": "ua"})
        user = {"sub": "user123", "email": "u@e.com", "role": "premium"}

        asyncio.run(audit_logger.log_auth_success(request, user))

        with open(audit_logger.events_file) as f:
            record = json.loads([line for line in f if line.strip()][0])

        assert record["event_type"] == "AUTH_SUCCESS"
        assert record["event_data"] == {}
        assert record["user"]["id"] == "user123"

    def test_log_auth_failure(self, audit_logger):
        """Test authentication failure convenience method."""
        request = _make_request()
        user = {"sub": "user456"}

        asyncio.run(
            audit_logger.log_auth_failure("invalid_password", request, user)
        )

        with open(audit_logger.events_file) as f:
            record = json.loads([line for line in f if line.strip()][0])

        assert record["event_type"] == "AUTH_FAILURE"
        assert record["event_data"]["reason"] == "invalid_password"

    def test_log_permission_denied(self, audit_logger):
        """Test permission-denied convenience method."""
        request = _make_request()
        user = {"sub": "user789", "role": "viewer"}

        asyncio.run(
            audit_logger.log_permission_denied("admin:write", request, user)
        )

        with open(audit_logger.events_file) as f:
            record = json.loads([line for line in f if line.strip()][0])

        assert record["event_type"] == "PERMISSION_DENIED"
        assert record["event_data"]["required_permission"] == "admin:write"


class TestSecurityAuditLoggerPerformance:
    """Test SecurityAuditLogger performance characteristics."""

    @pytest.fixture
    def audit_logger(self, tmp_log_dir):
        """Create audit logger for performance testing."""
        return SecurityAuditLogger()

    def test_high_volume_logging_performance(self, audit_logger):
        """Test performance with high volume of log events."""
        import time

        start_time = time.time()

        for i in range(100):
            asyncio.run(
                audit_logger.log_security_event(
                    event_type="test",
                    event_data={"event_id": i, "action": "test_action"},
                )
            )

        duration = time.time() - start_time

        # Should handle 100 log events in reasonable time (< 5 seconds).
        assert duration < 5.0

        # Verify all events were written to the local audit log.
        with open(audit_logger.events_file) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 100

    def test_concurrent_logging(self, audit_logger):
        """Test concurrent logging from multiple async tasks."""

        async def log_events(task_id):
            for i in range(10):
                await audit_logger.log_security_event(
                    event_type="concurrent_test",
                    event_data={"task_id": task_id, "event_id": i},
                )

        async def run_all():
            await asyncio.gather(*(log_events(i) for i in range(5)))

        asyncio.run(run_all())

        # Should have written 50 total log records (5 tasks x 10 events).
        with open(audit_logger.events_file) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 50

    def test_memory_usage_stability(self, audit_logger):
        """Test memory usage remains stable with continuous logging."""
        import gc

        gc.collect()
        initial_objects = len(gc.get_objects())

        for i in range(200):
            asyncio.run(
                audit_logger.log_security_event(
                    event_type="memory_test",
                    event_data={"iteration": i, "data": "x" * 100},
                )
            )

            if i % 50 == 0:
                gc.collect()

        gc.collect()
        final_objects = len(gc.get_objects())

        object_growth = final_objects - initial_objects
        assert object_growth < 2000, f"Memory usage grew by {object_growth} objects"

    def test_large_event_data_handling(self, audit_logger):
        """Test handling of large event data."""
        large_data = {
            "user_id": "user123",
            "action": "bulk_operation",
            "details": {
                "items": [f"item_{i}" for i in range(1000)],
                "metadata": "x" * 5000,
            },
        }

        result = asyncio.run(
            audit_logger.log_security_event(
                event_type="bulk_operation",
                event_data=large_data,
            )
        )

        assert result is None
        with open(audit_logger.events_file) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 1


class TestSecurityAuditLoggerErrorHandling:
    """Test SecurityAuditLogger error handling."""

    @pytest.fixture
    def audit_logger(self, tmp_log_dir):
        """Create audit logger for error-handling tests."""
        return SecurityAuditLogger()

    def test_write_unavailable(self, audit_logger):
        """Write errors are handled gracefully without raising."""
        with patch.object(
            audit_logger, "_write_record", side_effect=OSError("cannot write")
        ):
            result = asyncio.run(
                audit_logger.log_security_event(
                    event_type="test",
                    event_data={"action": "test"},
                )
            )

        assert result is None

    def test_metric_emit_failure_is_swallowed(self, audit_logger):
        """A metric-emission failure does not propagate."""
        with patch.object(
            audit_logger, "_emit_metric", side_effect=RuntimeError("boom")
        ):
            result = asyncio.run(
                audit_logger.log_security_event(
                    event_type="test",
                    event_data={"action": "test"},
                )
            )

        assert result is None

    def test_malformed_log_data_handling(self, audit_logger):
        """Test handling of non-serializable log data."""

        class NonSerializable:
            def __str__(self):
                raise Exception("Cannot serialize")

        malformed_data = {
            "user_id": "user123",
            "problematic_field": NonSerializable(),
        }

        # json.dumps will fail on the non-serializable object; the source
        # catches the exception inside log_security_event, so this must not
        # raise and returns None.
        result = asyncio.run(
            audit_logger.log_security_event(
                event_type="test",
                event_data=malformed_data,
            )
        )

        assert result is None


class TestGlobalSecurityLogger:
    """Test the global security_logger instance."""

    def test_security_logger_exists(self):
        """Test that security_logger is properly initialized."""
        assert security_logger is not None
        assert isinstance(security_logger, SecurityAuditLogger)

    def test_security_logger_has_default_group(self):
        """The global instance uses the default security log group."""
        assert security_logger.log_group == "neuronews-security"

    def test_security_logger_can_log(self, tmp_log_dir):
        """The global instance can log a security event without errors."""
        # Point the global instance at the temp dir for this test only.
        with patch.object(
            security_logger, "events_file", os.path.join(tmp_log_dir, "g.jsonl")
        ), patch.object(
            security_logger,
            "metrics_file",
            os.path.join(tmp_log_dir, "gm.jsonl"),
        ):
            result = asyncio.run(
                security_logger.log_security_event(
                    event_type="authentication",
                    event_data={"action": "login_attempt", "user": "user123"},
                )
            )

        assert result is None
        with open(os.path.join(tmp_log_dir, "g.jsonl")) as f:
            lines = [line for line in f if line.strip()]
        assert len(lines) == 1
