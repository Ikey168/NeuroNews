"""
DuckDB-backed alert rules and history store.

Tables
------
alert_rules    — one row per user-defined alert rule
alert_history  — one row per fired alert (for audit / dedup)
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.database.local_analytics_connector import get_shared_connection, _LOCK

_SCHEMA = """
CREATE TABLE IF NOT EXISTS alert_rules (
    id           VARCHAR PRIMARY KEY,
    name         VARCHAR NOT NULL,
    topic        VARCHAR NOT NULL,
    alert_type   VARCHAR NOT NULL,
    threshold    DOUBLE,
    channels     VARCHAR NOT NULL,
    email        VARCHAR,
    created_at   TIMESTAMP NOT NULL,
    last_fired   TIMESTAMP,
    cooldown_min INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS alert_history (
    id         VARCHAR PRIMARY KEY,
    rule_id    VARCHAR NOT NULL,
    alert_type VARCHAR NOT NULL,
    title      VARCHAR NOT NULL,
    body       VARCHAR NOT NULL,
    channels   VARCHAR NOT NULL,
    fired_at   TIMESTAMP NOT NULL
);
"""

_VALID_TYPES = {"breaking_news", "sentiment_shift", "new_event"}
_VALID_CHANNELS = {"email", "slack", "telegram"}

_schema_done = False
_schema_lock = threading.Lock()


def _init() -> None:
    global _schema_done
    if _schema_done:
        return
    with _schema_lock:
        if not _schema_done:
            conn = get_shared_connection()
            with _LOCK:
                for stmt in _SCHEMA.strip().split(";"):
                    s = stmt.strip()
                    if s:
                        conn.execute(s)
            _schema_done = True


# ---------------------------------------------------------------------------
# Rules CRUD
# ---------------------------------------------------------------------------

def create_rule(
    name: str,
    topic: str,
    alert_type: str,
    channels: List[str],
    email: Optional[str] = None,
    threshold: Optional[float] = None,
    cooldown_min: int = 60,
) -> Dict[str, Any]:
    _init()
    rule_id = secrets.token_hex(8)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    channels_json = json.dumps(sorted(set(channels)))
    conn = get_shared_connection()
    with _LOCK:
        conn.execute(
            """INSERT INTO alert_rules
               (id, name, topic, alert_type, threshold, channels, email, created_at, cooldown_min)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [rule_id, name, topic, alert_type, threshold, channels_json, email, now, cooldown_min],
        )
    return _rule_row(rule_id, name, topic, alert_type, threshold, channels_json, email, now, None, cooldown_min)


def list_rules() -> List[Dict[str, Any]]:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        rows = conn.execute(
            "SELECT id,name,topic,alert_type,threshold,channels,email,created_at,last_fired,cooldown_min"
            " FROM alert_rules ORDER BY created_at DESC"
        ).fetchall()
    return [_rule_row(*r) for r in rows]


def get_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        row = conn.execute(
            "SELECT id,name,topic,alert_type,threshold,channels,email,created_at,last_fired,cooldown_min"
            " FROM alert_rules WHERE id=?",
            [rule_id],
        ).fetchone()
    if not row:
        return None
    return _rule_row(row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9])


def delete_rule(rule_id: str) -> None:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        conn.execute("DELETE FROM alert_rules WHERE id=?", [rule_id])


def mark_fired(rule_id: str) -> None:
    _init()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_shared_connection()
    with _LOCK:
        conn.execute("UPDATE alert_rules SET last_fired=? WHERE id=?", [now, rule_id])


def log_history(rule_id: str, alert_type: str, title: str, body: str, channels: List[str]) -> str:
    _init()
    hist_id = secrets.token_hex(8)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conn = get_shared_connection()
    with _LOCK:
        conn.execute(
            "INSERT INTO alert_history (id,rule_id,alert_type,title,body,channels,fired_at)"
            " VALUES (?,?,?,?,?,?,?)",
            [hist_id, rule_id, alert_type, title, body, json.dumps(channels), now],
        )
    return hist_id


def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    _init()
    conn = get_shared_connection()
    with _LOCK:
        rows = conn.execute(
            "SELECT id,rule_id,alert_type,title,body,channels,fired_at"
            " FROM alert_history ORDER BY fired_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return [
        {
            "id": r[0], "rule_id": r[1], "alert_type": r[2],
            "title": r[3], "body": r[4],
            "channels": json.loads(r[5]), "fired_at": str(r[6]),
        }
        for r in rows
    ]


def _rule_row(
    id, name, topic, alert_type, threshold, channels_json, email, created_at, last_fired, cooldown_min
) -> Dict[str, Any]:
    return {
        "id": id, "name": name, "topic": topic, "alert_type": alert_type,
        "threshold": threshold,
        "channels": json.loads(channels_json) if channels_json else [],
        "email": email,
        "created_at": str(created_at),
        "last_fired": str(last_fired) if last_fired else None,
        "cooldown_min": cooldown_min,
    }
