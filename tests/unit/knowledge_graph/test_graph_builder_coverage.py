"""Coverage tests for src/knowledge_graph/graph_builder.py.

Targets branches the existing graph_builder tests leave uncovered:

  * connect() early-return when the connection is already open (lines 30-32)
  * connect() failure path -- Client raises, state reset + re-raise (lines 68-72)
  * _execute_traversal raising ConnectionError when no client after connect
    (lines 77-80)
  * _execute_traversal error path when submit_async raises (lines 126-130)
  * query_vertices with and without property filters (lines 199-213)
  * close() nested-loop skip in non-force mode (lines 243-244)
  * close() exception swallowing (lines 248-249)
  * close() with no active client (line 261)
  * async context manager __aenter__/__aexit__ (lines 266-270)

We drive the coroutines with asyncio.run inside a fresh loop so that the
"nested event loop" detection in _execute_traversal does NOT kick in when
force_websocket_mode is False, letting us exercise the real submit paths and
the close() skip branch deterministically.

gremlin_python is a hard import of the module, so guard it.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("gremlin_python")

from src.knowledge_graph.graph_builder import GraphBuilder  # noqa: E402

ENDPOINT = "ws://mock-neptune:8182/gremlin"


def _mock_result_set(data):
    rs = MagicMock()

    async def _all():
        return data

    rs.all = AsyncMock(side_effect=_all)
    return rs


def _run(coro):
    """Run a coroutine on a fresh event loop (no ambient running loop)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------

def test_connect_returns_early_if_already_connected():
    builder = GraphBuilder(ENDPOINT)
    # Simulate an existing, open connection.
    fake_conn = MagicMock()
    fake_conn.closed = False
    builder.connection = fake_conn

    with patch("src.knowledge_graph.graph_builder.Client") as MockedClient:
        _run(builder.connect())
        # Early return -> Client must never be constructed.
        MockedClient.assert_not_called()
    assert builder.connection is fake_conn


def test_connect_failure_resets_state_and_reraises():
    builder = GraphBuilder(ENDPOINT)
    with patch(
        "src.knowledge_graph.graph_builder.Client",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(RuntimeError, match="boom"):
            _run(builder.connect())
    # State must be cleaned up after a failed connect.
    assert builder.connection is None
    assert builder.g is None


# ---------------------------------------------------------------------------
# _execute_traversal error handling
# ---------------------------------------------------------------------------

def test_execute_traversal_raises_when_client_never_established():
    builder = GraphBuilder(ENDPOINT)

    async def scenario():
        # connect() is patched to a no-op that leaves client None.
        async def noop():
            return None

        builder.connect = noop  # type: ignore[assignment]
        traversal_obj = MagicMock()
        await builder._execute_traversal(traversal_obj)

    with pytest.raises(ConnectionError, match="Gremlin client not connected"):
        _run(scenario())


def test_execute_traversal_propagates_submit_error():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)

    async def scenario():
        builder.client = MagicMock()
        builder.client.submit_async = AsyncMock(side_effect=ValueError("query failed"))
        traversal_obj = MagicMock()
        traversal_obj.bytecode = "bc"
        await builder._execute_traversal(traversal_obj)

    with pytest.raises(ValueError, match="query failed"):
        _run(scenario())


def test_execute_traversal_returns_results_on_success():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)

    async def scenario():
        builder.client = MagicMock()
        builder.client.submit_async = AsyncMock(
            return_value=_mock_result_set([{"id": "v1"}])
        )
        traversal_obj = MagicMock()
        traversal_obj.bytecode = "bc"
        return await builder._execute_traversal(traversal_obj)

    result = _run(scenario())
    assert result == [{"id": "v1"}]


# ---------------------------------------------------------------------------
# query_vertices (lines 199-213)
# ---------------------------------------------------------------------------

def _builder_with_stub_g(result):
    """Return a builder whose .g is a chainable stub and _execute_traversal is stubbed."""
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    # chainable traversal stub: every method returns the same object.
    chain = MagicMock()
    chain.hasLabel.return_value = chain
    chain.has.return_value = chain
    chain.valueMap.return_value = chain
    g = MagicMock()
    g.V.return_value = chain
    builder.g = g
    builder._execute_traversal = AsyncMock(return_value=result)
    return builder, chain


def test_query_vertices_without_filters():
    builder, chain = _builder_with_stub_g([{"id": "v1"}, {"id": "v2"}])
    res = _run(builder.query_vertices("Person"))
    assert res == [{"id": "v1"}, {"id": "v2"}]
    chain.hasLabel.assert_called_once_with("Person")
    # No property filters -> has() should not be called for filtering.
    chain.has.assert_not_called()


def test_query_vertices_with_filters():
    builder, chain = _builder_with_stub_g([{"id": "v9"}])
    res = _run(builder.query_vertices("Person", {"name": "Alice", "age": 30}))
    assert res == [{"id": "v9"}]
    # Both property filters applied.
    assert chain.has.call_count == 2


def test_query_vertices_empty_result_returns_empty_list():
    builder, _ = _builder_with_stub_g([])
    res = _run(builder.query_vertices("Person"))
    assert res == []


def test_query_vertices_connects_when_g_missing():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    builder.g = None
    connect_called = {"n": 0}

    async def fake_connect():
        connect_called["n"] += 1
        chain = MagicMock()
        chain.hasLabel.return_value = chain
        chain.valueMap.return_value = chain
        g = MagicMock()
        g.V.return_value = chain
        builder.g = g

    builder.connect = fake_connect  # type: ignore[assignment]
    builder._execute_traversal = AsyncMock(return_value=[{"id": "x"}])
    res = _run(builder.query_vertices("Org"))
    assert res == [{"id": "x"}]
    assert connect_called["n"] == 1


# ---------------------------------------------------------------------------
# "if not self.g: await self.connect()" guards on the CRUD helpers
# ---------------------------------------------------------------------------

def _builder_that_connects_on_demand(result):
    """Builder starting with g=None; connect() installs a chainable stub g."""
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    builder.g = None

    async def fake_connect():
        chain = MagicMock()
        for name in ("addV", "property", "valueMap", "V", "has", "addE",
                     "to", "both", "hasLabel", "drop"):
            getattr(chain, name).return_value = chain
        g = MagicMock()
        for name in ("addV", "V"):
            getattr(g, name).return_value = chain
        builder.g = g

    builder.connect = fake_connect  # type: ignore[assignment]
    builder._execute_traversal = AsyncMock(return_value=result)
    return builder


def test_add_vertex_connects_when_g_missing():
    builder = _builder_that_connects_on_demand([{"id": "v1"}])
    res = _run(builder.add_vertex("Person", {"id": "v1", "name": "A"}))
    assert res == {"id": "v1"}
    assert builder.g is not None


def test_add_vertex_missing_id_raises_before_connect():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    with pytest.raises(ValueError, match="must include an 'id'"):
        _run(builder.add_vertex("Person", {"name": "no id"}))


def test_add_relationship_connects_when_g_missing():
    builder = _builder_that_connects_on_demand([{"id": "e1"}])
    res = _run(builder.add_relationship("v1", "v2", "REL", {"w": 1}))
    assert res == {"id": "e1"}


def test_get_related_vertices_connects_when_g_missing():
    builder = _builder_that_connects_on_demand([{"id": "v2"}])
    res = _run(builder.get_related_vertices("v1", "REL"))
    assert res == [{"id": "v2"}]


def test_get_vertex_by_id_connects_when_g_missing():
    builder = _builder_that_connects_on_demand([{"id": "v1"}])
    res = _run(builder.get_vertex_by_id("v1"))
    assert res == {"id": "v1"}


def test_get_vertex_by_id_returns_none_when_empty():
    builder = _builder_that_connects_on_demand([])
    assert _run(builder.get_vertex_by_id("missing")) is None


def test_delete_and_clear_connect_when_g_missing():
    builder = _builder_that_connects_on_demand([])
    _run(builder.delete_vertex("v1"))
    builder2 = _builder_that_connects_on_demand([])
    _run(builder2.clear_graph())
    # Both drove _execute_traversal without raising.
    assert builder._execute_traversal.await_count == 1
    assert builder2._execute_traversal.await_count == 1


def test_add_article_requires_id():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    with pytest.raises(ValueError, match="Article data must include an 'id'"):
        _run(builder.add_article({"headline": "no id"}))


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------

def test_close_with_no_client_logs_and_returns():
    builder = GraphBuilder(ENDPOINT)
    builder.client = None
    # Should simply return without error (line 261 branch).
    _run(builder.close())
    assert builder.client is None


def test_close_skips_when_nested_loop_and_not_forced():
    # force_websocket_mode is False (default) -> close() detects the running loop
    # created by asyncio.run and skips the async close (lines 243-244).
    builder = GraphBuilder(ENDPOINT)
    close_mock = AsyncMock()
    builder.client = MagicMock()
    builder.client.close = close_mock

    _run(builder.close())

    # The async close was skipped -> client.close() was never awaited. The early
    # return still runs the finally block, so the client reference is cleared.
    close_mock.assert_not_called()
    assert builder.client is None


def test_close_swallows_exceptions_in_force_mode():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    builder.client = MagicMock()
    builder.client.close = AsyncMock(side_effect=RuntimeError("close failed"))

    # Exception is caught and logged; finally-block nulls out the client.
    _run(builder.close())
    assert builder.client is None
    assert builder.connection is None
    assert builder.g is None


# ---------------------------------------------------------------------------
# async context manager
# ---------------------------------------------------------------------------

def test_async_context_manager_enters_and_exits():
    builder = GraphBuilder(ENDPOINT, force_websocket_mode=True)
    calls = {"connect": 0, "close": 0}

    async def fake_connect():
        calls["connect"] += 1

    async def fake_close():
        calls["close"] += 1

    builder.connect = fake_connect  # type: ignore[assignment]
    builder.close = fake_close  # type: ignore[assignment]

    async def scenario():
        async with builder as b:
            assert b is builder
        return True

    assert _run(scenario()) is True
    assert calls["connect"] == 1
    assert calls["close"] == 1
