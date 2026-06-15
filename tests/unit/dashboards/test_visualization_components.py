"""Tests for src/dashboards/visualization_components.py (plotly figure builders)."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("plotly")
pytest.importorskip("pandas")
pytest.importorskip("networkx")
go = pytest.importorskip("plotly.graph_objects")

from dashboards.visualization_components import (  # noqa: E402
    EventVisualization,
    NetworkVisualization,
    NewsVisualization,
)


def articles():
    return [
        {"published_date": "2026-01-01", "category": "Tech", "title": "AI advances",
         "content": "machine learning ai models neural networks", "sentiment_score": 0.8,
         "keywords": ["ai", "ml"], "source": "bbc"},
        {"published_date": "2026-01-02", "category": "Tech", "title": "More AI news",
         "content": "deep learning ai research", "sentiment_score": -0.2,
         "keywords": ["ai", "research"], "source": "cnn"},
    ]


def events():
    return [
        {"published_date": "2026-01-01", "type": "announcement", "title": "Event A",
         "sentiment_score": 0.5, "cluster_name": "AI", "date": "2026-01-01",
         "category": "Tech", "impact_score": 7.0, "trending_score": 5.0},
        {"published_date": "2026-01-02", "type": "research", "title": "Event B",
         "sentiment_score": -0.3, "cluster_name": "Sports", "date": "2026-01-02",
         "category": "Sports", "impact_score": 3.0, "trending_score": 2.0},
    ]


class TestNewsVisualization:
    def test_timeline_empty(self):
        assert isinstance(NewsVisualization.create_timeline_chart([]), go.Figure)

    def test_timeline(self):
        assert isinstance(NewsVisualization.create_timeline_chart(articles()), go.Figure)

    def test_sentiment_heatmap(self):
        assert isinstance(NewsVisualization.create_sentiment_heatmap(articles()), go.Figure)
        assert isinstance(NewsVisualization.create_sentiment_heatmap([]), go.Figure)

    def test_word_frequency(self):
        assert isinstance(
            NewsVisualization.create_word_frequency_chart(articles(), top_n=5), go.Figure
        )
        assert isinstance(NewsVisualization.create_word_frequency_chart([]), go.Figure)


class TestEventVisualization:
    def test_event_impact(self):
        assert isinstance(EventVisualization.create_event_impact_chart(events()), go.Figure)
        assert isinstance(EventVisualization.create_event_impact_chart([]), go.Figure)

    def test_event_timeline(self):
        assert isinstance(EventVisualization.create_event_timeline(events()), go.Figure)
        assert isinstance(EventVisualization.create_event_timeline([]), go.Figure)

    def test_category_distribution(self):
        assert isinstance(EventVisualization.create_category_distribution(events()), go.Figure)
        assert isinstance(EventVisualization.create_category_distribution([]), go.Figure)


class TestNetworkVisualization:
    def test_entity_network_empty(self):
        assert isinstance(NetworkVisualization.create_entity_network([], {}), go.Figure)

    def test_hierarchy_tree_empty(self):
        assert isinstance(NetworkVisualization.create_hierarchy_tree([], {}), go.Figure)
