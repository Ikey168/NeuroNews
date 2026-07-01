"""Coverage tests for src/dashboards/visualization_components.py.

Real tests: exercise the plotly/pandas/networkx figure builders with concrete
inputs and assert on the resulting Figure structure (trace count, trace data,
title text, node/edge coordinates) rather than merely checking isinstance.

The one Streamlit-dependent helper (create_metric_cards) is tested by patching
the streamlit module functions and asserting the metric calls it makes.
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
pytest.importorskip("pandas")
pytest.importorskip("networkx")
go = pytest.importorskip("plotly.graph_objects")

import dashboards.visualization_components as mod  # noqa: E402
from dashboards.visualization_components import (  # noqa: E402
    EventVisualization,
    NetworkVisualization,
    NewsVisualization,
    create_metric_cards,
)


# ---------------------------------------------------------------------------
# Fixtures / data builders
# ---------------------------------------------------------------------------
def articles_with_category():
    return [
        {"published_date": "2026-01-01T10:00:00", "category": "Tech", "title": "AI news one"},
        {"published_date": "2026-01-01T14:00:00", "category": "Tech", "title": "AI news two"},
        {"published_date": "2026-01-02T09:00:00", "category": "Sports", "title": "Game report"},
    ]


def articles_no_category():
    return [
        {"published_date": "2026-01-01T10:00:00", "title": "one"},
        {"published_date": "2026-01-02T10:00:00", "title": "two"},
    ]


def sentiment_articles():
    return [
        {"published_date": "2026-01-01T10:00:00", "sentiment_score": 0.8},
        {"published_date": "2026-01-01T11:00:00", "sentiment_score": 0.4},
        {"published_date": "2026-01-02T10:00:00", "sentiment_score": -0.3},
    ]


def entities():
    # NOTE: create_entity_network / create_hierarchy_tree call
    #   G.add_node(id, label=..., type=..., **entity)
    # so an entity dict that itself contains a "type" or "label" key raises
    # TypeError (duplicate kwarg). We therefore describe the entity type via a
    # non-colliding key ("entity_kind") in fixtures used by those builders; the
    # node "type" attribute is then taken from the explicit default ("unknown").
    return [
        {"id": "n1", "name": "Alice", "entity_kind": "PERSON"},
        {"id": "n2", "name": "Acme", "entity_kind": "ORG"},
        {"id": "n3", "name": "Paris", "entity_kind": "GPE"},
    ]


def relationships():
    return {
        "n1": {"relationships": [{"target": "n2", "type": "works_at", "weight": 3}]},
        "n2": {"relationships": [{"target": "n3", "type": "located_in", "weight": 1}]},
    }


def events_full():
    return [
        {
            "trending_score": 5.0,
            "impact_score": 7.0,
            "cluster_size": 4,
            "event_type": "announcement",
            "cluster_name": "AI",
            "category": "Tech",
            "first_article_date": "2026-01-01T10:00:00",
        },
        {
            "trending_score": 2.0,
            "impact_score": 3.0,
            "cluster_size": 2,
            "event_type": "research",
            "cluster_name": "Sports",
            "category": "Sports",
            "first_article_date": "2026-01-02T10:00:00",
        },
    ]


# ---------------------------------------------------------------------------
# NewsVisualization.create_timeline_chart
# ---------------------------------------------------------------------------
class TestTimelineChart:
    def test_empty_returns_empty_figure(self):
        fig = NewsVisualization.create_timeline_chart([])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_missing_published_date_returns_empty(self):
        fig = NewsVisualization.create_timeline_chart([{"title": "x"}])
        assert len(fig.data) == 0

    def test_all_dates_unparseable_returns_empty(self):
        fig = NewsVisualization.create_timeline_chart(
            [{"published_date": "not-a-date", "title": "x"}]
        )
        assert len(fig.data) == 0

    def test_with_category_creates_lines_per_category(self):
        fig = NewsVisualization.create_timeline_chart(
            articles_with_category(), title="My Timeline"
        )
        assert fig.layout.title.text == "My Timeline"
        # px.line with color=category yields one trace per distinct category
        assert len(fig.data) == 2
        assert fig.layout.height == mod.VIZ_CONFIG["chart_defaults"]["height"]
        assert fig.layout.xaxis.title.text == "Date"
        assert fig.layout.yaxis.title.text == "Article Count"

    def test_without_category_single_line(self):
        fig = NewsVisualization.create_timeline_chart(articles_no_category())
        assert len(fig.data) == 1
        # two distinct dates -> two points on the single line
        assert len(fig.data[0].x) == 2


# ---------------------------------------------------------------------------
# NewsVisualization.create_sentiment_heatmap
# ---------------------------------------------------------------------------
class TestSentimentHeatmap:
    def test_empty_returns_empty(self):
        assert len(NewsVisualization.create_sentiment_heatmap([]).data) == 0

    def test_missing_required_columns_returns_empty(self):
        fig = NewsVisualization.create_sentiment_heatmap(
            [{"published_date": "2026-01-01"}]  # no sentiment_score
        )
        assert len(fig.data) == 0

    def test_unparseable_dates_returns_empty(self):
        fig = NewsVisualization.create_sentiment_heatmap(
            [{"published_date": "bad", "sentiment_score": 0.1}]
        )
        assert len(fig.data) == 0

    def test_builds_heatmap_trace(self):
        fig = NewsVisualization.create_sentiment_heatmap(sentiment_articles())
        assert len(fig.data) == 1
        assert isinstance(fig.data[0], go.Heatmap)
        assert fig.data[0].z is not None
        assert "Sentiment Heatmap" in fig.layout.title.text


# ---------------------------------------------------------------------------
# NewsVisualization.create_word_frequency_chart
# ---------------------------------------------------------------------------
class TestWordFrequency:
    def test_empty_returns_empty(self):
        assert len(NewsVisualization.create_word_frequency_chart([]).data) == 0

    def test_no_extractable_words_returns_empty(self):
        # only short words (<=2 chars) which are filtered out
        fig = NewsVisualization.create_word_frequency_chart(
            [{"title": "a an to"}]
        )
        assert len(fig.data) == 0

    def test_uses_keywords_list(self):
        arts = [
            {"keywords": ["python", "coding"]},
            {"keywords": ["python", "data"]},
        ]
        fig = NewsVisualization.create_word_frequency_chart(arts, top_n=5)
        assert len(fig.data) == 1
        # "python" appears twice -> highest frequency
        freqs = list(fig.data[0].x)
        assert max(freqs) == 2
        assert "Top 5" in fig.layout.title.text

    def test_keywords_scalar_string_wrapped(self):
        fig = NewsVisualization.create_word_frequency_chart(
            [{"keywords": "singleword"}]
        )
        assert len(fig.data) == 1
        assert "singleword" in list(fig.data[0].y)

    def test_falls_back_to_topics(self):
        fig = NewsVisualization.create_word_frequency_chart(
            [{"topics": ["economy", "markets"]}]
        )
        assert "economy" in list(fig.data[0].y)

    def test_topics_scalar_string(self):
        fig = NewsVisualization.create_word_frequency_chart(
            [{"topics": "inflation"}]
        )
        assert "inflation" in list(fig.data[0].y)

    def test_falls_back_to_title_words(self):
        fig = NewsVisualization.create_word_frequency_chart(
            [{"title": "Quantum Computing Breakthrough"}]
        )
        ys = list(fig.data[0].y)
        assert "quantum" in ys
        assert "computing" in ys

    def test_top_n_limits_results(self):
        arts = [{"keywords": [f"word{i}" for i in range(30)]}]
        fig = NewsVisualization.create_word_frequency_chart(arts, top_n=5)
        assert len(fig.data[0].y) == 5


# ---------------------------------------------------------------------------
# NetworkVisualization.create_entity_network
# ---------------------------------------------------------------------------
class TestEntityNetwork:
    def test_empty_entities_returns_empty(self):
        assert len(NetworkVisualization.create_entity_network([], {}).data) == 0

    def test_builds_edge_and_node_traces(self):
        fig = NetworkVisualization.create_entity_network(entities(), relationships())
        # edge_trace + node_trace
        assert len(fig.data) == 2
        edge_trace, node_trace = fig.data
        assert node_trace.mode == "markers"
        # 3 nodes -> 3 node points
        assert len(node_trace.x) == 3
        assert "3 entities" in fig.layout.title.text
        assert "2 relationships" in fig.layout.title.text

    def test_circular_layout(self):
        fig = NetworkVisualization.create_entity_network(
            entities(), relationships(), layout_type="circular"
        )
        assert len(fig.data) == 2
        assert "Circular" in fig.layout.annotations[0].text

    def test_random_layout_default_branch(self):
        fig = NetworkVisualization.create_entity_network(
            entities(), relationships(), layout_type="random"
        )
        assert len(fig.data) == 2

    def test_entities_without_relationships_still_render_nodes(self):
        fig = NetworkVisualization.create_entity_network(entities(), {})
        node_trace = fig.data[1]
        assert len(node_trace.x) == 3
        assert "0 relationships" in fig.layout.title.text

    def test_node_color_defaults_to_unknown_fallback(self):
        # entities without a "type" key -> node "type" attribute defaults to
        # "unknown" -> fallback color from the config color scheme.
        fig = NetworkVisualization.create_entity_network(entities(), {})
        node_trace = fig.data[1]
        colors = list(node_trace.marker.color)
        assert all(c == "#FFEAA7" for c in colors)

    def test_node_size_scales_with_degree(self):
        fig = NetworkVisualization.create_entity_network(entities(), relationships())
        node_trace = fig.data[1]
        sizes = list(node_trace.marker.size)
        # sizes clamped into [10, 30]
        assert all(10 <= s <= 30 for s in sizes)

    def test_entity_with_type_key_raises_due_to_source_kwarg_collision(self):
        # Documents a real source-level limitation: G.add_node(..., type=...,
        # **entity) collides when the entity carries its own "type" key.
        bad_entities = [{"id": "x1", "name": "N", "type": "PERSON"}]
        with pytest.raises(TypeError):
            NetworkVisualization.create_entity_network(bad_entities, {})


# ---------------------------------------------------------------------------
# NetworkVisualization.create_hierarchy_tree
# ---------------------------------------------------------------------------
class TestHierarchyTree:
    def test_empty_returns_empty(self):
        assert len(NetworkVisualization.create_hierarchy_tree([], {}).data) == 0

    def test_no_relationships_returns_empty(self):
        assert len(NetworkVisualization.create_hierarchy_tree(entities(), {}).data) == 0

    def test_builds_tree_with_hierarchy_edges(self):
        rels = {
            "n1": {"relationships": [{"target": "n2", "type": "parent"}]},
            "n2": {"relationships": [{"target": "n3", "type": "contains"}]},
        }
        # graphviz (pygraphviz) is usually absent -> spring_layout fallback runs
        fig = NetworkVisualization.create_hierarchy_tree(entities(), rels)
        assert len(fig.data) == 2
        assert fig.layout.title.text == "Entity Hierarchy"
        node_trace = fig.data[1]
        assert len(node_trace.x) == 3

    def test_non_hierarchy_relationship_types_excluded(self):
        # relationship type not in [parent, contains, owns] -> no edges added,
        # nodes still present
        rels = {"n1": {"relationships": [{"target": "n2", "type": "mentions"}]}}
        fig = NetworkVisualization.create_hierarchy_tree(entities(), rels)
        assert len(fig.data) == 2
        # no hierarchy edges -> edge trace has no coordinates
        assert len(fig.data[0].x) == 0


# ---------------------------------------------------------------------------
# EventVisualization.create_event_impact_chart
# ---------------------------------------------------------------------------
class TestEventImpactChart:
    def test_empty_returns_empty(self):
        assert len(EventVisualization.create_event_impact_chart([]).data) == 0

    def test_missing_required_columns_returns_empty(self):
        fig = EventVisualization.create_event_impact_chart([{"trending_score": 1}])
        assert len(fig.data) == 0

    def test_builds_scatter_with_types(self):
        fig = EventVisualization.create_event_impact_chart(events_full())
        # px.scatter with color=event_type -> one trace per event_type
        assert len(fig.data) == 2
        assert "Impact vs Trending" in fig.layout.title.text
        assert fig.layout.height == mod.VIZ_CONFIG["chart_defaults"]["height"]

    def test_defaults_added_for_missing_optional_columns(self):
        events = [
            {"trending_score": 1.0, "impact_score": 2.0, "cluster_size": 3},
            {"trending_score": 4.0, "impact_score": 5.0, "cluster_size": 6},
        ]
        fig = EventVisualization.create_event_impact_chart(events)
        # event_type defaulted to "Unknown" -> single trace
        assert len(fig.data) == 1


# ---------------------------------------------------------------------------
# EventVisualization.create_event_timeline
# ---------------------------------------------------------------------------
class TestEventTimeline:
    def test_empty_returns_empty(self):
        assert len(EventVisualization.create_event_timeline([]).data) == 0

    def test_no_date_column_returns_empty(self):
        fig = EventVisualization.create_event_timeline(
            [{"impact_score": 1, "cluster_size": 1, "event_type": "x", "cluster_name": "c"}]
        )
        assert len(fig.data) == 0

    def test_all_dates_unparseable_returns_empty(self):
        fig = EventVisualization.create_event_timeline(
            [
                {
                    "first_article_date": "bad-date",
                    "impact_score": 1,
                    "cluster_size": 1,
                    "event_type": "x",
                    "cluster_name": "c",
                }
            ]
        )
        assert len(fig.data) == 0

    def test_builds_timeline(self):
        fig = EventVisualization.create_event_timeline(events_full())
        assert len(fig.data) >= 1
        assert fig.layout.title.text == "Event Timeline"
        assert fig.layout.yaxis.title.text == "Impact Score"


# ---------------------------------------------------------------------------
# EventVisualization.create_category_distribution
# ---------------------------------------------------------------------------
class TestCategoryDistribution:
    def test_empty_returns_empty(self):
        assert len(EventVisualization.create_category_distribution([]).data) == 0

    def test_uses_category_column(self):
        fig = EventVisualization.create_category_distribution(events_full())
        assert len(fig.data) == 1
        assert isinstance(fig.data[0], go.Pie)
        # two distinct categories
        assert set(fig.data[0].labels) == {"Tech", "Sports"}

    def test_falls_back_to_event_type(self):
        events = [
            {"event_type": "announcement", "trending_score": 1, "impact_score": 1,
             "cluster_size": 1},
            {"event_type": "announcement", "trending_score": 1, "impact_score": 1,
             "cluster_size": 1},
            {"event_type": "research", "trending_score": 1, "impact_score": 1,
             "cluster_size": 1},
        ]
        fig = EventVisualization.create_category_distribution(events)
        assert set(fig.data[0].labels) == {"announcement", "research"}
        # counts: announcement=2, research=1
        values = dict(zip(fig.data[0].labels, fig.data[0].values))
        assert values["announcement"] == 2
        assert values["research"] == 1


# ---------------------------------------------------------------------------
# create_metric_cards (Streamlit-dependent)
# ---------------------------------------------------------------------------
class TestMetricCards:
    def test_calls_st_metric_with_data(self):
        col_ctx = MagicMock()
        col_ctx.__enter__ = MagicMock(return_value=col_ctx)
        col_ctx.__exit__ = MagicMock(return_value=False)
        cols = [col_ctx, col_ctx, col_ctx, col_ctx]

        data = {
            "total_articles": 100,
            "articles_delta": 5,
            "active_events": 10,
            "events_delta": -2,
            "total_entities": 250,
            "entities_delta": 3,
            "avg_sentiment": 0.4567,
            "sentiment_delta": -0.12,
        }

        with patch.object(mod.st, "columns", return_value=cols) as mock_cols, patch.object(
            mod.st, "metric"
        ) as mock_metric:
            create_metric_cards(data)

        mock_cols.assert_called_once_with(4)
        assert mock_metric.call_count == 4
        labels = [c.kwargs["label"] for c in mock_metric.call_args_list]
        assert labels == ["Total Articles", "Active Events", "Entities", "Avg Sentiment"]

        values = {c.kwargs["label"]: c.kwargs["value"] for c in mock_metric.call_args_list}
        assert values["Total Articles"] == 100
        assert values["Active Events"] == 10
        assert values["Entities"] == 250
        # avg_sentiment formatted to 2 dp
        assert values["Avg Sentiment"] == "0.46"

    def test_uses_defaults_for_missing_keys(self):
        col_ctx = MagicMock()
        col_ctx.__enter__ = MagicMock(return_value=col_ctx)
        col_ctx.__exit__ = MagicMock(return_value=False)
        cols = [col_ctx, col_ctx, col_ctx, col_ctx]

        with patch.object(mod.st, "columns", return_value=cols), patch.object(
            mod.st, "metric"
        ) as mock_metric:
            create_metric_cards({})

        values = {c.kwargs["label"]: c.kwargs["value"] for c in mock_metric.call_args_list}
        assert values["Total Articles"] == 0
        assert values["Avg Sentiment"] == "0.00"
