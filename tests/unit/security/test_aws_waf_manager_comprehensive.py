"""Comprehensive tests for src/api/security/local_waf_manager.py."""

import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.security.local_waf_manager import (  # noqa: E402
    ActionType,
    LocalWAFManager,
    SecurityEvent,
    ThreatType,
    WAFRule,
)
from datetime import datetime, timezone  # noqa: E402


@pytest.fixture
def waf(monkeypatch):
    # No AWS creds -> clients stay None; we exercise pure logic + mock as needed
    for var in ("AWS_REGION", "WAF_WEB_ACL_NAME", "WAF_ALLOWED_COUNTRIES", "WAF_RATE_LIMIT"):
        monkeypatch.delenv(var, raising=False)
    return LocalWAFManager()


class TestEnumsAndDataclasses:
    def test_threat_types(self):
        assert ThreatType.SQL_INJECTION.value == "sql_injection"
        assert ThreatType.XSS_ATTACK.value == "xss_attack"

    def test_action_types(self):
        assert ActionType.BLOCK.value == "BLOCK"
        assert ActionType.CAPTCHA.value == "CAPTCHA"

    def test_waf_rule_defaults(self):
        r = WAFRule(name="r", priority=1, action=ActionType.BLOCK,
                    rule_type="managed", description="d")
        assert r.enabled is True
        assert r.metric_name is None

    def test_security_event(self):
        e = SecurityEvent(
            timestamp=datetime.now(timezone.utc), threat_type=ThreatType.XSS_ATTACK,
            source_ip="1.2.3.4", user_agent="ua", request_path="/x",
            action_taken=ActionType.BLOCK, details={},
        )
        assert e.severity == "medium"


class TestInit:
    def test_default_config(self, waf):
        assert waf.region == "us-east-1"
        assert waf.web_acl_name == "NeuroNewsAPIProtection"
        assert "US" in waf.allowed_countries
        assert waf.rate_limit_requests == 2000

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("AWS_REGION", "eu-west-1")
        monkeypatch.setenv("WAF_RATE_LIMIT", "500")
        monkeypatch.setenv("WAF_ALLOWED_COUNTRIES", "US,CA")
        m = LocalWAFManager()
        assert m.region == "eu-west-1"
        assert m.rate_limit_requests == 500
        assert m.allowed_countries == ["US", "CA"]


class TestWafRules:
    def test_get_waf_rules_structure(self, waf):
        rules = waf._get_waf_rules()
        assert isinstance(rules, list)
        assert len(rules) > 0
        # each rule has Name and Priority
        for rule in rules:
            assert "Name" in rule
            assert "Priority" in rule


class TestDetection:
    @pytest.mark.parametrize("payload", [
        "' OR 1=1--",
        "'; DROP TABLE users;--",
        "UNION SELECT password FROM users",
        "1' AND 1=1#",
    ])
    def test_sql_injection_detected(self, waf, payload):
        assert waf.detect_sql_injection(payload) is True

    def test_sql_injection_clean(self, waf):
        assert waf.detect_sql_injection("normal search query about news") is False

    def test_sql_injection_empty(self, waf):
        assert waf.detect_sql_injection("") is False

    @pytest.mark.parametrize("payload", [
        "<script>alert('XSS')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert(document.cookie)",
        "<svg/onload=alert(1)>",
    ])
    def test_xss_detected(self, waf, payload):
        assert waf.detect_xss(payload) is True

    def test_xss_clean(self, waf):
        assert waf.detect_xss("a normal sentence with <b>bold</b> only") is False

    def test_xss_empty(self, waf):
        assert waf.detect_xss("") is False


class TestHealthAndMetrics:
    def test_health_check_no_clients(self, waf):
        waf.wafv2_client = None
        waf.cloudwatch_client = None
        waf.logs_client = None
        health = waf.health_check()
        assert health["overall_status"] == "degraded"
        assert health["components"]["waf_client"] == "unavailable"

    def test_health_check_with_clients(self, waf):
        waf.wafv2_client = MagicMock()
        waf.cloudwatch_client = MagicMock()
        waf.logs_client = MagicMock()
        waf._get_existing_web_acl = MagicMock(return_value=True)
        health = waf.health_check()
        assert health["components"]["waf_client"] == "operational"
        assert health["components"]["web_acl"] == "operational"

    def test_create_web_acl_no_client(self, waf):
        waf.wafv2_client = None
        assert waf.create_web_acl() is False

    def test_get_security_metrics_no_client(self, waf):
        metrics = waf.get_security_metrics()
        assert isinstance(metrics, dict)

    def test_account_id_fallback(self, waf, monkeypatch):
        import api.security.local_waf_manager as mod
        if getattr(mod, "boto3", None) is not None:
            monkeypatch.setattr(mod.boto3, "client", MagicMock(side_effect=Exception("no")))
        assert waf._get_account_id() == "123456789012"
