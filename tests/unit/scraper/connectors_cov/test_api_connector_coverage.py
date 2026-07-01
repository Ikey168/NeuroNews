"""
Coverage-focused tests for APIConnector / RESTConnector / GraphQLConnector.

The aiohttp ClientSession is mocked directly (aioresponses is not installed).
The fake session's ``request`` returns an async context manager yielding a
fake response with a ``json()`` coroutine, matching how the connector consumes
responses. Assertions check the parsed record lists and error branches.
"""

import pytest

pytest.importorskip("aiohttp")

from src.scraper.extensions.connectors.api_connector import (
    APIConnector,
    RESTConnector,
    GraphQLConnector,
)
from src.scraper.extensions.connectors.base import (
    ConnectionError as ConnConnectionError,
    AuthenticationError,
)


# ---------------------------------------------------------------------------
# Fake aiohttp session plumbing
# ---------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status=200, json_data=None, reason="OK"):
        self.status = status
        self.reason = reason
        self._json_data = json_data

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    """Records the last request and returns a scripted FakeResponse."""

    def __init__(self, response=None, raise_exc=None):
        self.response = response or FakeResponse()
        self.raise_exc = raise_exc
        self.closed = False
        self.last_request = None

    def request(self, method, url, **kwargs):
        self.last_request = {"method": method, "url": url, "kwargs": kwargs}
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.response

    async def close(self):
        self.closed = True


def _attach(connector, session):
    connector._session = session
    connector._connected = True
    connector._headers = {"Accept": "application/json"}


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def test_validate_config_valid():
    assert APIConnector({"base_url": "https://api.example.com"}).validate_config() is True


def test_validate_config_missing_base_url():
    assert APIConnector({}).validate_config() is False


def test_validate_config_invalid_url():
    assert APIConnector({"base_url": "not-a-url"}).validate_config() is False


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_success_sets_headers(monkeypatch):
    c = APIConnector(
        {"base_url": "https://api.example.com", "headers": {"X-Trace": "1"}}
    )
    session = FakeSession()
    import src.scraper.extensions.connectors.api_connector as mod

    monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda *a, **k: session)
    assert await c.connect() is True
    assert c.is_connected is True
    assert c._headers["Accept"] == "application/json"
    assert c._headers["X-Trace"] == "1"


@pytest.mark.asyncio
async def test_connect_reuses_open_session():
    c = APIConnector({"base_url": "https://api.example.com"})
    session = FakeSession()
    session.closed = False
    c._session = session
    assert await c.connect() is True
    assert c.is_connected is True


@pytest.mark.asyncio
async def test_connect_with_auth_success(monkeypatch):
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "bearer", "token": "tok"},
    )
    session = FakeSession()
    import src.scraper.extensions.connectors.api_connector as mod

    monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda *a, **k: session)
    assert await c.connect() is True
    assert c._headers["Authorization"] == "Bearer tok"


@pytest.mark.asyncio
async def test_connect_with_auth_failure_returns_false(monkeypatch):
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "bearer"},  # missing token -> auth fails
    )
    session = FakeSession()
    import src.scraper.extensions.connectors.api_connector as mod

    monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda *a, **k: session)
    assert await c.connect() is False
    assert c.is_connected is False


@pytest.mark.asyncio
async def test_connect_exception_records_error(monkeypatch):
    c = APIConnector({"base_url": "https://api.example.com"})
    import src.scraper.extensions.connectors.api_connector as mod

    def boom(*a, **k):
        raise RuntimeError("no net")

    monkeypatch.setattr(mod.aiohttp, "ClientSession", boom)
    assert await c.connect() is False
    assert "no net" in str(c.last_error)


@pytest.mark.asyncio
async def test_disconnect_closes_session():
    c = APIConnector({"base_url": "https://api.example.com"})
    session = FakeSession()
    c._session = session
    c._connected = True
    await c.disconnect()
    assert session.closed is True
    assert c.is_connected is False


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_api_key():
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "api_key", "header": "X-Key", "key": "abc"},
    )
    c._headers = {}
    assert await c.authenticate() is True
    assert c._headers["X-Key"] == "abc"


@pytest.mark.asyncio
async def test_authenticate_api_key_missing_key():
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "api_key"},
    )
    c._headers = {}
    assert await c.authenticate() is False
    assert isinstance(c.last_error, AuthenticationError)


@pytest.mark.asyncio
async def test_authenticate_bearer():
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "bearer", "token": "xyz"},
    )
    c._headers = {}
    assert await c.authenticate() is True
    assert c._headers["Authorization"] == "Bearer xyz"


@pytest.mark.asyncio
async def test_authenticate_bearer_missing_token():
    c = APIConnector(
        {"base_url": "https://api.example.com"}, auth_config={"type": "bearer"}
    )
    c._headers = {}
    assert await c.authenticate() is False


@pytest.mark.asyncio
async def test_authenticate_basic():
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "basic", "username": "u", "password": "p"},
    )
    c._headers = {}
    assert await c.authenticate() is True
    assert c._headers["Authorization"].startswith("Basic ")
    import base64

    decoded = base64.b64decode(
        c._headers["Authorization"].split(" ", 1)[1]
    ).decode()
    assert decoded == "u:p"


@pytest.mark.asyncio
async def test_authenticate_basic_missing_credentials():
    c = APIConnector(
        {"base_url": "https://api.example.com"},
        auth_config={"type": "basic", "username": "u"},
    )
    c._headers = {}
    assert await c.authenticate() is False


@pytest.mark.asyncio
async def test_authenticate_oauth_not_implemented():
    c = APIConnector(
        {"base_url": "https://api.example.com"}, auth_config={"type": "oauth"}
    )
    c._headers = {}
    assert await c.authenticate() is False
    assert isinstance(c.last_error, AuthenticationError)


@pytest.mark.asyncio
async def test_authenticate_unknown_type_returns_true():
    c = APIConnector(
        {"base_url": "https://api.example.com"}, auth_config={"type": "none"}
    )
    c._headers = {}
    assert await c.authenticate() is True


# ---------------------------------------------------------------------------
# fetch_data response handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_data_list_response():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data=[{"id": 1}, {"id": 2}])))
    data = await c.fetch_data("items")
    assert data == [{"id": 1}, {"id": 2}]
    assert c._session.last_request["method"] == "GET"
    assert c._session.last_request["url"] == "https://api.example.com/items"


@pytest.mark.asyncio
async def test_fetch_data_dict_with_data_container():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(
        c,
        FakeSession(
            FakeResponse(status=200, json_data={"data": [{"a": 1}], "meta": {}})
        ),
    )
    data = await c.fetch_data("x")
    assert data == [{"a": 1}]


@pytest.mark.asyncio
async def test_fetch_data_dict_with_results_container():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(
        c, FakeSession(FakeResponse(status=200, json_data={"results": [{"r": 1}]}))
    )
    data = await c.fetch_data("x")
    assert data == [{"r": 1}]


@pytest.mark.asyncio
async def test_fetch_data_dict_no_container_wraps_object():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data={"id": 7, "name": "z"})))
    data = await c.fetch_data("x")
    assert data == [{"id": 7, "name": "z"}]


@pytest.mark.asyncio
async def test_fetch_data_scalar_wrapped():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data="hello")))
    data = await c.fetch_data("x")
    assert data == [{"data": "hello"}]


@pytest.mark.asyncio
async def test_fetch_data_post_with_dict_body_uses_json():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=201, json_data=[{"ok": True}])))
    data = await c.fetch_data("create", method="POST", data={"name": "x"})
    assert data == [{"ok": True}]
    assert c._session.last_request["kwargs"]["json"] == {"name": "x"}


@pytest.mark.asyncio
async def test_fetch_data_post_with_string_body_uses_data():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data=[])))
    await c.fetch_data("create", method="POST", data="raw-body")
    assert c._session.last_request["kwargs"]["data"] == "raw-body"


@pytest.mark.asyncio
async def test_fetch_data_401_raises_auth_error_wrapped():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=401)))
    with pytest.raises(ConnConnectionError, match="Failed to fetch API data"):
        await c.fetch_data("x")
    # The original AuthenticationError is stored as last_error.
    assert isinstance(c.last_error, AuthenticationError)


@pytest.mark.asyncio
async def test_fetch_data_403_raises():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=403)))
    with pytest.raises(ConnConnectionError):
        await c.fetch_data("x")
    assert isinstance(c.last_error, AuthenticationError)


@pytest.mark.asyncio
async def test_fetch_data_500_raises():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=500, reason="Server Error")))
    with pytest.raises(ConnConnectionError, match="Failed to fetch API data"):
        await c.fetch_data("x")


@pytest.mark.asyncio
async def test_fetch_data_not_connected_raises():
    c = APIConnector({"base_url": "https://api.example.com"})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.fetch_data("x")


@pytest.mark.asyncio
async def test_fetch_data_session_exception_wrapped():
    c = APIConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(raise_exc=RuntimeError("boom")))
    with pytest.raises(ConnConnectionError, match="Failed to fetch API data"):
        await c.fetch_data("x")
    assert c.last_error is not None


# ---------------------------------------------------------------------------
# validate_data_format
# ---------------------------------------------------------------------------


def test_validate_data_format_json_serializable():
    c = APIConnector({"base_url": "https://api.example.com"})
    assert c.validate_data_format({"a": 1}) is True
    assert c.validate_data_format([1, 2, 3]) is True
    assert c.validate_data_format("string") is True


def test_validate_data_format_non_serializable():
    c = APIConnector({"base_url": "https://api.example.com"})

    class NotSerializable:
        pass

    assert c.validate_data_format({"obj": NotSerializable()}) is False


# ---------------------------------------------------------------------------
# RESTConnector verbs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rest_get():
    c = RESTConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data=[{"g": 1}])))
    data = await c.get("res", params={"q": "1"})
    assert data == [{"g": 1}]
    assert c._session.last_request["method"] == "GET"
    assert c._session.last_request["kwargs"]["params"] == {"q": "1"}


@pytest.mark.asyncio
async def test_rest_post():
    c = RESTConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=201, json_data=[{"p": 1}])))
    data = await c.post("res", data={"body": True})
    assert data == [{"p": 1}]
    assert c._session.last_request["method"] == "POST"
    assert c._session.last_request["kwargs"]["json"] == {"body": True}


@pytest.mark.asyncio
async def test_rest_put():
    c = RESTConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data=[{"u": 1}])))
    data = await c.put("res", data={"body": 1})
    assert data == [{"u": 1}]
    assert c._session.last_request["method"] == "PUT"


@pytest.mark.asyncio
async def test_rest_delete():
    c = RESTConnector({"base_url": "https://api.example.com"})
    _attach(c, FakeSession(FakeResponse(status=200, json_data=[{"d": 1}])))
    data = await c.delete("res")
    assert data == [{"d": 1}]
    assert c._session.last_request["method"] == "DELETE"


# ---------------------------------------------------------------------------
# GraphQLConnector
# ---------------------------------------------------------------------------


def test_graphql_init_default_endpoint():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    assert c.endpoint == "/graphql"


def test_graphql_init_custom_endpoint():
    c = GraphQLConnector(
        {"base_url": "https://api.example.com", "endpoint": "/gql"}
    )
    assert c.endpoint == "/gql"


@pytest.mark.asyncio
async def test_graphql_query_extracts_list_from_data():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    _attach(
        c,
        FakeSession(
            FakeResponse(
                status=200,
                json_data={"data": {"users": [{"id": 1}, {"id": 2}]}},
            )
        ),
    )
    data = await c.query("query { users { id } }")
    assert data == [{"id": 1}, {"id": 2}]
    # Verify it posted to the GraphQL endpoint with the query payload.
    kwargs = c._session.last_request["kwargs"]
    assert kwargs["json"]["query"].startswith("query")
    assert kwargs["json"]["variables"] == {}


@pytest.mark.asyncio
async def test_graphql_query_no_list_wraps_data_dict():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    _attach(
        c,
        FakeSession(
            FakeResponse(status=200, json_data={"data": {"me": {"name": "x"}}})
        ),
    )
    data = await c.query("query { me { name } }", variables={"v": 1})
    assert data == [{"me": {"name": "x"}}]
    assert c._session.last_request["kwargs"]["json"]["variables"] == {"v": 1}


@pytest.mark.asyncio
async def test_graphql_query_data_is_list():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    # fetch_data returns the wrapped object [{"data": [...]}], then query pulls .data
    _attach(
        c,
        FakeSession(FakeResponse(status=200, json_data={"data": [{"n": 1}]})),
    )
    data = await c.query("{ things }")
    assert data == [{"n": 1}]


@pytest.mark.asyncio
async def test_graphql_query_data_scalar_wrapped():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    _attach(
        c, FakeSession(FakeResponse(status=200, json_data={"data": "scalar"}))
    )
    data = await c.query("{ ping }")
    assert data == [{"data": "scalar"}]


@pytest.mark.asyncio
async def test_graphql_query_errors_raise():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    _attach(
        c,
        FakeSession(
            FakeResponse(
                status=200,
                json_data={"errors": [{"message": "bad field"}, {"message": "oops"}]},
            )
        ),
    )
    with pytest.raises(ConnConnectionError, match="Failed to execute GraphQL query"):
        await c.query("{ bad }")
    assert "bad field" in str(c.last_error)


@pytest.mark.asyncio
async def test_graphql_mutation_delegates_to_query():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    _attach(
        c,
        FakeSession(
            FakeResponse(status=200, json_data={"data": {"create": [{"id": 9}]}})
        ),
    )
    data = await c.mutation("mutation { create { id } }", variables={"x": 1})
    assert data == [{"id": 9}]


def test_graphql_validate_query():
    c = GraphQLConnector({"base_url": "https://api.example.com"})
    assert c.validate_query("query { a }") is True
    assert c.validate_query("mutation { a }") is True
    assert c.validate_query("subscription { a }") is True
    assert c.validate_query("{ shorthand }") is True
    assert c.validate_query("no keywords here") is False
    assert c.validate_query("") is False
    assert c.validate_query("   ") is False
    assert c.validate_query(None) is False
    assert c.validate_query(123) is False
