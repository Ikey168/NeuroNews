"""Coverage tests for src/alerts/dispatcher.py.

Exercises the SSE fan-out registry, the cooldown parser, and the full
``poll_and_dispatch`` orchestration with REAL asyncio.Queue objects and REAL
datetime arithmetic. The store / detector / channels collaborators are imported
LAZILY inside ``poll_and_dispatch`` (``from src.alerts.store import ...`` etc.),
so we substitute those modules in ``sys.modules`` with lightweight fakes to keep
the test hermetic (no DuckDB, no SMTP/HTTP) while still driving the real dispatch
control flow and event assembly.
"""
from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

import src.alerts.dispatcher as dispatcher


# ---------------------------------------------------------------------------
# SSE registry: register / unregister / _push_sse
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_sse_registry():
    """Guarantee the module-global SSE client set starts and ends empty."""
    dispatcher._sse_clients.clear()
    yield
    dispatcher._sse_clients.clear()


def test_register_and_unregister_sse_client():
    q = asyncio.Queue()
    dispatcher.register_sse_client(q)
    assert q in dispatcher._sse_clients
    assert len(dispatcher._sse_clients) == 1

    dispatcher.unregister_sse_client(q)
    assert q not in dispatcher._sse_clients
    assert len(dispatcher._sse_clients) == 0


def test_unregister_missing_client_is_noop():
    q = asyncio.Queue()
    # discard() on an absent element must not raise.
    dispatcher.unregister_sse_client(q)
    assert q not in dispatcher._sse_clients


def test_push_sse_broadcasts_to_all_queues():
    q1, q2 = asyncio.Queue(), asyncio.Queue()
    dispatcher.register_sse_client(q1)
    dispatcher.register_sse_client(q2)

    event = {"id": "abc", "title": "hi"}
    dispatcher._push_sse(event)

    assert q1.get_nowait() == event
    assert q2.get_nowait() == event


def test_push_sse_drops_when_queue_full():
    full_q = asyncio.Queue(maxsize=1)
    full_q.put_nowait({"pre": "existing"})  # now full
    dispatcher.register_sse_client(full_q)

    # Should swallow QueueFull and not raise.
    dispatcher._push_sse({"id": "x"})
    # Only the pre-existing item remains; the new one was dropped.
    assert full_q.get_nowait() == {"pre": "existing"}
    assert full_q.empty()


# ---------------------------------------------------------------------------
# _is_cooled_down
# ---------------------------------------------------------------------------

def _naive_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_is_cooled_down_no_last_fired_returns_true():
    assert dispatcher._is_cooled_down({}) is True
    assert dispatcher._is_cooled_down({"last_fired": None}) is True


def test_is_cooled_down_unparseable_timestamp_returns_true():
    assert dispatcher._is_cooled_down({"last_fired": "not-a-timestamp"}) is True


def test_is_cooled_down_recent_fire_returns_false():
    recent = _naive_now().isoformat()
    assert dispatcher._is_cooled_down({"last_fired": recent, "cooldown_min": 60}) is False


def test_is_cooled_down_elapsed_returns_true():
    old = (_naive_now() - timedelta(hours=2)).isoformat()
    assert dispatcher._is_cooled_down({"last_fired": old, "cooldown_min": 60}) is True


def test_is_cooled_down_default_cooldown_used_when_absent():
    # No cooldown_min key -> defaults to 60 min; a 30-min-old fire is NOT cooled.
    thirty_min_ago = (_naive_now() - timedelta(minutes=30)).isoformat()
    assert dispatcher._is_cooled_down({"last_fired": thirty_min_ago}) is False


# ---------------------------------------------------------------------------
# poll_and_dispatch — full orchestration with fake collaborators
# ---------------------------------------------------------------------------

class _Recorder:
    def __init__(self):
        self.mark_fired_calls = []
        self.history_calls = []
        self.dispatch_calls = []
        self.check_calls = []


@pytest.fixture
def wired(monkeypatch):
    """Install fake store/detector/channels modules for the lazy imports."""
    rec = _Recorder()

    store_mod = types.ModuleType("src.alerts.store")
    detector_mod = types.ModuleType("src.alerts.detector")
    channels_mod = types.ModuleType("src.alerts.channels")

    # Defaults; individual tests override store_mod.list_rules / detector result.
    store_mod._rules = []

    def list_rules():
        return store_mod._rules

    def mark_fired(rule_id):
        rec.mark_fired_calls.append(rule_id)

    def log_history(rule_id, alert_type, title, body, channels):
        rec.history_calls.append((rule_id, alert_type, title, body, channels))
        return "hist-" + rule_id

    def run_all_checks(topic, alert_type, threshold):
        rec.check_calls.append((topic, alert_type, threshold))
        return store_mod._check_result

    def dispatch(channels, title, body, email=None):
        rec.dispatch_calls.append((channels, title, body, email))
        return {ch: True for ch in channels}

    store_mod.list_rules = list_rules
    store_mod.mark_fired = mark_fired
    store_mod.log_history = log_history
    store_mod._check_result = {"triggered": False, "title": "", "body": ""}
    detector_mod.run_all_checks = run_all_checks
    channels_mod.dispatch = dispatch

    monkeypatch.setitem(sys.modules, "src.alerts.store", store_mod)
    monkeypatch.setitem(sys.modules, "src.alerts.detector", detector_mod)
    monkeypatch.setitem(sys.modules, "src.alerts.channels", channels_mod)

    return types.SimpleNamespace(store=store_mod, rec=rec)


def test_poll_and_dispatch_no_rules_returns_empty(wired):
    wired.store._rules = []
    assert dispatcher.poll_and_dispatch() == []


def test_poll_and_dispatch_fires_triggered_rule(wired):
    wired.store._rules = [
        {
            "id": "r1",
            "name": "AI watch",
            "topic": "AI",
            "alert_type": "breaking_news",
            "channels": ["email", "slack"],
            "email": "ops@example.com",
            "threshold": None,
            "cooldown_min": 60,
            "last_fired": None,  # cooled down -> eligible
        }
    ]
    wired.store._check_result = {
        "triggered": True,
        "title": "Breaking: AI",
        "body": "Something happened",
    }

    fired = dispatcher.poll_and_dispatch()

    assert len(fired) == 1
    event = fired[0]
    assert event["id"] == "hist-r1"
    assert event["rule_id"] == "r1"
    assert event["rule_name"] == "AI watch"
    assert event["alert_type"] == "breaking_news"
    assert event["topic"] == "AI"
    assert event["title"] == "Breaking: AI"
    assert event["body"] == "Something happened"
    assert event["channels"] == ["email", "slack"]
    assert event["delivery"] == {"email": True, "slack": True}
    assert event["fired_at"]  # ISO timestamp string

    # Side effects: dispatch, history, mark_fired all invoked with right args.
    assert wired.rec.dispatch_calls == [
        (["email", "slack"], "Breaking: AI", "Something happened", "ops@example.com")
    ]
    assert wired.rec.history_calls[0][0] == "r1"
    assert wired.rec.mark_fired_calls == ["r1"]
    assert wired.rec.check_calls == [("AI", "breaking_news", None)]


def test_poll_and_dispatch_pushes_event_to_sse(wired):
    q = asyncio.Queue()
    dispatcher.register_sse_client(q)
    wired.store._rules = [
        {
            "id": "r2", "name": "n", "topic": "T", "alert_type": "new_event",
            "channels": ["slack"], "email": None, "threshold": None,
            "cooldown_min": 60, "last_fired": None,
        }
    ]
    wired.store._check_result = {"triggered": True, "title": "t", "body": "b"}

    fired = dispatcher.poll_and_dispatch()
    pushed = q.get_nowait()
    assert pushed == fired[0]
    assert pushed["rule_id"] == "r2"


def test_poll_and_dispatch_skips_non_triggered(wired):
    wired.store._rules = [
        {
            "id": "r3", "name": "n", "topic": "T", "alert_type": "new_event",
            "channels": ["slack"], "email": None, "threshold": None,
            "cooldown_min": 60, "last_fired": None,
        }
    ]
    wired.store._check_result = {"triggered": False, "title": "", "body": ""}

    fired = dispatcher.poll_and_dispatch()
    assert fired == []
    # run_all_checks ran, but no dispatch / history / mark_fired.
    assert wired.rec.check_calls == [("T", "new_event", None)]
    assert wired.rec.dispatch_calls == []
    assert wired.rec.mark_fired_calls == []


def test_poll_and_dispatch_skips_rule_in_cooldown(wired):
    recent = _naive_now().isoformat()
    wired.store._rules = [
        {
            "id": "r4", "name": "n", "topic": "T", "alert_type": "breaking_news",
            "channels": ["slack"], "email": None, "threshold": None,
            "cooldown_min": 60, "last_fired": recent,  # still cooling down
        }
    ]
    wired.store._check_result = {"triggered": True, "title": "t", "body": "b"}

    fired = dispatcher.poll_and_dispatch()
    assert fired == []
    # The check is never even run for a rule still in cooldown.
    assert wired.rec.check_calls == []


# ---------------------------------------------------------------------------
# Scheduler start/stop (apscheduler may be absent -> ImportError branch)
# ---------------------------------------------------------------------------

def test_stop_scheduler_when_not_running_is_noop():
    dispatcher._scheduler = None
    dispatcher.stop_alert_scheduler()
    assert dispatcher._scheduler is None


def test_start_scheduler_missing_apscheduler_logs_and_returns(monkeypatch):
    """When apscheduler is absent, start_alert_scheduler must swallow the
    ImportError and leave _scheduler as None."""
    dispatcher._scheduler = None
    # Force the `from apscheduler...` import to fail regardless of install state.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("apscheduler"):
            raise ImportError("simulated missing apscheduler")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    dispatcher.start_alert_scheduler()
    assert dispatcher._scheduler is None


def test_start_and_stop_scheduler_with_fake_apscheduler(monkeypatch):
    """Drive the success path with a fake apscheduler package so add_job /
    start / shutdown are all exercised without a real background thread."""
    dispatcher._scheduler = None

    started = {"start": False, "shutdown": False, "job": None}

    class FakeScheduler:
        def __init__(self, timezone=None):
            self.timezone = timezone

        def add_job(self, func, trigger, id=None):
            started["job"] = (func, id)

        def start(self):
            started["start"] = True

        def shutdown(self, wait=False):
            started["shutdown"] = True

    class FakeIntervalTrigger:
        def __init__(self, minutes=None):
            self.minutes = minutes

    sched_pkg = types.ModuleType("apscheduler")
    schedulers_pkg = types.ModuleType("apscheduler.schedulers")
    background_mod = types.ModuleType("apscheduler.schedulers.background")
    triggers_pkg = types.ModuleType("apscheduler.triggers")
    interval_mod = types.ModuleType("apscheduler.triggers.interval")

    background_mod.BackgroundScheduler = FakeScheduler
    interval_mod.IntervalTrigger = FakeIntervalTrigger

    monkeypatch.setitem(sys.modules, "apscheduler", sched_pkg)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", schedulers_pkg)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", background_mod)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers", triggers_pkg)
    monkeypatch.setitem(sys.modules, "apscheduler.triggers.interval", interval_mod)

    try:
        dispatcher.start_alert_scheduler()
        assert started["start"] is True
        assert started["job"][0] is dispatcher.poll_and_dispatch
        assert started["job"][1] == "alert_poll"
        assert dispatcher._scheduler is not None

        # Idempotency: a second start does not create/start a new scheduler.
        started["start"] = False
        dispatcher.start_alert_scheduler()
        assert started["start"] is False

        # Stop shuts the scheduler down and clears the global.
        dispatcher.stop_alert_scheduler()
        assert started["shutdown"] is True
        assert dispatcher._scheduler is None
    finally:
        dispatcher._scheduler = None


def test_stop_scheduler_swallows_shutdown_error(monkeypatch):
    class BoomScheduler:
        def shutdown(self, wait=False):
            raise RuntimeError("boom")

    dispatcher._scheduler = BoomScheduler()
    # Exception in shutdown must be swallowed; global reset to None.
    dispatcher.stop_alert_scheduler()
    assert dispatcher._scheduler is None
