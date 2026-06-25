"""
Alert dispatcher — ties store + detector + channels together.

An APScheduler job calls `poll_and_dispatch()` every 5 minutes.
Fired alerts are also pushed to an in-process SSE queue so the
frontend stream endpoint can relay them in real time.

SSE queue
---------
`get_sse_queue()` returns an asyncio.Queue per connected client.
`register_sse_client()` / `unregister_sse_client()` manage the set.
`_push_sse(event)` broadcasts to all registered queues.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SSE fan-out registry
# ---------------------------------------------------------------------------

_sse_clients: Set[asyncio.Queue] = set()


def register_sse_client(q: asyncio.Queue) -> None:
    _sse_clients.add(q)
    logger.debug("SSE client registered (%d total)", len(_sse_clients))


def unregister_sse_client(q: asyncio.Queue) -> None:
    _sse_clients.discard(q)
    logger.debug("SSE client disconnected (%d remaining)", len(_sse_clients))


def _push_sse(event: Dict[str, Any]) -> None:
    """Non-async fan-out: put on every registered queue, drop if full."""
    for q in list(_sse_clients):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ---------------------------------------------------------------------------
# Cooldown check
# ---------------------------------------------------------------------------

def _is_cooled_down(rule: Dict[str, Any]) -> bool:
    last = rule.get("last_fired")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(str(last))
    except ValueError:
        return True
    cooldown = timedelta(minutes=int(rule.get("cooldown_min", 60)))
    return datetime.now(timezone.utc).replace(tzinfo=None) - last_dt >= cooldown


# ---------------------------------------------------------------------------
# Core dispatch
# ---------------------------------------------------------------------------

def poll_and_dispatch() -> List[Dict[str, Any]]:
    """Check every active alert rule; fire channels for triggered ones."""
    from src.alerts.store import list_rules, mark_fired, log_history
    from src.alerts.detector import run_all_checks
    from src.alerts.channels import dispatch

    fired = []
    rules = list_rules()

    for rule in rules:
        if not _is_cooled_down(rule):
            continue

        result = run_all_checks(rule["topic"], rule["alert_type"], rule.get("threshold"))
        if not result["triggered"]:
            continue

        title = result["title"]
        body = result["body"]
        channels: List[str] = rule["channels"]
        email: Optional[str] = rule.get("email")

        # Dispatch to external channels (fail-soft per channel)
        delivery = dispatch(channels, title, body, email=email)

        # Record in history
        hist_id = log_history(rule["id"], rule["alert_type"], title, body, channels)
        mark_fired(rule["id"])

        event = {
            "id": hist_id,
            "rule_id": rule["id"],
            "rule_name": rule["name"],
            "alert_type": rule["alert_type"],
            "topic": rule["topic"],
            "title": title,
            "body": body,
            "channels": channels,
            "delivery": delivery,
            "fired_at": datetime.now(timezone.utc).isoformat(),
        }

        # Push to SSE clients
        _push_sse(event)
        fired.append(event)
        logger.info("Alert fired: %s (rule=%s)", title, rule["id"])

    return fired


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

_scheduler: Optional[Any] = None


def start_alert_scheduler() -> None:
    """Start the background poll job (every 5 minutes). Idempotent."""
    global _scheduler
    if _scheduler is not None:
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning("apscheduler missing — real-time alert polling disabled")
        return

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(poll_and_dispatch, IntervalTrigger(minutes=5), id="alert_poll")
    sched.start()
    _scheduler = sched
    logger.info("Alert scheduler started (polling every 5 min)")


def stop_alert_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception:
        pass
    _scheduler = None
