"""Coverage tests for src/alerts/detector.py.

Runs the REAL detection SQL (ILIKE / time-window filters / GROUP BY HAVING /
AVG) against a REAL in-memory DuckDB seeded with controlled ``news_articles``
rows, so every triggered / not-triggered branch is exercised with genuine
assertions on the returned title/body payloads.

detector.py binds ``get_shared_connection`` and ``_LOCK`` into its own module
namespace at import time (``from ... import get_shared_connection, _LOCK``), so
we patch those symbols on the detector module directly.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("duckdb")

import src.alerts.detector as detector


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def db(monkeypatch):
    """In-memory DuckDB with a news_articles table wired into the detector."""
    import duckdb

    conn = duckdb.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE news_articles (
            title           VARCHAR,
            source          VARCHAR,
            category        VARCHAR,
            sentiment_score DOUBLE,
            publish_date    TIMESTAMP
        )
        """
    )
    monkeypatch.setattr(detector, "get_shared_connection", lambda: conn)
    # A real (uncontended) lock so the `with _LOCK` blocks execute for real.
    monkeypatch.setattr(detector, "_LOCK", threading.Lock())
    yield conn
    conn.close()


def _insert(conn, *, title, source, category, sentiment, minutes_ago):
    ts = _naive_now() - timedelta(minutes=minutes_ago)
    conn.execute(
        "INSERT INTO news_articles VALUES (?, ?, ?, ?, ?)",
        [title, source, category, sentiment, ts],
    )


# ---------------------------------------------------------------------------
# check_breaking_news
# ---------------------------------------------------------------------------

def test_breaking_news_triggers_on_recent_negative(db):
    _insert(db, title="AI regulation shock", source="Reuters",
            category="tech", sentiment=-0.6, minutes_ago=5)
    _insert(db, title="AI funding round", source="Bloomberg",
            category="tech", sentiment=-0.3, minutes_ago=10)

    result = detector.check_breaking_news("AI")
    assert result["triggered"] is True
    assert "2 negative article" in result["title"]
    assert "'AI'" in result["title"]
    assert "AI regulation shock" in result["body"]
    # Most negative sorted-by-date row formatted with signed score.
    assert "(Reuters, score -0.60)" in result["body"]


def test_breaking_news_ignores_positive_sentiment(db):
    _insert(db, title="AI breakthrough celebrated", source="CNN",
            category="tech", sentiment=0.8, minutes_ago=3)
    result = detector.check_breaking_news("AI")
    assert result == {"triggered": False, "title": "", "body": ""}


def test_breaking_news_ignores_old_articles(db):
    _insert(db, title="AI old bad news", source="AP",
            category="tech", sentiment=-0.9, minutes_ago=60)
    result = detector.check_breaking_news("AI")
    assert result["triggered"] is False


def test_breaking_news_matches_via_category(db):
    _insert(db, title="Markets slump", source="WSJ",
            category="Climate policy", sentiment=-0.4, minutes_ago=2)
    result = detector.check_breaking_news("Climate")
    assert result["triggered"] is True
    assert "Markets slump" in result["body"]


def test_breaking_news_no_match_returns_not_triggered(db):
    _insert(db, title="Sports recap", source="ESPN",
            category="sports", sentiment=-0.7, minutes_ago=1)
    result = detector.check_breaking_news("Quantum")
    assert result["triggered"] is False


# ---------------------------------------------------------------------------
# check_sentiment_shift
# ---------------------------------------------------------------------------

def test_sentiment_shift_triggers_on_worsening(db):
    # Previous hour strongly positive, last hour strongly negative -> worsened.
    _insert(db, title="TopicX good", source="S1", category="x",
            sentiment=0.8, minutes_ago=90)
    _insert(db, title="TopicX great", source="S1", category="x",
            sentiment=0.6, minutes_ago=100)
    _insert(db, title="TopicX bad", source="S1", category="x",
            sentiment=-0.5, minutes_ago=20)
    _insert(db, title="TopicX awful", source="S1", category="x",
            sentiment=-0.7, minutes_ago=40)

    result = detector.check_sentiment_shift("TopicX", threshold=0.15)
    assert result["triggered"] is True
    assert "worsened" in result["title"]
    assert "Previous hour avg" in result["body"]
    assert "Last hour avg" in result["body"]
    assert "Delta" in result["body"]


def test_sentiment_shift_triggers_on_improvement(db):
    _insert(db, title="Topic bad", source="S", category="y",
            sentiment=-0.8, minutes_ago=90)
    _insert(db, title="Topic worse", source="S", category="y",
            sentiment=-0.6, minutes_ago=110)
    _insert(db, title="Topic good", source="S", category="y",
            sentiment=0.7, minutes_ago=15)
    result = detector.check_sentiment_shift("Topic", threshold=0.15)
    assert result["triggered"] is True
    assert "improved" in result["title"]


def test_sentiment_shift_below_threshold_not_triggered(db):
    _insert(db, title="Steady a", source="S", category="z",
            sentiment=0.20, minutes_ago=90)
    _insert(db, title="Steady b", source="S", category="z",
            sentiment=0.25, minutes_ago=15)
    result = detector.check_sentiment_shift("Steady", threshold=0.15)
    assert result["triggered"] is False


def test_sentiment_shift_missing_window_not_triggered(db):
    # Only recent-hour data; previous hour AVG is NULL -> avg_prev is None branch.
    _insert(db, title="OnlyRecent", source="S", category="w",
            sentiment=-0.5, minutes_ago=10)
    result = detector.check_sentiment_shift("OnlyRecent")
    assert result["triggered"] is False


def test_sentiment_shift_empty_returns_not_triggered(db):
    result = detector.check_sentiment_shift("Nonexistent")
    assert result["triggered"] is False


# ---------------------------------------------------------------------------
# check_new_event
# ---------------------------------------------------------------------------

def test_new_event_triggers_with_three_from_same_source(db):
    for i in range(3):
        _insert(db, title=f"Cluster {i}", source="RapidWire",
                category="event", sentiment=0.0, minutes_ago=5 + i)
    result = detector.check_new_event("Cluster")
    assert result["triggered"] is True
    assert "'Cluster'" in result["title"]
    assert "RapidWire (3 articles)" in result["body"]
    assert "breaking event" in result["body"]


def test_new_event_below_three_not_triggered(db):
    for i in range(2):
        _insert(db, title=f"Small {i}", source="Wire",
                category="event", sentiment=0.0, minutes_ago=5)
    result = detector.check_new_event("Small")
    assert result["triggered"] is False


def test_new_event_ignores_old_articles(db):
    for i in range(4):
        _insert(db, title=f"Stale {i}", source="Wire",
                category="event", sentiment=0.0, minutes_ago=45)
    result = detector.check_new_event("Stale")
    assert result["triggered"] is False


# ---------------------------------------------------------------------------
# run_all_checks dispatch
# ---------------------------------------------------------------------------

def test_run_all_checks_breaking_news(db):
    _insert(db, title="Breaking topic bad", source="Reuters",
            category="tech", sentiment=-0.5, minutes_ago=2)
    result = detector.run_all_checks("Breaking", "breaking_news", None)
    assert result["triggered"] is True
    assert "negative article" in result["title"]


def test_run_all_checks_sentiment_shift_uses_threshold(db):
    # Delta of ~0.3; passes with default threshold routed through run_all_checks.
    _insert(db, title="ShiftT pos", source="S", category="c",
            sentiment=0.5, minutes_ago=90)
    _insert(db, title="ShiftT neg", source="S", category="c",
            sentiment=0.1, minutes_ago=15)
    result = detector.run_all_checks("ShiftT", "sentiment_shift", None)
    assert result["triggered"] is True


def test_run_all_checks_sentiment_shift_custom_threshold_suppresses(db):
    _insert(db, title="Tiny pos", source="S", category="c",
            sentiment=0.5, minutes_ago=90)
    _insert(db, title="Tiny neg", source="S", category="c",
            sentiment=0.1, minutes_ago=15)
    # A very high threshold makes the ~0.4 delta insufficient.
    result = detector.run_all_checks("Tiny", "sentiment_shift", 0.99)
    assert result["triggered"] is False


def test_run_all_checks_new_event(db):
    for i in range(3):
        _insert(db, title=f"Ev {i}", source="Feed",
                category="event", sentiment=0.0, minutes_ago=3)
    result = detector.run_all_checks("Ev", "new_event", None)
    assert result["triggered"] is True
    assert "cluster forming" in result["title"]


def test_run_all_checks_unknown_type_not_triggered(db):
    result = detector.run_all_checks("Anything", "unknown_type", None)
    assert result == {"triggered": False, "title": "", "body": ""}
