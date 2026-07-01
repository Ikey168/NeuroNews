"""Coverage tests for src/dashboards/streamlit_dashboard.py.

Real tests: DashboardAPI wraps requests.get - requests is patched (where it is
looked up in the module) and request URL construction + response/status/error
handling is asserted. The chart builders (networkx/plotly/pandas) are exercised
with concrete data and asserted on figure structure. main() is driven with all
st.* functions and the API client mocked, asserting the control flow (which
data-fetching + rendering calls fire) for both the "data present" and "no data"
branches.
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

import dashboards.streamlit_dashboard as mod  # noqa: E402
from dashboards.streamlit_dashboard import (  # noqa: E402
    DashboardAPI,
    create_entity_network_graph,
    create_event_clusters_chart,
    create_news_trends_chart,
)


def resp(status=200, json_data=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data if json_data is not None else []
    return r


@pytest.fixture
def api():
    return DashboardAPI(base_url="http://test")


# ---------------------------------------------------------------------------
# DashboardAPI
# ---------------------------------------------------------------------------
class TestDashboardAPIInit:
    def test_default_base_url(self):
        a = DashboardAPI()
        assert a.base_url == mod.API_BASE_URL

    def test_custom_base_url(self):
        a = DashboardAPI(base_url="http://x:1")
        assert a.base_url == "http://x:1"


class TestGetArticlesByTopic:
    def test_success_builds_url(self, api):
        captured = {}

        def fake_get(url, *a, **k):
            captured["url"] = url
            return resp(200, [{"id": "1"}])

        with patch.object(mod.requests, "get", fake_get):
            out = api.get_articles_by_topic("ai", limit=25)
        assert out == [{"id": "1"}]
        assert captured["url"] == "http://test/news/articles/topic/ai?limit=25"

    def test_non_200_returns_empty(self, api):
        with patch.object(mod.requests, "get", lambda *a, **k: resp(500)):
            assert api.get_articles_by_topic("ai") == []

    def test_exception_returns_empty_and_shows_error(self, api):
        def boom(*a, **k):
            raise RuntimeError("net down")

        with patch.object(mod.requests, "get", boom), patch.object(
            mod.st, "error"
        ) as mock_err:
            assert api.get_articles_by_topic("ai") == []
        mock_err.assert_called_once()


class TestGetBreakingNews:
    def test_success_builds_url(self, api):
        captured = {}

        def fake_get(url, *a, **k):
            captured["url"] = url
            return resp(200, [{"e": 1}])

        with patch.object(mod.requests, "get", fake_get):
            out = api.get_breaking_news(hours=12, limit=7)
        assert out == [{"e": 1}]
        assert captured["url"] == "http://test/api/v1/breaking-news?hours=12&limit=7"

    def test_non_200_returns_empty(self, api):
        with patch.object(mod.requests, "get", lambda *a, **k: resp(404)):
            assert api.get_breaking_news() == []

    def test_exception_returns_empty(self, api):
        with patch.object(
            mod.requests, "get", MagicMock(side_effect=RuntimeError("x"))
        ), patch.object(mod.st, "error"):
            assert api.get_breaking_news() == []


class TestGetEntities:
    def test_success_builds_url(self, api):
        captured = {}

        def fake_get(url, *a, **k):
            captured["url"] = url
            return resp(200, [{"id": "e1"}])

        with patch.object(mod.requests, "get", fake_get):
            out = api.get_entities(limit=30)
        assert out == [{"id": "e1"}]
        assert captured["url"] == "http://test/graph/entities?limit=30"

    def test_non_200_returns_empty(self, api):
        with patch.object(mod.requests, "get", lambda *a, **k: resp(503)):
            assert api.get_entities() == []

    def test_exception_returns_empty(self, api):
        with patch.object(
            mod.requests, "get", MagicMock(side_effect=RuntimeError("x"))
        ), patch.object(mod.st, "error"):
            assert api.get_entities() == []


class TestGetEntityRelationships:
    def test_success_builds_url(self, api):
        captured = {}

        def fake_get(url, *a, **k):
            captured["url"] = url
            return resp(200, {"relationships": [{"target": "n2"}]})

        with patch.object(mod.requests, "get", fake_get):
            out = api.get_entity_relationships("n1")
        assert out == {"relationships": [{"target": "n2"}]}
        assert captured["url"] == "http://test/graph/entity/n1/relationships"

    def test_non_200_returns_empty_dict(self, api):
        with patch.object(mod.requests, "get", lambda *a, **k: resp(500)):
            assert api.get_entity_relationships("n1") == {}

    def test_exception_returns_empty_dict(self, api):
        with patch.object(
            mod.requests, "get", MagicMock(side_effect=RuntimeError("x"))
        ), patch.object(mod.st, "error"):
            assert api.get_entity_relationships("n1") == {}


# ---------------------------------------------------------------------------
# get_api_client (cache_resource)
# ---------------------------------------------------------------------------
def test_get_api_client_returns_dashboard_api():
    client = mod.get_api_client()
    assert isinstance(client, DashboardAPI)


# ---------------------------------------------------------------------------
# create_entity_network_graph
# ---------------------------------------------------------------------------
class TestEntityNetworkGraph:
    def test_empty_still_returns_figure_with_two_traces(self):
        fig = create_entity_network_graph([], {})
        assert isinstance(fig, go.Figure)
        # edge_trace + node_trace always constructed
        assert len(fig.data) == 2

    def test_nodes_and_edges_built(self):
        entities = [
            {"id": "n1", "name": "Alice", "type": "PERSON"},
            {"id": "n2", "name": "Acme", "type": "ORG"},
        ]
        relationships = {"n1": {"relationships": [{"target": "n2", "type": "works_at"}]}}
        fig = create_entity_network_graph(entities, relationships)
        edge_trace, node_trace = fig.data
        # two nodes -> two node marker points
        assert len(node_trace.x) == 2
        assert fig.layout.title.text == "Entity Relationship Network"

    def test_node_color_by_type(self):
        entities = [
            {"id": "n1", "name": "Alice", "type": "PERSON"},
            {"id": "n2", "name": "Acme", "type": "ORG"},
            {"id": "n3", "name": "Paris", "type": "GPE"},
            {"id": "n4", "name": "Mystery", "type": "SOMETHING"},
        ]
        fig = create_entity_network_graph(entities, {})
        colors = list(fig.data[1].marker.color)
        assert "red" in colors  # PERSON
        assert "blue" in colors  # ORG
        assert "green" in colors  # GPE
        assert "gray" in colors  # unknown/other -> fallback

    def test_relationship_without_target_skipped(self):
        entities = [{"id": "n1", "name": "A", "type": "PERSON"}]
        # relationship missing "target" -> no edge added, node still present
        relationships = {"n1": {"relationships": [{"type": "orphan"}]}}
        fig = create_entity_network_graph(entities, relationships)
        assert len(fig.data[1].x) == 1


# ---------------------------------------------------------------------------
# create_news_trends_chart
# ---------------------------------------------------------------------------
class TestNewsTrendsChart:
    def test_empty_returns_empty(self):
        fig = create_news_trends_chart([])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_no_published_date_returns_empty(self):
        fig = create_news_trends_chart([{"title": "x"}])
        assert len(fig.data) == 0

    def test_builds_line_chart(self):
        arts = [
            {"published_date": "2026-01-01T10:00:00", "title": "a"},
            {"published_date": "2026-01-01T15:00:00", "title": "b"},
            {"published_date": "2026-01-02T10:00:00", "title": "c"},
        ]
        fig = create_news_trends_chart(arts)
        assert len(fig.data) == 1
        # two distinct dates -> two aggregated points
        assert len(fig.data[0].x) == 2
        assert fig.layout.title.text == "News Articles Over Time"
        assert fig.layout.xaxis.title.text == "Date"


# ---------------------------------------------------------------------------
# create_event_clusters_chart
# ---------------------------------------------------------------------------
class TestEventClustersChart:
    def test_empty_returns_empty(self):
        fig = create_event_clusters_chart([])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_builds_scatter(self):
        events = [
            {
                "cluster_name": "AI", "impact_score": 5.0, "trending_score": 3.0,
                "category": "Tech", "cluster_size": 4, "velocity_score": 1.0,
                "event_type": "announcement",
            },
            {
                "cluster_name": "Sports", "impact_score": 2.0, "trending_score": 1.0,
                "category": "Sports", "cluster_size": 2, "velocity_score": 0.5,
                "event_type": "research",
            },
        ]
        fig = create_event_clusters_chart(events)
        # px.scatter colored by event_type -> one trace per event_type
        assert len(fig.data) == 2
        assert "Impact vs Trending" in fig.layout.title.text
        assert fig.layout.xaxis.title.text == "Trending Score"


# ---------------------------------------------------------------------------
# main() - drive both data-present and no-data branches
# ---------------------------------------------------------------------------
def _make_streamlit_mock():
    """Build a MagicMock replacement for the streamlit module used by main()."""
    st = MagicMock()

    # st.columns(...) must yield context-manager-capable column objects
    def make_col():
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=col)
        col.__exit__ = MagicMock(return_value=False)
        return col

    st.columns.side_effect = lambda spec: [make_col() for _ in range(
        spec if isinstance(spec, int) else len(spec)
    )]

    # st.expander(...) returns a context manager
    exp = MagicMock()
    exp.__enter__ = MagicMock(return_value=exp)
    exp.__exit__ = MagicMock(return_value=False)
    st.expander.return_value = exp

    # sidebar interactions
    st.sidebar.text_input.return_value = ""
    st.sidebar.slider.side_effect = [24, 50]  # hours_back, article_limit
    st.sidebar.button.return_value = False  # refresh not pressed

    return st


class TestMain:
    def test_main_with_full_data(self):
        st = _make_streamlit_mock()
        st.sidebar.text_input.return_value = ""  # default topic branch

        fake_api = MagicMock()
        fake_api.get_articles_by_topic.return_value = [
            {"title": "Art 1", "source": "bbc", "published_date": "2026-01-01T10:00:00",
             "summary": "summary text"},
            {"title": "Art 2", "source": "cnn", "published_date": "2026-01-02T10:00:00",
             "summary": "more text"},
        ]
        fake_api.get_entities.return_value = [
            {"id": "n1", "name": "Alice", "type": "PERSON"},
            {"id": "n2", "name": "Acme", "type": "ORG"},
        ]
        fake_api.get_entity_relationships.return_value = {
            "relationships": [{"target": "n2", "type": "works_at"}]
        }
        fake_api.get_breaking_news.return_value = [
            {
                "cluster_name": "AI", "impact_score": 5.0, "trending_score": 3.0,
                "category": "Tech", "cluster_size": 4, "velocity_score": 1.0,
                "event_type": "announcement", "event_duration_hours": 12.0,
            },
        ]

        with patch.object(mod, "st", st), patch.object(
            mod, "get_api_client", return_value=fake_api
        ):
            mod.main()

        # default-topic branch used "technology"
        fake_api.get_articles_by_topic.assert_called_once()
        assert fake_api.get_articles_by_topic.call_args.args[0] == "technology"
        # entity relationships fetched for the returned entities
        assert fake_api.get_entity_relationships.called
        fake_api.get_breaking_news.assert_called_once()
        # charts rendered
        assert st.plotly_chart.call_count >= 3
        assert st.title.called

    def test_main_with_topic_filter(self):
        st = _make_streamlit_mock()
        st.sidebar.text_input.return_value = "climate"  # explicit topic branch

        fake_api = MagicMock()
        fake_api.get_articles_by_topic.return_value = [
            {"title": "Art", "source": "s", "published_date": "2026-01-01", "summary": "x"},
        ]
        fake_api.get_entities.return_value = []
        fake_api.get_breaking_news.return_value = []

        with patch.object(mod, "st", st), patch.object(
            mod, "get_api_client", return_value=fake_api
        ):
            mod.main()

        assert fake_api.get_articles_by_topic.call_args.args[0] == "climate"
        # no entities and no events -> warnings shown
        assert st.warning.call_count >= 2

    def test_main_no_data_shows_warnings(self):
        st = _make_streamlit_mock()
        st.sidebar.text_input.return_value = ""

        fake_api = MagicMock()
        fake_api.get_articles_by_topic.return_value = []
        fake_api.get_entities.return_value = []
        fake_api.get_breaking_news.return_value = []

        with patch.object(mod, "st", st), patch.object(
            mod, "get_api_client", return_value=fake_api
        ):
            mod.main()

        # articles, entities, events all empty -> three warning branches
        assert st.warning.call_count == 3

    def test_main_refresh_button_clears_cache(self):
        st = _make_streamlit_mock()
        st.sidebar.button.return_value = True  # refresh pressed

        fake_api = MagicMock()
        fake_api.get_articles_by_topic.return_value = []
        fake_api.get_entities.return_value = []
        fake_api.get_breaking_news.return_value = []

        with patch.object(mod, "st", st), patch.object(
            mod, "get_api_client", return_value=fake_api
        ):
            mod.main()

        st.cache_data.clear.assert_called_once()
        st.rerun.assert_called_once()
