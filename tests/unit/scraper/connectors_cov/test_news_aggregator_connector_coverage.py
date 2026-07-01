"""
Coverage-focused tests for
src/scraper/extensions/connectors/news_aggregator_connector.py

The production module hard-imports ``feedparser`` (not installed). We install
a lightweight ``sys.modules`` stub for it *before* importing the module, then
mock the aiohttp session (JSON APIs and RSS text) and assert the exact
article records the connector produces for each service.
"""

import asyncio
import sys
import types
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# feedparser stub (used by the reuters / google_news RSS paths).
# ---------------------------------------------------------------------------
class _FeedResult:
    def __init__(self, entries=None):
        self.entries = entries or []


_PARSE_RESULT = {"value": _FeedResult()}


def _fake_parse(content):
    return _PARSE_RESULT["value"]


if "feedparser" not in sys.modules:
    fp = types.ModuleType("feedparser")
    fp.parse = _fake_parse
    sys.modules["feedparser"] = fp
else:  # pragma: no cover
    sys.modules["feedparser"].parse = _fake_parse


from src.scraper.extensions.connectors.news_aggregator_connector import (  # noqa: E402
    NewsAggregatorConnector,
)
from src.scraper.extensions.connectors.base import (  # noqa: E402
    ConnectionError,
    AuthenticationError,
)


# ---------------------------------------------------------------------------
# aiohttp session mocks.  session.get(...) returns an async context manager
# whose value is a response exposing .status, awaitable .json() and .text().
# ---------------------------------------------------------------------------
class _Response:
    def __init__(self, status=200, json_data=None, text=""):
        self.status = status
        self._json = json_data if json_data is not None else {}
        self._text = text

    async def json(self):
        return self._json

    async def text(self):
        return self._text


class _GetCtx:
    def __init__(self, response, recorder):
        self._response = response
        self._recorder = recorder

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, response, closed=False):
        self._response = response
        self.closed = closed
        self.requests = []  # (url, kwargs)

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return _GetCtx(self._response, self.requests)

    async def close(self):
        self.closed = True


def _connected(config, auth=None, response=None):
    """Build a connector with an injected open fake session + response."""
    conn = NewsAggregatorConnector(config, auth_config=auth or {})
    conn._session = _FakeSession(response if response is not None else _Response())
    conn._headers = {}
    conn._connected = True
    return conn


def _set_feed(entries):
    _PARSE_RESULT["value"] = _FeedResult(entries=entries)


# ---------------------------------------------------------------------------
# validate_config().
# ---------------------------------------------------------------------------
def test_validate_config_missing_service():
    assert NewsAggregatorConnector({}).validate_config() is False


def test_validate_config_newsapi_needs_api_key():
    assert (
        NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "k"}).validate_config()
        is True
    )
    assert NewsAggregatorConnector({"service": "newsapi"}, {}).validate_config() is False


def test_validate_config_bing_needs_subscription_key():
    assert (
        NewsAggregatorConnector(
            {"service": "bing_news"}, {"subscription_key": "s"}
        ).validate_config()
        is True
    )
    assert (
        NewsAggregatorConnector({"service": "bing_news"}, {}).validate_config() is False
    )


def test_validate_config_rss_services_need_no_key():
    assert NewsAggregatorConnector({"service": "reuters"}).validate_config() is True
    assert NewsAggregatorConnector({"service": "google_news"}).validate_config() is True


def test_validate_config_unknown_service_defaults_true():
    assert NewsAggregatorConnector({"service": "somethingelse"}).validate_config() is True


# ---------------------------------------------------------------------------
# connect() + _setup_service().
# ---------------------------------------------------------------------------
def test_connect_newsapi_sets_api_key_header():
    conn = NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "secret"})
    session = _FakeSession(_Response())
    with patch(
        "src.scraper.extensions.connectors.news_aggregator_connector.aiohttp.ClientSession",
        return_value=session,
    ):
        assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True
    assert conn._headers["X-API-Key"] == "secret"


def test_connect_bing_sets_subscription_header():
    conn = NewsAggregatorConnector({"service": "bing_news"}, {"subscription_key": "sk"})
    session = _FakeSession(_Response())
    with patch(
        "src.scraper.extensions.connectors.news_aggregator_connector.aiohttp.ClientSession",
        return_value=session,
    ):
        assert asyncio.run(conn.connect()) is True
    assert conn._headers["Ocp-Apim-Subscription-Key"] == "sk"


def test_connect_rss_sets_accept_header():
    conn = NewsAggregatorConnector({"service": "reuters"})
    session = _FakeSession(_Response())
    with patch(
        "src.scraper.extensions.connectors.news_aggregator_connector.aiohttp.ClientSession",
        return_value=session,
    ):
        assert asyncio.run(conn.connect()) is True
    assert "rss" in conn._headers["Accept"]


def test_connect_reuses_open_session():
    conn = NewsAggregatorConnector({"service": "reuters"})
    conn._session = _FakeSession(_Response(), closed=False)
    assert asyncio.run(conn.connect()) is True
    assert conn.is_connected is True


def test_disconnect_closes_session():
    conn = NewsAggregatorConnector({"service": "reuters"})
    session = _FakeSession(_Response(), closed=False)
    conn._session = session
    conn._connected = True
    asyncio.run(conn.disconnect())
    assert session.closed is True
    assert conn.is_connected is False


# ---------------------------------------------------------------------------
# fetch_data dispatch guards.
# ---------------------------------------------------------------------------
def test_fetch_data_requires_connection():
    conn = NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "k"})
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


def test_fetch_data_unsupported_service():
    conn = _connected({"service": "myspace"})
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "myspace" in str(ei.value)


# ---------------------------------------------------------------------------
# NewsAPI parsing.
# ---------------------------------------------------------------------------
def test_fetch_newsapi_top_headlines_records():
    resp = _Response(json_data={
        "articles": [
            {
                "title": "T1",
                "description": "D1",
                "content": "C1",
                "url": "https://n/1",
                "publishedAt": "2024-01-01",
                "author": "Auth",
                "source": {"name": "Src"},
                "urlToImage": "https://img/1",
            }
        ]
    })
    conn = _connected({"service": "newsapi"}, {"api_key": "k"}, resp)
    articles = asyncio.run(conn.fetch_data(country="us", language="en", limit=10))
    assert len(articles) == 1
    a = articles[0]
    assert a["title"] == "T1"
    assert a["source"] == "Src"
    assert a["url_to_image"] == "https://img/1"
    assert a["published_at"] == "2024-01-01"
    assert a["service"] == "newsapi"
    # top-headlines endpoint used (no query).
    url, kwargs = conn._session.requests[0]
    assert url == "https://newsapi.org/v2/top-headlines"
    assert kwargs["params"]["country"] == "us"


def test_fetch_newsapi_everything_endpoint_when_query():
    resp = _Response(json_data={"articles": []})
    conn = _connected({"service": "newsapi"}, {"api_key": "k"}, resp)
    asyncio.run(conn.fetch_data(query="ai", from_date="2024-01-01", to_date="2024-02-01"))
    url, kwargs = conn._session.requests[0]
    assert url == "https://newsapi.org/v2/everything"
    assert kwargs["params"]["q"] == "ai"
    assert kwargs["params"]["from"] == "2024-01-01"
    assert kwargs["params"]["to"] == "2024-02-01"


def test_fetch_newsapi_auth_error():
    conn = _connected({"service": "newsapi"}, {"api_key": "k"}, _Response(status=401))
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    # inner AuthenticationError is wrapped by fetch_data's ConnectionError.
    assert "authentication failed" in str(ei.value).lower()


def test_fetch_newsapi_rate_limit_error():
    conn = _connected({"service": "newsapi"}, {"api_key": "k"}, _Response(status=429))
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "rate limit" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# Guardian parsing.
# ---------------------------------------------------------------------------
def test_fetch_guardian_records_with_author_from_tags():
    resp = _Response(json_data={
        "response": {
            "results": [
                {
                    "webTitle": "WT",
                    "webUrl": "https://g/1",
                    "webPublicationDate": "2024-03-03",
                    "sectionName": "World",
                    "fields": {
                        "headline": "Head",
                        "trailText": "trail",
                        "body": "body text",
                        "thumbnail": "https://thumb",
                    },
                    "tags": [
                        {"type": "contributor", "webTitle": "Jane Doe"},
                        {"type": "keyword", "webTitle": "ignored"},
                    ],
                }
            ]
        }
    })
    conn = _connected({"service": "guardian"}, {"api_key": "gk"}, resp)
    articles = asyncio.run(conn.fetch_data(query="q", category="world", limit=5))
    assert len(articles) == 1
    a = articles[0]
    assert a["title"] == "Head"
    assert a["description"] == "trail"
    assert a["content"] == "body text"
    assert a["author"] == "Jane Doe"  # only contributor tag included
    assert a["source"] == "The Guardian"
    assert a["url_to_image"] == "https://thumb"
    assert a["section"] == "World"
    assert a["service"] == "guardian"
    _, kwargs = conn._session.requests[0]
    assert kwargs["params"]["q"] == "q"
    assert kwargs["params"]["section"] == "world"


def test_fetch_guardian_auth_error():
    conn = _connected({"service": "guardian"}, {"api_key": "gk"}, _Response(status=401))
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


# ---------------------------------------------------------------------------
# NYTimes parsing (both endpoints).
# ---------------------------------------------------------------------------
def test_fetch_nytimes_article_search_with_query():
    resp = _Response(json_data={
        "response": {
            "docs": [
                {
                    "headline": {"main": "NYT Title"},
                    "abstract": "abs",
                    "lead_paragraph": "lead",
                    "web_url": "https://nyt/1",
                    "pub_date": "2024-04-04",
                    "byline": {"person": [
                        {"firstname": "John", "lastname": "Smith"},
                    ]},
                    "section_name": "Tech",
                }
            ]
        }
    })
    conn = _connected({"service": "nytimes"}, {"api_key": "nk"}, resp)
    articles = asyncio.run(conn.fetch_data(query="ai", limit=3))
    a = articles[0]
    assert a["title"] == "NYT Title"
    assert a["content"] == "lead"
    assert a["author"] == "John Smith"
    assert a["section"] == "Tech"
    assert a["service"] == "nytimes"
    url, _ = conn._session.requests[0]
    assert "articlesearch" in url


def test_fetch_nytimes_top_stories_without_query():
    resp = _Response(json_data={
        "results": [
            {
                "title": "Top",
                "abstract": "a",
                "url": "https://nyt/top",
                "published_date": "2024-05-05",
                "byline": "By Someone",
                "section": "Home",
                "multimedia": [{"url": "https://img"}],
            }
        ]
    })
    conn = _connected({"service": "nytimes"}, {"api_key": "nk"}, resp)
    articles = asyncio.run(conn.fetch_data(limit=3))
    a = articles[0]
    assert a["title"] == "Top"
    assert a["author"] == "By Someone"
    assert a["url_to_image"] == "https://img"
    assert a["content"] == ""
    url, _ = conn._session.requests[0]
    assert "topstories" in url


def test_fetch_nytimes_rate_limit():
    conn = _connected({"service": "nytimes"}, {"api_key": "nk"}, _Response(status=429))
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data(query="x"))
    assert "rate limit" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# Reuters RSS parsing (uses feedparser stub + response.text()).
# ---------------------------------------------------------------------------
def test_fetch_reuters_rss_records():
    _set_feed([
        {
            "title": "R Title",
            "summary": "sum",
            "description": "descr",
            "link": "https://r/1",
            "published": "2024-06-06",
            "author": "Reporter",
        }
    ])
    conn = _connected({"service": "reuters"}, {}, _Response(status=200, text="<rss/>"))
    articles = asyncio.run(conn.fetch_data(category="technology", limit=5))
    assert len(articles) == 1
    a = articles[0]
    assert a["title"] == "R Title"
    assert a["description"] == "sum"
    assert a["content"] == "descr"
    assert a["url"] == "https://r/1"
    assert a["source"] == "Reuters"
    assert a["service"] == "reuters"
    # technology category maps to the technology RSS url.
    url, _ = conn._session.requests[0]
    assert "technologyNews" in url


def test_fetch_reuters_unknown_category_falls_back_to_world():
    _set_feed([])
    conn = _connected({"service": "reuters"}, {}, _Response(status=200, text="<rss/>"))
    asyncio.run(conn.fetch_data(category="unknowncat"))
    url, _ = conn._session.requests[0]
    assert "worldNews" in url


def test_fetch_reuters_http_error():
    conn = _connected({"service": "reuters"}, {}, _Response(status=500))
    with pytest.raises(ConnectionError) as ei:
        asyncio.run(conn.fetch_data())
    assert "500" in str(ei.value)


# ---------------------------------------------------------------------------
# Google News RSS parsing.
# ---------------------------------------------------------------------------
def test_fetch_google_news_records_with_query():
    _set_feed([
        {
            "title": "G Title",
            "summary": "gsum",
            "link": "https://g/news",
            "published": "2024-07-07",
            "source": {"title": "BBC"},
        }
    ])
    conn = _connected({"service": "google_news"}, {}, _Response(status=200, text="<rss/>"))
    articles = asyncio.run(conn.fetch_data(query="ai", country="us", language="en"))
    a = articles[0]
    assert a["title"] == "G Title"
    assert a["source"] == "BBC"
    assert a["service"] == "google_news"
    url, _ = conn._session.requests[0]
    assert "search?q=ai" in url


def test_fetch_google_news_without_query_uses_base_feed():
    _set_feed([])
    conn = _connected({"service": "google_news"}, {}, _Response(status=200, text="<rss/>"))
    asyncio.run(conn.fetch_data(country="gb", language="en"))
    url, _ = conn._session.requests[0]
    assert "search" not in url
    assert "hl=en" in url


# ---------------------------------------------------------------------------
# Bing News parsing.
# ---------------------------------------------------------------------------
def test_fetch_bing_news_records():
    resp = _Response(json_data={
        "value": [
            {
                "name": "B Title",
                "description": "bdesc",
                "url": "https://b/1",
                "datePublished": "2024-08-08",
                "provider": [{"name": "Provider"}],
                "image": {"thumbnail": {"contentUrl": "https://bimg"}},
            }
        ]
    })
    conn = _connected({"service": "bing_news"}, {"subscription_key": "s"}, resp)
    articles = asyncio.run(conn.fetch_data(query="tech", category="business", country="us"))
    a = articles[0]
    assert a["title"] == "B Title"
    assert a["source"] == "Provider"
    assert a["url_to_image"] == "https://bimg"
    assert a["service"] == "bing_news"
    _, kwargs = conn._session.requests[0]
    assert kwargs["params"]["q"] == "tech"
    assert kwargs["params"]["category"] == "business"


def test_fetch_bing_news_auth_error():
    conn = _connected(
        {"service": "bing_news"}, {"subscription_key": "s"}, _Response(status=401)
    )
    with pytest.raises(ConnectionError):
        asyncio.run(conn.fetch_data())


# ---------------------------------------------------------------------------
# validate_data_format().
# ---------------------------------------------------------------------------
def test_validate_data_format_non_dict():
    conn = NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "k"})
    assert conn.validate_data_format([1, 2]) is False


def test_validate_data_format_missing_required():
    conn = NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "k"})
    assert conn.validate_data_format({"title": "t", "url": "u"}) is False  # no service
    assert conn.validate_data_format(
        {"title": "", "url": "u", "service": "newsapi"}
    ) is False


def test_validate_data_format_valid():
    conn = NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "k"})
    assert conn.validate_data_format(
        {"title": "t", "url": "u", "service": "newsapi"}
    ) is True


# ---------------------------------------------------------------------------
# get_available_categories() / get_service_limits().
# ---------------------------------------------------------------------------
def test_get_available_categories_known_service():
    conn = NewsAggregatorConnector({"service": "newsapi"}, {"api_key": "k"})
    cats = asyncio.run(conn.get_available_categories())
    assert "technology" in cats
    assert "business" in cats


def test_get_available_categories_unknown_service_empty():
    conn = NewsAggregatorConnector({"service": "unknown"})
    assert asyncio.run(conn.get_available_categories()) == []


def test_get_service_limits_known_service():
    conn = NewsAggregatorConnector({"service": "guardian"}, {"api_key": "k"})
    limits = asyncio.run(conn.get_service_limits())
    assert limits["requests_per_day"] == 5000
    assert limits["requires_api_key"] is True


def test_get_service_limits_unknown_service_empty():
    conn = NewsAggregatorConnector({"service": "unknown"})
    assert asyncio.run(conn.get_service_limits()) == {}
