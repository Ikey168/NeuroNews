"""Coverage tests for src/reports/subscriptions.py.

Uses a REAL in-memory DuckDB connection so the CREATE TABLE / INSERT / UPDATE /
DELETE SQL actually runs. ``get_shared_connection`` and ``_LOCK`` are imported
at module scope in subscriptions.py, so they are patched directly on that
module. The module-level "schema done" flags are reset so ``_init`` /
``_init_custom`` create the schema against our fresh connection.
"""
from __future__ import annotations

import threading

import pytest

import src.reports.subscriptions as subs


@pytest.fixture
def duck(monkeypatch):
    import duckdb

    conn = duckdb.connect(":memory:")
    lock = threading.Lock()
    monkeypatch.setattr(subs, "get_shared_connection", lambda: conn)
    monkeypatch.setattr(subs, "_LOCK", lock)
    # Force schema (re)creation against this fresh connection.
    monkeypatch.setattr(subs, "_schema_done", False)
    monkeypatch.setattr(subs, "_custom_schema_done", False)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# _init / _ensure_schema
# ---------------------------------------------------------------------------

def test_init_creates_tables(duck):
    subs._init()
    tables = {
        r[0]
        for r in duck.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert "report_subscriptions" in tables
    assert "report_deliveries" in tables


def test_init_idempotent(duck):
    subs._init()
    # Second call should short-circuit on the _schema_done flag.
    subs._init()
    assert subs._schema_done is True


# ---------------------------------------------------------------------------
# create / list / get / delete subscription
# ---------------------------------------------------------------------------

def test_create_subscription_returns_dict(duck):
    row = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    assert row["email"] == "a@ex.com"
    assert row["topic"] == "Nvidia"
    assert row["frequency"] == "weekly"
    assert row["format"] == "pdf"
    assert row["last_sent"] is None
    assert isinstance(row["id"], str) and len(row["id"]) == 16  # token_hex(8)
    # Row actually persisted
    count = duck.execute("SELECT COUNT(*) FROM report_subscriptions").fetchone()[0]
    assert count == 1


def test_list_subscriptions_all_and_by_email(duck):
    subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    subs.create_subscription("b@ex.com", "Tesla", "monthly", "csv")
    subs.create_subscription("a@ex.com", "AMD", "weekly", "csv")

    all_rows = subs.list_subscriptions()
    assert len(all_rows) == 3

    a_rows = subs.list_subscriptions("a@ex.com")
    assert len(a_rows) == 2
    assert {r["topic"] for r in a_rows} == {"Nvidia", "AMD"}

    none_rows = subs.list_subscriptions("nobody@ex.com")
    assert none_rows == []


def test_get_subscription_found_and_missing(duck):
    created = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    got = subs.get_subscription(created["id"])
    assert got is not None
    assert got["id"] == created["id"]
    assert got["email"] == "a@ex.com"

    assert subs.get_subscription("deadbeef") is None


def test_delete_subscription(duck):
    created = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    # add a delivery so the deliveries cleanup path runs too
    subs.mark_sent(created["id"])
    assert subs.delete_subscription(created["id"]) is True
    assert subs.get_subscription(created["id"]) is None
    deliv = duck.execute(
        "SELECT COUNT(*) FROM report_deliveries WHERE sub_id = ?", [created["id"]]
    ).fetchone()[0]
    assert deliv == 0


# ---------------------------------------------------------------------------
# mark_sent / record_open / delivery_stats
# ---------------------------------------------------------------------------

def test_mark_sent_records_delivery_and_updates_last_sent(duck):
    created = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    token = subs.mark_sent(created["id"])
    assert isinstance(token, str) and len(token) > 10

    row = duck.execute(
        "SELECT sub_id FROM report_deliveries WHERE token = ?", [token]
    ).fetchone()
    assert row[0] == created["id"]

    # last_sent should now be populated
    refreshed = subs.get_subscription(created["id"])
    assert refreshed["last_sent"] is not None


def test_record_open_found(duck):
    created = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    token = subs.mark_sent(created["id"])
    assert subs.record_open(token) is True
    # A second open increments the count
    assert subs.record_open(token) is True
    count = duck.execute(
        "SELECT open_count FROM report_deliveries WHERE token = ?", [token]
    ).fetchone()[0]
    assert count == 2


def test_record_open_missing_token(duck):
    assert subs.record_open("no-such-token") is False


def test_delivery_stats_no_deliveries(duck):
    created = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    stats = subs.delivery_stats(created["id"])
    assert stats["total_sent"] == 0
    assert stats["total_opens"] == 0
    assert stats["open_rate"] == 0.0
    assert stats["last_opened"] is None


def test_delivery_stats_with_opens(duck):
    created = subs.create_subscription("a@ex.com", "Nvidia", "weekly", "pdf")
    t1 = subs.mark_sent(created["id"])
    t2 = subs.mark_sent(created["id"])
    subs.record_open(t1)
    subs.record_open(t1)
    subs.record_open(t2)
    stats = subs.delivery_stats(created["id"])
    assert stats["total_sent"] == 2
    assert stats["total_opens"] == 3
    # open_rate = opens / sent
    assert stats["open_rate"] == round(3 / 2, 3)
    assert stats["last_opened"] is not None


# ---------------------------------------------------------------------------
# _row_to_dict
# ---------------------------------------------------------------------------

def test_row_to_dict_last_sent_none_and_value():
    d1 = subs._row_to_dict("id1", "e", "t", "weekly", "pdf", "2026-01-01", None)
    assert d1["last_sent"] is None
    assert d1["created_at"] == "2026-01-01"

    d2 = subs._row_to_dict("id2", "e", "t", "weekly", "pdf", "2026-01-01", "2026-02-01")
    assert d2["last_sent"] == "2026-02-01"


# ---------------------------------------------------------------------------
# Custom schedules
# ---------------------------------------------------------------------------

def test_init_custom_creates_table(duck):
    subs._init_custom()
    tables = {
        r[0]
        for r in duck.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    assert "custom_report_schedules" in tables


def test_init_custom_idempotent(duck):
    subs._init_custom()
    subs._init_custom()
    assert subs._custom_schema_done is True


def test_create_custom_schedule_serialises_filters(duck):
    filters = {"keywords": ["Nvidia", "AMD"], "sentiment": "positive", "limit": 50}
    sched = subs.create_custom_schedule(
        name="Chip watch", email="a@ex.com",
        frequency="weekly", fmt="pdf", filters=filters,
    )
    assert sched["name"] == "Chip watch"
    assert sched["filters"] == filters  # round-trips via json
    assert sched["last_sent"] is None
    assert len(sched["id"]) == 16

    stored = duck.execute(
        "SELECT filters_json FROM custom_report_schedules WHERE id = ?",
        [sched["id"]],
    ).fetchone()[0]
    assert "Nvidia" in stored


def test_list_custom_schedules_all_and_by_email(duck):
    subs.create_custom_schedule("A", "a@ex.com", "weekly", "pdf", {"keywords": ["x"]})
    subs.create_custom_schedule("B", "b@ex.com", "monthly", "csv", {"keywords": ["y"]})
    subs.create_custom_schedule("C", "a@ex.com", "weekly", "csv", {"keywords": ["z"]})

    all_rows = subs.list_custom_schedules()
    assert len(all_rows) == 3

    a_rows = subs.list_custom_schedules("a@ex.com")
    assert len(a_rows) == 2
    assert {r["name"] for r in a_rows} == {"A", "C"}

    assert subs.list_custom_schedules("nope@ex.com") == []


def test_get_custom_schedule_found_and_missing(duck):
    sched = subs.create_custom_schedule(
        "A", "a@ex.com", "weekly", "pdf", {"keywords": ["x"]}
    )
    got = subs.get_custom_schedule(sched["id"])
    assert got is not None
    assert got["name"] == "A"
    assert got["filters"] == {"keywords": ["x"]}

    assert subs.get_custom_schedule("missing") is None


def test_delete_custom_schedule(duck):
    sched = subs.create_custom_schedule(
        "A", "a@ex.com", "weekly", "pdf", {"keywords": ["x"]}
    )
    subs.delete_custom_schedule(sched["id"])
    assert subs.get_custom_schedule(sched["id"]) is None


def test_mark_custom_sent_updates_last_sent(duck):
    sched = subs.create_custom_schedule(
        "A", "a@ex.com", "weekly", "pdf", {"keywords": ["x"]}
    )
    assert sched["last_sent"] is None
    subs.mark_custom_sent(sched["id"])
    refreshed = subs.get_custom_schedule(sched["id"])
    assert refreshed["last_sent"] is not None


def test_custom_row_empty_filters_json():
    # When filters_json is falsy, filters -> {}
    row = subs._custom_row("id1", "n", "e", "weekly", "pdf", "", "2026-01-01", None)
    assert row["filters"] == {}
    assert row["last_sent"] is None

    row2 = subs._custom_row(
        "id2", "n", "e", "weekly", "pdf", '{"k": 1}', "2026-01-01", "2026-02-01"
    )
    assert row2["filters"] == {"k": 1}
    assert row2["last_sent"] == "2026-02-01"
