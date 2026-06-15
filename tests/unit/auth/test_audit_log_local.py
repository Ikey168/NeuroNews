"""
Unit tests for the local (no-AWS) security audit logger.

Verifies that SecurityAuditLogger writes audit events and metrics to local
newline-delimited JSON files under NEURONEWS_LOG_DIR, with no boto3 dependency.
"""

import json
import os
import sys

import pytest

import src.api.auth.audit_log as audit_log
from src.api.auth.audit_log import SecurityAuditLogger


class _FakeClient:
    def __init__(self, host="1.2.3.4"):
        self.host = host


class _FakeRequest:
    """Minimal stand-in for a FastAPI Request."""

    def __init__(self, host="1.2.3.4", method="GET", url="http://test/path"):
        self.client = _FakeClient(host)
        self.method = method
        self.url = url
        self.headers = {
            "user-agent": "pytest",
            "x-request-id": "req-123",
        }


def _read_jsonl(path):
    with open(path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_no_boto3_import():
    """The audit_log module must not import boto3/botocore."""
    assert "boto3" not in sys.modules or audit_log.__dict__.get("boto3") is None
    assert not hasattr(audit_log, "boto3")
    assert not hasattr(audit_log, "botocore")


def test_uses_log_dir_env(tmp_path, monkeypatch):
    """Logger should resolve its files under NEURONEWS_LOG_DIR."""
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    logger = SecurityAuditLogger()
    assert logger.events_file == os.path.join(str(tmp_path), "audit_log.jsonl")
    assert logger.metrics_file == os.path.join(str(tmp_path), "audit_metrics.jsonl")


@pytest.mark.asyncio
async def test_log_security_event_writes_event_and_metric(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    logger = SecurityAuditLogger()

    await logger.log_security_event("CUSTOM_EVENT", {"foo": "bar"})

    events = _read_jsonl(logger.events_file)
    assert len(events) == 1
    assert events[0]["event_type"] == "CUSTOM_EVENT"
    assert events[0]["event_data"] == {"foo": "bar"}
    assert events[0]["log_group"] == logger.log_group

    metrics = _read_jsonl(logger.metrics_file)
    assert len(metrics) == 1
    assert metrics[0]["MetricName"] == "SecurityEventCUSTOM_EVENT"
    assert metrics[0]["Namespace"] == "NeuroNews/Security"
    assert metrics[0]["Value"] == 1


@pytest.mark.asyncio
async def test_log_with_request_and_user(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    logger = SecurityAuditLogger()

    request = _FakeRequest()
    user = {"sub": "u1", "email": "a@b.com", "role": "admin"}

    await logger.log_security_event("AUTH_SUCCESS", {}, request, user)

    events = _read_jsonl(logger.events_file)
    assert events[0]["client_ip"] == "1.2.3.4"
    assert events[0]["method"] == "GET"
    assert events[0]["request_id"] == "req-123"
    assert events[0]["user"] == {"id": "u1", "email": "a@b.com", "role": "admin"}


@pytest.mark.asyncio
async def test_helper_methods(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    logger = SecurityAuditLogger()
    request = _FakeRequest()
    user = {"sub": "u1", "email": "a@b.com", "role": "user"}

    await logger.log_auth_failure("bad creds", request)
    await logger.log_auth_success(request, user)
    await logger.log_permission_denied("read:articles", request, user)

    events = _read_jsonl(logger.events_file)
    types = [e["event_type"] for e in events]
    assert types == ["AUTH_FAILURE", "AUTH_SUCCESS", "PERMISSION_DENIED"]
    assert events[0]["event_data"] == {"reason": "bad creds"}
    assert events[2]["event_data"] == {"required_permission": "read:articles"}

    metrics = _read_jsonl(logger.metrics_file)
    metric_names = [m["MetricName"] for m in metrics]
    assert "SecurityEventAUTH_FAILURE" in metric_names
    assert "SecurityEventPERMISSION_DENIED" in metric_names


@pytest.mark.asyncio
async def test_events_appended_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    logger = SecurityAuditLogger()

    await logger.log_security_event("E1", {})
    await logger.log_security_event("E2", {})

    events = _read_jsonl(logger.events_file)
    assert [e["event_type"] for e in events] == ["E1", "E2"]
