from unittest.mock import MagicMock

import pytest

from src.knowledge_graph.examples.graph_queries import GraphQueries


@pytest.fixture
def mock_graph():
    mock = MagicMock()
    g = MagicMock()
    mock.g = g

    # Configure mock traversals
    mock_traversal = MagicMock()
    mock_traversal.toList.return_value = []
    mock_traversal.project.return_value = mock_traversal
    mock_traversal.by.return_value = mock_traversal
    mock_traversal.hasLabel.return_value = mock_traversal
    mock_traversal.has.return_value = mock_traversal
    mock_traversal.values.return_value = mock_traversal
    mock_traversal.select.return_value = mock_traversal
    mock_traversal.where.return_value = mock_traversal
    mock_traversal.out.return_value = mock_traversal
    mock_traversal.in_.return_value = mock_traversal
    mock_traversal.fold.return_value = mock_traversal
    mock_traversal.count.return_value = mock_traversal
    mock_traversal.is_.return_value = mock_traversal

    g.V.return_value = mock_traversal

    return mock


@pytest.fixture
def graph_queries(mock_graph):
    return GraphQueries(mock_graph)


def test_org_mentions_query(graph_queries):
    """Test query for organization mentions."""
    mock_result = [{"org": "Org1", "mentions": 5}, {"org": "Org2", "mentions": 3}]
    graph_queries.g.V().hasLabel().project().by().by().toList.return_value = mock_result

    results = graph_queries.gremlin_queries()["org_mentions"]
    assert isinstance(results, list)
    assert len(results) > 0
    assert "org" in results[0]
    assert "mentions" in results[0]


def test_org_network_query(graph_queries):
    """Test query for organization collaboration network."""
    mock_result = [{"org1": "Org1", "org2": "Org2"}, {"org1": "Org2", "org2": "Org3"}]
    graph_queries.g.V().hasLabel().as_().out().as_().select().by().toList.return_value = (
        mock_result
    )

    results = graph_queries.gremlin_queries()["org_network"]
    assert isinstance(results, list)
    assert len(results) > 0
    assert "org1" in results[0]
    assert "org2" in results[0]


def test_sparql_query_structure(graph_queries):
    """Test the structure of SPARQL queries."""
    sparql_queries = graph_queries.sparql_queries()

    for query_name, query in sparql_queries.items():
        assert isinstance(query, str)
        assert "SELECT" in query.upper() or "CONSTRUCT" in query.upper()
        assert "WHERE" in query.upper()


def test_temporal_query_elements(graph_queries):
    """Test temporal aspects of queries."""
    mock_result = [
        {"event": "Event1", "date": "2025-01-01", "impact": "high"},
        {"event": "Event2", "date": "2025-01-02", "impact": "medium"},
    ]
    graph_queries.g.V().hasLabel().has().project().by().by().by().toList.return_value = (
        mock_result
    )

    gremlin_results = graph_queries.gremlin_queries()
    recent_events = gremlin_results["recent_events"]
    assert isinstance(recent_events, list)
    assert len(recent_events) > 0
    assert "date" in recent_events[0]


def test_sentiment_analysis_queries(graph_queries):
    """Test sentiment analysis related queries."""
    mock_result = [
        {"article": "Article1", "sentiment": 0.8, "date": "2025-01-01"},
        {"article": "Article2", "sentiment": 0.6, "date": "2025-01-02"},
    ]
    graph_queries.g.V().hasLabel().project().by().by().by().toList.return_value = (
        mock_result
    )

    results = graph_queries.gremlin_queries()["sentiment_scores"]
    assert isinstance(results, list)
    assert len(results) > 0
    assert "sentiment" in results[0]


def test_relationship_path_queries(graph_queries):
    """Test queries that traverse relationship paths."""
    mock_result = [
        {"source": "Org1", "target": "Org2", "event": "Event1", "date": "2025-01-01"},
        {"source": "Org2", "target": "Org3", "event": "Event2", "date": "2025-01-02"},
    ]
    graph_queries.g.V().hasLabel().as_().out().as_().in_().where().project().by().by().by().by().toList.return_value = (
        mock_result
    )

    results = graph_queries.gremlin_queries()["related_org_mentions"]
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(key in results[0] for key in ["source", "target", "event", "date"])


def test_query_error_handling(graph_queries):
    """Test error handling in queries."""
    with pytest.raises(KeyError):
        graph_queries.gremlin_queries()["non_existent_query"]


def test_complex_traversals(graph_queries):
    """Test more complex traversal patterns."""
    mock_result = [
        {"event": "Event1", "participants": ["Org1", "Org2"], "date": "2025-01-01"},
        {"event": "Event2", "participants": ["Org2", "Org3"], "date": "2025-01-02"},
    ]
    graph_queries.g.V().hasLabel().as_().where().project().by().by().by().toList.return_value = (
        mock_result
    )

    results = graph_queries.gremlin_queries()["common_events"]
    assert isinstance(results, list)
    assert len(results) > 0
    assert all(key in results[0] for key in ["event", "participants", "date"])
