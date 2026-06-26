"""
Local resource monitor — Issue #334.

Samples system-wide CPU, memory, and disk metrics plus this process's RSS
using psutil, stores snapshots in the ``resource_metrics`` DuckDB table, and
exposes query helpers for the API routes.

A background daemon thread fires every ``COLLECT_INTERVAL_SECONDS`` and calls
:func:`collect_and_store`.  Start it with :func:`start_background_collector`.
The collector is idempotent — calling start twice is safe.

Standalone usage::

    python3 -m src.monitoring.resource_monitor

returns a single JSON sample to stdout and exits.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)

COLLECT_INTERVAL_SECONDS: int = 60
_TABLE = "resource_metrics"

_collector_started = False
_collector_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resource_metrics (
    id           VARCHAR PRIMARY KEY,
    sampled_at   TIMESTAMP NOT NULL,
    metric_name  VARCHAR NOT NULL,
    value        DOUBLE NOT NULL,
    unit         VARCHAR NOT NULL,
    pid          INTEGER,
    process_name VARCHAR
);
"""


def ensure_schema(conn: Any) -> None:
    conn.execute(SCHEMA_SQL)


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def collect_sample() -> List[Dict[str, Any]]:
    """
    Read current system and process metrics via psutil.

    Returns a list of metric dicts:
        {metric_name, value, unit, pid, process_name, sampled_at}
    """
    now = datetime.now(timezone.utc)
    pid = os.getpid()
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
        rss_mb = proc.memory_info().rss / (1024 * 1024)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        proc_name = "unknown"
        rss_mb = 0.0

    # Disk: use the repo root's filesystem, fall back to "/"
    try:
        from pathlib import Path
        _repo = Path(__file__).resolve().parents[2]
        disk = psutil.disk_usage(str(_repo))
    except Exception:
        disk = psutil.disk_usage("/")

    rows = [
        {
            "metric_name": "cpu_percent",
            "value": psutil.cpu_percent(interval=0.1),
            "unit": "%",
            "pid": None,
            "process_name": None,
        },
        {
            "metric_name": "memory_percent",
            "value": psutil.virtual_memory().percent,
            "unit": "%",
            "pid": None,
            "process_name": None,
        },
        {
            "metric_name": "memory_rss_mb",
            "value": round(rss_mb, 2),
            "unit": "MB",
            "pid": pid,
            "process_name": proc_name,
        },
        {
            "metric_name": "disk_used_gb",
            "value": round(disk.used / (1024 ** 3), 3),
            "unit": "GB",
            "pid": None,
            "process_name": None,
        },
        {
            "metric_name": "disk_free_gb",
            "value": round(disk.free / (1024 ** 3), 3),
            "unit": "GB",
            "pid": None,
            "process_name": None,
        },
        {
            "metric_name": "disk_percent",
            "value": disk.percent,
            "unit": "%",
            "pid": None,
            "process_name": None,
        },
    ]
    for r in rows:
        r["sampled_at"] = now
    return rows


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def store_sample(conn: Any, rows: List[Dict[str, Any]]) -> None:
    """Write *rows* (from :func:`collect_sample`) into the DuckDB table."""
    ensure_schema(conn)
    conn.executemany(
        f"""
        INSERT INTO {_TABLE}
            (id, sampled_at, metric_name, value, unit, pid, process_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                str(uuid.uuid4()),
                r["sampled_at"],
                r["metric_name"],
                r["value"],
                r["unit"],
                r["pid"],
                r["process_name"],
            )
            for r in rows
        ],
    )


def collect_and_store(conn: Any) -> List[Dict[str, Any]]:
    """Sample metrics and persist them. Returns the collected rows."""
    rows = collect_sample()
    try:
        store_sample(conn, rows)
    except Exception as exc:
        logger.warning("Failed to store resource metrics: %s", exc)
    return rows


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_metrics(
    conn: Any,
    metric_name: Optional[str] = None,
    n: int = 100,
    since_minutes: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Return the most recent metric rows, newest first.

    Args:
        metric_name:    Filter to one metric (e.g. ``"cpu_percent"``).
                        ``None`` returns all metrics.
        n:              Maximum rows (default 100).
        since_minutes:  If set, only return rows from the last N minutes.
    """
    ensure_schema(conn)
    where_parts = []
    params: List[Any] = []

    if metric_name:
        where_parts.append("metric_name = ?")
        params.append(metric_name)
    if since_minutes is not None:
        where_parts.append(
            f"sampled_at >= CURRENT_TIMESTAMP - INTERVAL '{since_minutes} minutes'"
        )

    where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
    params.append(n)
    rows = conn.execute(
        f"""
        SELECT sampled_at, metric_name, value, unit, pid, process_name
        FROM {_TABLE}
        {where}
        ORDER BY sampled_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()

    return [
        {
            "sampled_at": str(r[0]),
            "metric_name": r[1],
            "value": r[2],
            "unit": r[3],
            "pid": r[4],
            "process_name": r[5],
        }
        for r in rows
    ]


def get_summary(conn: Any) -> Dict[str, Any]:
    """
    Return 1h and 24h averages for each metric.

    Returns::

        {
          "1h":  {"cpu_percent": {"avg": 12.3, "min": 5.1, "max": 40.2, "unit": "%"}, ...},
          "24h": {...},
          "sampled_at": "<iso timestamp>"
        }
    """
    ensure_schema(conn)

    def _window(hours: int) -> Dict[str, Dict[str, Any]]:
        rows = conn.execute(
            f"""
            SELECT
                metric_name,
                AVG(value)  AS avg_val,
                MIN(value)  AS min_val,
                MAX(value)  AS max_val,
                MAX(unit)   AS unit
            FROM {_TABLE}
            WHERE sampled_at >= CURRENT_TIMESTAMP - INTERVAL '{hours * 60} minutes'
            GROUP BY metric_name
            ORDER BY metric_name
            """
        ).fetchall()
        return {
            r[0]: {
                "avg": round(r[1], 3) if r[1] is not None else None,
                "min": round(r[2], 3) if r[2] is not None else None,
                "max": round(r[3], 3) if r[3] is not None else None,
                "unit": r[4],
            }
            for r in rows
        }

    return {
        "1h": _window(1),
        "24h": _window(24),
        "sampled_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Background collector
# ---------------------------------------------------------------------------

def _run_collector(interval: int) -> None:
    from src.database.local_analytics_connector import get_shared_connection
    conn = get_shared_connection()
    while True:
        try:
            collect_and_store(conn)
        except Exception as exc:
            logger.warning("Resource collector error: %s", exc)
        time.sleep(interval)


def start_background_collector(interval: int = COLLECT_INTERVAL_SECONDS) -> None:
    """
    Start the background metric-collection daemon thread.

    Idempotent — calling more than once is safe.
    """
    global _collector_started
    with _collector_lock:
        if _collector_started:
            return
        t = threading.Thread(
            target=_run_collector,
            args=(interval,),
            daemon=True,
            name="resource-monitor",
        )
        t.start()
        _collector_started = True
        logger.info("Resource monitor started (interval=%ds)", interval)


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    rows = collect_sample()
    # Print as a tidy table
    print(f"{'metric':<22} {'value':>10}  {'unit':<5}")
    print("-" * 42)
    for r in rows:
        print(f"{r['metric_name']:<22} {r['value']:>10.3f}  {r['unit']:<5}")
    print()
    print(json.dumps(
        {r["metric_name"]: {"value": r["value"], "unit": r["unit"]} for r in rows},
        indent=2,
    ))
