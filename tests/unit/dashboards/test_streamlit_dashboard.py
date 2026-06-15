"""Tests for src/dashboards/streamlit_dashboard.py (API client + chart builders)."""

import os
import sys
from unittest.mock import MagicMock

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
pytest.importorskip("networkx")
go = pytest.importorskip("plotly.graph_objects")

import dashboards.streamlit_dashboard as mod  # noqa: E402


@pytest.fixture
def api():
    return mod.DashboardAPI(base_url="http://test")


def resp(status=200, json_data=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else []
    return r


class TestDashboardAPI:
    def test_get_articles_by_topic(self, api, monkeypatch):
        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resp(200, [{"id": "1"}]))
        assert api.get_articles_by_topic("ai") == [{"id": "1"}]

    def test_get_articles_non_200(self, api, monkeypatch):
        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resp(500))
        assert api.get_articles_by_topic("ai") == []

    def test_get_articles_exception(self, api, monkeypatch):
        def boom(*a, **k):
            raise RuntimeError("net down")
        monkeypatch.setattr(mod.requests, "get", boom)
        assert api.get_articles_by_topic("ai") == []

    def test_get_breaking_news(self, api, monkeypatch):
        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resp(200, [{"e": 1}]))
        assert isinstance(api.get_breaking_news(), list)

    def test_get_entities(self, api, monkeypatch):
        monkeypatch.setattr(mod.requests, "get", lambda *a, **k: resp(200, [{"id": "e1"}]))
        assert isinstance(api.get_entities(), list)


class TestCharts:
    def test_news_trends_empty(self):
        assert isinstance(mod.create_news_trends_chart([]), go.Figure)

    def test_news_trends(self):
        arts = [{"published_date": "2026-01-01", "category": "Tech", "title": "t"},
                {"published_date": "2026-01-02", "category": "Tech", "title": "t2"}]
        assert isinstance(mod.create_news_trends_chart(arts), go.Figure)

    def test_event_clusters_empty(self):
        assert isinstance(mod.create_event_clusters_chart([]), go.Figure)

    def test_event_clusters(self):
        events = [{
            "cluster_name": "AI", "title": "x", "impact_score": 5.0,
            "trending_score": 3.0, "category": "Tech", "cluster_size": 4,
            "velocity_score": 1.0, "sentiment_score": 0.2, "event_type": "announcement",
        }]
        assert isinstance(mod.create_event_clusters_chart(events), go.Figure)

    def test_entity_network_empty(self):
        assert isinstance(mod.create_entity_network_graph([], {}), go.Figure)
