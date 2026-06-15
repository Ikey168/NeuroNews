"""Extra focused tests for WebScrapingConnector to cover gaps.

Targets paths not exercised by test_web_connector.py and
test_web_connector_comprehensive.py: the already-connected/exception branches of
connect, no-session disconnect, html attribute extraction, single-item attribute
and next_page handling, pagination link discovery, extract_links non-200/error,
robots.txt error handling, and fetch_data exception wrapping.
"""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")
pytest.importorskip("bs4")

from unittest.mock import AsyncMock  # noqa: E402

from scraper.extensions.connectors.web_connector import WebScrapingConnector  # noqa: E402
from scraper.extensions.connectors.base import ConnectionError  # noqa: E402


# ---------------------------------------------------------------------------
# Test doubles for aiohttp session / response (async context managers).
# ---------------------------------------------------------------------------
class FakeResponse:
    def __init__(self, html="", status=200, reason="OK"):
        self._html = html
        self.status = status
        self.reason = reason

    async def text(self):
        return self._html

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    """Returns a fixed response, or per-URL responses when ``mapping`` given."""

    def __init__(self, html="", status=200, reason="OK", mapping=None):
        self._html = html
        self._status = status
        self._reason = reason
        self._mapping = mapping or {}
        self.closed = False
        self.requested = []

    def get(self, url, headers=None):
        self.requested.append(url)
        if url in self._mapping:
            html, status = self._mapping[url]
            return FakeResponse(html, status)
        return FakeResponse(self._html, self._status, self._reason)

    async def close(self):
        self.closed = True


class ExplodingSession:
    """A session whose .get raises to exercise error handling paths."""

    def __init__(self):
        self.closed = False

    def get(self, url, headers=None):
        raise RuntimeError("boom")

    async def close(self):
        self.closed = True


def make(config=None):
    return WebScrapingConnector(config or {"base_url": "https://news.example.com"})


def connected(config=None, session=None):
    c = make(config)
    c._session = session or FakeSession()
    c._connected = True
    return c


# ---------------------------------------------------------------------------
# validate_config edge
# ---------------------------------------------------------------------------
def test_validate_config_url_missing_netloc():
    # scheme present but no netloc -> all([...]) is False
    assert WebScrapingConnector({"base_url": "http:///nopath"}).validate_config() is False


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_returns_early_when_session_open():
    c = make()
    sess = FakeSession()
    c._session = sess
    result = await c.connect()
    assert result is True
    assert c.is_connected is True
    # Early return: no HTTP request should have been issued.
    assert sess.requested == []


@pytest.mark.asyncio
async def test_connect_handles_exception_and_records_error(monkeypatch):
    c = make()

    def boom(*a, **k):
        raise RuntimeError("network down")

    # ClientSession construction itself raising is the simplest exception path.
    monkeypatch.setattr(
        "scraper.extensions.connectors.web_connector.aiohttp.ClientSession", boom
    )
    result = await c.connect()
    assert result is False
    assert c.is_connected is False
    assert isinstance(c.last_error, ConnectionError)
    assert "Failed to connect" in str(c.last_error)


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disconnect_with_no_session():
    c = make()
    c._connected = True
    # Should not raise even though there is no session.
    await c.disconnect()
    assert c.is_connected is False


@pytest.mark.asyncio
async def test_disconnect_with_already_closed_session():
    c = make()
    sess = FakeSession()
    sess.closed = True
    c._session = sess
    c._connected = True
    await c.disconnect()
    # close() must NOT be called on an already-closed session.
    assert sess.closed is True
    assert c.is_connected is False


# ---------------------------------------------------------------------------
# _scrape_page advanced extraction branches
# ---------------------------------------------------------------------------
CONTAINER_HTML = """
<html><body>
  <div class="card">
    <h2 class="t">Title A</h2>
    <a class="l" href="/a/1">go</a>
  </div>
</body></html>
"""


@pytest.mark.asyncio
async def test_scrape_page_container_html_attribute():
    c = connected(session=FakeSession(html=CONTAINER_HTML))
    selectors = {
        "container": "div.card",
        "raw": {"selector": "h2.t", "attribute": "html"},
    }
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert len(rows) == 1
    assert rows[0]["raw"] == '<h2 class="t">Title A</h2>'


@pytest.mark.asyncio
async def test_scrape_page_container_missing_element_yields_empty_string():
    c = connected(session=FakeSession(html=CONTAINER_HTML))
    selectors = {
        "container": "div.card",
        "title": "h2.t",
        "missing": ".does-not-exist",
        "missing_attr": {"selector": ".nope", "attribute": "href"},
    }
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert rows[0]["title"] == "Title A"
    assert rows[0]["missing"] == ""
    assert rows[0]["missing_attr"] == ""


@pytest.mark.asyncio
async def test_scrape_page_container_advanced_selector_without_selector_key():
    c = connected(session=FakeSession(html=CONTAINER_HTML))
    selectors = {
        "container": "div.card",
        "bad": {"attribute": "href"},  # no "selector" -> element is None
    }
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert rows[0]["bad"] == ""


@pytest.mark.asyncio
async def test_scrape_page_invalid_items_filtered_out():
    # A container whose only field is source_url fails validate_data_format,
    # so the row is dropped.
    c = connected(session=FakeSession(html=CONTAINER_HTML))
    selectors = {"container": "div.card"}  # no real fields
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert rows == []


SINGLE_HTML = """
<html><body>
  <h1>Solo Title</h1>
  <a href="/x" class="lnk">L1</a>
  <a href="/y" class="lnk">L2</a>
  <article>raw body</article>
</body></html>
"""


@pytest.mark.asyncio
async def test_scrape_page_single_item_html_attribute():
    c = connected(session=FakeSession(html=SINGLE_HTML))
    selectors = {"body": {"selector": "article", "attribute": "html"}}
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert rows[0]["body"] == "<article>raw body</article>"


@pytest.mark.asyncio
async def test_scrape_page_single_item_multiple_elements_with_attribute():
    c = connected(session=FakeSession(html=SINGLE_HTML))
    selectors = {"hrefs": {"selector": "a.lnk", "attribute": "href"}}
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert rows[0]["hrefs"] == ["/x", "/y"]


@pytest.mark.asyncio
async def test_scrape_page_single_item_no_match_attribute_dict():
    c = connected(session=FakeSession(html=SINGLE_HTML))
    selectors = {
        "title": "h1",
        "nomatch": {"selector": ".absent", "attribute": "href"},
    }
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert rows[0]["title"] == "Solo Title"
    assert rows[0]["nomatch"] == ""


@pytest.mark.asyncio
async def test_scrape_page_single_item_skips_next_page_key():
    c = connected(session=FakeSession(html=SINGLE_HTML))
    selectors = {"title": "h1", "next_page": ".pager"}
    rows = await c._scrape_page("https://news.example.com", selectors)
    assert "next_page" not in rows[0]
    assert rows[0]["title"] == "Solo Title"


@pytest.mark.asyncio
async def test_scrape_page_exception_returns_empty():
    c = connected(session=ExplodingSession())
    rows = await c._scrape_page("https://news.example.com", {"container": "div"})
    assert rows == []


# ---------------------------------------------------------------------------
# _find_pagination_links
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_find_pagination_links_no_selector_returns_empty():
    c = connected()
    assert await c._find_pagination_links("https://news.example.com", None) == []


@pytest.mark.asyncio
async def test_find_pagination_links_resolves_relative_urls():
    html = '<html><body><a class="next" href="/page2">Next</a></body></html>'
    c = connected(session=FakeSession(html=html))
    urls = await c._find_pagination_links("https://news.example.com/list", "a.next")
    assert urls == ["https://news.example.com/page2"]


@pytest.mark.asyncio
async def test_find_pagination_links_non_200_returns_empty():
    c = connected(session=FakeSession(html="x", status=500))
    assert await c._find_pagination_links("https://news.example.com", "a.next") == []


@pytest.mark.asyncio
async def test_find_pagination_links_skips_links_without_href():
    html = '<html><body><a class="next">No href</a></body></html>'
    c = connected(session=FakeSession(html=html))
    assert await c._find_pagination_links("https://news.example.com", "a.next") == []


@pytest.mark.asyncio
async def test_find_pagination_links_exception_returns_empty():
    c = connected(session=ExplodingSession())
    assert await c._find_pagination_links("https://news.example.com", "a.next") == []


# ---------------------------------------------------------------------------
# extract_links
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_extract_links_non_200_returns_empty():
    c = connected(session=FakeSession(html="x", status=404))
    assert await c.extract_links("page") == []


@pytest.mark.asyncio
async def test_extract_links_dedupes_and_resolves():
    html = """
    <html><body>
      <a href="/dup">d1</a>
      <a href="/dup">d2</a>
      <a href="https://other.com/ext">ext</a>
      <a>no href</a>
    </body></html>
    """
    c = connected(session=FakeSession(html=html))
    links = await c.extract_links("page")
    assert set(links) == {
        "https://news.example.com/dup",
        "https://other.com/ext",
    }


@pytest.mark.asyncio
async def test_extract_links_exception_wrapped():
    c = connected(session=ExplodingSession())
    with pytest.raises(ConnectionError, match="Failed to extract links"):
        await c.extract_links("page")
    assert c.last_error is not None


# ---------------------------------------------------------------------------
# fetch_data error wrapping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_data_wraps_internal_exception(monkeypatch):
    c = connected(config={"base_url": "https://news.example.com", "delay": 0})

    async def boom(*a, **k):
        raise RuntimeError("scrape failed")

    monkeypatch.setattr(c, "_scrape_page", boom)
    with pytest.raises(ConnectionError, match="Failed to fetch web data"):
        await c.fetch_data()
    assert isinstance(c.last_error, RuntimeError)


@pytest.mark.asyncio
async def test_fetch_data_no_delay_branch():
    # delay=0 skips the asyncio.sleep branch; verify data still returns.
    html = '<html><body><div class="a"><h2>Hi</h2></div></body></html>'
    c = connected(config={"base_url": "https://news.example.com", "delay": 0},
                  session=FakeSession(html=html))
    data = await c.fetch_data(selectors={"container": "div.a", "title": "h2"})
    assert data[0]["title"] == "Hi"


# ---------------------------------------------------------------------------
# check_robots_txt
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_check_robots_txt_parses_fields_and_bad_crawl_delay():
    robots = "\n".join([
        "User-agent: *",
        "Disallow: /admin/",
        "Allow: /public/",
        "Disallow:",          # empty path -> ignored
        "Crawl-delay: notanumber",  # ValueError -> crawl_delay stays None
    ])
    c = connected(session=FakeSession(html=robots, status=200))
    info = await c.check_robots_txt()
    assert info["exists"] is True
    assert "/admin/" in info["disallowed_paths"]
    assert "/public/" in info["allowed_paths"]
    assert info["crawl_delay"] is None


@pytest.mark.asyncio
async def test_check_robots_txt_not_found():
    c = connected(session=FakeSession(html="", status=404))
    info = await c.check_robots_txt()
    assert info == {"exists": False}


@pytest.mark.asyncio
async def test_check_robots_txt_exception_returns_error():
    c = connected(session=ExplodingSession())
    info = await c.check_robots_txt()
    assert info["exists"] is False
    assert "error" in info


# ---------------------------------------------------------------------------
# Sanity: AsyncMock session disconnect path matches existing style.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_disconnect_calls_close_on_open_async_mock():
    c = make()
    sess = AsyncMock()
    sess.closed = False
    c._session = sess
    c._connected = True
    await c.disconnect()
    sess.close.assert_awaited_once()
    assert c.is_connected is False
