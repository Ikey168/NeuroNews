"""
Detect stance drift between consecutive weekly windows per (source, topic).

Reads the `source_stances` table populated by the nightly stance aggregation
job and writes `stance_drift_events` rows when either:
  - the dominant stance changes across consecutive windows, OR
  - the average confidence delta exceeds CONF_DELTA_THRESHOLD.
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CONF_DELTA_THRESHOLD = 0.2


def _dominant(window_data: dict) -> tuple[str, float]:
    """Return (dominant_stance, avg_confidence) for a single window bucket."""
    best = max(window_data, key=lambda s: window_data[s]["count"])
    total = sum(d["count"] for d in window_data.values()) or 1
    avg_conf = sum(d["conf_sum"] for d in window_data.values()) / total
    return best, avg_conf


def run_drift_detection(conn, lock: threading.Lock) -> dict:
    """
    Compare consecutive weekly windows in `source_stances` and write
    `stance_drift_events` rows for detected pivots.

    Returns {"events_written": n}.
    """
    with lock:
        rows = conn.execute(
            """
            SELECT source, source_type, topic, stance, document_count, confidence, window_start
            FROM source_stances
            ORDER BY source, source_type, topic, window_start
            """
        ).fetchall()

    if not rows:
        logger.info("drift_detector: source_stances is empty — nothing to compare")
        return {"events_written": 0}

    # groups[(src, src_type, topic)][window_start][stance] = {count, conf_sum}
    groups: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {"count": 0, "conf_sum": 0.0})))

    for source, source_type, topic, stance, doc_count, conf, window_start in rows:
        if not window_start or not stance:
            continue
        key = (source, source_type, topic)
        bucket = groups[key][window_start][stance]
        bucket["count"] += doc_count or 0
        bucket["conf_sum"] += (conf or 0.0) * (doc_count or 0)

    events_written = 0
    now = datetime.now(timezone.utc).isoformat()

    for (source, source_type, topic), windows in groups.items():
        sorted_windows = sorted(windows.keys())
        for i in range(len(sorted_windows) - 1):
            w_a = sorted_windows[i]
            w_b = sorted_windows[i + 1]

            stance_a, conf_a = _dominant(windows[w_a])
            stance_b, conf_b = _dominant(windows[w_b])
            conf_delta = abs(conf_b - conf_a)

            if stance_a == stance_b and conf_delta <= CONF_DELTA_THRESHOLD:
                continue

            window_pair = f"{w_a}:{w_b}"
            with lock:
                conn.execute(
                    """
                    DELETE FROM stance_drift_events
                    WHERE source = ? AND source_type = ? AND topic = ? AND window_pair = ?
                    """,
                    [source, source_type, topic, window_pair],
                )
                conn.execute(
                    """
                    INSERT INTO stance_drift_events
                        (source, source_type, topic, from_stance, to_stance,
                         confidence_delta, detected_at, window_pair)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [source, source_type, topic, stance_a, stance_b,
                     round(conf_delta, 4), now, window_pair],
                )
            events_written += 1

    logger.info("drift_detector: detected %d drift events", events_written)
    return {"events_written": events_written}


def run_once() -> None:
    """Entry point for scheduled execution."""
    from src.database.local_analytics_connector import get_shared_connection

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()
    result = run_drift_detection(conn, lock)
    logger.info("Drift detection complete: %s", result)


def schedule_drift_job(scheduler, *, hour: int = 4) -> None:
    """Register a nightly 04:00 UTC drift detection job (runs after stance aggregation)."""
    from apscheduler.triggers.cron import CronTrigger

    scheduler.add_job(
        run_once,
        CronTrigger(hour=hour, minute=0),
        id="stance_drift_detection",
        replace_existing=True,
    )
    logger.info("Stance drift detection scheduled at %02d:00 UTC", hour)
