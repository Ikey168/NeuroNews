"""Coverage tests for src/api/handler.py (AWS Lambda entry point).

``handler.py`` builds ``Mangum(app)`` at import time and imports the full
FastAPI ``app``. Both are heavy *external* concerns for a unit test, so we
install a lightweight ``mangum`` stub and a stub ``src.api.app`` module in
``sys.modules`` BEFORE importing ``src.api.handler``. This lets the module's own
real logic (event validation, response-shape enforcement, header injection,
non-HTTP routing, error formatting) run for real. The Mangum call itself is
replaced per-test via ``handler.handler`` so we can drive the HTTP branch with
controlled responses.
"""
from __future__ import annotations

import importlib
import json
import sys
import types

import pytest


@pytest.fixture(scope="module")
def handler_mod():
    """Import src.api.handler with mangum + src.api.app stubbed out."""
    # --- stub mangum ---------------------------------------------------------
    mangum_stub = types.ModuleType("mangum")

    class _Mangum:
        def __init__(self, app):
            self.app = app

        def __call__(self, event, context):  # pragma: no cover - replaced per test
            return {"statusCode": 200, "body": "{}", "headers": {}}

    mangum_stub.Mangum = _Mangum
    sys.modules["mangum"] = mangum_stub

    # --- stub the heavy FastAPI app -----------------------------------------
    app_stub = types.ModuleType("src.api.app")
    app_stub.app = object()
    sys.modules["src.api.app"] = app_stub

    # Ensure a fresh import that binds to our stubs.
    sys.modules.pop("src.api.handler", None)
    mod = importlib.import_module("src.api.handler")

    # Sanity: the module wired Mangum around our stub app.
    assert mod.handler.app is app_stub.app

    yield mod

    sys.modules.pop("src.api.handler", None)
    sys.modules.pop("mangum", None)
    sys.modules.pop("src.api.app", None)


# ---------------------------------------------------------------------------
# create_error_response
# ---------------------------------------------------------------------------

def test_create_error_response_structure(handler_mod):
    resp = handler_mod.create_error_response(404, "Not here")
    assert resp["statusCode"] == 404
    assert resp["headers"]["Content-Type"] == "application/json"
    assert resp["headers"]["X-Powered-By"] == "NeuroNews-Lambda"
    payload = json.loads(resp["body"])
    assert payload == {"error": "Not here", "statusCode": 404}


# ---------------------------------------------------------------------------
# handle_non_http_event
# ---------------------------------------------------------------------------

def test_handle_non_http_scheduled_event(handler_mod):
    event = {"source": "aws.events", "detail-type": "Scheduled Event"}
    resp = handler_mod.handle_non_http_event(event, None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["message"] == "Scheduled event processed successfully"


def test_handle_non_http_sqs_records_event(handler_mod):
    event = {"Records": [{"body": "1"}, {"body": "2"}, {"body": "3"}]}
    resp = handler_mod.handle_non_http_event(event, None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["message"] == "Processed 3 records"


def test_handle_non_http_unknown_event(handler_mod):
    event = {"foo": "bar"}
    resp = handler_mod.handle_non_http_event(event, None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["message"] == "Event processed"
    assert body["type"] == "unknown"


def test_handle_non_http_event_error_path(handler_mod, monkeypatch):
    """Force the scheduled-branch json.dumps to raise so the except-branch (500)
    is exercised. The recovery path (create_error_response) also calls
    json.dumps, so we make only the FIRST dumps call fail and let subsequent
    ones succeed — otherwise the recovery itself would blow up."""
    real_dumps = json.dumps
    calls = {"n": 0}

    def flaky_dumps(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("dump failed")
        return real_dumps(*a, **k)

    monkeypatch.setattr(handler_mod.json, "dumps", flaky_dumps)
    # 'source' present -> scheduled branch, first dumps() raises -> 500 recovery.
    resp = handler_mod.handle_non_http_event({"source": "aws.events"}, None)
    assert resp["statusCode"] == 500
    assert json.loads(resp["body"])["error"] == "Error processing event"
    assert calls["n"] >= 2  # first failed, recovery re-invoked dumps


# ---------------------------------------------------------------------------
# lambda_handler — validation branches
# ---------------------------------------------------------------------------

def test_lambda_handler_non_dict_event_returns_400(handler_mod):
    resp = handler_mod.lambda_handler(["not", "a", "dict"], None)
    assert resp["statusCode"] == 400
    body = json.loads(resp["body"])
    assert "Bad Request" in body["error"]
    assert "Event must be a dictionary" in body["error"]


def test_lambda_handler_routes_non_http_event(handler_mod):
    # No httpMethod key -> routed to handle_non_http_event (SQS shape here).
    event = {"Records": [{"x": 1}]}
    resp = handler_mod.lambda_handler(event, None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["message"] == "Processed 1 records"


def test_lambda_handler_http_event_success(handler_mod, monkeypatch):
    """Drive the HTTP path with a well-formed Mangum response and assert the
    standard headers are injected."""
    def fake_mangum(event, context):
        return {"statusCode": 201, "body": json.dumps({"ok": True})}

    monkeypatch.setattr(handler_mod, "handler", fake_mangum)

    event = {"httpMethod": "GET", "path": "/health"}
    resp = handler_mod.lambda_handler(event, None)

    assert resp["statusCode"] == 201
    # headers dict was created and standard headers merged in.
    assert resp["headers"]["Content-Type"] == "application/json"
    assert resp["headers"]["X-Powered-By"] == "NeuroNews-Lambda"


def test_lambda_handler_http_event_preserves_existing_headers(handler_mod, monkeypatch):
    def fake_mangum(event, context):
        return {
            "statusCode": 200,
            "body": "{}",
            "headers": {"X-Custom": "keep-me"},
        }

    monkeypatch.setattr(handler_mod, "handler", fake_mangum)

    resp = handler_mod.lambda_handler({"httpMethod": "POST", "path": "/x"}, None)
    assert resp["headers"]["X-Custom"] == "keep-me"
    assert resp["headers"]["X-Powered-By"] == "NeuroNews-Lambda"


def test_lambda_handler_non_dict_response_returns_400(handler_mod, monkeypatch):
    """Mangum returning a non-dict trips 'Handler response must be a dictionary'.
    That ValueError is raised inside the try and caught by `except ValueError`,
    so the handler returns a 400 (not a 500)."""
    def fake_mangum(event, context):
        return "not-a-dict"

    monkeypatch.setattr(handler_mod, "handler", fake_mangum)
    resp = handler_mod.lambda_handler({"httpMethod": "GET", "path": "/x"}, None)
    # The ValueError is caught by `except ValueError` -> 400.
    assert resp["statusCode"] == 400
    assert "Handler response must be a dictionary" in json.loads(resp["body"])["error"]


def test_lambda_handler_missing_required_key_returns_400(handler_mod, monkeypatch):
    def fake_mangum(event, context):
        return {"statusCode": 200}  # missing 'body'

    monkeypatch.setattr(handler_mod, "handler", fake_mangum)
    resp = handler_mod.lambda_handler({"httpMethod": "GET", "path": "/x"}, None)
    assert resp["statusCode"] == 400
    assert "missing required key: body" in json.loads(resp["body"])["error"]


def test_lambda_handler_unexpected_exception_returns_500(handler_mod, monkeypatch):
    def boom(event, context):
        raise RuntimeError("mangum exploded")

    monkeypatch.setattr(handler_mod, "handler", boom)
    resp = handler_mod.lambda_handler({"httpMethod": "GET", "path": "/x"}, None)
    assert resp["statusCode"] == 500
    assert json.loads(resp["body"])["error"] == "Internal Server Error"
