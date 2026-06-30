"""
Tests for the database setup module (src/database/setup.py).

The current source API is function-based:
    - get_db_config(testing=False) -> dict
    - get_sync_connection(testing=False) -> psycopg2 connection
    - get_async_connection(testing=False) -> asyncpg connection (async)
    - setup_test_database() (async)
    - cleanup_test_database() (async)
    - create_test_articles(count=10) -> list[str]

These tests align with that API. The legacy class-based API
(DatabaseSetup / DatabaseSetupConfig) does not exist in the source and is
intentionally not tested here.
"""

import sys
import types

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

# The source module does ``import asyncpg`` at module load time. asyncpg is an
# optional dependency that may not be installed in the test environment, so we
# provide a lightweight stub before importing the module under test. This keeps
# collection from crashing without weakening any assertions.
if "asyncpg" not in sys.modules:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        _asyncpg_stub = types.ModuleType("asyncpg")
        _asyncpg_stub.Connection = type("Connection", (), {})
        # ``connect`` is patched per-test; provide a placeholder so attribute
        # access during patching resolves.
        _asyncpg_stub.connect = lambda *a, **k: None
        sys.modules["asyncpg"] = _asyncpg_stub

from src.database import setup as db_setup_mod  # noqa: E402
from src.database.setup import (  # noqa: E402
    get_db_config,
    get_sync_connection,
    get_async_connection,
    create_test_articles,
    setup_test_database,
    cleanup_test_database,
)


class TestGetDbConfig:
    """Tests for get_db_config()."""

    def test_dev_config_defaults(self, monkeypatch):
        """Non-testing config returns the development defaults."""
        for var in (
            "TESTING",
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
        ):
            monkeypatch.delenv(var, raising=False)

        config = get_db_config(testing=False)

        assert config == {
            "host": "postgres",
            "port": 5432,
            "database": "neuronews_dev",
            "user": "neuronews",
            "password": "dev_password",
        }

    def test_testing_config_defaults(self, monkeypatch):
        """Testing config returns the test defaults."""
        for var in (
            "TESTING",
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
        ):
            monkeypatch.delenv(var, raising=False)

        config = get_db_config(testing=True)

        assert config == {
            "host": "test-postgres",
            "port": 5432,
            "database": "neuronews_test",
            "user": "test_user",
            "password": "test_password",
        }

    def test_testing_flag_via_env(self, monkeypatch):
        """The TESTING env var forces the test configuration."""
        for var in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("TESTING", "1")

        config = get_db_config(testing=False)

        assert config["database"] == "neuronews_test"
        assert config["host"] == "test-postgres"

    def test_env_overrides(self, monkeypatch):
        """Environment variables override the defaults, and port is an int."""
        monkeypatch.delenv("TESTING", raising=False)
        monkeypatch.setenv("DB_HOST", "env-host")
        monkeypatch.setenv("DB_PORT", "5433")
        monkeypatch.setenv("DB_NAME", "env_db")
        monkeypatch.setenv("DB_USER", "env_user")
        monkeypatch.setenv("DB_PASSWORD", "env_pass")

        config = get_db_config(testing=False)

        assert config["host"] == "env-host"
        assert config["port"] == 5433
        assert isinstance(config["port"], int)
        assert config["database"] == "env_db"
        assert config["user"] == "env_user"
        assert config["password"] == "env_pass"


class TestGetSyncConnection:
    """Tests for get_sync_connection()."""

    def test_sync_connection_uses_psycopg2(self, monkeypatch):
        """A sync connection is created via psycopg2.connect with the config."""
        monkeypatch.delenv("TESTING", raising=False)
        with patch.object(db_setup_mod.psycopg2, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_connect.return_value = mock_conn

            result = get_sync_connection(testing=True)

            assert result is mock_conn
            mock_connect.assert_called_once()
            # Connection is established with the testing config kwargs.
            _, kwargs = mock_connect.call_args
            assert kwargs["database"] == "neuronews_test"
            assert kwargs["user"] == "test_user"
            assert kwargs["host"] == "test-postgres"
            assert kwargs["port"] == 5432


@pytest.mark.asyncio
class TestGetAsyncConnection:
    """Tests for get_async_connection()."""

    async def test_async_connection_uses_asyncpg(self, monkeypatch):
        """An async connection awaits asyncpg.connect with the config."""
        monkeypatch.delenv("TESTING", raising=False)
        mock_conn = MagicMock()
        # asyncpg.connect is a coroutine function -> AsyncMock.
        with patch.object(
            db_setup_mod.asyncpg, "connect", new=AsyncMock(return_value=mock_conn)
        ) as mock_connect:
            result = await get_async_connection(testing=True)

            assert result is mock_conn
            mock_connect.assert_awaited_once()
            _, kwargs = mock_connect.call_args
            assert kwargs["database"] == "neuronews_test"
            assert kwargs["user"] == "test_user"


class TestCreateTestArticles:
    """Tests for create_test_articles()."""

    def test_create_test_articles_inserts_and_returns_ids(self):
        """create_test_articles inserts each article and returns their ids."""
        count = 3

        # Build a cursor that returns a fresh id for every fetchone() call.
        ids = iter([{"id": i} for i in range(1, count + 1)])
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = lambda: next(ids)

        # Cursor is used as a context manager: conn.cursor(...) -> cm -> cursor.
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = mock_cursor
        cursor_cm.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor_cm

        # Connection is used as a context manager too.
        conn_cm = MagicMock()
        conn_cm.__enter__.return_value = mock_conn
        conn_cm.__exit__.return_value = False

        with patch.object(
            db_setup_mod, "get_sync_connection", return_value=conn_cm
        ) as mock_get_conn:
            result = create_test_articles(count=count)

            mock_get_conn.assert_called_once_with(testing=True)
            assert result == ["1", "2", "3"]
            assert mock_cursor.execute.call_count == count
            mock_conn.commit.assert_called_once()

    def test_create_test_articles_raises_on_error(self):
        """Database errors are propagated (the source re-raises)."""
        with patch.object(
            db_setup_mod, "get_sync_connection", side_effect=RuntimeError("boom")
        ):
            with pytest.raises(RuntimeError, match="boom"):
                create_test_articles(count=1)


@pytest.mark.asyncio
class TestSetupTestDatabase:
    """Tests for the async setup/cleanup helpers."""

    async def test_setup_test_database_truncates_existing_tables(self):
        """setup_test_database verifies tables and truncates existing ones."""
        mock_cursor = MagicMock()
        # information_schema query returns two of the known test tables.
        mock_cursor.fetchall.return_value = [("articles",), ("api_keys",)]

        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = mock_cursor
        cursor_cm.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor_cm
        mock_conn.close.return_value = None

        conn_cm = MagicMock()
        conn_cm.__enter__.return_value = mock_conn
        conn_cm.__exit__.return_value = False

        # get_sync_connection is called once for the readiness probe (closed
        # immediately) and once as a context manager for the real work.
        with patch.object(
            db_setup_mod,
            "get_sync_connection",
            side_effect=[mock_conn, conn_cm],
        ) as mock_get_conn:
            await setup_test_database()

        assert mock_get_conn.call_count == 2
        # The first call's connection is closed (readiness probe).
        mock_conn.close.assert_called()
        # Both present tables get truncated.
        truncate_calls = [
            c.args[0]
            for c in mock_cursor.execute.call_args_list
            if "TRUNCATE" in c.args[0]
        ]
        assert any("articles" in q for q in truncate_calls)
        assert any("api_keys" in q for q in truncate_calls)
        mock_conn.commit.assert_called_once()

    async def test_cleanup_test_database_truncates_all(self):
        """cleanup_test_database truncates the full set of tables."""
        mock_cursor = MagicMock()
        cursor_cm = MagicMock()
        cursor_cm.__enter__.return_value = mock_cursor
        cursor_cm.__exit__.return_value = False

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = cursor_cm

        conn_cm = MagicMock()
        conn_cm.__enter__.return_value = mock_conn
        conn_cm.__exit__.return_value = False

        with patch.object(
            db_setup_mod, "get_sync_connection", return_value=conn_cm
        ):
            await cleanup_test_database()

        mock_cursor.execute.assert_called_once()
        executed_sql = mock_cursor.execute.call_args.args[0]
        assert "TRUNCATE TABLE" in executed_sql
        assert "neuronews.articles" in executed_sql
        mock_conn.commit.assert_called_once()

    async def test_cleanup_test_database_swallows_errors(self):
        """cleanup_test_database logs and does not re-raise on failure."""
        with patch.object(
            db_setup_mod,
            "get_sync_connection",
            side_effect=RuntimeError("cleanup failed"),
        ):
            # Source catches the exception and only logs it; no raise expected.
            await cleanup_test_database()
