"""Tests for src/dashboards/api_client.py (requests session mocked)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("streamlit")
pytest.importorskip("requests")

import requests  # noqa: E402

from dashboards.api_client import APIError, NeuroNewsAPIClient  # noqa: E402


def make_response(json_data, status_ok=True):
    resp = MagicMock()
    resp.json.return_value = json_data
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    return resp


@pytest.fixture
def client():
    c = NeuroNewsAPIClient(base_url="http://test")
    c.session = MagicMock()
    c.retry_attempts = 1  # avoid retry sleeps
    return c


class TestMakeRequest:
    def test_success(self, client):
        resp = make_response([{"a": 1}])
        client.session.request.return_value = resp
        out = client._make_request("GET", "/x")
        assert out is resp

    def test_failure_raises_apierror(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("down")
        with pytest.raises(APIError):
            client._make_request("GET", "/x")


class TestEndpoints:
    def test_articles_by_topic(self, client):
        client.session.request.return_value = make_response([{"id": "1"}])
        out = client.get_articles_by_topic("uniquetopic1")
        assert out == [{"id": "1"}]

    def test_breaking_news(self, client):
        client.session.request.return_value = make_response([{"event": "x"}])
        out = client.get_breaking_news(hours=12)
        assert isinstance(out, list)

    def test_articles_by_category(self, client):
        client.session.request.return_value = make_response([{"id": "2"}])
        out = client.get_articles_by_category("uniquecat1")
        assert isinstance(out, list)

    def test_search_articles(self, client):
        client.session.request.return_value = make_response([{"id": "3"}])
        out = client.search_articles("uniquequery1")
        assert isinstance(out, list)

    def test_error_path_returns_empty(self, client):
        client.session.request.side_effect = requests.exceptions.ConnectionError("x")
        out = client.get_articles_by_topic("errtopic1")
        assert out == []
