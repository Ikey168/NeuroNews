"""
Alert delivery channels: Email, Slack, Telegram.

Each channel reads its config from env vars and fails soft — a delivery
error is logged but never raises, so one bad channel never blocks others.

Email
-----
    Reuses SMTP env vars from src/reports/email_sender.py:
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS
    ALERT_EMAIL_FROM  (overrides SMTP_FROM for alerts; optional)

Slack
-----
    SLACK_WEBHOOK_URL   Incoming Webhook URL from api.slack.com/apps

Telegram
--------
    TELEGRAM_BOT_TOKEN  Bot token from @BotFather
    TELEGRAM_CHAT_ID    Target chat/channel ID
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def _smtp_cfg(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def send_email_alert(*, to: str, title: str, body: str) -> bool:
    from_addr = _smtp_cfg("ALERT_EMAIL_FROM") or _smtp_cfg("SMTP_FROM", "alerts@noesis.local")
    host = _smtp_cfg("SMTP_HOST", "localhost")
    port = int(_smtp_cfg("SMTP_PORT", "587"))
    user = _smtp_cfg("SMTP_USER")
    password = _smtp_cfg("SMTP_PASSWORD")
    use_ssl = _smtp_cfg("SMTP_SSL", "false").lower() == "true"
    use_tls = _smtp_cfg("SMTP_TLS", "true").lower() == "true" and not use_ssl

    html = f"""<html><body style="font-family:sans-serif;color:#222;max-width:600px;margin:auto">
  <h2 style="color:#e25c3a">&#9888; Noesis Alert</h2>
  <h3>{title}</h3>
  <p style="white-space:pre-wrap">{body}</p>
  <hr><p style="color:#999;font-size:11px">Noesis Knowledge Engine</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Noesis Alert] {title}"
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with cls(host, port) as server:
            if use_tls:
                server.starttls()
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        logger.info("Alert email sent to %s: %s", to, title)
        return True
    except Exception:
        logger.exception("Failed to send alert email to %s", to)
        return False


# ---------------------------------------------------------------------------
# Slack
# ---------------------------------------------------------------------------

def send_slack_alert(*, title: str, body: str) -> bool:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping Slack alert")
        return False

    payload = {
        "text": f"*[Noesis Alert] {title}*",
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": f"Noesis Alert: {title}"}},
            {"type": "section", "text": {"type": "mrkdwn", "text": body}},
        ],
    }
    try:
        req = urllib.request.Request(
            webhook,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        logger.info("Alert sent to Slack: %s", title)
        return True
    except Exception:
        logger.exception("Failed to send Slack alert")
        return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

def send_telegram_alert(*, title: str, body: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set — skipping Telegram alert")
        return False

    text = f"*⚠️ Noesis Alert*\n*{title}*\n\n{body}"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        logger.info("Alert sent to Telegram chat %s: %s", chat_id, title)
        return True
    except Exception:
        logger.exception("Failed to send Telegram alert")
        return False


# ---------------------------------------------------------------------------
# Dispatch to a list of channels
# ---------------------------------------------------------------------------

def dispatch(channels: List[str], title: str, body: str, email: str | None = None) -> dict:
    results: dict = {}
    for ch in channels:
        if ch == "email":
            if email:
                results["email"] = send_email_alert(to=email, title=title, body=body)
            else:
                logger.warning("Email channel requested but no email address on rule")
                results["email"] = False
        elif ch == "slack":
            results["slack"] = send_slack_alert(title=title, body=body)
        elif ch == "telegram":
            results["telegram"] = send_telegram_alert(title=title, body=body)
    return results
