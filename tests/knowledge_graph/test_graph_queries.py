import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from src.knowledge_graph.examples.graph_queries import GraphQueries

@pytest.fixture
def mock_graph():
    """Create a mock graph with test data."""
    mock = Mock()
    
    # Mock vertices for organizations
    org1 = Mock(id="org1")
    org1.valueMap.return_value = {"orgName": ["TechCorp"]}
    
    org2 = Mock(id="org2")
    org2.valueMap.return_value = {"orgName": ["AI Research Inc"]}
    
    # Mock vertices for people
    person1 = Mock(id="person1")
    person1.valueMap.return_value = {"name": ["John Doe"]}
    
    person2 = Mock(id="person2")
    person2.valueMap.return_value = {"name": ["Jane Smith"]}
    
    # Mock vertices for events
    event = Mock(id="event1")
    event.valueMap.return_value = {
        "eventName": ["Tech Summit 2025"],
        "startDate": [datetime.now()]
    }
    
    # Mock vertex for article
    article = Mock(id="article1")
    article.valueMap.return_value = {
        "headline": ["Tech Companies Collaborate"],
        "sentiment": [0.8]
    }
    
    # Set up mock traversals
    mock.V().hasLabel.return_value.outE.return_value.has.return_value\
        .inV.return_value.valueMap.return_value.toList.return_value = [
            {"orgName": "TechCorp", "industry": ["Technology"]},
            {"orgName": "AI Research Inc", "industry": ["AI"]}
        ]
    
    mock.V().hasLabel.return_value.project.return_value\
        .by.return_value.by.return_value.by.return_value.toList.return_value = [
            {
                "org1": "TechCorp",
                "org2": "AI Research Inc",
                "relationship": "PARTNERS_WITH"
            }
        ]
    
    return mock

@pytest.fixture
def graph_queries(mock_graph):
    """Create GraphQueries instance with mock graph."""
    return GraphQueries(Mock(g=mock_graph))

def test_org_mentions_query(graph_queries):
    """Test query for organizations mentioned in articles."""
    results = graph_queries.gremlin_queries()['org_mentions']
    
    assert len(results) == 2
    assert results[0]['orgName'] == "TechCorp"
    assert results[1]['orgName'] == "AI Research Inc"

def test_org_network_query(graph_queries):
    """Test query for organization collaboration network."""
    results = graph_queries.gremlin_queries()['org_network']
    
    assert len(results) > 0
    assert results[0]['org1'] == "TechCorp"
    assert results[0]['org2'] == "AI Research Inc"
    assert results[0]['partnership_type'] == "PARTNERS_WITH"

def test_sparql_query_structure(graph_queries):
    """Test SPARQL query structure and syntax."""
    queries = graph_queries.sparql_queries()
    
    # Check organization events query
    org_events = queries['org_events']
    assert 'PREFIX' in org_events
    assert 'SELECT' in org_events
    assert 'WHERE' in org_events
    assert 'Organization' in org_events
    assert 'Event' in org_events
    
    # Check connected people query
    connected_people = queries['connected_people']
    assert 'MENTIONS_PERSON' in connected_people
    assert 'FILTER' in connected_people
    assert '!=' in connected_people

def test_temporal_query_elements(graph_queries):
    """Test temporal aspects of queries."""
    gremlin_results = graph_queries.gremlin_queries()
    sparql_queries = graph_queries.sparql_queries()
    
    # Check Gremlin temporal query
    recent_events = gremlin_results['recent_events']
    assert isinstance(recent_events, list)
    
    # Check SPARQL temporal query
    temporal = sparql_queries['temporal_analysis']
    assert 'startDate' in temporal
    assert 'xsd:date' in temporal
    assert 'ORDER BY' in temporal

def test_sentiment_analysis_queries(graph_queries):
    """Test sentiment analysis related queries."""
    gremlin_results = graph_queries.gremlin_queries()
    sparql_queries = graph_queries.sparql_queries()
    
    # Check Gremlin sentiment query
    org_mentions = gremlin_results['org_mentions']
    assert len(org_mentions) > 0
    
    # Check SPARQL sentiment query
    sentiment = sparql_queries['sentiment_patterns']
    assert 'sentiment' in sentiment
    assert 'positiveCount' in sentiment
    assert 'negativeCount' in sentiment

def test_relationship_path_queries(graph_queries):
    """Test queries that traverse relationship paths."""
    results = graph_queries.gremlin_queries()['related_org_mentions']
    
    assert isinstance(results, list)
    # Verify result structure
    if results:
        assert 'article' in results[0]
        assert 'org1' in results[0]
        assert 'org2' in results[0]
        assert 'relationship' in results[0]

def test_query_error_handling():
    """Test error handling in queries."""
    # Create a graph that raises an exception
    error_graph = Mock()
    error_graph.V.side_effect = Exception("Connection error")
    
    queries = GraphQueries(Mock(g=error_graph))
    
    with pytest.raises(Exception):
        queries.gremlin_queries()

def test_query_performance(graph_queries, benchmark):
    """Test query performance."""
    def run_queries():
        return graph_queries.gremlin_queries()
    
    result = benchmark(run_queries)
    assert result is not None

def test_complex_traversals(graph_queries):
    """Test more complex traversal patterns."""
    results = graph_queries.gremlin_queries()['common_events']
    
    # Verify the structure of common events results
    assert isinstance(results, list)
    if results:
        assert 'person1' in results[0]
        assert 'person2' in results[0]
        assert 'event' in results[0]