"""Coverage-focused unit tests for src/reports/email_sender.py.

smtplib is mocked so no real network connection is made. Assertions verify
that configuration is read from the environment, that TLS/SSL/auth branches
behave correctly, and that the constructed MIME message carries the expected
subject, addresses, tracking pixel, and attachment.
"""

import base64
import os
from email.mime.multipart import MIMEMultipart
from unittest.mock import MagicMock, patch

import pytest

from src.reports import email_sender


# ---------------------------------------------------------------------------
# _cfg
# ---------------------------------------------------------------------------
def test_cfg_returns_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_UNSET_KEY", raising=False)
    assert email_sender._cfg("SOME_UNSET_KEY", "fallback") == "fallback"


def test_cfg_strips_whitespace(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "  mail.example.com  ")
    assert email_sender._cfg("SMTP_HOST") == "mail.example.com"


def test_cfg_empty_default(monkeypatch):
    monkeypatch.delenv("MISSING_XYZ", raising=False)
    assert email_sender._cfg("MISSING_XYZ") == ""


# ---------------------------------------------------------------------------
# _send_raw
# ---------------------------------------------------------------------------
def _clear_smtp_env(monkeypatch):
    for key in (
        "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
        "SMTP_SSL", "SMTP_TLS", "SMTP_FROM", "BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_send_raw_plain_smtp_with_starttls(monkeypatch):
    """Default config: plain SMTP + STARTTLS, no login."""
    _clear_smtp_env(monkeypatch)

    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    smtp_cls = MagicMock(return_value=server)

    msg = MIMEMultipart()
    with patch.object(email_sender.smtplib, "SMTP", smtp_cls) as mock_smtp, \
         patch.object(email_sender.smtplib, "SMTP_SSL") as mock_ssl:
        email_sender._send_raw(msg)

    # Uses plain SMTP class, not SSL
    mock_smtp.assert_called_once_with("localhost", 587)
    mock_ssl.assert_not_called()
    # STARTTLS is the default
    server.starttls.assert_called_once_with()
    # No credentials => no login
    server.login.assert_not_called()
    server.send_message.assert_called_once_with(msg)


def test_send_raw_with_ssl_disables_starttls(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_SSL", "true")
    monkeypatch.setenv("SMTP_HOST", "ssl.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")

    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    ssl_cls = MagicMock(return_value=server)

    msg = MIMEMultipart()
    with patch.object(email_sender.smtplib, "SMTP") as mock_plain, \
         patch.object(email_sender.smtplib, "SMTP_SSL", ssl_cls) as mock_ssl:
        email_sender._send_raw(msg)

    # SSL branch selected
    mock_ssl.assert_called_once_with("ssl.example.com", 465)
    mock_plain.assert_not_called()
    # STARTTLS must NOT be called when using SSL
    server.starttls.assert_not_called()
    server.send_message.assert_called_once_with(msg)


def test_send_raw_with_credentials_logs_in(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_USER", "apikey")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_TLS", "false")

    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    smtp_cls = MagicMock(return_value=server)

    msg = MIMEMultipart()
    with patch.object(email_sender.smtplib, "SMTP", smtp_cls):
        email_sender._send_raw(msg)

    server.starttls.assert_not_called()
    server.login.assert_called_once_with("apikey", "secret")
    server.send_message.assert_called_once_with(msg)


def test_send_raw_no_tls_no_login_when_only_user_set(monkeypatch):
    """Login requires BOTH user and password; user only => no login."""
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_USER", "someone")
    monkeypatch.setenv("SMTP_TLS", "false")

    server = MagicMock()
    server.__enter__.return_value = server
    server.__exit__.return_value = False
    smtp_cls = MagicMock(return_value=server)

    msg = MIMEMultipart()
    with patch.object(email_sender.smtplib, "SMTP", smtp_cls):
        email_sender._send_raw(msg)

    server.login.assert_not_called()


# ---------------------------------------------------------------------------
# send_report_email
# ---------------------------------------------------------------------------
def test_send_report_email_pdf_builds_message(monkeypatch):
    _clear_smtp_env(monkeypatch)
    monkeypatch.setenv("SMTP_FROM", "sender@noesis.test")
    monkeypatch.setenv("BASE_URL", "https://noesis.test")

    captured = {}

    def fake_send_raw(msg):
        captured["msg"] = msg

    payload = b"%PDF-1.4 fake pdf bytes"
    with patch.object(email_sender, "_send_raw", side_effect=fake_send_raw):
        email_sender.send_report_email(
            to="dest@example.com",
            topic="Climate Change",
            period="last_7_days",
            frequency="weekly",
            fmt="pdf",
            report_bytes=payload,
            tracking_token="tok123",
        )

    msg = captured["msg"]
    assert msg["To"] == "dest@example.com"
    assert msg["From"] == "sender@noesis.test"
    # Subject: capitalized frequency, topic, and period with underscores replaced
    assert msg["Subject"] == "[Noesis] Weekly report: Climate Change (last 7 days)"

    # Walk the MIME tree
    parts = list(msg.walk())
    content_types = [p.get_content_type() for p in parts]
    assert "text/plain" in content_types
    assert "text/html" in content_types
    assert "application/pdf" in content_types

    # HTML body contains tracking pixel URL built from BASE_URL + token
    html_part = next(p for p in parts if p.get_content_type() == "text/html")
    html_body = html_part.get_payload(decode=True).decode()
    assert "https://noesis.test/api/v1/reports/track/open/tok123" in html_body
    assert "Climate Change" in html_body

    # Attachment: filename slug + base64-encoded original bytes
    pdf_part = next(p for p in parts if p.get_content_type() == "application/pdf")
    disp = pdf_part.get("Content-Disposition")
    assert 'filename="noesis_report_climate_change_last_7_days.pdf"' in disp
    decoded = base64.b64decode(pdf_part.get_payload())
    assert decoded == payload


def test_send_report_email_csv_attachment(monkeypatch):
    _clear_smtp_env(monkeypatch)

    captured = {}
    with patch.object(email_sender, "_send_raw", side_effect=lambda m: captured.update(msg=m)):
        email_sender.send_report_email(
            to="csv@example.com",
            topic="AI News",
            period="last_30_days",
            frequency="monthly",
            fmt="csv",
            report_bytes=b"col1,col2\n1,2\n",
            tracking_token="tok-csv",
        )

    msg = captured["msg"]
    csv_part = next(p for p in msg.walk() if p.get_content_type() == "text/csv")
    disp = csv_part.get("Content-Disposition")
    # Slug lowercases and replaces spaces with underscores
    assert 'filename="noesis_report_ai_news_last_30_days.csv"' in disp


def test_send_report_email_uses_default_from_and_base_url(monkeypatch):
    _clear_smtp_env(monkeypatch)

    captured = {}
    with patch.object(email_sender, "_send_raw", side_effect=lambda m: captured.update(msg=m)):
        email_sender.send_report_email(
            to="x@example.com",
            topic="Topic",
            period="p",
            frequency="daily",
            fmt="pdf",
            report_bytes=b"data",
            tracking_token="tk",
        )

    msg = captured["msg"]
    assert msg["From"] == "reports@noesis.local"
    html_part = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    html_body = html_part.get_payload(decode=True).decode()
    assert "http://localhost:8000/api/v1/reports/track/open/tk" in html_body


def test_send_report_email_logs_and_propagates_send_error(monkeypatch, caplog):
    _clear_smtp_env(monkeypatch)

    with patch.object(email_sender, "_send_raw", side_effect=RuntimeError("smtp down")):
        with pytest.raises(RuntimeError, match="smtp down"):
            email_sender.send_report_email(
                to="x@example.com",
                topic="T",
                period="p",
                frequency="daily",
                fmt="pdf",
                report_bytes=b"d",
                tracking_token="tk",
            )


def test_send_report_email_logs_success(monkeypatch, caplog):
    _clear_smtp_env(monkeypatch)

    import logging
    with patch.object(email_sender, "_send_raw"):
        with caplog.at_level(logging.INFO, logger="src.reports.email_sender"):
            email_sender.send_report_email(
                to="log@example.com",
                topic="LogTopic",
                period="p",
                frequency="daily",
                fmt="pdf",
                report_bytes=b"d",
                tracking_token="logtok",
            )

    assert any("Report email sent to log@example.com" in r.message for r in caplog.records)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
