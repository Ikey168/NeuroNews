"""
Coverage-focused tests for WebScrapingConnector.

These tests mock the aiohttp ClientSession directly (aioresponses is not
installed in this environment) and exercise connect/fetch/parse/error paths
with real assertions on the returned records.
"""

import asyncio

import pytest

# bs4 and aiohttp are hard imports of the module under test; both are present
# in this environment, but guard bs4 defensively per convention.
pytest.importorskip("bs4")
pytest.importorskip("aiohttp")

from src.scraper.extensions.connectors.web_connector import WebScrapingConnector
from src.scraper.extensions.connectors.base import ConnectionError as ConnConnectionError


# ---------------------------------------------------------------------------
# Fake aiohttp session plumbing
# ---------------------------------------------------------------------------


class FakeResponse:
    """Mimics an aiohttp response usable as an async context manager."""

    def __init__(self, status=200, body="", reason="OK"):
        self.status = status
        self.reason = reason
        self._body = body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    """Mimics aiohttp.ClientSession.

    ``routes`` maps an exact URL to a FakeResponse (or a list of responses that
    are returned in sequence on repeated calls). ``default`` is returned for
    URLs not present in ``routes``.
    """

    def __init__(self, routes=None, default=None, raise_on=None):
        self.routes = routes or {}
        self.default = default
        self.raise_on = raise_on or {}
        self.closed = False
        self.get_calls = []

    def _resolve(self, url):
        if url in self.raise_on:
            raise self.raise_on[url]
        resp = self.routes.get(url, self.default)
        if isinstance(resp, list):
            # Pop the next scripted response, keep the last one sticky.
            if len(resp) > 1:
                return resp.pop(0)
            return resp[0]
        if resp is None:
            return FakeResponse(status=404, reason="Not Found", body="")
        return resp

    def get(self, url, headers=None, **kwargs):
        self.get_calls.append(url)
        return self._resolve(url)

    async def close(self):
        self.closed = True


def _attach_session(connector, session):
    """Attach a fake session and mark the connector connected."""
    connector._session = session
    connector._connected = True
    connector._headers = {"User-Agent": "test-agent"}


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def test_validate_config_valid():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    assert c.validate_config() is True


def test_validate_config_missing_base_url():
    c = WebScrapingConnector({})
    assert c.validate_config() is False


def test_validate_config_invalid_url_no_scheme():
    c = WebScrapingConnector({"base_url": "example.com/path"})
    assert c.validate_config() is False


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_success_sets_headers(monkeypatch):
    c = WebScrapingConnector(
        {"base_url": "https://example.com", "headers": {"X-Custom": "yes"}}
    )
    session = FakeSession(
        routes={"https://example.com": FakeResponse(status=200, body="OK")}
    )

    def fake_ctor(*args, **kwargs):
        return session

    import src.scraper.extensions.connectors.web_connector as mod

    monkeypatch.setattr(mod.aiohttp, "ClientSession", fake_ctor)

    result = await c.connect()
    assert result is True
    assert c.is_connected is True
    assert c._session is session
    assert c._headers["User-Agent"].startswith("Mozilla")
    assert c._headers["X-Custom"] == "yes"


@pytest.mark.asyncio
async def test_connect_403_still_succeeds(monkeypatch):
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(routes={"https://example.com": FakeResponse(status=403)})
    import src.scraper.extensions.connectors.web_connector as mod

    monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda *a, **k: session)

    assert await c.connect() is True
    assert c.is_connected is True


@pytest.mark.asyncio
async def test_connect_500_fails_and_records_error(monkeypatch):
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(
        routes={"https://example.com": FakeResponse(status=500, reason="Server Error")}
    )
    import src.scraper.extensions.connectors.web_connector as mod

    monkeypatch.setattr(mod.aiohttp, "ClientSession", lambda *a, **k: session)

    assert await c.connect() is False
    assert c.is_connected is False
    assert c.last_error is not None
    assert "500" in str(c.last_error)


@pytest.mark.asyncio
async def test_connect_exception_records_error(monkeypatch):
    c = WebScrapingConnector({"base_url": "https://example.com"})
    import src.scraper.extensions.connectors.web_connector as mod

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(mod.aiohttp, "ClientSession", boom)
    assert await c.connect() is False
    assert "network down" in str(c.last_error)


@pytest.mark.asyncio
async def test_connect_reuses_open_session():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession()
    session.closed = False
    c._session = session
    # Should short-circuit without creating a new session.
    assert await c.connect() is True
    assert c.is_connected is True
    assert session.get_calls == []


@pytest.mark.asyncio
async def test_disconnect_closes_session():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession()
    c._session = session
    c._connected = True
    await c.disconnect()
    assert session.closed is True
    assert c.is_connected is False


# ---------------------------------------------------------------------------
# fetch_data (parsing)
# ---------------------------------------------------------------------------

CONTAINER_HTML = """
<html><body>
  <div class="article">
     <h2>First Title</h2>
     <p>First body</p>
     <a class="lnk" href="/a1">read</a>
  </div>
  <div class="article">
     <h2>Second Title</h2>
     <p>Second body</p>
     <a class="lnk" href="/a2">read</a>
  </div>
</body></html>
"""


@pytest.mark.asyncio
async def test_fetch_data_container_selector_extracts_records():
    c = WebScrapingConnector(
        {
            "base_url": "https://example.com",
            "delay": 0,
            "selectors": {
                "container": ".article",
                "title": "h2",
                "body": "p",
                "link": {"selector": "a.lnk", "attribute": "href"},
                "raw": {"selector": "h2", "attribute": "html"},
            },
        }
    )
    session = FakeSession(
        routes={"https://example.com": FakeResponse(status=200, body=CONTAINER_HTML)}
    )
    _attach_session(c, session)

    data = await c.fetch_data()
    assert len(data) == 2
    assert data[0]["title"] == "First Title"
    assert data[0]["body"] == "First body"
    assert data[0]["link"] == "/a1"
    assert "<h2>" in data[0]["raw"]
    assert data[0]["source_url"] == "https://example.com"
    assert data[1]["title"] == "Second Title"


SINGLE_HTML = """
<html><body>
  <h1>Main</h1>
  <p>one</p>
  <p>two</p>
  <a id="mylink" href="https://target/x">go</a>
</body></html>
"""


@pytest.mark.asyncio
async def test_fetch_data_single_item_string_and_dict_selectors():
    c = WebScrapingConnector({"base_url": "https://example.com", "delay": 0})
    session = FakeSession(
        default=FakeResponse(status=200, body=SINGLE_HTML)
    )
    _attach_session(c, session)

    selectors = {
        "title": "h1",  # single element -> string
        "paras": "p",  # multiple -> list
        "missing": ".nope",  # none -> ""
        "href": {"selector": "#mylink", "attribute": "href"},
        "text_attr": {"selector": "h1", "attribute": "text"},
        "html_attr": {"selector": "h1", "attribute": "html"},
        "empty_dict": {"selector": ".nope", "attribute": "href"},
    }
    data = await c.fetch_data("page", selectors=selectors)
    assert len(data) == 1
    rec = data[0]
    assert rec["title"] == "Main"
    assert rec["paras"] == ["one", "two"]
    assert rec["missing"] == ""
    assert rec["href"] == "https://target/x"
    assert rec["text_attr"] == "Main"
    assert rec["html_attr"].startswith("<h1>")
    assert rec["empty_dict"] == ""


@pytest.mark.asyncio
async def test_fetch_data_multiple_elements_with_attribute_returns_list():
    html = (
        "<html><body>"
        '<a href="/one">1</a><a href="/two">2</a>'
        "</body></html>"
    )
    c = WebScrapingConnector({"base_url": "https://example.com", "delay": 0})
    session = FakeSession(default=FakeResponse(status=200, body=html))
    _attach_session(c, session)

    selectors = {"hrefs": {"selector": "a", "attribute": "href"}}
    data = await c.fetch_data("page", selectors=selectors)
    assert data[0]["hrefs"] == ["/one", "/two"]


@pytest.mark.asyncio
async def test_fetch_data_not_connected_raises():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.fetch_data()


@pytest.mark.asyncio
async def test_fetch_data_http_error_returns_empty():
    c = WebScrapingConnector({"base_url": "https://example.com", "delay": 0})
    session = FakeSession(default=FakeResponse(status=404, reason="Not Found"))
    _attach_session(c, session)
    data = await c.fetch_data("missing")
    assert data == []


@pytest.mark.asyncio
async def test_fetch_data_session_exception_wrapped():
    c = WebScrapingConnector({"base_url": "https://example.com", "delay": 0})
    # urljoin will fail because base_url is not a string -> triggers except branch
    c._connected = True
    c.config["base_url"] = 12345  # non-string breaks urljoin inside fetch_data
    with pytest.raises(ConnConnectionError, match="Failed to fetch web data"):
        await c.fetch_data("page")
    assert c.last_error is not None


@pytest.mark.asyncio
async def test_fetch_data_scrape_page_exception_returns_empty(monkeypatch):
    c = WebScrapingConnector({"base_url": "https://example.com", "delay": 0})
    session = FakeSession(default=FakeResponse(status=200, body="<html></html>"))
    _attach_session(c, session)

    # Force BeautifulSoup to raise inside _scrape_page's try block.
    import src.scraper.extensions.connectors.web_connector as mod

    def boom(*a, **k):
        raise ValueError("parse boom")

    monkeypatch.setattr(mod, "BeautifulSoup", boom)
    data = await c.fetch_data("page", selectors={"title": "h1"})
    assert data == []


@pytest.mark.asyncio
async def test_fetch_data_with_pagination_follows_links():
    page1 = (
        "<html><body>"
        '<div class="article"><h2>P1</h2></div>'
        '<a class="next" href="/page2">next</a>'
        "</body></html>"
    )
    page2 = (
        "<html><body>"
        '<div class="article"><h2>P2</h2></div>'
        "</body></html>"
    )
    selectors = {"container": ".article", "title": "h2", "next_page": ".next"}
    c = WebScrapingConnector({"base_url": "https://example.com", "delay": 0})
    session = FakeSession(
        routes={
            "https://example.com/page": FakeResponse(status=200, body=page1),
            "https://example.com/page2": FakeResponse(status=200, body=page2),
        }
    )
    _attach_session(c, session)

    data = await c.fetch_data(
        "page", selectors=selectors, follow_links=True, max_pages=2
    )
    titles = {rec["title"] for rec in data}
    assert titles == {"P1", "P2"}


# ---------------------------------------------------------------------------
# validate_data_format
# ---------------------------------------------------------------------------


def test_validate_data_format_variants():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    assert c.validate_data_format({"source_url": "u", "title": "t"}) is True
    assert c.validate_data_format({"source_url": "u"}) is False  # only 1 field
    assert c.validate_data_format({"title": "t", "x": "y"}) is False  # no source_url
    assert c.validate_data_format("nope") is False
    assert c.validate_data_format(None) is False


# ---------------------------------------------------------------------------
# extract_links
# ---------------------------------------------------------------------------

LINKS_HTML = """
<html><body>
  <a href="/rel">rel</a>
  <a href="https://example.com/abs">abs</a>
  <a href="/rel">dup</a>
  <a>no-href</a>
</body></html>
"""


@pytest.mark.asyncio
async def test_extract_links_dedupes_and_absolutizes():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(default=FakeResponse(status=200, body=LINKS_HTML))
    _attach_session(c, session)
    links = await c.extract_links("page")
    assert sorted(links) == [
        "https://example.com/abs",
        "https://example.com/rel",
    ]


@pytest.mark.asyncio
async def test_extract_links_http_error_returns_empty():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(default=FakeResponse(status=500))
    _attach_session(c, session)
    assert await c.extract_links("page") == []


@pytest.mark.asyncio
async def test_extract_links_not_connected_raises():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    with pytest.raises(ConnConnectionError, match="Not connected"):
        await c.extract_links()


@pytest.mark.asyncio
async def test_extract_links_exception_wrapped():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    c._connected = True
    c.config["base_url"] = 999  # break urljoin
    with pytest.raises(ConnConnectionError, match="Failed to extract links"):
        await c.extract_links("page")


# ---------------------------------------------------------------------------
# check_robots_txt
# ---------------------------------------------------------------------------

ROBOTS = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Allow: /public/
Crawl-delay: 2.5
Crawl-delay: notanumber
"""


@pytest.mark.asyncio
async def test_check_robots_txt_parses_content():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(
        routes={
            "https://example.com/robots.txt": FakeResponse(status=200, body=ROBOTS)
        }
    )
    _attach_session(c, session)
    info = await c.check_robots_txt()
    assert info["exists"] is True
    assert "/admin/" in info["disallowed_paths"]
    assert "/private/" in info["disallowed_paths"]
    assert "/public/" in info["allowed_paths"]
    # First valid crawl-delay is parsed; the invalid one is ignored.
    assert info["crawl_delay"] == 2.5


@pytest.mark.asyncio
async def test_check_robots_txt_missing_returns_false():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(
        routes={"https://example.com/robots.txt": FakeResponse(status=404)}
    )
    _attach_session(c, session)
    info = await c.check_robots_txt()
    assert info == {"exists": False}


@pytest.mark.asyncio
async def test_check_robots_txt_exception_returns_error():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(
        raise_on={"https://example.com/robots.txt": RuntimeError("boom")}
    )
    _attach_session(c, session)
    info = await c.check_robots_txt()
    assert info["exists"] is False
    assert "boom" in info["error"]


# ---------------------------------------------------------------------------
# _find_pagination_links directly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_pagination_links_no_selector_returns_empty():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession()
    _attach_session(c, session)
    assert await c._find_pagination_links("https://example.com", None) == []
    # No request should have been issued.
    assert session.get_calls == []


@pytest.mark.asyncio
async def test_find_pagination_links_http_error_returns_empty():
    c = WebScrapingConnector({"base_url": "https://example.com"})
    session = FakeSession(default=FakeResponse(status=500))
    _attach_session(c, session)
    assert await c._find_pagination_links("https://example.com", ".next") == []
