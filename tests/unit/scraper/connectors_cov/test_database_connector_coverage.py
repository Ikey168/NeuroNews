"""
Coverage-focused tests for
src/scraper/extensions/connectors/database_connector.py

The production module hard-imports ``asyncpg``, ``aiomysql`` and
``aiosqlite`` which are not installed in this environment. We install
lightweight ``sys.modules`` stubs *before* importing the module so it loads,
then drive the parsing / record-production logic against mocked drivers.

All assertions are real: they check the exact records / return values /
error behaviour produced by the connector's own code.
"""

import asyncio
import sys
import types

import pytest


# ---------------------------------------------------------------------------
# Install lightweight driver stubs BEFORE importing the target module.
# ---------------------------------------------------------------------------
def _install_db_stubs():
    if "asyncpg" not in sys.modules:
        asyncpg = types.ModuleType("asyncpg")
        asyncpg.connect = None  # replaced per-test with an AsyncMock
        sys.modules["asyncpg"] = asyncpg

    if "aiomysql" not in sys.modules:
        aiomysql = types.ModuleType("aiomysql")

        class DictCursor:  # marker type used by the connector
            pass

        aiomysql.DictCursor = DictCursor
        aiomysql.connect = None
        sys.modules["aiomysql"] = aiomysql

    if "aiosqlite" not in sys.modules:
        aiosqlite = types.ModuleType("aiosqlite")

        class Row:  # marker type used by the connector
            pass

        aiosqlite.Row = Row
        aiosqlite.connect = None
        sys.modules["aiosqlite"] = aiosqlite


_install_db_stubs()

from src.scraper.extensions.connectors.database_connector import (  # noqa: E402
    DatabaseConnector,
)
from src.scraper.extensions.connectors.base import ConnectionError  # noqa: E402


# ---------------------------------------------------------------------------
# Small async mock helpers.
# ---------------------------------------------------------------------------
class _Coro:
    """Callable returning a coroutine that yields a fixed value / raises."""

    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    async def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.exc is not None:
            raise self.exc
        return self.result


class _AsyncCtx:
    """Async context manager wrapping a value (for cursor / execute)."""

    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


# ---------------------------------------------------------------------------
# Construction / config validation.
# ---------------------------------------------------------------------------
def test_init_defaults_to_postgresql():
    conn = DatabaseConnector({})
    assert conn.db_type == "postgresql"
    assert conn._connection is None
    assert conn.is_connected is False


def test_init_lowercases_db_type():
    conn = DatabaseConnector({"type": "SQLite", "database": "x.db"})
    assert conn.db_type == "sqlite"


def test_validate_config_missing_type():
    assert DatabaseConnector({}).validate_config() is False


def test_validate_config_postgresql_requires_host_and_database():
    assert (
        DatabaseConnector({"type": "postgresql", "host": "h"}).validate_config()
        is False
    )
    assert (
        DatabaseConnector(
            {"type": "postgresql", "host": "h", "database": "d"}
        ).validate_config()
        is True
    )


def test_validate_config_mysql_requires_host_and_database():
    assert (
        DatabaseConnector(
            {"type": "mysql", "host": "h", "database": "d"}
        ).validate_config()
        is True
    )
    assert (
        DatabaseConnector({"type": "mysql", "database": "d"}).validate_config()
        is False
    )


def test_validate_config_sqlite_requires_database_path():
    assert (
        DatabaseConnector({"type": "sqlite", "database": "f.db"}).validate_config()
        is True
    )
    assert DatabaseConnector({"type": "sqlite"}).validate_config() is False


def test_validate_config_unsupported_type():
    assert DatabaseConnector({"type": "oracle"}).validate_config() is False


# ---------------------------------------------------------------------------
# connect() dispatch.
# ---------------------------------------------------------------------------
def test_connect_postgresql_builds_params_and_marks_connected():
    fake_conn = object()
    connect_mock = _Coro(result=fake_conn)
    sys.modules["asyncpg"].connect = connect_mock

    conn = DatabaseConnector(
        {
            "type": "postgresql",
            "host": "db.example",
            "port": 6000,
            "database": "news",
        },
        auth_config={"username": "u", "password": "p"},
    )

    assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True
    assert conn._connection is fake_conn

    # connection params were built from config + auth_config, no None values.
    _, kwargs = connect_mock.calls[0]
    assert kwargs["host"] == "db.example"
    assert kwargs["port"] == 6000
    assert kwargs["user"] == "u"
    assert kwargs["password"] == "p"
    assert kwargs["database"] == "news"


def test_connect_postgresql_default_port_and_drops_none():
    connect_mock = _Coro(result=object())
    sys.modules["asyncpg"].connect = connect_mock

    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    assert asyncio.run(conn.connect()) is True

    _, kwargs = connect_mock.calls[0]
    assert kwargs["port"] == 5432  # default
    # user/password were None (no auth) and must be stripped out.
    assert "user" not in kwargs
    assert "password" not in kwargs


def test_connect_mysql_builds_db_param():
    connect_mock = _Coro(result=object())
    sys.modules["aiomysql"].connect = connect_mock

    conn = DatabaseConnector(
        {"type": "mysql", "host": "h", "database": "d"},
        auth_config={"username": "root", "password": "secret"},
    )
    assert asyncio.run(conn.connect()) is True

    _, kwargs = connect_mock.calls[0]
    assert kwargs["db"] == "d"
    assert kwargs["port"] == 3306
    assert kwargs["user"] == "root"


def test_connect_sqlite_uses_database_path():
    connect_mock = _Coro(result=object())
    sys.modules["aiosqlite"].connect = connect_mock

    conn = DatabaseConnector({"type": "sqlite", "database": "/tmp/x.db"})
    assert asyncio.run(conn.connect()) is True

    args, _ = connect_mock.calls[0]
    assert args == ("/tmp/x.db",)


def test_connect_unsupported_type_returns_false_and_records_error():
    conn = DatabaseConnector({"type": "weird", "database": "d"})
    conn.db_type = "weird"  # bypass validate; exercise connect dispatch
    assert asyncio.run(conn.connect()) is False
    assert conn.is_connected is False
    assert isinstance(conn.last_error, ConnectionError)


def test_connect_driver_exception_returns_false():
    sys.modules["asyncpg"].connect = _Coro(exc=RuntimeError("boom"))
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    assert asyncio.run(conn.connect()) is False
    assert isinstance(conn.last_error, ConnectionError)
    assert "boom" in str(conn.last_error)


def test_connect_reuses_open_connection():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})

    class _Existing:
        is_closed = False

    conn._connection = _Existing()
    assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True


# ---------------------------------------------------------------------------
# disconnect().
# ---------------------------------------------------------------------------
def test_disconnect_sync_close():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})

    closed = {"v": False}

    class _Conn:
        def close(self):
            closed["v"] = True

    conn._connection = _Conn()
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert closed["v"] is True
    assert conn.is_connected is False


def test_disconnect_async_close():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})

    state = {"closed": False}

    class _Conn:
        async def close(self):
            state["closed"] = True

    conn._connection = _Conn()
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert state["closed"] is True
    assert conn.is_connected is False


def test_disconnect_no_connection_noop():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert conn.is_connected is False


# ---------------------------------------------------------------------------
# fetch_data() dispatch + per-driver parsing.
# ---------------------------------------------------------------------------
def test_fetch_data_requires_connection():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data("SELECT 1"))


def test_fetch_postgresql_maps_rows_to_dicts():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        def __init__(self):
            self.captured = None

        async def fetch(self, query, *params):
            self.captured = (query, params)
            # asyncpg Records behave like mappings -> dict(row) works.
            return [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]

    conn._connection = _FakeConn()

    rows = asyncio.run(conn.fetch_data("SELECT * FROM t WHERE id=$1", [1]))
    assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
    # list params are splatted into positional args.
    assert conn._connection.captured == ("SELECT * FROM t WHERE id=$1", (1,))


def test_fetch_postgresql_no_params():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        async def fetch(self, query, *params):
            assert params == ()
            return [{"n": 1}]

    conn._connection = _FakeConn()
    assert asyncio.run(conn.fetch_data("SELECT 1")) == [{"n": 1}]


def test_fetch_mysql_uses_dict_cursor():
    conn = DatabaseConnector({"type": "mysql", "host": "h", "database": "d"})
    conn._connected = True

    expected = [{"col": "v1"}, {"col": "v2"}]

    class _Cursor:
        def __init__(self):
            self.executed = None

        async def execute(self, query, params):
            self.executed = (query, params)

        async def fetchall(self):
            return expected

    cursor = _Cursor()

    class _FakeConn:
        def cursor(self, cursor_type):
            # connector passes aiomysql.DictCursor
            assert cursor_type is sys.modules["aiomysql"].DictCursor
            return _AsyncCtx(cursor)

    conn._connection = _FakeConn()
    rows = asyncio.run(conn.fetch_data("SELECT * FROM t WHERE a=%s", ["x"]))
    assert rows == expected
    assert cursor.executed == ("SELECT * FROM t WHERE a=%s", ["x"])


def test_fetch_sqlite_maps_rows_to_dicts():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    conn._connected = True

    class _Cursor:
        async def fetchall(self):
            return [{"id": 1}, {"id": 2}]

    class _FakeConn:
        def __init__(self):
            self.row_factory = None
            self.executed = None

        def execute(self, query, params):
            self.executed = (query, params)
            return _AsyncCtx(_Cursor())

    conn._connection = _FakeConn()
    rows = asyncio.run(conn.fetch_data("SELECT * FROM t"))
    assert rows == [{"id": 1}, {"id": 2}]
    # row_factory is set to aiosqlite.Row by the connector.
    assert conn._connection.row_factory is sys.modules["aiosqlite"].Row
    assert conn._connection.executed == ("SELECT * FROM t", [])


def test_fetch_data_wraps_driver_errors():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        async def fetch(self, query, *params):
            raise RuntimeError("db down")

    conn._connection = _FakeConn()
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data("SELECT 1"))
    assert "db down" in str(ei.value)
    assert isinstance(conn.last_error, RuntimeError)


# ---------------------------------------------------------------------------
# execute_query().
# ---------------------------------------------------------------------------
def test_execute_query_requires_connection():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.execute_query("DELETE FROM t"))


def test_execute_query_postgresql_parses_affected_rows():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        async def execute(self, query, *params):
            return "INSERT 0 5"

    conn._connection = _FakeConn()
    assert asyncio.run(conn.execute_query("INSERT ...", [1, 2])) == 5


def test_execute_query_postgresql_empty_result_zero():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        async def execute(self, query, *params):
            return ""

    conn._connection = _FakeConn()
    assert asyncio.run(conn.execute_query("UPDATE t SET a=1")) == 0


def test_execute_query_mysql_commits_and_returns_rowcount():
    conn = DatabaseConnector({"type": "mysql", "host": "h", "database": "d"})
    conn._connected = True

    class _Cursor:
        rowcount = 3

        async def execute(self, query, params):
            self.q = (query, params)

    committed = {"v": False}

    class _FakeConn:
        def cursor(self):
            return _AsyncCtx(_Cursor())

        async def commit(self):
            committed["v"] = True

    conn._connection = _FakeConn()
    assert asyncio.run(conn.execute_query("DELETE FROM t", [9])) == 3
    assert committed["v"] is True


def test_execute_query_sqlite_returns_total_changes():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    conn._connected = True

    committed = {"v": False}

    class _FakeConn:
        total_changes = 7

        async def execute(self, query, params):
            self.q = (query, params)

        async def commit(self):
            committed["v"] = True

    conn._connection = _FakeConn()
    assert asyncio.run(conn.execute_query("INSERT ...")) == 7
    assert committed["v"] is True


def test_execute_query_wraps_errors():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        async def execute(self, query, *params):
            raise RuntimeError("bad sql")

    conn._connection = _FakeConn()
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.execute_query("BOOM"))
    assert "bad sql" in str(ei.value)


# ---------------------------------------------------------------------------
# validate_data_format().
# ---------------------------------------------------------------------------
def test_validate_data_format_non_dict():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    assert conn.validate_data_format(["not", "a", "dict"]) is False
    assert conn.validate_data_format("str") is False


def test_validate_data_format_json_serializable_with_default_str():
    import datetime as _dt

    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    # datetime is not JSON serializable normally, but default=str handles it.
    assert conn.validate_data_format({"ts": _dt.datetime(2020, 1, 1)}) is True
    assert conn.validate_data_format({"a": 1, "b": "x"}) is True


def test_validate_data_format_unserializable_returns_false():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})

    class _NotSerializable:
        def __repr__(self):
            raise TypeError("nope")

    # json.dumps(..., default=str) calls str() which calls __repr__ -> TypeError
    assert conn.validate_data_format({"x": _NotSerializable()}) is False


# ---------------------------------------------------------------------------
# test_query() convenience.
# ---------------------------------------------------------------------------
def test_test_query_true_on_success():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    conn._connected = True

    class _Cursor:
        async def fetchall(self):
            return [{"1": 1}]

    class _FakeConn:
        def __init__(self):
            self.row_factory = None

        def execute(self, query, params):
            return _AsyncCtx(_Cursor())

    conn._connection = _FakeConn()
    assert asyncio.run(conn.test_query()) is True


def test_test_query_false_on_failure():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    # not connected -> fetch_data raises -> test_query swallows -> False
    assert asyncio.run(conn.test_query()) is False


# ---------------------------------------------------------------------------
# get_table_info().
# ---------------------------------------------------------------------------
def test_get_table_info_requires_connection():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.get_table_info("articles"))


def test_get_table_info_postgresql():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    cols = [
        {"column_name": "id", "data_type": "integer"},
        {"column_name": "title", "data_type": "text"},
    ]

    class _FakeConn:
        async def fetch(self, query, *params):
            assert "information_schema.columns" in query
            assert params == ("articles",)
            return cols

    conn._connection = _FakeConn()
    info = asyncio.run(conn.get_table_info("articles"))
    assert info["table_name"] == "articles"
    assert info["column_count"] == 2
    assert info["columns"] == cols


def test_get_table_info_sqlite_maps_pragma():
    conn = DatabaseConnector({"type": "sqlite", "database": "d"})
    conn._connected = True

    pragma_rows = [
        {"name": "id", "type": "INTEGER", "notnull": 1, "dflt_value": None},
        {"name": "body", "type": "TEXT", "notnull": 0, "dflt_value": "''"},
    ]

    class _Cursor:
        async def fetchall(self):
            return pragma_rows

    class _FakeConn:
        def __init__(self):
            self.row_factory = None

        def execute(self, query, params):
            assert query.startswith("PRAGMA table_info")
            return _AsyncCtx(_Cursor())

    conn._connection = _FakeConn()
    info = asyncio.run(conn.get_table_info("mytable"))
    assert info["column_count"] == 2
    # notnull=1 -> not nullable -> "NO"; notnull=0 -> "YES"
    assert info["columns"][0] == {
        "column_name": "id",
        "data_type": "INTEGER",
        "is_nullable": "NO",
        "column_default": None,
    }
    assert info["columns"][1]["is_nullable"] == "YES"
    assert info["columns"][1]["column_default"] == "''"


def test_get_table_info_wraps_errors():
    conn = DatabaseConnector({"type": "postgresql", "host": "h", "database": "d"})
    conn._connected = True

    class _FakeConn:
        async def fetch(self, query, *params):
            raise RuntimeError("no table")

    conn._connection = _FakeConn()
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.get_table_info("ghost"))
    assert "no table" in str(ei.value)
