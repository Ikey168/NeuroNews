"""
Coverage-focused tests for
src/scraper/extensions/connectors/social_media_connector.py

This module does not hard-import praw/tweepy: it talks to the platform HTTP
APIs directly via aiohttp.  We therefore mock the aiohttp session (both GET
and, for Reddit's OAuth, POST) and assert the exact post records the
connector produces for each platform.
"""

import asyncio
from unittest.mock import patch

import pytest

from src.scraper.extensions.connectors.social_media_connector import (  # noqa: E402
    SocialMediaConnector,
)
from src.scraper.extensions.connectors.base import (  # noqa: E402
    ConnectionError,
    AuthenticationError,
)


# ---------------------------------------------------------------------------
# aiohttp session mocks.
# ---------------------------------------------------------------------------
class _Response:
    def __init__(self, status=200, json_data=None):
        self.status = status
        self._json = json_data if json_data is not None else {}

    async def json(self):
        return self._json


class _ReqCtx:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, get_response=None, post_response=None, closed=False):
        self._get_response = get_response if get_response is not None else _Response()
        self._post_response = post_response
        self.closed = closed
        self.get_requests = []
        self.post_requests = []

    def get(self, url, **kwargs):
        self.get_requests.append((url, kwargs))
        return _ReqCtx(self._get_response)

    def post(self, url, **kwargs):
        self.post_requests.append((url, kwargs))
        return _ReqCtx(self._post_response)

    async def close(self):
        self.closed = True


def _connected(config, auth=None, get_response=None):
    conn = SocialMediaConnector(config, auth_config=auth or {})
    conn._session = _FakeSession(get_response=get_response)
    conn._headers = {"User-Agent": "test"}
    conn._connected = True
    return conn


# ---------------------------------------------------------------------------
# validate_config().
# ---------------------------------------------------------------------------
def test_validate_config_missing_platform():
    assert SocialMediaConnector({}).validate_config() is False


def test_validate_config_twitter_needs_token_or_key():
    assert (
        SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"}).validate_config()
        is True
    )
    assert (
        SocialMediaConnector({"platform": "x"}, {"api_key": "k"}).validate_config() is True
    )
    assert SocialMediaConnector({"platform": "twitter"}, {}).validate_config() is False


def test_validate_config_reddit_needs_client_credentials():
    assert (
        SocialMediaConnector(
            {"platform": "reddit"}, {"client_id": "c", "client_secret": "s"}
        ).validate_config()
        is True
    )
    assert (
        SocialMediaConnector({"platform": "reddit"}, {"client_id": "c"}).validate_config()
        is False
    )


def test_validate_config_facebook_needs_access_token():
    assert (
        SocialMediaConnector({"platform": "facebook"}, {"access_token": "a"}).validate_config()
        is True
    )
    assert SocialMediaConnector({"platform": "facebook"}, {}).validate_config() is False


def test_validate_config_unknown_platform_defaults_true():
    assert SocialMediaConnector({"platform": "mastodon"}).validate_config() is True


# ---------------------------------------------------------------------------
# connect() + platform setup.
# ---------------------------------------------------------------------------
def _patch_session(session):
    return patch(
        "src.scraper.extensions.connectors.social_media_connector.aiohttp.ClientSession",
        return_value=session,
    )


def test_connect_twitter_bearer_sets_auth_header():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "abc"})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True
    assert conn._headers["Authorization"] == "Bearer abc"


def test_connect_twitter_api_key_fallback():
    conn = SocialMediaConnector({"platform": "twitter"}, {"api_key": "xyz"})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is True
    assert conn._headers["Authorization"] == "Bearer xyz"


def test_connect_twitter_no_credentials_fails():
    conn = SocialMediaConnector({"platform": "twitter"}, {})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is False
    assert conn.is_connected is False
    assert isinstance(conn.last_error, AuthenticationError)


def test_connect_facebook_sets_bearer():
    conn = SocialMediaConnector({"platform": "facebook"}, {"access_token": "fbtok"})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is True
    assert conn._headers["Authorization"] == "Bearer fbtok"


def test_connect_instagram_sets_bearer():
    conn = SocialMediaConnector({"platform": "instagram"}, {"access_token": "igtok"})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is True
    assert conn._headers["Authorization"] == "Bearer igtok"


def test_connect_linkedin_sets_bearer():
    conn = SocialMediaConnector({"platform": "linkedin"}, {"access_token": "litok"})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is True
    assert conn._headers["Authorization"] == "Bearer litok"


def test_connect_unsupported_platform_fails():
    conn = SocialMediaConnector({"platform": "myspace"}, {})
    with _patch_session(_FakeSession()):
        assert asyncio.run(conn.connect()) is False
    assert isinstance(conn.last_error, AuthenticationError)


def test_connect_reddit_oauth_success():
    conn = SocialMediaConnector(
        {"platform": "reddit"}, {"client_id": "cid", "client_secret": "sec"}
    )
    post_resp = _Response(status=200, json_data={"access_token": "reddit-token"})
    session = _FakeSession(post_response=post_resp)
    with _patch_session(session):
        assert asyncio.run(conn.connect()) is True
    assert conn._headers["Authorization"] == "Bearer reddit-token"
    # OAuth POST was made to the reddit token endpoint.
    assert session.post_requests[0][0] == "https://www.reddit.com/api/v1/access_token"


def test_connect_reddit_oauth_failure():
    conn = SocialMediaConnector(
        {"platform": "reddit"}, {"client_id": "cid", "client_secret": "sec"}
    )
    session = _FakeSession(post_response=_Response(status=403))
    with _patch_session(session):
        assert asyncio.run(conn.connect()) is False
    assert isinstance(conn.last_error, AuthenticationError)


def test_connect_reuses_open_session():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    conn._session = _FakeSession(closed=False)
    assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True


def test_disconnect_closes_session():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    session = _FakeSession(closed=False)
    conn._session = session
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert session.closed is True
    assert conn.is_connected is False


# ---------------------------------------------------------------------------
# fetch_data dispatch guards.
# ---------------------------------------------------------------------------
def test_fetch_data_requires_connection():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


def test_fetch_data_unsupported_platform():
    conn = _connected({"platform": "myspace"})
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "myspace" in str(ei.value)


# ---------------------------------------------------------------------------
# Twitter parsing (includes user expansion join).
# ---------------------------------------------------------------------------
def test_fetch_twitter_joins_user_expansions():
    resp = _Response(json_data={
        "data": [
            {
                "id": "111",
                "text": "hello world",
                "created_at": "2024-01-01",
                "author_id": "u1",
                "public_metrics": {"like_count": 5},
                "lang": "en",
            }
        ],
        "includes": {
            "users": [
                {"id": "u1", "username": "alice", "name": "Alice", "verified": True}
            ]
        },
    })
    conn = _connected({"platform": "twitter"}, {"bearer_token": "t"}, resp)
    posts = asyncio.run(conn.fetch_data(query="hi", limit=10))
    assert len(posts) == 1
    p = posts[0]
    assert p["id"] == "111"
    assert p["text"] == "hello world"
    assert p["author_username"] == "alice"
    assert p["author_name"] == "Alice"
    assert p["author_verified"] is True
    assert p["metrics"] == {"like_count": 5}
    assert p["platform"] == "twitter"
    assert p["url"] == "https://twitter.com/alice/status/111"


def test_fetch_twitter_missing_user_uses_unknown_url():
    resp = _Response(json_data={
        "data": [{"id": "222", "text": "orphan", "author_id": "ghost"}],
        "includes": {},
    })
    conn = _connected({"platform": "twitter"}, {"bearer_token": "t"}, resp)
    posts = asyncio.run(conn.fetch_data())
    assert posts[0]["author_username"] is None
    assert posts[0]["url"] == "https://twitter.com/unknown/status/222"


def test_fetch_twitter_auth_error():
    conn = _connected({"platform": "twitter"}, {"bearer_token": "t"}, _Response(status=401))
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


def test_fetch_twitter_generic_error():
    conn = _connected({"platform": "twitter"}, {"bearer_token": "t"}, _Response(status=500))
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "500" in str(ei.value)


# ---------------------------------------------------------------------------
# Reddit parsing (timestamp conversion, permalink url).
# ---------------------------------------------------------------------------
def test_fetch_reddit_records():
    resp = _Response(json_data={
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc",
                        "title": "Reddit Post",
                        "selftext": "body",
                        "created_utc": 1704067200,  # 2024-01-01 UTC
                        "author": "redditor",
                        "subreddit": "python",
                        "score": 42,
                        "num_comments": 7,
                        "upvote_ratio": 0.95,
                        "permalink": "/r/python/comments/abc/",
                    }
                }
            ]
        }
    })
    conn = _connected({"platform": "reddit"}, {"client_id": "c", "client_secret": "s"}, resp)
    posts = asyncio.run(conn.fetch_data(query="", subreddit="python", sort="hot"))
    p = posts[0]
    assert p["id"] == "abc"
    assert p["title"] == "Reddit Post"
    assert p["text"] == "body"
    assert p["author"] == "redditor"
    assert p["subreddit"] == "python"
    assert p["score"] == 42
    assert p["platform"] == "reddit"
    assert p["url"] == "https://reddit.com/r/python/comments/abc/"
    # created_at is an ISO timestamp string derived from created_utc.
    assert isinstance(p["created_at"], str)
    assert "2024" in p["created_at"]


def test_fetch_reddit_search_url_when_query():
    resp = _Response(json_data={"data": {"children": []}})
    conn = _connected({"platform": "reddit"}, {"client_id": "c", "client_secret": "s"}, resp)
    asyncio.run(conn.fetch_data(query="django", subreddit="python"))
    url, kwargs = conn._session.get_requests[0]
    assert url.endswith("/r/python/search")
    assert kwargs["params"]["q"] == "django"
    assert kwargs["params"]["restrict_sr"] == "true"


def test_fetch_reddit_auth_error():
    conn = _connected(
        {"platform": "reddit"}, {"client_id": "c", "client_secret": "s"}, _Response(status=401)
    )
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


# ---------------------------------------------------------------------------
# Facebook parsing.
# ---------------------------------------------------------------------------
def test_fetch_facebook_records():
    resp = _Response(json_data={
        "data": [
            {
                "id": "fb1",
                "message": "hi fb",
                "created_time": "2024-02-02",
                "likes": {"summary": {"total_count": 10}},
                "comments": {"summary": {"total_count": 3}},
                "shares": {"count": 2},
            }
        ]
    })
    conn = _connected({"platform": "facebook"}, {"access_token": "a"}, resp)
    posts = asyncio.run(conn.fetch_data(page_id="mypage"))
    p = posts[0]
    assert p["id"] == "fb1"
    assert p["text"] == "hi fb"
    assert p["likes"] == 10
    assert p["comments"] == 3
    assert p["shares"] == 2
    assert p["platform"] == "facebook"
    url, _ = conn._session.get_requests[0]
    assert "mypage/posts" in url


def test_fetch_facebook_requires_page_id():
    conn = _connected({"platform": "facebook"}, {"access_token": "a"})
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "page_id" in str(ei.value)


def test_fetch_facebook_auth_error():
    conn = _connected({"platform": "facebook"}, {"access_token": "a"}, _Response(status=401))
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data(page_id="p"))


# ---------------------------------------------------------------------------
# Instagram parsing.
# ---------------------------------------------------------------------------
def test_fetch_instagram_records():
    resp = _Response(json_data={
        "data": [
            {
                "id": "ig1",
                "caption": "a caption",
                "media_type": "IMAGE",
                "media_url": "https://ig/media",
                "thumbnail_url": "https://ig/thumb",
                "timestamp": "2024-03-03",
                "username": "insta_user",
            }
        ]
    })
    conn = _connected({"platform": "instagram"}, {"access_token": "a"}, resp)
    posts = asyncio.run(conn.fetch_data())
    p = posts[0]
    assert p["id"] == "ig1"
    assert p["text"] == "a caption"
    assert p["media_type"] == "IMAGE"
    assert p["media_url"] == "https://ig/media"
    assert p["username"] == "insta_user"
    assert p["platform"] == "instagram"


def test_fetch_instagram_auth_error():
    conn = _connected({"platform": "instagram"}, {"access_token": "a"}, _Response(status=401))
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


# ---------------------------------------------------------------------------
# LinkedIn parsing (millisecond timestamp conversion).
# ---------------------------------------------------------------------------
def test_fetch_linkedin_records():
    resp = _Response(json_data={
        "elements": [
            {
                "id": "li1",
                "text": {"text": "linkedin post"},
                "created": {"time": 1704067200000},  # ms
                "author": "urn:li:person:123",
            }
        ]
    })
    conn = _connected({"platform": "linkedin"}, {"access_token": "a"}, resp)
    posts = asyncio.run(conn.fetch_data())
    p = posts[0]
    assert p["id"] == "li1"
    assert p["text"] == "linkedin post"
    assert p["author"] == "urn:li:person:123"
    assert p["platform"] == "linkedin"
    assert isinstance(p["created_at"], str)
    assert "2024" in p["created_at"]


def test_fetch_linkedin_auth_error():
    conn = _connected({"platform": "linkedin"}, {"access_token": "a"}, _Response(status=401))
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


# ---------------------------------------------------------------------------
# validate_data_format().
# ---------------------------------------------------------------------------
def test_validate_data_format_non_dict():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    assert conn.validate_data_format("nope") is False


def test_validate_data_format_missing_required_keys():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    # missing 'platform'
    assert conn.validate_data_format({"id": "1", "text": "x"}) is False


def test_validate_data_format_requires_some_content():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    # has id + platform but no text/title/message -> invalid
    assert conn.validate_data_format({"id": "1", "platform": "twitter"}) is False


def test_validate_data_format_valid_with_text():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    assert (
        conn.validate_data_format({"id": "1", "platform": "twitter", "text": "hi"})
        is True
    )


def test_validate_data_format_valid_with_title():
    conn = SocialMediaConnector({"platform": "reddit"}, {"client_id": "c", "client_secret": "s"})
    assert (
        conn.validate_data_format({"id": "1", "platform": "reddit", "title": "t"})
        is True
    )


# ---------------------------------------------------------------------------
# get_platform_info().
# ---------------------------------------------------------------------------
def test_get_platform_info_known_platform():
    conn = SocialMediaConnector({"platform": "twitter"}, {"bearer_token": "t"})
    info = asyncio.run(conn.get_platform_info())
    assert info["max_results_per_request"] == 100
    assert "text" in info["supported_fields"]


def test_get_platform_info_unknown_platform_empty():
    conn = SocialMediaConnector({"platform": "unknown"})
    assert asyncio.run(conn.get_platform_info()) == {}
