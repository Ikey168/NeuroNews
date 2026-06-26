"""
Nightly follow-through batch runner for position tracking (issue #111).

Run directly:
    python -m src.argument_mining.followthrough_scheduler

Or via APScheduler:
    from src.argument_mining.followthrough_scheduler import schedule_followthrough_job
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def run_once(limit: int = 50) -> dict:
    """Run one pass of the follow-through batch and return summary counts."""
    from src.database.local_analytics_connector import get_shared_connection
    from src.argument_mining.position_tracker import run_followthrough_batch

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()
    return run_followthrough_batch(conn, lock, limit=limit)


def schedule_followthrough_job(scheduler: object, hour: int = 3) -> None:
    """Register a nightly APScheduler job at *hour* UTC (defaults to 03:00)."""
    from apscheduler.triggers.cron import CronTrigger  # type: ignore[import]

    scheduler.add_job(  # type: ignore[attr-defined]
        run_once,
        trigger=CronTrigger(hour=hour, minute=0),
        id="followthrough_nightly",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled nightly follow-through check at %02d:00 UTC", hour)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = run_once()
    print(f"Done: {summary}")
