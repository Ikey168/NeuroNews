"""
Report subscription store backed by DuckDB.

Tables
------
report_subscriptions  — one row per active subscription
report_deliveries     — one row per email sent (open tracking)
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database.local_analytics_connector import get_shared_connection, _LOCK

import json

_SCHEMA = """
CREATE TABLE IF NOT EXISTS report_subscriptions (
    id          VARCHAR PRIMARY KEY,
    email       VARCHAR NOT NULL,
    topic       VARCHAR NOT NULL,
    frequency   VARCHAR NOT NULL,   -- 'weekly' | 'monthly'
    format      VARCHAR NOT NULL,   -- 'pdf' | 'csv'
    created_at  TIMESTAMP NOT NULL,
    last_sent   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS report_deliveries (
    token       VARCHAR PRIMARY KEY,
    sub_id      VARCHAR NOT NULL,
    sent_at     TIMESTAMP NOT NULL,
    opened_at   TIMESTAMP,
    open_count  INTEGER NOT NULL DEFAULT 0
);
"""


def _ensure_schema() -> None:
    conn = get_shared_connection()
    with _LOCK:
        for stmt in _SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)


_schema_done = False
_schema_lock = threading.Lock()


def _init():
    global _schema_done
    if _schema_done:
        return
    with _schema_lock:
        if not _schema_done:
            _ensure_schema()
            _schema_done = True


# ---------------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------------

def create_subscription(email: str, topic: str, frequency: str, fmt: str) -> Dict[str, Any]:
    _init()
    sub_id = secrets.token_hex(8)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_shared_connection()
    with _LOCK:
        conn.execute(
            """
            INSERT INTO report_subscriptions (id, email, topic, frequency, format, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [sub_id, email, topic, frequency, fmt, now],
        )
    return _row_to_dict(sub_id, email, topic, frequency, fmt, now, None)


def list_subscriptions(email: Optional[str] = None) -> List[Dict[str, Any]]:
    _init()
    conn = get_shared_connection()
    if email:
        with _LOCK:
            rows = conn.execute(
                "SELECT id, email, topic, frequency, format, created_at, last_sent FROM report_subscriptions WHERE email = ? ORDER BY created_at DESC",
                [email],
            ).fetchall()
    else:
        with _LOCK:
            rows = conn.execute(
                "SELECT id, email, topic, frequency, format, created_at, last_sent FROM report_subscriptions ORDER BY created_at DESC"
            ).fetchall()
    return [_row_to_dict(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]


def get_subscription(sub_id: str) -> Optional[Dict[str, Any]]:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        row = conn.execute(
            "SELECT id, email, topic, frequency, format, created_at, last_sent FROM report_subscriptions WHERE id = ?",
            [sub_id],
        ).fetchone()
    if not row:
        return None
    return _row_to_dict(row[0], row[1], row[2], row[3], row[4], row[5], row[6])


def delete_subscription(sub_id: str) -> bool:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        conn.execute("DELETE FROM report_subscriptions WHERE id = ?", [sub_id])
        conn.execute("DELETE FROM report_deliveries WHERE sub_id = ?", [sub_id])
    return True


def mark_sent(sub_id: str) -> str:
    """Record a delivery; return the tracking token."""
    _init()
    token = secrets.token_urlsafe(16)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_shared_connection()
    with _LOCK:
        conn.execute(
            "INSERT INTO report_deliveries (token, sub_id, sent_at) VALUES (?, ?, ?)",
            [token, sub_id, now],
        )
        conn.execute(
            "UPDATE report_subscriptions SET last_sent = ? WHERE id = ?",
            [now, sub_id],
        )
    return token


def record_open(token: str) -> bool:
    """Increment open count for a delivery token. Returns True if token found."""
    _init()
    conn = get_shared_connection()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    with _LOCK:
        row = conn.execute(
            "SELECT token FROM report_deliveries WHERE token = ?", [token]
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE report_deliveries SET open_count = open_count + 1, opened_at = ? WHERE token = ?",
            [now, token],
        )
    return True


def delivery_stats(sub_id: str) -> Dict[str, Any]:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        rows = conn.execute(
            "SELECT COUNT(*), SUM(open_count), MAX(opened_at) FROM report_deliveries WHERE sub_id = ?",
            [sub_id],
        ).fetchone()
    # COUNT(*) always returns a row; guard satisfies type checker
    total_sent = int(rows[0]) if rows else 0
    total_opens = int(rows[1] or 0) if rows else 0
    last_opened = str(rows[2]) if (rows and rows[2]) else None
    return {
        "total_sent": total_sent,
        "total_opens": total_opens,
        "open_rate": round(total_opens / total_sent, 3) if total_sent else 0.0,
        "last_opened": last_opened,
    }


def _row_to_dict(id, email, topic, frequency, fmt, created_at, last_sent) -> Dict[str, Any]:
    return {
        "id": id,
        "email": email,
        "topic": topic,
        "frequency": frequency,
        "format": fmt,
        "created_at": str(created_at),
        "last_sent": str(last_sent) if last_sent else None,
    }


# ---------------------------------------------------------------------------
# Custom report schedules (issue #54)
# ---------------------------------------------------------------------------

_CUSTOM_SCHEMA = """
CREATE TABLE IF NOT EXISTS custom_report_schedules (
    id           VARCHAR PRIMARY KEY,
    name         VARCHAR NOT NULL,
    email        VARCHAR NOT NULL,
    frequency    VARCHAR NOT NULL,
    format       VARCHAR NOT NULL,
    filters_json VARCHAR NOT NULL,
    created_at   TIMESTAMP NOT NULL,
    last_sent    TIMESTAMP
);
"""

_custom_schema_done = False
_custom_schema_lock = threading.Lock()


def _init_custom() -> None:
    global _custom_schema_done
    if _custom_schema_done:
        return
    with _custom_schema_lock:
        if not _custom_schema_done:
            conn = get_shared_connection()
            with _LOCK:
                conn.execute(_CUSTOM_SCHEMA)
            _custom_schema_done = True


def create_custom_schedule(
    name: str,
    email: str,
    frequency: str,
    fmt: str,
    filters: Dict[str, Any],
) -> Dict[str, Any]:
    _init_custom()
    sched_id = secrets.token_hex(8)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    filters_json = json.dumps(filters)
    conn = get_shared_connection()
    with _LOCK:
        conn.execute(
            """INSERT INTO custom_report_schedules
               (id, name, email, frequency, format, filters_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [sched_id, name, email, frequency, fmt, filters_json, now],
        )
    return _custom_row(sched_id, name, email, frequency, fmt, filters_json, now, None)


def list_custom_schedules(email: Optional[str] = None) -> List[Dict[str, Any]]:
    _init_custom()
    conn = get_shared_connection()
    if email:
        with _LOCK:
            rows = conn.execute(
                "SELECT id,name,email,frequency,format,filters_json,created_at,last_sent"
                " FROM custom_report_schedules WHERE email=? ORDER BY created_at DESC",
                [email],
            ).fetchall()
    else:
        with _LOCK:
            rows = conn.execute(
                "SELECT id,name,email,frequency,format,filters_json,created_at,last_sent"
                " FROM custom_report_schedules ORDER BY created_at DESC"
            ).fetchall()
    return [_custom_row(*r) for r in rows]


def get_custom_schedule(sched_id: str) -> Optional[Dict[str, Any]]:
    _init_custom()
    conn = get_shared_connection()
    with _LOCK:
        row = conn.execute(
            "SELECT id,name,email,frequency,format,filters_json,created_at,last_sent"
            " FROM custom_report_schedules WHERE id=?",
            [sched_id],
        ).fetchone()
    if not row:
        return None
    return _custom_row(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7])


def delete_custom_schedule(sched_id: str) -> None:
    _init_custom()
    conn = get_shared_connection()
    with _LOCK:
        conn.execute("DELETE FROM custom_report_schedules WHERE id=?", [sched_id])


def mark_custom_sent(sched_id: str) -> None:
    _init_custom()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_shared_connection()
    with _LOCK:
        conn.execute(
            "UPDATE custom_report_schedules SET last_sent=? WHERE id=?",
            [now, sched_id],
        )


def _custom_row(id, name, email, frequency, fmt, filters_json, created_at, last_sent) -> Dict[str, Any]:
    return {
        "id": id,
        "name": name,
        "email": email,
        "frequency": frequency,
        "format": fmt,
        "filters": json.loads(filters_json) if filters_json else {},
        "created_at": str(created_at),
        "last_sent": str(last_sent) if last_sent else None,
    }
