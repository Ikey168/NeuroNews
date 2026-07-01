"""
Coverage-focused tests for
src/scraper/extensions/connectors/rss_connector.py

The production module hard-imports ``feedparser`` which is not installed.
We install a lightweight ``sys.modules`` stub for ``feedparser`` *before*
importing the module, then mock both the feed parse result and the aiohttp
session so the fetch / validation / feed-info logic is exercised with real
assertions on the produced records.
"""

import asyncio
import sys
import types
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# feedparser stub.  ``feedparser.parse`` returns an object with ``entries``,
# ``feed``, ``bozo``, ``bozo_exception`` and ``version`` attributes.  Real
# feedparser entries behave like dicts (``.get``), so we back them with dicts.
# ---------------------------------------------------------------------------
class _FeedResult:
    def __init__(self, entries=None, feed=None, bozo=False,
                 bozo_exception=None, version="rss20"):
        self.entries = entries or []
        self.feed = feed or {}
        self.bozo = bozo
        self.bozo_exception = bozo_exception
        self.version = version


# Mutable holder the tests set to control what parse() returns.
_PARSE_RESULT = {"value": _FeedResult()}
_PARSE_CALLS = []


def _fake_parse(content):
    _PARSE_CALLS.append(content)
    return _PARSE_RESULT["value"]


if "feedparser" not in sys.modules:
    fp = types.ModuleType("feedparser")
    fp.parse = _fake_parse
    sys.modules["feedparser"] = fp
else:  # pragma: no cover - defensive
    sys.modules["feedparser"].parse = _fake_parse


from src.scraper.extensions.connectors.rss_connector import (  # noqa: E402
    RSSConnector,
)
from src.scraper.extensions.connectors.base import ConnectionError  # noqa: E402


# ---------------------------------------------------------------------------
# aiohttp session mock: session.get(url) is an async context manager whose
# value is a response with .status, .reason and awaitable .text().
# ---------------------------------------------------------------------------
class _Response:
    def __init__(self, status=200, text="", reason="OK"):
        self.status = status
        self.reason = reason
        self._text = text

    async def text(self):
        return self._text


class _GetCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response, closed=False):
        self._response = response
        self.closed = closed
        self.get_urls = []

    def get(self, url):
        self.get_urls.append(url)
        return _GetCtx(self._response)

    async def close(self):
        self.closed = True


def _set_feed(**kwargs):
    _PARSE_RESULT["value"] = _FeedResult(**kwargs)


def _patch_session(session):
    """Patch aiohttp.ClientSession in the connector to return ``session``."""
    return patch(
        "src.scraper.extensions.connectors.rss_connector.aiohttp.ClientSession",
        return_value=session,
    )


# ---------------------------------------------------------------------------
# validate_config().
# ---------------------------------------------------------------------------
def test_validate_config_missing_url():
    assert RSSConnector({}).validate_config() is False


def test_validate_config_valid_url():
    assert RSSConnector({"url": "https://example.com/feed.xml"}).validate_config() is True


def test_validate_config_rejects_non_url_string():
    # No scheme/netloc -> invalid.
    assert RSSConnector({"url": "not-a-url"}).validate_config() is False


# ---------------------------------------------------------------------------
# connect().
# ---------------------------------------------------------------------------
def test_connect_success_sets_connected():
    conn = RSSConnector({"url": "https://example.com/feed"})
    session = _FakeSession(_Response(status=200))
    with _patch_session(session):
        assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True
    # the connect() network test hit the configured url.
    assert session.get_urls == ["https://example.com/feed"]


def test_connect_non_200_records_error():
    conn = RSSConnector({"url": "https://example.com/feed"})
    session = _FakeSession(_Response(status=404, reason="Not Found"))
    with _patch_session(session):
        assert asyncio.run(conn.connect()) is False
    assert conn.is_connected is False
    assert isinstance(conn.last_error, ConnectionError)
    assert "404" in str(conn.last_error)


def test_connect_reuses_open_session():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=500), closed=False)
    # existing open session short-circuits and is treated as connected.
    assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True
    # response should not have been consumed (no get called)
    assert conn._session.get_urls == []


def test_connect_exception_wrapped():
    conn = RSSConnector({"url": "https://example.com/feed"})

    class _BadSession:
        closed = False

        def get(self, url):
            raise RuntimeError("network dead")

        async def close(self):
            self.closed = True

    with _patch_session(_BadSession()):
        assert asyncio.run(conn.connect()) is False
    assert isinstance(conn.last_error, ConnectionError)
    assert "network dead" in str(conn.last_error)


# ---------------------------------------------------------------------------
# disconnect().
# ---------------------------------------------------------------------------
def test_disconnect_closes_session():
    conn = RSSConnector({"url": "https://example.com/feed"})
    session = _FakeSession(_Response(), closed=False)
    conn._session = session
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert session.closed is True
    assert conn.is_connected is False


def test_disconnect_when_already_closed():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(), closed=True)
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert conn.is_connected is False


# ---------------------------------------------------------------------------
# fetch_data() -- the core parsing / record production logic.
# ---------------------------------------------------------------------------
def test_fetch_data_requires_connection():
    conn = RSSConnector({"url": "https://example.com/feed"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


def test_fetch_data_produces_entry_records():
    url = "https://example.com/feed"
    conn = RSSConnector({"url": url})
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    conn._connected = True

    _set_feed(entries=[
        {
            "title": "First",
            "link": "https://example.com/1",
            "description": "desc1",
            "published": "Mon, 01 Jan 2024",
            "published_parsed": (2024, 1, 1, 0, 0, 0, 0, 1, 0),
            "author": "Alice",
            "tags": [{"term": "tech"}, {"term": "ai"}],
            "id": "guid-1",
        },
        {
            "title": "Second",
            "link": "https://example.com/2",
        },
    ])

    entries = asyncio.run(conn.fetch_data())
    assert len(entries) == 2

    first = entries[0]
    assert first["title"] == "First"
    assert first["link"] == "https://example.com/1"
    assert first["description"] == "desc1"
    assert first["author"] == "Alice"
    assert first["tags"] == ["tech", "ai"]
    assert first["source"] == url
    assert first["entry_id"] == "guid-1"
    assert first["published_parsed"] == (2024, 1, 1, 0, 0, 0, 0, 1, 0)

    second = entries[1]
    # missing id falls back to link.
    assert second["entry_id"] == "https://example.com/2"
    assert second["tags"] == []


def test_fetch_data_filters_invalid_entries():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    conn._connected = True

    # Entry with no title should be filtered by validate_data_format.
    _set_feed(entries=[
        {"link": "https://example.com/x"},  # no title -> invalid
        {"title": "Valid", "link": "https://example.com/y"},
    ])

    entries = asyncio.run(conn.fetch_data())
    assert len(entries) == 1
    assert entries[0]["title"] == "Valid"


def test_fetch_data_honours_limit():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    conn._connected = True

    _set_feed(entries=[
        {"title": f"T{i}", "link": f"https://example.com/{i}"} for i in range(5)
    ])

    entries = asyncio.run(conn.fetch_data(limit=2))
    assert len(entries) == 2
    assert entries[0]["title"] == "T0"
    assert entries[1]["title"] == "T1"


def test_fetch_data_non_200_wrapped_error():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=503, reason="Unavailable"))
    conn._connected = True
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "503" in str(ei.value)


def test_fetch_data_logs_bozo_warning_but_returns_entries():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    conn._connected = True

    _set_feed(
        entries=[{"title": "Ok", "link": "https://example.com/ok"}],
        bozo=True,
        bozo_exception=ValueError("mildly malformed"),
    )

    entries = asyncio.run(conn.fetch_data())
    assert len(entries) == 1
    assert entries[0]["title"] == "Ok"


# ---------------------------------------------------------------------------
# validate_data_format().
# ---------------------------------------------------------------------------
def test_validate_data_format_non_dict():
    conn = RSSConnector({"url": "https://example.com/feed"})
    assert conn.validate_data_format("nope") is False


def test_validate_data_format_missing_required():
    conn = RSSConnector({"url": "https://example.com/feed"})
    assert conn.validate_data_format({"title": "t", "link": "l"}) is False  # no source
    assert conn.validate_data_format({"title": "", "link": "l", "source": "s"}) is False


def test_validate_data_format_valid():
    conn = RSSConnector({"url": "https://example.com/feed"})
    assert (
        conn.validate_data_format(
            {"title": "t", "link": "l", "source": "s"}
        )
        is True
    )


# ---------------------------------------------------------------------------
# get_feed_info().
# ---------------------------------------------------------------------------
def test_get_feed_info_requires_connection():
    conn = RSSConnector({"url": "https://example.com/feed"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.get_feed_info())


def test_get_feed_info_returns_metadata():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    conn._connected = True

    _set_feed(
        entries=[{"title": "a"}, {"title": "b"}],
        feed={
            "title": "My Feed",
            "description": "A feed",
            "link": "https://example.com",
            "language": "en",
            "updated": "yesterday",
            "updated_parsed": (2024, 6, 1, 0, 0, 0, 0, 1, 0),
        },
        version="atom10",
    )

    info = asyncio.run(conn.get_feed_info())
    assert info["title"] == "My Feed"
    assert info["description"] == "A feed"
    assert info["link"] == "https://example.com"
    assert info["language"] == "en"
    assert info["entries_count"] == 2
    assert info["version"] == "atom10"
    assert info["updated_parsed"] == (2024, 6, 1, 0, 0, 0, 0, 1, 0)


def test_get_feed_info_wraps_errors():
    conn = RSSConnector({"url": "https://example.com/feed"})

    class _BadSession:
        closed = False

        def get(self, url):
            raise RuntimeError("boom")

    conn._session = _BadSession()
    conn._connected = True
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.get_feed_info())
    assert "boom" in str(ei.value)


# ---------------------------------------------------------------------------
# check_feed_validity().
# ---------------------------------------------------------------------------
def test_check_feed_validity_true_when_not_bozo():
    conn = RSSConnector({"url": "https://example.com/feed"})
    # connect() runs first inside check_feed_validity; provide open session.
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    _set_feed(entries=[{"title": "x"}], bozo=False, bozo_exception=None)
    assert asyncio.run(conn.check_feed_validity()) is True


def test_check_feed_validity_false_on_non_200():
    conn = RSSConnector({"url": "https://example.com/feed"})
    # First connect() reuses open session -> True; then get() returns 500.
    conn._session = _FakeSession(_Response(status=500, reason="err"))
    assert asyncio.run(conn.check_feed_validity()) is False


def test_check_feed_validity_false_when_bozo_with_exception():
    conn = RSSConnector({"url": "https://example.com/feed"})
    conn._session = _FakeSession(_Response(status=200, text="<rss/>"))
    _set_feed(entries=[], bozo=True, bozo_exception=ValueError("broken"))
    assert asyncio.run(conn.check_feed_validity()) is False
