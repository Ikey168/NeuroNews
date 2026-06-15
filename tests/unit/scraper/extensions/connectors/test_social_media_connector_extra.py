"""Tests for src/scraper/extensions/connectors/social_media_connector.py."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("aiohttp")

from scraper.extensions.connectors.social_media_connector import (  # noqa: E402
    SocialMediaConnector,
)


class FakeResponse:
    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json = json_data or {}

    async def json(self):
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class FakeSession:
    def __init__(self, response):
        self._response = response
        self.closed = False

    def get(self, *a, **k):
        return self._response

    def post(self, *a, **k):
        return self._response

    async def close(self):
        self.closed = True


def conn(platform, auth=None, **cfg):
    config = {"platform": platform, **cfg}
    return SocialMediaConnector(config, auth or {})


class TestValidateConfig:
    def test_missing_platform(self):
        c = SocialMediaConnector({}, {})
        assert c.validate_config() is False

    def test_twitter_requires_token(self):
        assert conn("twitter", {"bearer_token": "t"}).validate_config() is True
        assert conn("twitter", {}).validate_config() is False

    def test_reddit_requires_creds(self):
        assert conn("reddit", {"client_id": "i", "client_secret": "s"}).validate_config() is True
        assert conn("reddit", {"client_id": "i"}).validate_config() is False

    def test_facebook_requires_access_token(self):
        assert conn("facebook", {"access_token": "a"}).validate_config() is True
        assert conn("facebook", {}).validate_config() is False

    def test_unknown_platform_ok(self):
        assert conn("mastodon").validate_config() is True


class TestSetup:
    @pytest.mark.asyncio
    async def test_setup_twitter_bearer(self):
        c = conn("twitter", {"bearer_token": "tok"})
        assert await c._setup_twitter() is True
        assert c._headers["Authorization"] == "Bearer tok"

    @pytest.mark.asyncio
    async def test_setup_twitter_api_key(self):
        c = conn("twitter", {"api_key": "k"})
        assert await c._setup_twitter() is True

    @pytest.mark.asyncio
    async def test_setup_twitter_no_creds_raises(self):
        from scraper.extensions.connectors.base import AuthenticationError
        c = conn("twitter", {})
        with pytest.raises(AuthenticationError):
            await c._setup_twitter()

    @pytest.mark.asyncio
    async def test_setup_facebook(self):
        c = conn("facebook", {"access_token": "a"})
        assert await c._setup_facebook() is True
        assert "Bearer a" in c._headers["Authorization"]


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_twitter(self):
        c = conn("twitter", {"bearer_token": "tok"})
        with patch("scraper.extensions.connectors.social_media_connector.aiohttp."
                   "ClientSession", return_value=FakeSession(FakeResponse())):
            assert await c.connect() is True
            assert c.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_unsupported_platform_fails(self):
        c = conn("myspace")
        with patch("scraper.extensions.connectors.social_media_connector.aiohttp."
                   "ClientSession", return_value=FakeSession(FakeResponse())):
            assert await c.connect() is False

    @pytest.mark.asyncio
    async def test_disconnect(self):
        c = conn("twitter", {"bearer_token": "t"})
        sess = FakeSession(FakeResponse())
        c._session = sess
        await c.disconnect()
        assert sess.closed is True
        assert c.is_connected is False


class TestFetch:
    @pytest.mark.asyncio
    async def test_fetch_not_connected_raises(self):
        from scraper.extensions.connectors.base import ConnectionError
        c = conn("twitter", {"bearer_token": "t"})
        with pytest.raises(ConnectionError):
            await c.fetch_data("query")

    @pytest.mark.asyncio
    async def test_fetch_twitter_data(self):
        c = conn("twitter", {"bearer_token": "t"})
        payload = {
            "data": [{"id": "1", "text": "hello", "author_id": "u1",
                      "public_metrics": {}, "lang": "en"}],
            "includes": {"users": [{"id": "u1", "username": "bob", "name": "Bob",
                                    "verified": True}]},
        }
        c._session = FakeSession(FakeResponse(200, payload))
        posts = await c._fetch_twitter_data("ai", 10)
        assert len(posts) == 1
        assert posts[0]["text"] == "hello"
        assert posts[0]["author_username"] == "bob"
        assert posts[0]["platform"] == "twitter"

    @pytest.mark.asyncio
    async def test_fetch_twitter_auth_error(self):
        from scraper.extensions.connectors.base import AuthenticationError
        c = conn("twitter", {"bearer_token": "t"})
        c._session = FakeSession(FakeResponse(401))
        with pytest.raises(AuthenticationError):
            await c._fetch_twitter_data("ai", 10)


class TestValidateDataFormat:
    def test_valid(self):
        c = conn("twitter")
        assert c.validate_data_format({"id": "1", "platform": "twitter", "text": "x"}) is True

    def test_not_dict(self):
        assert conn("twitter").validate_data_format("nope") is False

    def test_missing_required(self):
        assert conn("twitter").validate_data_format({"id": "1"}) is False

    def test_no_content(self):
        assert conn("twitter").validate_data_format({"id": "1", "platform": "twitter"}) is False

    @pytest.mark.asyncio
    async def test_get_platform_info(self):
        info = await conn("twitter").get_platform_info()
        assert isinstance(info, dict)
