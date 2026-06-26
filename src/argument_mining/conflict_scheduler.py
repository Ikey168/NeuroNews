"""
Nightly conflict-graph batch runner (issue #112).

Run directly:
    python -m src.argument_mining.conflict_scheduler

Or via APScheduler:
    from src.argument_mining.conflict_scheduler import schedule_conflict_job
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


def run_once(limit: int = 300) -> dict:
    """Run one pass of the conflict detection batch and return summary counts."""
    from src.database.local_analytics_connector import get_shared_connection
    from src.argument_mining.conflict_graph import compute_claim_conflicts

    conn = get_shared_connection()
    lock = getattr(conn, "_lock", None) or threading.Lock()
    return compute_claim_conflicts(conn, lock, limit=limit)


def schedule_conflict_job(scheduler: object, hour: int = 1) -> None:
    """Register a nightly APScheduler job at *hour* UTC (default 01:00)."""
    from apscheduler.triggers.cron import CronTrigger  # type: ignore[import]

    scheduler.add_job(  # type: ignore[attr-defined]
        run_once,
        trigger=CronTrigger(hour=hour, minute=0),
        id="conflict_graph_nightly",
        replace_existing=True,
        max_instances=1,
    )
    logger.info("Scheduled nightly conflict-graph computation at %02d:00 UTC", hour)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    summary = run_once()
    print(f"Done: {summary}")
