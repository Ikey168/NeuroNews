"""Coverage tests for src/reports/scheduler.py.

The scheduler imports its collaborators lazily *inside* each function via
``from src.reports.subscriptions import ...`` / ``from src.reports.email_sender
import ...`` / ``from src.reports.generate_report import ...``. We therefore patch
those symbols on the collaborator modules so the real scheduler code paths run
against fakes (no DB, no SMTP, no PDF rendering).

apscheduler is genuinely optional and not installed in this environment, so
``start_scheduler`` normally takes the ImportError branch. To exercise the real
add_job/start path we inject a fake ``apscheduler`` package into sys.modules.
"""
from __future__ import annotations

import sys
import types

import pytest

import src.reports.scheduler as sched
import src.reports.subscriptions as subscriptions
import src.reports.email_sender as email_sender
import src.reports.generate_report as generate_report


@pytest.fixture(autouse=True)
def reset_scheduler_singleton():
    sched._scheduler = None
    yield
    sched._scheduler = None


# ---------------------------------------------------------------------------
# _deliver_subscriptions
# ---------------------------------------------------------------------------

def test_deliver_subscriptions_pdf_and_filtering(monkeypatch):
    subs = [
        {"id": 1, "email": "a@x.com", "topic": "AI", "frequency": "weekly", "format": "pdf"},
        {"id": 2, "email": "b@x.com", "topic": "ML", "frequency": "monthly", "format": "csv"},
    ]
    sent = []
    monkeypatch.setattr(subscriptions, "list_subscriptions", lambda: subs)
    monkeypatch.setattr(subscriptions, "mark_sent", lambda sub_id: f"tok-{sub_id}")
    monkeypatch.setattr(generate_report, "generate_pdf", lambda topic, period: b"PDF")
    monkeypatch.setattr(generate_report, "generate_csv", lambda topic, period: b"CSV")
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.append(kw))

    sched._deliver_subscriptions("weekly")

    # Only the weekly PDF subscription should be delivered.
    assert len(sent) == 1
    call = sent[0]
    assert call["to"] == "a@x.com"
    assert call["topic"] == "AI"
    assert call["frequency"] == "weekly"
    assert call["fmt"] == "pdf"
    assert call["period"] == "last_7_days"
    assert call["report_bytes"] == b"PDF"
    assert call["tracking_token"] == "tok-1"


def test_deliver_subscriptions_monthly_csv_period(monkeypatch):
    subs = [{"id": 5, "email": "c@x.com", "topic": "Chips", "frequency": "monthly", "format": "csv"}]
    sent = []
    monkeypatch.setattr(subscriptions, "list_subscriptions", lambda: subs)
    monkeypatch.setattr(subscriptions, "mark_sent", lambda sub_id: "tok")
    monkeypatch.setattr(generate_report, "generate_pdf", lambda t, p: b"PDF")
    monkeypatch.setattr(generate_report, "generate_csv", lambda t, p: b"CSV")
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.append(kw))

    sched._deliver_subscriptions("monthly")

    assert len(sent) == 1
    assert sent[0]["period"] == "last_30_days"
    assert sent[0]["fmt"] == "csv"
    assert sent[0]["report_bytes"] == b"CSV"


def test_deliver_subscriptions_exception_is_swallowed(monkeypatch):
    subs = [{"id": 9, "email": "e@x.com", "topic": "T", "frequency": "weekly", "format": "pdf"}]
    monkeypatch.setattr(subscriptions, "list_subscriptions", lambda: subs)
    monkeypatch.setattr(subscriptions, "mark_sent", lambda sub_id: "tok")

    def boom(topic, period):
        raise RuntimeError("render failed")

    monkeypatch.setattr(generate_report, "generate_pdf", boom)
    calls = []
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: calls.append(kw))

    # Must not raise even though generate_pdf blows up.
    sched._deliver_subscriptions("weekly")
    assert calls == []


# ---------------------------------------------------------------------------
# _deliver_custom_schedules
# ---------------------------------------------------------------------------

def test_deliver_custom_schedules_success(monkeypatch):
    schedules = [
        {
            "id": 11,
            "email": "cust@x.com",
            "name": "My Custom Report",
            "frequency": "weekly",
            "format": "pdf",
            "filters": {"keywords": ["ai"], "period": "last_7_days", "limit": 50},
        },
        {  # different frequency -> filtered out
            "id": 12,
            "email": "no@x.com",
            "name": "Monthly One",
            "frequency": "monthly",
            "format": "csv",
            "filters": {},
        },
    ]
    sent = []
    marked_custom = []
    created_subs = []
    deleted_subs = []

    monkeypatch.setattr(subscriptions, "list_custom_schedules", lambda: schedules)
    monkeypatch.setattr(subscriptions, "mark_custom_sent", lambda sid: marked_custom.append(sid))
    monkeypatch.setattr(
        subscriptions, "create_subscription",
        lambda email, name, freq, fmt: created_subs.append((email, name)) or {"id": 999},
    )
    monkeypatch.setattr(subscriptions, "mark_sent", lambda sub_id: "custom-tok")
    monkeypatch.setattr(subscriptions, "delete_subscription", lambda sid: deleted_subs.append(sid))
    monkeypatch.setattr(generate_report, "generate_custom_pdf", lambda filt: b"CPDF")
    monkeypatch.setattr(generate_report, "generate_custom_csv", lambda filt: b"CCSV")
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.append(kw))

    sched._deliver_custom_schedules("weekly")

    assert len(sent) == 1
    call = sent[0]
    assert call["to"] == "cust@x.com"
    assert call["topic"] == "My Custom Report"
    assert call["fmt"] == "pdf"
    assert call["report_bytes"] == b"CPDF"
    assert call["tracking_token"] == "custom-tok"
    assert call["period"] == "last_7_days"
    assert marked_custom == [11]
    assert deleted_subs == [999]


def test_deliver_custom_schedules_defaults_keywords_from_name(monkeypatch):
    """When filters lack 'keywords', the schedule name is used as the keyword."""
    captured = {}
    schedules = [
        {
            "id": 20,
            "email": "z@x.com",
            "name": "FallbackName",
            "frequency": "monthly",
            "format": "csv",
            "filters": {},  # no keywords / no period
        }
    ]
    monkeypatch.setattr(subscriptions, "list_custom_schedules", lambda: schedules)
    monkeypatch.setattr(subscriptions, "mark_custom_sent", lambda sid: None)
    monkeypatch.setattr(subscriptions, "create_subscription", lambda *a, **k: {"id": 1})
    monkeypatch.setattr(subscriptions, "mark_sent", lambda sub_id: "t")
    monkeypatch.setattr(subscriptions, "delete_subscription", lambda sid: None)

    def capture_csv(filt):
        captured["keywords"] = filt.keywords
        captured["title"] = filt.report_title
        return b"CSV"

    monkeypatch.setattr(generate_report, "generate_custom_csv", capture_csv)
    monkeypatch.setattr(generate_report, "generate_custom_pdf", lambda filt: b"PDF")
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: None)

    sched._deliver_custom_schedules("monthly")

    assert captured["keywords"] == ["FallbackName"]
    assert captured["title"] == "FallbackName"


def test_deliver_custom_schedules_exception_swallowed(monkeypatch):
    schedules = [
        {"id": 30, "email": "q@x.com", "name": "N", "frequency": "weekly",
         "format": "pdf", "filters": {"keywords": ["k"]}},
    ]
    monkeypatch.setattr(subscriptions, "list_custom_schedules", lambda: schedules)

    def boom(filt):
        raise ValueError("custom render failed")

    monkeypatch.setattr(generate_report, "generate_custom_pdf", boom)
    sent = []
    monkeypatch.setattr(email_sender, "send_report_email", lambda **kw: sent.append(kw))
    # Should not raise.
    sched._deliver_custom_schedules("weekly")
    assert sent == []


# ---------------------------------------------------------------------------
# _weekly_job / _monthly_job
# ---------------------------------------------------------------------------

def test_weekly_job_calls_both_delivery_functions(monkeypatch):
    calls = []
    monkeypatch.setattr(sched, "_deliver_subscriptions", lambda f: calls.append(("subs", f)))
    monkeypatch.setattr(sched, "_deliver_custom_schedules", lambda f: calls.append(("custom", f)))
    sched._weekly_job()
    assert calls == [("subs", "weekly"), ("custom", "weekly")]


def test_monthly_job_calls_both_delivery_functions(monkeypatch):
    calls = []
    monkeypatch.setattr(sched, "_deliver_subscriptions", lambda f: calls.append(("subs", f)))
    monkeypatch.setattr(sched, "_deliver_custom_schedules", lambda f: calls.append(("custom", f)))
    sched._monthly_job()
    assert calls == [("subs", "monthly"), ("custom", "monthly")]


# ---------------------------------------------------------------------------
# trigger_now
# ---------------------------------------------------------------------------

def test_trigger_now_returns_processed_count(monkeypatch):
    monkeypatch.setattr(
        subscriptions, "list_subscriptions",
        lambda: [{"frequency": "weekly"}, {"frequency": "weekly"}, {"frequency": "monthly"}],
    )
    monkeypatch.setattr(
        subscriptions, "list_custom_schedules",
        lambda: [{"frequency": "weekly"}],
    )
    monkeypatch.setattr(sched, "_deliver_subscriptions", lambda f: None)
    monkeypatch.setattr(sched, "_deliver_custom_schedules", lambda f: None)

    # 2 weekly subscriptions + 1 weekly custom schedule = 3.
    assert sched.trigger_now("weekly") == 3


# ---------------------------------------------------------------------------
# start_scheduler / stop_scheduler
# ---------------------------------------------------------------------------

def test_start_scheduler_missing_apscheduler(monkeypatch):
    """With apscheduler absent, start_scheduler warns and stays uninitialized."""
    # Ensure the import fails deterministically regardless of environment.
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", None)
    sched.start_scheduler()
    assert sched._scheduler is None


def test_start_and_stop_scheduler_with_fake_apscheduler(monkeypatch):
    """Inject a fake apscheduler to exercise the real add_job/start/stop path."""
    added_jobs = []
    started = {"count": 0}
    shutdown = {"called": False}

    class FakeScheduler:
        def __init__(self, timezone=None):
            self.timezone = timezone

        def add_job(self, func, trigger, id=None):
            added_jobs.append(id)

        def start(self):
            started["count"] += 1

        def shutdown(self, wait=False):
            shutdown["called"] = True

    class FakeCronTrigger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    bg_mod = types.ModuleType("apscheduler.schedulers.background")
    bg_mod.BackgroundScheduler = FakeScheduler
    cron_mod = types.ModuleType("apscheduler.triggers.cron")
    cron_mod.CronTrigger = FakeCronTrigger
    pkg = types.ModuleType("apscheduler")
    sched_pkg = types.ModuleType("apscheduler.schedulers")
    triggers_pkg = types.ModuleType("apscheduler.triggers")

    monkeypatch.setitem(sys.modules, "apscheduler", pkg)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", sched_pkg)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", bg_mod)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers", triggers_pkg)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers.cron", cron_mod)

    sched.start_scheduler()
    assert sched._scheduler is not None
    assert started["count"] == 1
    assert set(added_jobs) == {"weekly_reports", "monthly_reports"}

    # Idempotent: second start is a no-op (scheduler already set).
    sched.start_scheduler()
    assert started["count"] == 1

    # Stop shuts it down and clears the singleton.
    sched.stop_scheduler()
    assert shutdown["called"] is True
    assert sched._scheduler is None


def test_stop_scheduler_noop_when_not_started():
    sched._scheduler = None
    sched.stop_scheduler()  # should not raise
    assert sched._scheduler is None


def test_stop_scheduler_swallows_shutdown_error():
    class BadScheduler:
        def shutdown(self, wait=False):
            raise RuntimeError("cannot shut down")

    sched._scheduler = BadScheduler()
    sched.stop_scheduler()  # exception must be swallowed
    assert sched._scheduler is None
