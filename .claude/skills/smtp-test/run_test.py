"""
smtp-test: end-to-end smoke test for scheduled report email delivery.

1. Starts a local SMTP sink on a random port (no external service needed).
2. Points the email_sender at the sink via env vars.
3. Creates a test subscription in DuckDB.
4. Fires the weekly delivery job directly (no API server needed).
5. Waits for the message to arrive at the sink.
6. Pretty-prints the email headers, body preview, and attachment info.
7. Cleans up the test subscription.

Usage:
    python3 .claude/skills/smtp-test/run_test.py [--to EMAIL] [--topic TOPIC] [--freq weekly|monthly]
"""

from __future__ import annotations

import argparse
import email as email_lib
import os
import sys
import textwrap
from pathlib import Path

# Ensure repo root is on sys.path regardless of CWD
REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
SKILL_DIR = Path(__file__).resolve().parent


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SMTP delivery smoke test for Noesis reports")
    p.add_argument("--to", default="test@noesis.local", help="Recipient email address")
    p.add_argument("--topic", default="AI", help="Report topic keyword")
    p.add_argument("--freq", choices=["weekly", "monthly"], default="weekly")
    p.add_argument("--format", choices=["pdf", "csv"], default="pdf", dest="fmt")
    p.add_argument("--timeout", type=float, default=15.0, help="Seconds to wait for SMTP delivery")
    return p.parse_args()


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _parse_email_summary(raw: str) -> None:
    """Print a readable summary of the captured raw email."""
    msg = email_lib.message_from_string(raw)
    print(f"  From:    {msg['From']}")
    print(f"  To:      {msg['To']}")
    print(f"  Subject: {msg['Subject']}")
    print()

    parts_info = []
    body_shown = False

    for part in msg.walk():
        ct = part.get_content_type()
        cd = part.get("Content-Disposition", "")

        if ct == "text/plain" and not body_shown:
            payload = part.get_payload(decode=True)
            if payload:
                text = payload.decode("utf-8", errors="replace").strip()
                print("  Body (text):")
                for line in textwrap.wrap(text, 70):
                    print(f"    {line}")
                body_shown = True

        elif ct == "text/html" and not body_shown:
            payload = part.get_payload(decode=True)
            if payload:
                html = payload.decode("utf-8", errors="replace")
                # strip tags for preview
                import re
                plain = re.sub(r"<[^>]+>", "", html).strip()
                plain = re.sub(r"\s+", " ", plain)
                print("  Body (html preview):")
                for line in textwrap.wrap(plain[:300], 70):
                    print(f"    {line}")
                body_shown = True

        if "attachment" in cd:
            fname = part.get_filename() or "attachment"
            payload = part.get_payload(decode=True) or b""
            parts_info.append((fname, len(payload), ct))

    if parts_info:
        print()
        print("  Attachments:")
        for fname, size, ct in parts_info:
            print(f"    {fname}  ({size:,} bytes, {ct})")


def main() -> int:
    args = _parse_args()

    # ------------------------------------------------------------------ sink
    _section("1/5  Starting local SMTP sink")
    sys.path.insert(0, str(SKILL_DIR))
    from smtp_sink import start_sink, wait_for_message, stop_sink

    port = start_sink()
    print(f"  SMTP sink listening on 127.0.0.1:{port}")

    # Point email_sender at the sink
    os.environ["SMTP_HOST"] = "127.0.0.1"
    os.environ["SMTP_PORT"] = str(port)
    os.environ["SMTP_TLS"] = "false"
    os.environ["SMTP_SSL"] = "false"
    os.environ.pop("SMTP_USER", None)
    os.environ.pop("SMTP_PASSWORD", None)
    os.environ["SMTP_FROM"] = "reports@noesis.local"
    os.environ["BASE_URL"] = "http://localhost:8000"

    # ----------------------------------------------------------- subscription
    _section("2/5  Creating test subscription")
    from src.reports.subscriptions import create_subscription, delete_subscription

    sub = create_subscription(args.to, args.topic, args.freq, args.fmt)
    sub_id = sub["id"]
    print(f"  id:        {sub_id}")
    print(f"  email:     {sub['email']}")
    print(f"  topic:     {sub['topic']}")
    print(f"  frequency: {sub['frequency']}")
    print(f"  format:    {sub['format']}")

    # ----------------------------------------------------------- delivery
    _section("3/5  Firing delivery")
    from src.reports.scheduler import _deliver_subscriptions

    try:
        _deliver_subscriptions(args.freq)
        print(f"  Delivery function completed for frequency='{args.freq}'")
    except Exception as exc:
        print(f"  ERROR during delivery: {exc}")
        delete_subscription(sub_id)
        stop_sink()
        return 1

    # ----------------------------------------------------------- capture
    _section("4/5  Waiting for SMTP message")
    msg = wait_for_message(timeout=args.timeout)
    if msg is None:
        print(f"  TIMEOUT — no message received within {args.timeout}s")
        delete_subscription(sub_id)
        stop_sink()
        return 1

    print(f"  Message received!  ({len(msg['raw_data'])} raw bytes)")
    print()
    _parse_email_summary(msg["raw_data"])

    # ----------------------------------------------------------- cleanup
    _section("5/5  Cleanup")
    delete_subscription(sub_id)
    stop_sink()
    print(f"  Subscription {sub_id} deleted")
    print(f"  SMTP sink stopped")

    print()
    print("  RESULT: PASS — email delivered end-to-end via SMTP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
