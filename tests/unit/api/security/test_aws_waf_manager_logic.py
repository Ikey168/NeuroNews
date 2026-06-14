"""Tests for pure logic of src/api/security/aws_waf_manager.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.security.aws_waf_manager import AWSWAFManager  # noqa: E402


@pytest.fixture
def waf(monkeypatch):
    # No AWS creds -> boto3 clients stay None (offline-safe)
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    mgr = AWSWAFManager()
    mgr.wafv2_client = None
    mgr.cloudwatch_client = None
    mgr.logs_client = None
    return mgr


class TestConfig:
    def test_defaults(self, waf):
        assert "US" in waf.allowed_countries
        assert waf.rate_limit_requests == 2000
        assert waf.web_acl_name

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("WAF_RATE_LIMIT", "500")
        monkeypatch.setenv("WAF_ALLOWED_COUNTRIES", "US,CA")
        mgr = AWSWAFManager()
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


class TestNoClientFallbacks:
    def test_create_web_acl_no_client(self, waf):
        assert waf.create_web_acl() is False

    def test_security_metrics_no_client(self, waf):
        assert "error" in waf.get_security_metrics()

    def test_blocked_requests_no_client(self, waf):
        assert waf.get_blocked_requests() == []

    def test_create_dashboard_no_client(self, waf):
        assert waf.create_security_dashboard() is False
