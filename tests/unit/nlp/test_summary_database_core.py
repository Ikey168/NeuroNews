"""Tests for cache/metrics logic of src/nlp/summary_database.py."""

import os
import sys
from datetime import datetime, timedelta

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from nlp.summary_database import SummaryDatabase, SummaryRecord  # noqa: E402


@pytest.fixture
def db():
    return SummaryDatabase({"host": "localhost", "dbname": "x"})


def record(article_id="a1"):
    return SummaryRecord(article_id=article_id, summary_text="summary", word_count=5)


class TestSummaryRecord:
    def test_defaults(self):
        r = SummaryRecord()
        assert r.id is None
        assert r.confidence_score == 0.0
        assert r.article_id == ""


class TestInit:
    def test_metrics_initialized(self, db):
        assert db.metrics["queries_executed"] == 0
        assert db.table_name == "article_summaries"
        assert db._cache == {}


class TestMetrics:
    def test_update_metrics_cache_hit(self, db):
        db._update_metrics(0.5, cache_hit=True)
        assert db.metrics["queries_executed"] == 1
        assert db.metrics["cache_hits"] == 1
        assert db.metrics["average_query_time"] == 0.5

    def test_update_metrics_miss(self, db):
        db._update_metrics(0.2, cache_hit=False)
        db._update_metrics(0.4, cache_hit=False)
        assert db.metrics["cache_misses"] == 2
        assert db.metrics["average_query_time"] == pytest.approx(0.3)

    def test_get_performance_metrics(self, db):
        db._update_metrics(0.1, cache_hit=True)
        m = db.get_performance_metrics()
        assert isinstance(m, dict)
        assert m["queries_executed"] == 1


class TestCache:
    def test_set_and_get(self, db):
        rec = record()
        db._cache_set("k1", rec)
        assert db._cache_get("k1") is rec

    def test_get_missing(self, db):
        assert db._cache_get("nope") is None

    def test_is_cache_valid(self, db):
        db._cache_set("k1", record())
        assert db._is_cache_valid("k1") is True

    def test_expired_entry_removed(self, db):
        db._cache_set("k1", record())
        # force the timestamp into the past beyond the timeout
        db._cache_timestamps["k1"] = datetime.now() - timedelta(seconds=db._cache_timeout + 10)
        assert db._is_cache_valid("k1") is False
        assert db._cache_get("k1") is None
        assert "k1" not in db._cache  # cleaned up

    def test_clear_cache(self, db):
        db._cache_set("k1", record())
        db._cache_set("k2", record("a2"))
        db.clear_cache()
        assert db._cache == {}
        assert db._cache_timestamps == {}
