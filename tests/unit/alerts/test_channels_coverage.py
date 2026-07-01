"""Coverage tests for src/alerts/channels.py.

Exercises the real public API (send_email_alert, send_slack_alert,
send_telegram_alert, dispatch) with external I/O (smtplib, urllib) mocked
where the module looks them up. Assertions are on genuine return values,
call arguments, and dispatch routing.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.alerts.channels as ch  # noqa: E402


# ---------------------------------------------------------------------------
# _smtp_cfg
# ---------------------------------------------------------------------------

def test_smtp_cfg_reads_env_and_strips(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "  mail.example.com  ")
    assert ch._smtp_cfg("SMTP_HOST") == "mail.example.com"


def test_smtp_cfg_default_when_unset(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    assert ch._smtp_cfg("SMTP_HOST", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# send_email_alert
# ---------------------------------------------------------------------------

def _clear_smtp_env(monkeypatch):
    for k in ("ALERT_EMAIL_FROM", "SMTP_FROM", "SMTP_HOST", "SMTP_PORT",
              "SMTP_USER", "SMTP_PASSWORD", "SMTP_SSL", "SMTP_TLS"):
        monkeypatch.delenv(k, raising=False)


def test_send_email_alert_plain_smtp_with_tls_and_login(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "user1")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("SMTP_SSL", "false")
    monkeypatch.setenv("SMTP_FROM", "from@test")

    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    ctx.__exit__.return_value = False
    smtp_cls = MagicMock(return_value=ctx)

    with patch.object(ch.smtplib, "SMTP", smtp_cls) as smtp_mock, \
            patch.object(ch.smtplib, "SMTP_SSL") as ssl_mock:
        ok = ch.send_email_alert(to="dest@test", title="Hi", body="Body text")

    assert ok is True
    # Plain SMTP was chosen (not SSL) with the configured host/port.
    smtp_mock.assert_called_once_with("smtp.test", 2525)
    ssl_mock.assert_not_called()
    # TLS started and login performed with credentials.
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("user1", "secret")
    server.send_message.assert_called_once()
    # The message carries the alert subject and recipient.
    sent_msg = server.send_message.call_args.args[0]
    assert sent_msg["Subject"] == "[Noesis Alert] Hi"
    assert sent_msg["To"] == "dest@test"
    assert sent_msg["From"] == "from@test"


def test_send_email_alert_ssl_no_tls_no_login(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.ssl")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_SSL", "true")
    # SMTP_TLS true but SSL wins -> use_tls becomes False

    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    ctx.__exit__.return_value = False
    ssl_cls = MagicMock(return_value=ctx)

    with patch.object(ch.smtplib, "SMTP_SSL", ssl_cls) as ssl_mock, \
            patch.object(ch.smtplib, "SMTP") as plain_mock:
        ok = ch.send_email_alert(to="dest@test", title="T", body="B")

    assert ok is True
    ssl_mock.assert_called_once_with("smtp.ssl", 465)
    plain_mock.assert_not_called()
    # No TLS when SSL is used; no login without credentials.
    server.starttls.assert_not_called()
    server.login.assert_not_called()
    server.send_message.assert_called_once()


def test_send_email_alert_uses_alert_email_from_override(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("ALERT_EMAIL_FROM", "alerts-override@test")
    monkeypatch.setenv("SMTP_FROM", "ignored@test")

    server = MagicMock()
    ctx = MagicMock()
    ctx.__enter__.return_value = server
    ctx.__exit__.return_value = False

    with patch.object(ch.smtplib, "SMTP", MagicMock(return_value=ctx)):
        ok = ch.send_email_alert(to="d@test", title="T", body="B")

    assert ok is True
    sent = server.send_message.call_args.args[0]
    assert sent["From"] == "alerts-override@test"


def test_send_email_alert_returns_false_on_exception(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_HOST", "smtp.test")

    with patch.object(ch.smtplib, "SMTP", side_effect=OSError("connect refused")):
        ok = ch.send_email_alert(to="d@test", title="T", body="B")

    assert ok is False


# ---------------------------------------------------------------------------
# send_slack_alert
# ---------------------------------------------------------------------------

def test_send_slack_alert_no_webhook_returns_false(monkeypatch):
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)
    assert ch.send_slack_alert(title="T", body="B") is False


def test_send_slack_alert_success_posts_payload(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/abc")

    captured = {}

    def fake_request(url, data=None, headers=None, method=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        captured["method"] = method
        return MagicMock(name="request")

    resp_ctx = MagicMock()
    resp_ctx.__enter__.return_value = MagicMock()
    resp_ctx.__exit__.return_value = False

    with patch.object(ch.urllib.request, "Request", side_effect=fake_request), \
            patch.object(ch.urllib.request, "urlopen", return_value=resp_ctx) as urlopen_mock:
        ok = ch.send_slack_alert(title="MyTitle", body="MyBody")

    assert ok is True
    urlopen_mock.assert_called_once()
    assert captured["url"] == "https://hooks.slack.test/abc"
    assert captured["method"] == "POST"
    payload = json.loads(captured["data"].decode())
    assert payload["text"] == "*[Noesis Alert] MyTitle*"
    assert payload["blocks"][1]["text"]["text"] == "MyBody"


def test_send_slack_alert_returns_false_on_exception(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.test/abc")
    with patch.object(ch.urllib.request, "urlopen", side_effect=OSError("boom")):
        ok = ch.send_slack_alert(title="T", body="B")
    assert ok is False


# ---------------------------------------------------------------------------
# send_telegram_alert
# ---------------------------------------------------------------------------

def test_send_telegram_alert_missing_config_returns_false(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert ch.send_telegram_alert(title="T", body="B") is False


def test_send_telegram_alert_missing_chat_id_returns_false(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert ch.send_telegram_alert(title="T", body="B") is False


def test_send_telegram_alert_success_builds_url_and_payload(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:ABC")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-4567")

    captured = {}

    def fake_request(url, data=None, headers=None, method=None):
        captured["url"] = url
        captured["data"] = data
        captured["method"] = method
        return MagicMock()

    resp_ctx = MagicMock()
    resp_ctx.__enter__.return_value = MagicMock()
    resp_ctx.__exit__.return_value = False

    with patch.object(ch.urllib.request, "Request", side_effect=fake_request), \
            patch.object(ch.urllib.request, "urlopen", return_value=resp_ctx):
        ok = ch.send_telegram_alert(title="Warn", body="Something happened")

    assert ok is True
    assert captured["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert captured["method"] == "POST"
    payload = json.loads(captured["data"].decode())
    assert payload["chat_id"] == "-4567"
    assert payload["parse_mode"] == "Markdown"
    assert "Warn" in payload["text"]
    assert "Something happened" in payload["text"]


def test_send_telegram_alert_returns_false_on_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    with patch.object(ch.urllib.request, "urlopen", side_effect=OSError("net")):
        assert ch.send_telegram_alert(title="T", body="B") is False


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def test_dispatch_email_with_address_calls_send_email():
    with patch.object(ch, "send_email_alert", return_value=True) as m:
        results = ch.dispatch(["email"], "T", "B", email="x@test")
    m.assert_called_once_with(to="x@test", title="T", body="B")
    assert results == {"email": True}


def test_dispatch_email_without_address_records_false():
    with patch.object(ch, "send_email_alert") as m:
        results = ch.dispatch(["email"], "T", "B", email=None)
    m.assert_not_called()
    assert results == {"email": False}


def test_dispatch_slack_and_telegram_routes():
    with patch.object(ch, "send_slack_alert", return_value=True) as slack, \
            patch.object(ch, "send_telegram_alert", return_value=False) as tg:
        results = ch.dispatch(["slack", "telegram"], "T", "B")
    slack.assert_called_once_with(title="T", body="B")
    tg.assert_called_once_with(title="T", body="B")
    assert results == {"slack": True, "telegram": False}


def test_dispatch_unknown_channel_ignored():
    results = ch.dispatch(["carrier_pigeon"], "T", "B")
    assert results == {}


def test_dispatch_all_channels_combined():
    with patch.object(ch, "send_email_alert", return_value=True), \
            patch.object(ch, "send_slack_alert", return_value=True), \
            patch.object(ch, "send_telegram_alert", return_value=True):
        results = ch.dispatch(["email", "slack", "telegram"], "T", "B", email="e@test")
    assert results == {"email": True, "slack": True, "telegram": True}
