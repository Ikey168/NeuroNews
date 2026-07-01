"""Coverage tests for src/api/routes/alert_routes.py.

Mounts the router on a fresh FastAPI app and hits every endpoint via
TestClient(raise_server_exceptions=False). The endpoints perform late imports
of src.alerts.{store,dispatcher,channels}, so those are patched at their
definition sites. Exercises success, validation (422), not-found (404), and
error (500) branches with real assertions.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _load_alert_routes():
    """Import src.api.routes.alert_routes under its canonical name.

    The real ``src/api/routes/__init__.py`` eagerly imports ~20 sibling route
    modules that pull in torch/transformers/spacy. Tracing that native stack
    under coverage segfaults in this environment. alert_routes.py itself has no
    heavy imports (its src.alerts.* imports are lazy, inside handlers), so we
    load it directly from its file — installing a lightweight placeholder for
    the ``src.api.routes`` package — and skip the heavy package __init__.
    The module keeps its canonical name and __file__, so ``--cov`` still tracks
    it as src.api.routes.alert_routes.
    """
    canonical = "src.api.routes.alert_routes"
    if canonical in sys.modules:
        return sys.modules[canonical]

    import src  # noqa: F401
    import src.api  # lightweight (1-line __init__)

    routes_dir = os.path.join(os.path.dirname(src.api.__file__), "routes")
    if "src.api.routes" not in sys.modules:
        pkg = types.ModuleType("src.api.routes")
        pkg.__path__ = [routes_dir]
        pkg.__package__ = "src.api.routes"
        sys.modules["src.api.routes"] = pkg

    path = os.path.join(routes_dir, "alert_routes.py")
    spec = importlib.util.spec_from_file_location(canonical, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[canonical] = module
    spec.loader.exec_module(module)
    return module


def _install_alerts_stubs():
    """Install lightweight stub modules for src.alerts.{store,dispatcher,channels}.

    The handlers do lazy ``from src.alerts.store import ...`` at request time.
    The real store imports duckdb, whose native extension breaks when imported
    under coverage's tracer in this environment (ModuleNotFoundError for
    ``_duckdb._sqltypes``). Since every test patches these functions anyway, we
    replace the modules with stubs that expose the same callables. ``patch``
    targets the stub attributes, and no native deps are imported. A real
    ``src.alerts`` package (1-line __init__) is kept so ``src.alerts.channels``
    etc. resolve as its submodules.
    """
    import src  # noqa: F401
    import src.alerts  # lightweight package __init__

    def _stub(name, funcs):
        m = sys.modules.get(name)
        if m is None:
            m = types.ModuleType(name)
            m.__package__ = "src.alerts"
            sys.modules[name] = m
            setattr(sys.modules["src.alerts"], name.rsplit(".", 1)[1], m)
        for fn in funcs:
            if not hasattr(m, fn):
                setattr(m, fn, lambda *a, **k: None)
        return m

    _stub("src.alerts.store",
          ["create_rule", "list_rules", "get_rule", "delete_rule", "get_history"])
    _stub("src.alerts.dispatcher",
          ["poll_and_dispatch", "register_sse_client", "unregister_sse_client"])
    _stub("src.alerts.channels", ["dispatch"])


_install_alerts_stubs()
mod = _load_alert_routes()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app, raise_server_exceptions=False)


def _sample_rule(rule_id="abc123"):
    return {
        "id": rule_id,
        "name": "R",
        "topic": "AI",
        "alert_type": "breaking_news",
        "threshold": None,
        "channels": ["email"],
        "email": "e@test",
        "created_at": "2026-01-01 00:00:00",
        "last_fired": None,
        "cooldown_min": 60,
    }


# ---------------------------------------------------------------------------
# POST /rules
# ---------------------------------------------------------------------------

def test_create_rule_success(client):
    with patch("src.alerts.store.create_rule", return_value=_sample_rule()) as m:
        resp = client.post("/api/v1/alerts/rules", json={
            "name": "R",
            "topic": "AI",
            "alert_type": "breaking_news",
            "channels": ["email"],
            "email": "e@test",
        })
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "created"
    assert body["rule"]["id"] == "abc123"
    m.assert_called_once()
    kwargs = m.call_args.kwargs
    assert kwargs["name"] == "R"
    assert kwargs["channels"] == ["email"]


def test_create_rule_invalid_alert_type_422(client):
    resp = client.post("/api/v1/alerts/rules", json={
        "name": "R",
        "topic": "AI",
        "alert_type": "not_a_type",
        "channels": ["email"],
    })
    assert resp.status_code == 422
    assert "alert_type" in resp.text


def test_create_rule_invalid_channel_422(client):
    resp = client.post("/api/v1/alerts/rules", json={
        "name": "R",
        "topic": "AI",
        "alert_type": "breaking_news",
        "channels": ["carrier_pigeon"],
    })
    assert resp.status_code == 422
    assert "Unknown channels" in resp.text


def test_create_rule_empty_channels_422(client):
    resp = client.post("/api/v1/alerts/rules", json={
        "name": "R",
        "topic": "AI",
        "alert_type": "breaking_news",
        "channels": [],
    })
    assert resp.status_code == 422


def test_create_rule_store_error_500(client):
    with patch("src.alerts.store.create_rule", side_effect=RuntimeError("db down")):
        resp = client.post("/api/v1/alerts/rules", json={
            "name": "R",
            "topic": "AI",
            "alert_type": "breaking_news",
            "channels": ["email"],
        })
    assert resp.status_code == 500
    assert "db down" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /rules
# ---------------------------------------------------------------------------

def test_list_rules_success(client):
    with patch("src.alerts.store.list_rules", return_value=[_sample_rule("r1"), _sample_rule("r2")]):
        resp = client.get("/api/v1/alerts/rules")
    assert resp.status_code == 200
    rules = resp.json()["rules"]
    assert [r["id"] for r in rules] == ["r1", "r2"]


def test_list_rules_error_500(client):
    with patch("src.alerts.store.list_rules", side_effect=RuntimeError("boom")):
        resp = client.get("/api/v1/alerts/rules")
    assert resp.status_code == 500
    assert "boom" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /rules/{id}
# ---------------------------------------------------------------------------

def test_get_rule_success(client):
    with patch("src.alerts.store.get_rule", return_value=_sample_rule("r9")):
        resp = client.get("/api/v1/alerts/rules/r9")
    assert resp.status_code == 200
    assert resp.json()["rule"]["id"] == "r9"


def test_get_rule_not_found_404(client):
    with patch("src.alerts.store.get_rule", return_value=None):
        resp = client.get("/api/v1/alerts/rules/missing")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


def test_get_rule_error_500(client):
    with patch("src.alerts.store.get_rule", side_effect=RuntimeError("bad")):
        resp = client.get("/api/v1/alerts/rules/x")
    assert resp.status_code == 500
    assert "bad" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /rules/{id}
# ---------------------------------------------------------------------------

def test_delete_rule_success(client):
    with patch("src.alerts.store.get_rule", return_value=_sample_rule("r5")), \
            patch("src.alerts.store.delete_rule") as dele:
        resp = client.delete("/api/v1/alerts/rules/r5")
    assert resp.status_code == 200
    assert resp.json() == {"status": "deleted", "id": "r5"}
    dele.assert_called_once_with("r5")


def test_delete_rule_not_found_404(client):
    with patch("src.alerts.store.get_rule", return_value=None), \
            patch("src.alerts.store.delete_rule") as dele:
        resp = client.delete("/api/v1/alerts/rules/nope")
    assert resp.status_code == 404
    dele.assert_not_called()


def test_delete_rule_error_500(client):
    with patch("src.alerts.store.get_rule", side_effect=RuntimeError("kaboom")):
        resp = client.delete("/api/v1/alerts/rules/x")
    assert resp.status_code == 500
    assert "kaboom" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /poll
# ---------------------------------------------------------------------------

def test_manual_poll_success(client):
    fired = [{"rule_id": "r1", "title": "t"}, {"rule_id": "r2", "title": "t2"}]
    with patch("src.alerts.dispatcher.poll_and_dispatch", return_value=fired):
        resp = client.post("/api/v1/alerts/poll")
    assert resp.status_code == 200
    body = resp.json()
    assert body["alerts_fired"] == 2
    assert body["alerts"] == fired


def test_manual_poll_error_500(client):
    with patch("src.alerts.dispatcher.poll_and_dispatch", side_effect=RuntimeError("poll fail")):
        resp = client.post("/api/v1/alerts/poll")
    assert resp.status_code == 500
    assert "poll fail" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /history
# ---------------------------------------------------------------------------

def test_get_history_success(client):
    hist = [{"id": "h1", "rule_id": "r1", "alert_type": "new_event",
             "title": "t", "body": "b", "channels": ["email"], "fired_at": "now"}]
    with patch("src.alerts.store.get_history", return_value=hist) as m:
        resp = client.get("/api/v1/alerts/history?limit=10")
    assert resp.status_code == 200
    assert resp.json()["history"] == hist
    assert m.call_args.kwargs["limit"] == 10


def test_get_history_limit_validation_422(client):
    # limit above the le=500 bound is rejected by FastAPI.
    resp = client.get("/api/v1/alerts/history?limit=9999")
    assert resp.status_code == 422


def test_get_history_error_500(client):
    with patch("src.alerts.store.get_history", side_effect=RuntimeError("hist fail")):
        resp = client.get("/api/v1/alerts/history")
    assert resp.status_code == 500
    assert "hist fail" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /stream (SSE)
#
# The endpoint returns a StreamingResponse whose body_iterator is an infinite
# async generator. Driving it via TestClient's streaming client and reading raw
# bytes proved unstable under coverage's C tracer, so the generator is driven
# directly with asyncio: this exercises the connected line, the data-event
# branch (queue item), the keep-alive ping branch (timeout), and the
# finally-block unregister — all with real assertions.
# ---------------------------------------------------------------------------

def test_alert_stream_generator_all_branches():
    import asyncio
    import json as _json

    registered = []
    unregistered = []

    async def _run():
        with patch("src.alerts.dispatcher.register_sse_client", side_effect=registered.append), \
                patch("src.alerts.dispatcher.unregister_sse_client", side_effect=unregistered.append):
            response = await mod.alert_stream()

        assert response.media_type == "text/event-stream"
        assert response.headers["cache-control"] == "no-cache"
        assert response.headers["x-accel-buffering"] == "no"
        # register_sse_client was called with the endpoint's queue.
        assert len(registered) == 1
        q = registered[0]
        assert isinstance(q, asyncio.Queue)

        agen = response.body_iterator

        # 1) Initial keep-alive comment.
        first = await agen.__anext__()
        assert ": connected" in first

        # 2) A queued event is emitted as a `data:` SSE frame.
        event = {"rule_id": "r1", "title": "fire"}
        await q.put(event)
        data_frame = await agen.__anext__()
        assert data_frame.startswith("data: ")
        assert _json.loads(data_frame[len("data: "):].strip()) == event

        # 3) When wait_for times out, the generator emits a ping comment.
        async def _fake_wait_for(coro, timeout):
            # Close the coroutine we were handed to avoid "never awaited".
            coro.close()
            raise asyncio.TimeoutError

        with patch("asyncio.wait_for", side_effect=_fake_wait_for):
            ping = await agen.__anext__()
        assert ": ping" in ping

        # 4) Closing the generator runs the finally-block -> unregister.
        await agen.aclose()
        assert unregistered == [q]

    asyncio.run(_run())


def test_alert_stream_cancelled_error_branch():
    """A CancelledError raised inside the stream loop is swallowed (line 186),
    and the finally-block still unregisters the client."""
    import asyncio

    registered = []
    unregistered = []

    async def _run():
        with patch("src.alerts.dispatcher.register_sse_client", side_effect=registered.append), \
                patch("src.alerts.dispatcher.unregister_sse_client", side_effect=unregistered.append):
            response = await mod.alert_stream()

        agen = response.body_iterator
        # Consume the initial ": connected" frame so the loop is at the await.
        first = await agen.__anext__()
        assert ": connected" in first

        # Throw CancelledError into the generator at its await point. The
        # endpoint catches asyncio.CancelledError and exits cleanly (no reraise),
        # so athrow completes with StopAsyncIteration rather than propagating.
        with pytest.raises(StopAsyncIteration):
            await agen.athrow(asyncio.CancelledError())

        # finally-block ran unregister exactly once for this queue.
        assert len(unregistered) == 1
        assert unregistered[0] is registered[0]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# POST /test/{channel}
# ---------------------------------------------------------------------------

def test_test_channel_invalid_channel_422(client):
    resp = client.post("/api/v1/alerts/test/pigeon")
    assert resp.status_code == 422
    assert "channel must be one of" in resp.json()["detail"]


def test_test_channel_email_missing_address_422(client):
    resp = client.post("/api/v1/alerts/test/email")
    assert resp.status_code == 422
    assert "email" in resp.json()["detail"]


def test_test_channel_slack_delivered(client):
    with patch("src.alerts.channels.dispatch", return_value={"slack": True}) as m:
        resp = client.post("/api/v1/alerts/test/slack")
    assert resp.status_code == 200
    body = resp.json()
    assert body["channel"] == "slack"
    assert body["delivered"] is True
    assert body["note"] == ""
    m.assert_called_once()
    assert m.call_args.args[0] == ["slack"]


def test_test_channel_email_delivered_with_address(client):
    with patch("src.alerts.channels.dispatch", return_value={"email": True}) as m:
        resp = client.post("/api/v1/alerts/test/email?email=me@test")
    assert resp.status_code == 200
    assert resp.json()["delivered"] is True
    assert m.call_args.kwargs["email"] == "me@test"


def test_test_channel_not_delivered_returns_note(client):
    with patch("src.alerts.channels.dispatch", return_value={"telegram": False}):
        resp = client.post("/api/v1/alerts/test/telegram")
    assert resp.status_code == 200
    body = resp.json()
    assert body["delivered"] is False
    assert "Check server logs" in body["note"]
