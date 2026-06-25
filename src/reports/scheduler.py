"""
APScheduler-based report delivery scheduler.

Jobs
----
weekly_reports   — every Monday at 08:00 UTC
monthly_reports  — 1st of each month at 08:00 UTC

Start/stop
----------
Call start_scheduler() once at app startup (idempotent).
Call stop_scheduler() at shutdown (no-op if not started).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_scheduler: Optional[object] = None


def _deliver_subscriptions(frequency: str) -> None:
    """Fetch all subscriptions matching frequency, generate and email each."""
    from src.reports.subscriptions import list_subscriptions, mark_sent
    from src.reports.email_sender import send_report_email
    from src.reports.generate_report import generate_pdf, generate_csv

    subs = list_subscriptions()
    matching = [s for s in subs if s["frequency"] == frequency]
    logger.info("Scheduler: delivering %s reports (%d subscriptions)", frequency, len(matching))

    for sub in matching:
        try:
            fmt = sub["format"]
            topic = sub["topic"]
            period = "last_7_days" if frequency == "weekly" else "last_30_days"

            report_bytes = generate_pdf(topic, period) if fmt == "pdf" else generate_csv(topic, period)
            token = mark_sent(sub["id"])
            send_report_email(
                to=sub["email"],
                topic=topic,
                period=period,
                frequency=frequency,
                fmt=fmt,
                report_bytes=report_bytes,
                tracking_token=token,
            )
        except Exception:
            logger.exception("Failed to deliver report to %s (sub_id=%s)", sub["email"], sub["id"])


def _weekly_job() -> None:
    _deliver_subscriptions("weekly")
    _deliver_custom_schedules("weekly")


def _monthly_job() -> None:
    _deliver_subscriptions("monthly")
    _deliver_custom_schedules("monthly")


def start_scheduler() -> None:
    """Start the background scheduler (idempotent)."""
    global _scheduler
    if _scheduler is not None:
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.warning("apscheduler not installed — scheduled report delivery disabled")
        return

    sched = BackgroundScheduler(timezone="UTC")
    # Every Monday at 08:00 UTC
    sched.add_job(_weekly_job, CronTrigger(day_of_week="mon", hour=8, minute=0), id="weekly_reports")
    # 1st of each month at 08:00 UTC
    sched.add_job(_monthly_job, CronTrigger(day=1, hour=8, minute=0), id="monthly_reports")

    sched.start()
    _scheduler = sched
    logger.info("Report scheduler started (weekly=Mon 08:00, monthly=1st 08:00 UTC)")


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)  # type: ignore[attr-defined]
    except Exception:
        pass
    _scheduler = None
    logger.info("Report scheduler stopped")


def _deliver_custom_schedules(frequency: str) -> None:
    """Generate and email custom-filter scheduled reports."""
    from src.reports.subscriptions import list_custom_schedules, mark_custom_sent
    from src.reports.email_sender import send_report_email
    from src.reports.generate_report import (
        CustomReportFilter, generate_custom_pdf, generate_custom_csv,
    )

    schedules = [s for s in list_custom_schedules() if s["frequency"] == frequency]
    logger.info("Custom scheduler: %d schedules for frequency=%s", len(schedules), frequency)

    for sched in schedules:
        try:
            f_dict = sched["filters"]
            filt = CustomReportFilter(
                keywords=f_dict.get("keywords", [sched.get("name", "report")]),
                period=f_dict.get("period"),
                date_from=f_dict.get("date_from"),
                date_to=f_dict.get("date_to"),
                sentiment=f_dict.get("sentiment"),
                sentiment_min=f_dict.get("sentiment_min"),
                sentiment_max=f_dict.get("sentiment_max"),
                source=f_dict.get("source"),
                category=f_dict.get("category"),
                limit=f_dict.get("limit", 200),
                report_title=sched["name"],
            )
            fmt = sched["format"]
            report_bytes = generate_custom_pdf(filt) if fmt == "pdf" else generate_custom_csv(filt)

            # Reuse the report subscription token mechanism
            from src.reports.subscriptions import mark_sent, create_subscription, delete_subscription
            # Create ephemeral subscription entry just to get a tracking token
            tmp = create_subscription(sched["email"], sched["name"], frequency, fmt)
            token = mark_sent(tmp["id"])
            delete_subscription(tmp["id"])

            send_report_email(
                to=sched["email"],
                topic=sched["name"],
                period=filt.period or "custom",
                frequency=frequency,
                fmt=fmt,
                report_bytes=report_bytes,
                tracking_token=token,
            )
            mark_custom_sent(sched["id"])
        except Exception:
            logger.exception("Failed to deliver custom report to %s (id=%s)", sched["email"], sched["id"])


def trigger_now(frequency: str) -> int:
    """Manually fire a delivery run (for testing). Returns subscription count processed."""
    from src.reports.subscriptions import list_subscriptions, list_custom_schedules
    subs = [s for s in list_subscriptions() if s["frequency"] == frequency]
    custom = [s for s in list_custom_schedules() if s["frequency"] == frequency]
    _deliver_subscriptions(frequency)
    _deliver_custom_schedules(frequency)
    return len(subs) + len(custom)
