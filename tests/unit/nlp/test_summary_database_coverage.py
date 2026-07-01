"""Coverage-focused tests for src/nlp/summary_database.py.

Targets the lines left uncovered by the existing summary_database tests:
the ``get_summary_by_article_and_length`` query (all three branches), every
error-handling ``except`` block that re-raises, the ``_get_connection``
psycopg2 call, and the ``setup_summary_database`` helper.

Heavy imports (torch, transformers) are warmed up before pytest-cov's tracer
touches ``src/nlp/__init__.py`` so the C-extension init does not crash under
coverage instrumentation.
"""

# --- Warm up heavy C-extension imports BEFORE coverage traces them. ----------
import torch  # noqa: E402,F401

try:  # force torch._dynamo/_inductor library registration eagerly
    import torch._dynamo  # noqa: E402,F401
except Exception:
    pass
try:  # force transformers' lazy pipeline import eagerly
    from transformers import pipeline as _warm_pipeline  # noqa: E402,F401
except Exception:
    pass
# -----------------------------------------------------------------------------

import os  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import nlp.summary_database as mod  # noqa: E402
from nlp.summary_database import SummaryDatabase, SummaryRecord  # noqa: E402


def make_conn(fetchone=None, fetchall=None, rowcount=0):
    """Build a psycopg2-style connection context manager returning canned rows."""
    cursor = MagicMock()
    cursor.fetchone.return_value = fetchone
    cursor.fetchall.return_value = fetchall or []
    cursor.rowcount = rowcount
    cursor_cm = MagicMock()
    cursor_cm.__enter__ = MagicMock(return_value=cursor)
    cursor_cm.__exit__ = MagicMock(return_value=False)
    conn = MagicMock()
    conn.cursor.return_value = cursor_cm
    conn_cm = MagicMock()
    conn_cm.__enter__ = MagicMock(return_value=conn)
    conn_cm.__exit__ = MagicMock(return_value=False)
    return conn_cm, conn, cursor


ROW = (
    9, "art-9", "hash9", "some summary", "medium", "pegasus",
    0.77, 0.33, 42, 3, 0.6, datetime(2026, 3, 1), datetime(2026, 3, 2),
)


@pytest.fixture
def db():
    return SummaryDatabase({"host": "localhost", "dbname": "test"})


class FakeLength:
    """Stand-in for SummaryLength enum with a ``.value`` attribute."""

    def __init__(self, value):
        self.value = value


# --------------------------------------------------------------------------- #
# _get_connection -> real psycopg2.connect call (line 90)
# --------------------------------------------------------------------------- #
class TestGetConnection:
    def test_get_connection_calls_psycopg2(self, db, monkeypatch):
        fake_conn = object()
        connect = MagicMock(return_value=fake_conn)
        monkeypatch.setattr(mod.psycopg2, "connect", connect)
        result = db._get_connection()
        assert result is fake_conn
        connect.assert_called_once_with(host="localhost", dbname="test")


# --------------------------------------------------------------------------- #
# get_summary_by_article_and_length (lines 419-478) - all branches
# --------------------------------------------------------------------------- #
class TestGetSummaryByArticleAndLength:
    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached(self, db):
        rec = SummaryRecord(id=3, article_id="art-9", summary_length="short")
        db._cache_set("article:art-9:length:short", rec)
        result = await db.get_summary_by_article_and_length(
            "art-9", FakeLength("short")
        )
        assert result is rec
        assert db.metrics["cache_hits"] == 1

    @pytest.mark.asyncio
    async def test_db_hit_builds_and_caches_record(self, db, monkeypatch):
        conn_cm, conn, cursor = make_conn(fetchone=ROW)
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        result = await db.get_summary_by_article_and_length(
            "art-9", FakeLength("medium")
        )
        assert result.id == 9
        assert result.summary_length == "medium"
        assert result.confidence_score == pytest.approx(0.77)
        # The result must now be served from cache on a second call.
        assert db._cache_get("article:art-9:length:medium") is result
        assert db.metrics["cache_misses"] == 1

    @pytest.mark.asyncio
    async def test_db_miss_returns_none(self, db, monkeypatch):
        conn_cm, conn, cursor = make_conn(fetchone=None)
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        result = await db.get_summary_by_article_and_length(
            "art-9", FakeLength("long")
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_error_is_logged_and_reraised(self, db, monkeypatch):
        boom = MagicMock(side_effect=RuntimeError("db down"))
        monkeypatch.setattr(db, "_get_connection", boom)
        with pytest.raises(RuntimeError, match="db down"):
            await db.get_summary_by_article_and_length("art-9", FakeLength("short"))


# --------------------------------------------------------------------------- #
# Error-handling branches that log then re-raise
# --------------------------------------------------------------------------- #
class TestErrorPaths:
    @pytest.mark.asyncio
    async def test_create_table_error(self, db, monkeypatch):
        monkeypatch.setattr(
            db, "_get_connection", MagicMock(side_effect=RuntimeError("no table"))
        )
        with pytest.raises(RuntimeError, match="no table"):
            await db.create_table()

    @pytest.mark.asyncio
    async def test_store_summary_error(self, db, monkeypatch):
        monkeypatch.setattr(mod, "create_summary_hash", lambda *a: "h")
        monkeypatch.setattr(db, "get_summary_by_hash", AsyncMock(return_value=None))
        monkeypatch.setattr(
            db, "_get_connection", MagicMock(side_effect=RuntimeError("insert boom"))
        )
        summary = MagicMock()
        summary.text = "t"
        summary.length = FakeLength("short")
        summary.model = FakeLength("bart")
        summary.confidence_score = 0.5
        summary.processing_time = 0.1
        summary.word_count = 3
        summary.sentence_count = 1
        summary.compression_ratio = 0.2
        with pytest.raises(RuntimeError, match="insert boom"):
            await db.store_summary("art-1", "original", summary)

    @pytest.mark.asyncio
    async def test_get_summary_by_hash_error(self, db, monkeypatch):
        monkeypatch.setattr(
            db, "_get_connection", MagicMock(side_effect=RuntimeError("select boom"))
        )
        with pytest.raises(RuntimeError, match="select boom"):
            await db.get_summary_by_hash("nohash")

    @pytest.mark.asyncio
    async def test_get_summaries_by_article_error(self, db, monkeypatch):
        monkeypatch.setattr(
            db, "_get_connection", MagicMock(side_effect=RuntimeError("list boom"))
        )
        with pytest.raises(RuntimeError, match="list boom"):
            await db.get_summaries_by_article("art-x")

    @pytest.mark.asyncio
    async def test_delete_error(self, db, monkeypatch):
        monkeypatch.setattr(
            db, "_get_connection", MagicMock(side_effect=RuntimeError("delete boom"))
        )
        with pytest.raises(RuntimeError, match="delete boom"):
            await db.delete_summaries_by_article("art-x")

    @pytest.mark.asyncio
    async def test_statistics_error(self, db, monkeypatch):
        monkeypatch.setattr(
            db, "_get_connection", MagicMock(side_effect=RuntimeError("stats boom"))
        )
        with pytest.raises(RuntimeError, match="stats boom"):
            await db.get_summary_statistics()


# --------------------------------------------------------------------------- #
# get_summaries_by_article: DB-miss with real record construction (float casts)
# --------------------------------------------------------------------------- #
class TestGetSummariesByArticleTypes:
    @pytest.mark.asyncio
    async def test_null_numeric_fields_default_to_zero(self, db, monkeypatch):
        # confidence/processing/compression are None -> should coerce to 0.0
        row = (
            1, "art-1", "h", "sum", "short", "bart",
            None, None, 5, 1, None, datetime(2026, 1, 1), None,
        )
        conn_cm, conn, cursor = make_conn(fetchall=[row])
        monkeypatch.setattr(db, "_get_connection", lambda: conn_cm)
        records = await db.get_summaries_by_article("art-1")
        assert len(records) == 1
        assert records[0].confidence_score == 0.0
        assert records[0].processing_time == 0.0
        assert records[0].compression_ratio == 0.0


# --------------------------------------------------------------------------- #
# setup_summary_database helper (lines 619-624)
# --------------------------------------------------------------------------- #
class TestSetupHelper:
    @pytest.mark.asyncio
    async def test_setup_builds_db_and_creates_table(self, monkeypatch):
        created = {}

        async def fake_create_table(self):
            created["called"] = True

        monkeypatch.setattr(mod.SummaryDatabase, "create_table", fake_create_table)
        # get_shared_connection is imported lazily inside the function; provide a stub
        # module so the import resolves without a real DuckDB dependency.
        import types

        stub = types.ModuleType("src.database.local_analytics_connector")
        stub.get_shared_connection = lambda: None
        monkeypatch.setitem(
            sys.modules, "src.database.local_analytics_connector", stub
        )
        db = await mod.setup_summary_database()
        assert isinstance(db, SummaryDatabase)
        assert created.get("called") is True
        assert db.connection_params == {"duckdb_path": "data/neuronews.duckdb"}
