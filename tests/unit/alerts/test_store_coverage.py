"""Coverage tests for src/alerts/store.py.

Uses a REAL DuckDB connection backed by a tmp_path file (NEURONEWS_DB_PATH),
exercising every CRUD + history path with genuine round-trip assertions.
"""

from __future__ import annotations

import os
import sys

import pytest

pytest.importorskip("duckdb")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Fresh alert store backed by an isolated DuckDB file per test."""
    db_file = tmp_path / "alerts_test.duckdb"
    monkeypatch.setenv("NEURONEWS_DB_PATH", str(db_file))

    import src.database.local_analytics_connector as lac
    import src.alerts.store as st

    # Reset the process-wide cached connection so it re-opens the tmp DB.
    if lac._CONNECTION is not None:
        try:
            lac._CONNECTION.close()
        except Exception:
            pass
    lac._CONNECTION = None
    # Reset the store's one-time schema flag so _init() runs against tmp DB.
    st._schema_done = False

    yield st

    # Tear down: close and reset so the next test gets a clean singleton.
    if lac._CONNECTION is not None:
        try:
            lac._CONNECTION.close()
        except Exception:
            pass
    lac._CONNECTION = None
    st._schema_done = False


# ---------------------------------------------------------------------------
# create_rule + get_rule + _rule_row
# ---------------------------------------------------------------------------

def test_create_rule_returns_full_row(store):
    rule = store.create_rule(
        name="My Rule",
        topic="AI",
        alert_type="breaking_news",
        channels=["slack", "email", "slack"],  # dedup + sort expected
        email="me@test",
        threshold=0.75,
        cooldown_min=30,
    )
    assert rule["name"] == "My Rule"
    assert rule["topic"] == "AI"
    assert rule["alert_type"] == "breaking_news"
    assert rule["threshold"] == 0.75
    assert rule["email"] == "me@test"
    assert rule["cooldown_min"] == 30
    assert rule["last_fired"] is None
    # channels are deduped + sorted by create_rule.
    assert rule["channels"] == ["email", "slack"]
    assert isinstance(rule["id"], str) and len(rule["id"]) == 16
    assert rule["created_at"]  # non-empty timestamp string


def test_create_rule_defaults_and_roundtrip(store):
    created = store.create_rule(
        name="Defaults",
        topic="Climate",
        alert_type="sentiment_shift",
        channels=["telegram"],
    )
    # threshold/email default to None, cooldown default 60.
    assert created["threshold"] is None
    assert created["email"] is None
    assert created["cooldown_min"] == 60

    fetched = store.get_rule(created["id"])
    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["name"] == "Defaults"
    assert fetched["channels"] == ["telegram"]
    assert fetched["cooldown_min"] == 60


def test_get_rule_missing_returns_none(store):
    assert store.get_rule("deadbeefdeadbeef") is None


# ---------------------------------------------------------------------------
# list_rules
# ---------------------------------------------------------------------------

def test_list_rules_empty(store):
    assert store.list_rules() == []


def test_list_rules_returns_all(store):
    a = store.create_rule(name="A", topic="t1", alert_type="new_event", channels=["email"], email="a@t")
    b = store.create_rule(name="B", topic="t2", alert_type="breaking_news", channels=["slack"])
    ids = {r["id"] for r in store.list_rules()}
    assert a["id"] in ids
    assert b["id"] in ids
    assert len(store.list_rules()) == 2


# ---------------------------------------------------------------------------
# mark_fired
# ---------------------------------------------------------------------------

def test_mark_fired_sets_last_fired(store):
    rule = store.create_rule(name="F", topic="t", alert_type="new_event", channels=["email"], email="e@t")
    assert store.get_rule(rule["id"])["last_fired"] is None
    store.mark_fired(rule["id"])
    updated = store.get_rule(rule["id"])
    assert updated["last_fired"] is not None
    assert updated["last_fired"] != "None"


# ---------------------------------------------------------------------------
# delete_rule
# ---------------------------------------------------------------------------

def test_delete_rule_removes_it(store):
    rule = store.create_rule(name="D", topic="t", alert_type="new_event", channels=["email"], email="e@t")
    assert store.get_rule(rule["id"]) is not None
    store.delete_rule(rule["id"])
    assert store.get_rule(rule["id"]) is None


def test_delete_rule_nonexistent_is_noop(store):
    # Deleting a missing id must not raise.
    store.delete_rule("00000000ffffffff")
    assert store.list_rules() == []


# ---------------------------------------------------------------------------
# log_history + get_history
# ---------------------------------------------------------------------------

def test_log_history_and_get_history(store):
    hid = store.log_history(
        rule_id="rule-1",
        alert_type="breaking_news",
        title="Big news",
        body="Details here",
        channels=["slack", "email"],
    )
    assert isinstance(hid, str) and len(hid) == 16

    hist = store.get_history(limit=10)
    assert len(hist) == 1
    entry = hist[0]
    assert entry["id"] == hid
    assert entry["rule_id"] == "rule-1"
    assert entry["alert_type"] == "breaking_news"
    assert entry["title"] == "Big news"
    assert entry["body"] == "Details here"
    assert entry["channels"] == ["slack", "email"]
    assert entry["fired_at"]  # non-empty timestamp


def test_get_history_empty(store):
    assert store.get_history() == []


def test_get_history_respects_limit(store):
    for i in range(5):
        store.log_history(
            rule_id=f"r{i}",
            alert_type="new_event",
            title=f"t{i}",
            body=f"b{i}",
            channels=["email"],
        )
    limited = store.get_history(limit=2)
    assert len(limited) == 2
    # Ordered by fired_at DESC; all entries have the required keys.
    for e in limited:
        assert set(e.keys()) == {
            "id", "rule_id", "alert_type", "title", "body", "channels", "fired_at",
        }


# ---------------------------------------------------------------------------
# _init idempotency
# ---------------------------------------------------------------------------

def test_init_is_idempotent(store):
    store._init()
    store._init()  # second call short-circuits on _schema_done
    assert store._schema_done is True
    # Store is still usable after repeated init.
    rule = store.create_rule(name="X", topic="t", alert_type="new_event", channels=["email"], email="e@t")
    assert store.get_rule(rule["id"]) is not None
