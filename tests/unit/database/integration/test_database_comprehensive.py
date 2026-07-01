#!/usr/bin/env python3
"""
Comprehensive Database Integration Tests
Issue #429: Database: Connection & Performance Tests

Integration-flavoured counterpart of
``tests/unit/database/test_database_comprehensive.py``. It exercises the *real*
``src.database.setup`` connection helpers and ``src.nlp.summary_database`` API
end-to-end with mocked drivers, so it runs without a live PostgreSQL server yet
still verifies the module wiring (config -> connect -> cursor -> commit).

Rewrite notes
-------------
The previous version tried to ``from .test_database_connection_performance_mock
import *`` (a module that no longer exists) and to import ``DatabaseSetup`` /
``DatabaseSetupConfig`` classes (which never existed), so ``DATABASE_AVAILABLE``
was always ``False`` and *zero* tests ran.

The real API is function-based (``get_db_config``, ``get_sync_connection``,
``get_async_connection``, ``create_test_articles``) plus the ``SummaryDatabase``
helper. ``asyncpg`` is not installed here, so a lightweight module stub is
installed in ``sys.modules`` before importing ``src.database.setup`` (which does
``import asyncpg`` at import time). Drivers are patched at the source module.

The connection-level tests model the full connect/cursor/commit flow the real
database integration relies on, without needing a live server.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# asyncpg import stub -- src.database.setup does `import asyncpg` at import time,
# and asyncpg is not installed here. Provide a minimal async-capable stub.
# ---------------------------------------------------------------------------
if "asyncpg" not in sys.modules:
    _asyncpg_stub = types.ModuleType("asyncpg")
    _asyncpg_stub.connect = AsyncMock()
    _asyncpg_stub.Connection = object
    sys.modules["asyncpg"] = _asyncpg_stub

from src.database import setup as db_setup  # noqa: E402
from src.nlp.summary_database import SummaryDatabase, SummaryRecord  # noqa: E402


# ---------------------------------------------------------------------------
# get_db_config -- pure function, no mocking required.
# ---------------------------------------------------------------------------
class TestGetDbConfig:
    def test_testing_config_uses_test_defaults(self, monkeypatch):
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        config = db_setup.get_db_config(testing=True)
        assert config["host"] == "test-postgres"
        assert config["database"] == "neuronews_test"
        assert config["user"] == "test_user"
        assert config["port"] == 5432

    def test_production_config_uses_prod_defaults(self, monkeypatch):
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        config = db_setup.get_db_config(testing=False)
        assert config["host"] == "postgres"
        assert config["database"] == "neuronews_dev"
        assert config["user"] == "neuronews"

    def test_env_vars_override_defaults(self, monkeypatch):
        monkeypatch.setenv("DB_HOST", "custom-host")
        monkeypatch.setenv("DB_PORT", "6543")
        monkeypatch.setenv("DB_NAME", "custom_db")
        monkeypatch.setenv("DB_USER", "custom_user")
        monkeypatch.setenv("DB_PASSWORD", "custom_pw")

        config = db_setup.get_db_config(testing=True)
        assert config["host"] == "custom-host"
        assert config["port"] == 6543  # coerced to int
        assert config["database"] == "custom_db"
        assert config["user"] == "custom_user"
        assert config["password"] == "custom_pw"

    def test_testing_env_var_forces_test_config(self, monkeypatch):
        for var in ("DB_HOST", "DB_NAME"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("TESTING", "1")
        config = db_setup.get_db_config(testing=False)
        assert config["database"] == "neuronews_test"


# ---------------------------------------------------------------------------
# get_sync_connection -- patch psycopg2.connect at the source module.
# ---------------------------------------------------------------------------
class TestGetSyncConnection:
    def test_returns_psycopg2_connection_with_config(self, monkeypatch):
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        fake_conn = MagicMock(name="psycopg2_connection")
        with patch.object(db_setup.psycopg2, "connect", return_value=fake_conn) as mock_connect:
            conn = db_setup.get_sync_connection(testing=True)

        assert conn is fake_conn
        mock_connect.assert_called_once()
        called_kwargs = mock_connect.call_args.kwargs
        assert called_kwargs["host"] == "test-postgres"
        assert called_kwargs["database"] == "neuronews_test"

    def test_propagates_operational_error(self):
        import psycopg2

        with patch.object(
            db_setup.psycopg2,
            "connect",
            side_effect=psycopg2.OperationalError("no server"),
        ):
            with pytest.raises(psycopg2.OperationalError):
                db_setup.get_sync_connection(testing=True)


# ---------------------------------------------------------------------------
# get_async_connection -- patch asyncpg.connect at the source module.
# ---------------------------------------------------------------------------
class TestGetAsyncConnection:
    @pytest.mark.asyncio
    async def test_awaits_asyncpg_connect_with_config(self, monkeypatch):
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("TESTING", raising=False)

        fake_conn = MagicMock(name="asyncpg_connection")
        mock_connect = AsyncMock(return_value=fake_conn)
        with patch.object(db_setup.asyncpg, "connect", mock_connect):
            conn = await db_setup.get_async_connection(testing=True)

        assert conn is fake_conn
        mock_connect.assert_awaited_once()
        called_kwargs = mock_connect.await_args.kwargs
        assert called_kwargs["database"] == "neuronews_test"
        assert called_kwargs["user"] == "test_user"


# ---------------------------------------------------------------------------
# create_test_articles -- verify INSERTs are issued and IDs collected.
# ---------------------------------------------------------------------------
class TestCreateTestArticles:
    def test_inserts_requested_number_and_returns_ids(self):
        cursor = MagicMock(name="cursor")
        cursor.fetchone.side_effect = [{"id": i} for i in range(1, 6)]
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False

        conn = MagicMock(name="connection")
        conn.cursor.return_value = cursor
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = False

        with patch.object(db_setup.psycopg2, "connect", return_value=conn):
            ids = db_setup.create_test_articles(count=5)

        assert ids == ["1", "2", "3", "4", "5"]
        assert cursor.execute.call_count == 5
        conn.commit.assert_called_once()

    def test_raises_on_insert_failure(self):
        cursor = MagicMock(name="cursor")
        cursor.execute.side_effect = RuntimeError("insert boom")
        cursor.__enter__.return_value = cursor
        cursor.__exit__.return_value = False

        conn = MagicMock(name="connection")
        conn.cursor.return_value = cursor
        conn.__enter__.return_value = conn
        conn.__exit__.return_value = False

        with patch.object(db_setup.psycopg2, "connect", return_value=conn):
            with pytest.raises(RuntimeError, match="insert boom"):
                db_setup.create_test_articles(count=3)


# ---------------------------------------------------------------------------
# SummaryDatabase / SummaryRecord.
# ---------------------------------------------------------------------------
class TestSummaryDatabase:
    def test_get_connection_uses_connection_params(self):
        params = {
            "host": "db-host",
            "port": 5432,
            "database": "summaries",
            "user": "u",
            "password": "p",
        }
        db = SummaryDatabase(params)
        fake_conn = MagicMock(name="summary_conn")

        with patch("src.nlp.summary_database.psycopg2.connect", return_value=fake_conn) as mock_connect:
            conn = db._get_connection()

        assert conn is fake_conn
        mock_connect.assert_called_once_with(**params)

    def test_summary_record_defaults(self):
        record = SummaryRecord(article_id="a1", summary_text="hello")
        assert record.article_id == "a1"
        assert record.summary_text == "hello"
        assert record.id is None
        assert record.confidence_score == 0.0
        assert record.word_count == 0


# ---------------------------------------------------------------------------
# Sanity: the current setup API surface is present (regression guard for the
# original broken import that referenced non-existent DatabaseSetup classes).
# ---------------------------------------------------------------------------
def test_setup_module_exposes_function_based_api():
    for name in (
        "get_db_config",
        "get_sync_connection",
        "get_async_connection",
        "setup_test_database",
        "cleanup_test_database",
        "create_test_articles",
    ):
        assert callable(getattr(db_setup, name)), f"missing {name}"

    # The classes the old test expected must genuinely not exist.
    assert not hasattr(db_setup, "DatabaseSetup")
    assert not hasattr(db_setup, "DatabaseSetupConfig")
