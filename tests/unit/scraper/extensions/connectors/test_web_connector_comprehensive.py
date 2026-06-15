"""Comprehensive tests for the web scraping connector and its base."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")
pytest.importorskip("bs4")

from scraper.extensions.connectors.web_connector import WebScrapingConnector  # noqa: E402
from scraper.extensions.connectors.base import ConnectionError  # noqa: E402


SAMPLE_HTML = """
<html><body>
  <div class="article">
    <h2 class="title">First Headline</h2>
    <a class="link" href="/a/1">read</a>
    <span class="author">Alice</span>
  </div>
  <div class="article">
    <h2 class="title">Second Headline</h2>
    <a class="link" href="/a/2">read</a>
    <span class="author">Bob</span>
  </div>
</body></html>
"""


class FakeResponse:
    def __init__(self, html, status=200):
        self._html = html
        self.status = status
        self.reason = "OK"

    async def text(self):
        return self._html

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, html=SAMPLE_HTML, status=200):
        self._html = html
        self._status = status
        self.closed = False

    def get(self, url, headers=None):
        return FakeResponse(self._html, self._status)

    async def close(self):
        self.closed = True


def make(config=None):
    return WebScrapingConnector(config or {"base_url": "https://news.example.com"})


class TestValidateConfig:
    def test_valid(self):
        assert make().validate_config() is True

    def test_missing_base_url(self):
        assert WebScrapingConnector({}).validate_config() is False

    def test_invalid_url(self):
        assert WebScrapingConnector({"base_url": "not-a-url"}).validate_config() is False


class TestValidateDataFormat:
    def test_valid(self):
        assert make().validate_data_format({"source_url": "u", "title": "t"}) is True

    def test_non_dict(self):
        assert make().validate_data_format("nope") is False

    def test_only_source_url(self):
        assert make().validate_data_format({"source_url": "u"}) is False


class TestStatusAndAuth:
    def test_get_status(self):
        status = make().get_status()
        assert status["connector_type"] == "WebScrapingConnector"
        assert status["connected"] is False
        assert status["config_valid"] is True

    @pytest.mark.asyncio
    async def test_authenticate_no_auth(self):
        assert await make().authenticate() is True

    @pytest.mark.asyncio
    async def test_disconnect_closes_session(self):
        c = make()
        c._session = FakeSession()
        await c.disconnect()
        assert c.is_connected is False
        assert c._session.closed is True


class TestScrapePage:
    @pytest.mark.asyncio
    async def test_container_extraction(self):
        c = make()
        c._session = FakeSession()
        selectors = {
            "container": "div.article",
            "title": "h2.title",
            "author": "span.author",
        }
        rows = await c._scrape_page("https://news.example.com", selectors)
        assert len(rows) == 2
        assert rows[0]["title"] == "First Headline"
        assert rows[0]["author"] == "Alice"
        assert rows[0]["source_url"] == "https://news.example.com"

    @pytest.mark.asyncio
    async def test_advanced_selector_attribute(self):
        c = make()
        c._session = FakeSession()
        selectors = {
            "container": "div.article",
            "url": {"selector": "a.link", "attribute": "href"},
        }
        rows = await c._scrape_page("https://news.example.com", selectors)
        assert rows[0]["url"] == "/a/1"

    @pytest.mark.asyncio
    async def test_non_200_returns_empty(self):
        c = make()
        c._session = FakeSession(status=404)
        rows = await c._scrape_page("https://news.example.com", {"container": "div.article"})
        assert rows == []


class TestConnectContextManager:
    @pytest.mark.asyncio
    async def test_test_connection_success(self, monkeypatch):
        c = make()

        async def fake_connect():
            c._connected = True
            return True

        async def fake_disconnect():
            c._connected = False

        monkeypatch.setattr(c, "connect", fake_connect)
        monkeypatch.setattr(c, "disconnect", fake_disconnect)
        assert await c.test_connection() is True

    @pytest.mark.asyncio
    async def test_aenter_failure_raises(self, monkeypatch):
        c = make()

        async def fail_connect():
            return False

        monkeypatch.setattr(c, "connect", fail_connect)
        with pytest.raises(ConnectionError):
            async with c:
                pass
