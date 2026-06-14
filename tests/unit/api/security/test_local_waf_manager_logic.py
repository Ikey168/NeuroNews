"""Tests for pure logic of src/api/security/local_waf_manager.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.security.local_waf_manager import (  # noqa: E402
    ActionType,
    LocalWAFManager,
    SecurityEvent,
    ThreatType,
)


@pytest.fixture
def waf(monkeypatch, tmp_path):
    # Persist local WAF state under a temp dir (fully offline, no AWS)
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    return LocalWAFManager()


class TestConfig:
    def test_defaults(self, waf):
        assert "US" in waf.allowed_countries
        assert waf.rate_limit_requests == 2000
        assert waf.web_acl_name

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("WAF_RATE_LIMIT", "500")
        monkeypatch.setenv("WAF_ALLOWED_COUNTRIES", "US,CA")
        mgr = LocalWAFManager()
        assert mgr.rate_limit_requests == 500
        assert mgr.allowed_countries == ["US", "CA"]


class TestSqlInjectionDetection:
    @pytest.mark.parametrize("payload", [
        "' OR 1=1",
        "' AND 1=1",
        "1 UNION SELECT password FROM users",
        "'; DROP TABLE users",
        "DELETE FROM accounts",
        "INSERT INTO logs VALUES(1)",
        "admin'--",
    ])
    def test_detects_attacks(self, waf, payload):
        assert waf._detect_sql_injection(payload) is True

    @pytest.mark.parametrize("payload", [
        "",
        "a normal search query about cats",
        "the union of two sets is selected later",
    ])
    def test_allows_clean(self, waf, payload):
        # "union ... select" with words between should not trigger the strict pattern
        assert waf._detect_sql_injection(payload) is False


class TestXssDetection:
    @pytest.mark.parametrize("payload", [
        "<script>alert(1)</script>",
        "</script>",
        "javascript:alert(1)",
        '<img src=x onerror=alert(1)>',
        '<svg onload=alert(1)>',
        "<iframe src=evil></iframe>",
        "document.cookie",
        '<a onclick="x">',
    ])
    def test_detects_attacks(self, waf, payload):
        assert waf._detect_xss(payload) is True

    @pytest.mark.parametrize("payload", ["", "just some plain text", "a < b and c > d"])
    def test_allows_clean(self, waf, payload):
        assert waf._detect_xss(payload) is False


class TestLocalOperations:
    def test_create_web_acl_writes_local_config(self, waf):
        assert waf.create_web_acl() is True
        assert os.path.exists(waf.web_acl_file)
        assert waf._get_existing_web_acl() is True

    def test_security_metrics_no_error(self, waf):
        metrics = waf.get_security_metrics()
        assert "error" not in metrics
        assert "SQLInjectionBlocked" in metrics["metrics"]

    def test_blocked_requests_empty_initially(self, waf):
        assert waf.get_blocked_requests() == []

    def test_create_dashboard_writes_file(self, waf):
        assert waf.create_security_dashboard() is True
        assert os.path.exists(waf.dashboard_file)

    def test_setup_logging(self, waf):
        assert waf.setup_logging() is True

    def test_health_check_healthy(self, waf):
        health = waf.health_check()
        assert health["overall_status"] == "healthy"
        assert health["components"]["waf_engine"] == "operational"

    def test_record_event_tracks_metrics_and_blocked(self, waf):
        event = SecurityEvent(
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            threat_type=ThreatType.SQL_INJECTION,
            source_ip="1.2.3.4",
            user_agent="curl",
            request_path="/api/x",
            action_taken=ActionType.BLOCK,
            details={"method": "GET", "country": "US"},
        )
        waf.record_event(event)
        assert waf.get_security_metrics()["metrics"]["SQLInjectionBlocked"][
            "blocked_requests"
        ] == 1
        blocked = waf.get_blocked_requests()
        assert len(blocked) == 1
        assert blocked[0]["client_ip"] == "1.2.3.4"
        assert os.path.exists(waf.events_file)
