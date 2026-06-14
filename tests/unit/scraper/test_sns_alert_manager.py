"""Tests for src/scraper/sns_alert_manager.py (local file-based alerting)."""

import json
import os
import sys
import time

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.sns_alert_manager import (  # noqa: E402
    Alert,
    AlertSeverity,
    AlertType,
    LocalAlertManager,
    SNSAlertManager,
)


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURONEWS_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("NEURONEWS_ALERT_WEBHOOK_URL", raising=False)
    return LocalAlertManager(max_alerts_per_window=3, rate_limit_window=3600)


def _read_alerts(mgr):
    if not os.path.exists(mgr.alerts_file):
        return []
    with open(mgr.alerts_file) as f:
        return [json.loads(line) for line in f if line.strip()]


class TestAlertDataclass:
    def test_to_message(self):
        a = Alert(AlertType.SCRAPER_FAILURE, AlertSeverity.ERROR, "t", "m",
                  time.time(), {"k": "v"})
        msg = json.loads(a.to_message())
        assert msg["severity"] == "ERROR"
        assert msg["alert_type"] == "scraper_failure"
        assert msg["metadata"] == {"k": "v"}

    def test_to_sns_message_alias(self):
        a = Alert(AlertType.SYSTEM_ERROR, AlertSeverity.INFO, "t", "m",
                  time.time(), {})
        assert a.to_sns_message() == a.to_message()


class TestSendAlert:
    @pytest.mark.asyncio
    async def test_send_writes_file(self, mgr):
        a = Alert(AlertType.SYSTEM_ERROR, AlertSeverity.INFO, "Hi", "msg",
                  time.time(), {})
        assert await mgr.send_alert(a) is True
        records = _read_alerts(mgr)
        assert len(records) == 1
        assert records[0]["title"] == "Hi"
        assert records[0]["message_id"].startswith("local-")

    @pytest.mark.asyncio
    async def test_rate_limiting_mutes(self, mgr):
        for i in range(3):
            a = Alert(AlertType.SYSTEM_ERROR, AlertSeverity.INFO, f"a{i}", "m",
                      time.time(), {})
            assert await mgr.send_alert(a) is True
        # 4th exceeds the window limit -> rate limited
        a = Alert(AlertType.SYSTEM_ERROR, AlertSeverity.INFO, "over", "m",
                  time.time(), {})
        assert await mgr.send_alert(a) is False
        assert mgr.muted_until > time.time()

    @pytest.mark.asyncio
    async def test_force_bypasses_mute(self, mgr):
        mgr.muted_until = time.time() + 1000
        a = Alert(AlertType.SYSTEM_ERROR, AlertSeverity.INFO, "forced", "m",
                  time.time(), {})
        assert await mgr.send_alert(a, force=True) is True

    @pytest.mark.asyncio
    async def test_muted_blocks_without_force(self, mgr):
        mgr.muted_until = time.time() + 1000
        a = Alert(AlertType.SYSTEM_ERROR, AlertSeverity.INFO, "x", "m",
                  time.time(), {})
        assert await mgr.send_alert(a) is False


class TestRateLimitHelpers:
    def test_is_within_rate_limit(self, mgr):
        assert mgr._is_within_rate_limit() is True
        mgr.alert_history = [time.time()] * 3
        assert mgr._is_within_rate_limit() is False

    def test_cleanup_old_alerts(self, mgr):
        mgr.alert_history = [time.time() - 99999, time.time()]
        mgr._cleanup_old_alerts()
        assert len(mgr.alert_history) == 1


class TestConvenienceAlerts:
    @pytest.mark.asyncio
    async def test_scraper_failure_severity(self, mgr):
        await mgr.alert_scraper_failure("u", "boom", retry_count=5)
        rec = _read_alerts(mgr)[-1]
        assert rec["severity"] == "ERROR"
        assert rec["alert_type"] == "scraper_failure"

    @pytest.mark.asyncio
    async def test_high_failure_rate_critical(self, mgr):
        await mgr.alert_high_failure_rate(90.0, 24, 90, 100)
        rec = _read_alerts(mgr)[-1]
        assert rec["severity"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_captcha_blocking(self, mgr):
        await mgr.alert_captcha_blocking("u", 7, 2)
        assert _read_alerts(mgr)[-1]["alert_type"] == "captcha_blocking"

    @pytest.mark.asyncio
    async def test_ip_blocking_truncates(self, mgr):
        await mgr.alert_ip_blocking("u", [f"1.1.1.{i}" for i in range(10)], 1)
        rec = _read_alerts(mgr)[-1]
        assert rec["alert_type"] == "ip_blocking"
        assert "..." in rec["message"]

    @pytest.mark.asyncio
    async def test_performance_and_system(self, mgr):
        await mgr.alert_performance_degradation(40000, 30000, 1)
        await mgr.alert_system_error("KeyError", "missing", "scraper")
        types = {r["alert_type"] for r in _read_alerts(mgr)}
        assert "performance_degradation" in types
        assert "system_error" in types

    @pytest.mark.asyncio
    async def test_test_alert_system(self, mgr):
        assert await mgr.test_alert_system() is True


class TestThresholdSetters:
    def test_setters(self, mgr):
        mgr.set_failure_rate_threshold(75.0)
        mgr.set_consecutive_failure_threshold(8)
        mgr.set_response_time_threshold(12345)
        assert mgr.failure_rate_threshold == 75.0
        assert mgr.consecutive_failure_threshold == 8
        assert mgr.response_time_threshold == 12345


def test_sns_alias_is_local():
    assert SNSAlertManager is LocalAlertManager
