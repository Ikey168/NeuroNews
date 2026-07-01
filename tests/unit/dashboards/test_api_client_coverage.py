"""Coverage tests for src/dashboards/api_client.py.

Real tests: the requests.Session is mocked at the instance level (patch where
it is looked up), and we assert request construction (method/url/params) and
response handling for every public method plus all error paths.

Cached methods (@st.cache_data) are keyed on their arguments, so each test that
exercises a cached method uses a unique argument value to avoid cache hits from
a previous test masking the mocked session behaviour.
"""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("streamlit")
pytest.importorskip("requests")

import requests  # noqa: E402

import dashboards.api_client as mod  # noqa: E402
from dashboards.api_client import (  # noqa: E402
    APIError,
    BatchAPIClient,
    NeuroNewsAPIClient,
    check_api_connection,
    get_api_status,
)


def make_response(json_data=None, status_code=200, raise_http=False):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data if json_data is not None else []
    if raise_http:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    else:
        resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def client():
    c = NeuroNewsAPIClient(base_url="http://test")
    c.session = MagicMock()
    c.retry_attempts = 1  # avoid retry sleeps
    return c


# ---------------------------------------------------------------------------
# __init__ / configuration
# ---------------------------------------------------------------------------
class TestInit:
    def test_default_base_url_from_config(self):
        c = NeuroNewsAPIClient()
        assert c.base_url == mod.API_CONFIG["base_url"]
        assert c.timeout == mod.API_CONFIG["timeout"]
        assert c.retry_attempts == mod.API_CONFIG["retry_attempts"]

    def test_custom_base_url(self):
        c = NeuroNewsAPIClient(base_url="http://custom:9000")
        assert c.base_url == "http://custom:9000"

    def test_default_headers_are_set(self):
        c = NeuroNewsAPIClient()
        assert c.session.headers["Content-Type"] == "application/json"
        assert c.session.headers["User-Agent"] == "NeuroNews-Dashboard/1.0"


# ---------------------------------------------------------------------------
# _make_request
# ---------------------------------------------------------------------------
class TestMakeRequest:
    def test_success_builds_url_and_returns_response(self, client):
        resp = make_response([{"a": 1}])
        client.session.request.return_value = resp
        out = client._make_request("GET", "/foo", params={"limit": 3})
        assert out is resp
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["method"] == "GET"
        assert kwargs["url"] == "http://test/foo"
        assert kwargs["timeout"] == client.timeout
        assert kwargs["params"] == {"limit": 3}
        resp.raise_for_status.assert_called_once()

    def test_http_error_status_raises_apierror(self, client):
        client.session.request.return_value = make_response(raise_http=True)
        with pytest.raises(APIError):
            client._make_request("GET", "/bad")

    def test_connection_error_raises_apierror(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("down")
        with pytest.raises(APIError) as exc:
            client._make_request("GET", "/x")
        assert "after 1 attempts" in str(exc.value)

    def test_retries_then_succeeds(self):
        c = NeuroNewsAPIClient(base_url="http://test")
        c.session = MagicMock()
        c.retry_attempts = 3
        good = make_response([{"ok": True}])
        c.session.request.side_effect = [
            requests.exceptions.Timeout("t1"),
            requests.exceptions.Timeout("t2"),
            good,
        ]
        with patch("time.sleep", return_value=None):
            out = c._make_request("GET", "/retry")
        assert out is good
        assert c.session.request.call_count == 3

    def test_retries_exhausted_raises(self):
        c = NeuroNewsAPIClient(base_url="http://test")
        c.session = MagicMock()
        c.retry_attempts = 2
        c.session.request.side_effect = requests.exceptions.ConnectionError("down")
        with patch("time.sleep", return_value=None):
            with pytest.raises(APIError):
                c._make_request("GET", "/retry-fail")
        assert c.session.request.call_count == 2


# ---------------------------------------------------------------------------
# Cached GET endpoints - success paths (unique args to dodge cache)
# ---------------------------------------------------------------------------
class TestCachedEndpointsSuccess:
    def test_get_articles_by_topic(self, client):
        client.session.request.return_value = make_response([{"id": "a1"}])
        out = client.get_articles_by_topic("topic_uniq_1", limit=5)
        assert out == [{"id": "a1"}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/news/articles/topic/topic_uniq_1"
        assert kwargs["params"] == {"limit": 5}

    def test_get_articles_by_topic_limit_capped(self, client):
        client.session.request.return_value = make_response([])
        client.get_articles_by_topic("topic_uniq_cap", limit=10_000)
        params = client.session.request.call_args.kwargs["params"]
        assert params["limit"] == mod.DATA_CONFIG["max_articles"]

    def test_get_breaking_news(self, client):
        client.session.request.return_value = make_response([{"event": "x"}])
        out = client.get_breaking_news(hours=12, limit=4)
        assert out == [{"event": "x"}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/api/v1/breaking-news"
        assert kwargs["params"]["hours"] == 12
        assert kwargs["params"]["limit"] == 4

    def test_get_breaking_news_limit_capped(self, client):
        client.session.request.return_value = make_response([])
        client.get_breaking_news(hours=99, limit=10_000)
        params = client.session.request.call_args.kwargs["params"]
        assert params["limit"] == mod.DATA_CONFIG["max_events"]

    def test_get_entities(self, client):
        client.session.request.return_value = make_response([{"id": "e1"}])
        out = client.get_entities(limit=7)
        assert out == [{"id": "e1"}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/graph/entities"
        assert kwargs["params"]["limit"] == 7

    def test_get_entities_limit_capped(self, client):
        client.session.request.return_value = make_response([])
        client.get_entities(limit=10_000)
        params = client.session.request.call_args.kwargs["params"]
        assert params["limit"] == mod.DATA_CONFIG["max_entities"]

    def test_get_entity_relationships(self, client):
        client.session.request.return_value = make_response({"relationships": []})
        out = client.get_entity_relationships("ent_uniq_1")
        assert out == {"relationships": []}
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/graph/entity/ent_uniq_1/relationships"

    def test_get_sentiment_trends(self, client):
        client.session.request.return_value = make_response([{"day": 1}])
        out = client.get_sentiment_trends(days=3)
        assert out == [{"day": 1}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/sentiment/trends"
        assert kwargs["params"] == {"days": 3}

    def test_get_trending_topics(self, client):
        client.session.request.return_value = make_response([{"topic": "t"}])
        out = client.get_trending_topics(limit=9)
        assert out == [{"topic": "t"}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/topics/trending"
        assert kwargs["params"] == {"limit": 9}


# ---------------------------------------------------------------------------
# Non-cached GET endpoints - success paths
# ---------------------------------------------------------------------------
class TestNonCachedEndpointsSuccess:
    def test_get_articles_by_category(self, client):
        client.session.request.return_value = make_response([{"id": "c1"}])
        out = client.get_articles_by_category("business", limit=6)
        assert out == [{"id": "c1"}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/news/articles/category/business"
        assert kwargs["params"]["limit"] == 6

    def test_search_articles(self, client):
        client.session.request.return_value = make_response([{"id": "s1"}])
        out = client.search_articles("neural nets", limit=8)
        assert out == [{"id": "s1"}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/news/search"
        assert kwargs["params"] == {"q": "neural nets", "limit": 8}

    def test_get_event_clusters(self, client):
        client.session.request.return_value = make_response([{"cluster": 1}])
        out = client.get_event_clusters(method="dbscan", min_size=5)
        assert out == [{"cluster": 1}]
        kwargs = client.session.request.call_args.kwargs
        assert kwargs["url"] == "http://test/api/v1/event-clusters"
        assert kwargs["params"] == {"clustering_method": "dbscan", "min_cluster_size": 5}

    def test_get_dashboard_summary(self, client):
        client.session.request.return_value = make_response({"total": 10})
        out = client.get_dashboard_summary()
        assert out == {"total": 10}
        assert client.session.request.call_args.kwargs["url"] == "http://test/dashboard/summary"

    def test_health_check_true(self, client):
        client.session.request.return_value = make_response({}, status_code=200)
        assert client.health_check() is True

    def test_health_check_non_200(self, client):
        client.session.request.return_value = make_response({}, status_code=503)
        assert client.health_check() is False

    def test_health_check_exception(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.health_check() is False


# ---------------------------------------------------------------------------
# Error paths - APIError caught, empty container returned
# ---------------------------------------------------------------------------
class TestErrorPaths:
    def test_articles_by_topic_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_articles_by_topic("err_topic_1") == []

    def test_breaking_news_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_breaking_news(hours=7777) == []

    def test_entities_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_entities(limit=123) == []

    def test_entity_relationships_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_entity_relationships("err_ent_1") == {}

    def test_sentiment_trends_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_sentiment_trends(days=999) == []

    def test_trending_topics_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_trending_topics(limit=987) == []

    def test_articles_by_category_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_articles_by_category("errcat") == []

    def test_search_articles_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.search_articles("errquery") == []

    def test_event_clusters_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_event_clusters() == []

    def test_dashboard_summary_error(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        assert client.get_dashboard_summary() == {}

    def test_unexpected_exception_returns_empty_list(self, client):
        # raise a non-APIError from json() so the generic except branch runs
        resp = make_response()
        resp.json.side_effect = ValueError("bad json")
        client.session.request.return_value = resp
        assert client.get_articles_by_category("weirdcat") == []

    def test_unexpected_exception_summary_returns_empty_dict(self, client):
        resp = make_response()
        resp.json.side_effect = ValueError("bad json")
        client.session.request.return_value = resp
        assert client.get_dashboard_summary() == {}

    # Generic (non-APIError) exception branches for the cached endpoints.
    # A response whose .json() raises ValueError bypasses the APIError branch
    # and exercises the "except Exception" fallback. Unique args avoid cache.
    def _bad_json_response(self):
        resp = make_response()
        resp.json.side_effect = ValueError("bad json")
        return resp

    def test_articles_by_topic_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_articles_by_topic("gen_topic_1") == []

    def test_breaking_news_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_breaking_news(hours=8888) == []

    def test_entities_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_entities(limit=321) == []

    def test_entity_relationships_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_entity_relationships("gen_ent_1") == {}

    def test_sentiment_trends_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_sentiment_trends(days=888) == []

    def test_trending_topics_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_trending_topics(limit=876) == []

    def test_search_articles_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.search_articles("gen_query_1") == []

    def test_event_clusters_generic_exception(self, client):
        client.session.request.return_value = self._bad_json_response()
        assert client.get_event_clusters(method="spectral") == []


# ---------------------------------------------------------------------------
# BatchAPIClient
# ---------------------------------------------------------------------------
class TestBatchAPIClient:
    def test_init_reads_perf_config(self, client):
        batch = BatchAPIClient(client)
        assert batch.api_client is client
        assert batch.max_concurrent == mod.PERFORMANCE_CONFIG["max_concurrent_requests"]

    def test_fetch_multiple_success(self, client):
        batch = BatchAPIClient(client)

        # Build a fake aiohttp session whose .get() returns a context manager
        class FakeResp:
            status = 200

            async def json(self):
                return {"relationships": [{"target": "z"}]}

        class FakeCtx:
            async def __aenter__(self_inner):
                return FakeResp()

            async def __aexit__(self_inner, *a):
                return False

        class FakeSession:
            def get(self_inner, url, timeout=None):
                return FakeCtx()

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *a):
                return False

        with patch.object(mod.aiohttp, "ClientSession", return_value=FakeSession()):
            result = asyncio.run(
                batch.fetch_multiple_entity_relationships(["e1", "e2"])
            )
        assert result == {
            "e1": {"relationships": [{"target": "z"}]},
            "e2": {"relationships": [{"target": "z"}]},
        }

    def test_fetch_multiple_non_200_returns_empty(self, client):
        batch = BatchAPIClient(client)

        class FakeResp:
            status = 404

            async def json(self):
                return {"should": "not be used"}

        class FakeCtx:
            async def __aenter__(self_inner):
                return FakeResp()

            async def __aexit__(self_inner, *a):
                return False

        class FakeSession:
            def get(self_inner, url, timeout=None):
                return FakeCtx()

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *a):
                return False

        with patch.object(mod.aiohttp, "ClientSession", return_value=FakeSession()):
            result = asyncio.run(batch.fetch_multiple_entity_relationships(["e1"]))
        assert result == {"e1": {}}

    def test_fetch_multiple_exception_returns_empty(self, client):
        batch = BatchAPIClient(client)

        class FakeSession:
            def get(self_inner, url, timeout=None):
                raise RuntimeError("boom")

            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *a):
                return False

        with patch.object(mod.aiohttp, "ClientSession", return_value=FakeSession()):
            result = asyncio.run(batch.fetch_multiple_entity_relationships(["e1"]))
        assert result == {"e1": {}}

    def test_get_multiple_sync_wrapper(self, client):
        batch = BatchAPIClient(client)
        with patch.object(
            batch,
            "fetch_multiple_entity_relationships",
            new=_make_coro({"e1": {"relationships": []}}),
        ):
            out = batch.get_multiple_entity_relationships(["e1"])
        assert out == {"e1": {"relationships": []}}

    def test_get_multiple_sync_wrapper_error(self, client):
        batch = BatchAPIClient(client)

        async def boom(entity_ids):
            raise RuntimeError("fail")

        with patch.object(batch, "fetch_multiple_entity_relationships", new=boom):
            out = batch.get_multiple_entity_relationships(["e1"])
        assert out == {}


def _make_coro(return_value):
    async def _coro(*args, **kwargs):
        return return_value

    return _coro


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------
class TestModuleHelpers:
    def test_check_api_connection_true(self):
        fake_client = MagicMock()
        fake_client.health_check.return_value = True
        with patch.object(mod, "get_api_client", return_value=fake_client):
            assert check_api_connection() is True
        fake_client.health_check.assert_called_once()

    def test_check_api_connection_false(self):
        fake_client = MagicMock()
        fake_client.health_check.return_value = False
        with patch.object(mod, "get_api_client", return_value=fake_client):
            assert check_api_connection() is False

    def test_get_api_status_all_healthy(self):
        fake_client = MagicMock()
        fake_client.base_url = "http://test"
        fake_client._make_request.return_value = make_response({}, status_code=200)
        with patch.object(mod, "get_api_client", return_value=fake_client):
            status = get_api_status()
        assert status["healthy"] is True
        assert status["base_url"] == "http://test"
        assert set(status["endpoints"].keys()) == {
            "Health Check",
            "News API",
            "Graph API",
            "Event Detection API",
        }
        for ep in status["endpoints"].values():
            assert ep["status"] == "healthy"
            assert ep["status_code"] == 200

    def test_get_api_status_error_status_code(self):
        fake_client = MagicMock()
        fake_client.base_url = "http://test"
        fake_client._make_request.return_value = make_response({}, status_code=500)
        with patch.object(mod, "get_api_client", return_value=fake_client):
            status = get_api_status()
        assert status["healthy"] is False
        for ep in status["endpoints"].values():
            assert ep["status"] == "error"
            assert ep["status_code"] == 500

    def test_get_api_status_endpoint_exception(self):
        fake_client = MagicMock()
        fake_client.base_url = "http://test"
        fake_client._make_request.side_effect = RuntimeError("network")
        with patch.object(mod, "get_api_client", return_value=fake_client):
            status = get_api_status()
        assert status["healthy"] is False
        for ep in status["endpoints"].values():
            assert ep["status"] == "error"
            assert "error" in ep


# ---------------------------------------------------------------------------
# cache_resource factory functions
# ---------------------------------------------------------------------------
class TestCachedFactories:
    def test_get_api_client_returns_client(self):
        c = mod.get_api_client()
        assert isinstance(c, NeuroNewsAPIClient)

    def test_get_batch_api_client_returns_batch(self):
        b = mod.get_batch_api_client()
        assert isinstance(b, BatchAPIClient)
        assert isinstance(b.api_client, NeuroNewsAPIClient)
