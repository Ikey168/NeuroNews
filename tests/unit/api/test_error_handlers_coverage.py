"""Coverage tests for src/api/error_handlers.py.

Registers the real error handlers on a fresh FastAPI app, wires routes that raise
each exception type, and asserts the JSON response shape/status via TestClient.
Also exercises the static ErrorResponse builder, the Database/Auth handler
classes, the raise_* helpers, and the custom exception classes directly.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

import src.api.error_handlers as eh


# ---------------------------------------------------------------------------
# App fixture with handlers registered + routes that raise each error type
# ---------------------------------------------------------------------------

class _Item(BaseModel):
    name: str
    count: int


@pytest.fixture
def client():
    app = FastAPI()
    eh.configure_error_handlers(app)

    @app.get("/http-404")
    def _http_404():
        raise HTTPException(status_code=404, detail="Widget missing")

    @app.get("/http-teapot")
    def _http_teapot():
        # 418 is not in the error_code_map -> UNKNOWN_ERROR branch.
        raise HTTPException(status_code=418, detail="I am a teapot")

    @app.post("/validate")
    def _validate(item: _Item):  # triggers RequestValidationError on bad body
        return {"ok": True}

    @app.get("/pydantic")
    def _pydantic():
        # Direct pydantic validation error (not the FastAPI request one).
        _Item(name="x")  # missing 'count'
        return {"ok": True}

    @app.get("/boom")
    def _boom():
        raise RuntimeError("unexpected kaboom")

    @app.get("/starlette")
    def _starlette():
        raise StarletteHTTPException(status_code=503, detail="Down for maintenance")

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# http_exception_handler
# ---------------------------------------------------------------------------

def test_http_exception_mapped_error_code(client):
    resp = client.get("/http-404")
    assert resp.status_code == 404
    body = resp.json()["error"]
    assert body["status_code"] == 404
    assert body["message"] == "Widget missing"
    assert body["code"] == "NOT_FOUND"
    assert body["path"] == "/http-404"
    assert body["timestamp"].endswith("Z")


def test_http_exception_unknown_status_code(client):
    resp = client.get("/http-teapot")
    assert resp.status_code == 418
    body = resp.json()["error"]
    assert body["code"] == "UNKNOWN_ERROR"
    assert body["status_code"] == 418


# ---------------------------------------------------------------------------
# validation_exception_handler (RequestValidationError)
# ---------------------------------------------------------------------------

def test_request_validation_error(client):
    resp = client.post("/validate", json={"name": "x"})  # missing 'count'
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"] == "Validation failed"
    assert isinstance(body["details"], list)
    assert body["details"]
    first = body["details"][0]
    assert set(["field", "message", "type", "input"]).issubset(first.keys())
    assert "count" in first["field"]


# ---------------------------------------------------------------------------
# pydantic_validation_exception_handler
# ---------------------------------------------------------------------------

def test_pydantic_validation_error(client):
    resp = client.get("/pydantic")
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "PYDANTIC_VALIDATION_ERROR"
    assert body["message"] == "Model validation failed"
    assert isinstance(body["details"], list) and body["details"]
    assert "count" in body["details"][0]["field"]


# ---------------------------------------------------------------------------
# general_exception_handler
# ---------------------------------------------------------------------------

def test_general_exception_handler(client):
    resp = client.get("/boom")
    assert resp.status_code == 500
    body = resp.json()["error"]
    assert body["code"] == "INTERNAL_SERVER_ERROR"
    assert body["message"] == "An internal server error occurred"
    # Internal details are not leaked.
    assert body.get("details") is None


# ---------------------------------------------------------------------------
# starlette_http_exception_handler
# ---------------------------------------------------------------------------

def test_starlette_http_exception(client):
    resp = client.get("/starlette")
    assert resp.status_code == 503
    body = resp.json()["error"]
    assert body["code"] == "HTTP_ERROR"
    assert body["message"] == "Down for maintenance"


@pytest.mark.asyncio
async def test_starlette_http_exception_no_detail_direct():
    """Starlette fills a default detail when raised, so exercise the falsy-detail
    fallback ("HTTP Error") by calling the handler directly with detail=''."""
    exc = StarletteHTTPException(status_code=500, detail="")
    resp = await eh.starlette_http_exception_handler(_FakeRequest(), exc)
    assert resp.status_code == 500
    body = _json_body(resp)["error"]
    assert body["message"] == "HTTP Error"
    assert body["code"] == "HTTP_ERROR"


# ---------------------------------------------------------------------------
# ErrorResponse.create_error_response (static builder)
# ---------------------------------------------------------------------------

def test_create_error_response_minimal():
    resp = eh.ErrorResponse.create_error_response(400, "bad")
    err = resp["error"]
    assert err["status_code"] == 400
    assert err["message"] == "bad"
    assert err["path"] is None
    assert "code" not in err
    assert "details" not in err
    assert err["timestamp"].endswith("Z")


def test_create_error_response_full():
    resp = eh.ErrorResponse.create_error_response(
        status_code=422,
        message="nope",
        details=[{"field": "x"}],
        error_code="VALIDATION_ERROR",
        path="/p",
        timestamp="2020-01-01T00:00:00Z",
    )
    err = resp["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"] == [{"field": "x"}]
    assert err["path"] == "/p"
    assert err["timestamp"] == "2020-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# DatabaseErrorHandler
# ---------------------------------------------------------------------------

class _FakeRequest:
    class _URL:
        path = "/db"

    url = _URL()


def _json_body(json_response):
    import json as _json

    return _json.loads(bytes(json_response.body).decode())


def test_database_connection_error_handler():
    resp = eh.DatabaseErrorHandler.handle_connection_error(_FakeRequest(), Exception("gone"))
    assert resp.status_code == 503
    body = _json_body(resp)["error"]
    assert body["code"] == "DATABASE_CONNECTION_ERROR"
    assert body["status_code"] == 503


def test_database_timeout_error_handler():
    resp = eh.DatabaseErrorHandler.handle_timeout_error(_FakeRequest(), Exception("slow"))
    assert resp.status_code == 504
    body = _json_body(resp)["error"]
    assert body["code"] == "DATABASE_TIMEOUT"


# ---------------------------------------------------------------------------
# AuthErrorHandler
# ---------------------------------------------------------------------------

def test_auth_invalid_token_handler():
    resp = eh.AuthErrorHandler.handle_invalid_token(_FakeRequest())
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"
    body = _json_body(resp)["error"]
    assert body["code"] == "INVALID_TOKEN"


def test_auth_insufficient_permissions_without_role():
    resp = eh.AuthErrorHandler.handle_insufficient_permissions(_FakeRequest())
    assert resp.status_code == 403
    body = _json_body(resp)["error"]
    assert body["code"] == "INSUFFICIENT_PERMISSIONS"
    assert "requires" not in body["message"]


def test_auth_insufficient_permissions_with_role():
    resp = eh.AuthErrorHandler.handle_insufficient_permissions(_FakeRequest(), required_role="admin")
    assert resp.status_code == 403
    body = _json_body(resp)["error"]
    assert "requires admin role" in body["message"]


# ---------------------------------------------------------------------------
# raise_* helpers
# ---------------------------------------------------------------------------

def test_raise_not_found_error_with_identifier():
    with pytest.raises(HTTPException) as ei:
        eh.raise_not_found_error("Article", "abc")
    assert ei.value.status_code == 404
    assert "Article not found" in ei.value.detail
    assert "abc" in ei.value.detail


def test_raise_not_found_error_without_identifier():
    with pytest.raises(HTTPException) as ei:
        eh.raise_not_found_error("Article")
    assert ei.value.status_code == 404
    assert ei.value.detail == "Article not found"


def test_raise_validation_error():
    with pytest.raises(HTTPException) as ei:
        eh.raise_validation_error("email", "invalid format")
    assert ei.value.status_code == 422
    assert "email" in ei.value.detail
    assert "invalid format" in ei.value.detail


def test_raise_unauthorized_error_default_and_custom():
    with pytest.raises(HTTPException) as ei:
        eh.raise_unauthorized_error()
    assert ei.value.status_code == 401
    assert ei.value.detail == "Authentication required"

    with pytest.raises(HTTPException) as ei2:
        eh.raise_unauthorized_error("please log in")
    assert ei2.value.detail == "please log in"


def test_raise_forbidden_error():
    with pytest.raises(HTTPException) as ei:
        eh.raise_forbidden_error()
    assert ei.value.status_code == 403
    assert ei.value.detail == "Access forbidden"


def test_raise_server_error():
    with pytest.raises(HTTPException) as ei:
        eh.raise_server_error("kaput")
    assert ei.value.status_code == 500
    assert ei.value.detail == "kaput"


# ---------------------------------------------------------------------------
# Custom exception classes
# ---------------------------------------------------------------------------

def test_neuronews_api_error_defaults():
    err = eh.NeuroNewsAPIError("base failure")
    assert err.message == "base failure"
    assert err.status_code == 500
    assert err.error_code is None
    assert str(err) == "base failure"


def test_neuronews_api_error_custom_fields():
    err = eh.NeuroNewsAPIError("x", status_code=418, error_code="TEAPOT")
    assert err.status_code == 418
    assert err.error_code == "TEAPOT"


def test_database_connection_error_class():
    err = eh.DatabaseConnectionError()
    assert err.status_code == 503
    assert err.error_code == "DATABASE_CONNECTION_ERROR"
    assert isinstance(err, eh.NeuroNewsAPIError)


def test_rate_limit_exceeded_error_class():
    err = eh.RateLimitExceededError("too fast")
    assert err.status_code == 429
    assert err.error_code == "RATE_LIMIT_EXCEEDED"
    assert err.message == "too fast"


def test_graph_service_error_class():
    err = eh.GraphServiceError()
    assert err.status_code == 503
    assert err.error_code == "GRAPH_SERVICE_ERROR"


# ---------------------------------------------------------------------------
# configure_error_handlers registers all five handlers
# ---------------------------------------------------------------------------

def test_configure_error_handlers_registers_all():
    app = FastAPI()
    eh.configure_error_handlers(app)
    registered = app.exception_handlers
    assert HTTPException in registered
    assert Exception in registered
    assert StarletteHTTPException in registered
    assert ValidationError in registered
