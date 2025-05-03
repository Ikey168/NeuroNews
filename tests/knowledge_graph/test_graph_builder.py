import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from src.knowledge_graph.graph_builder import GraphBuilder

@pytest.fixture
def mock_graph():
    """Create a mock graph with traversal stub."""
    with patch('src.knowledge_graph.graph_builder.Graph') as mock:
        # Create mock traversal
        mock_traversal = Mock()
        mock.return_value.traversal.return_value.withRemote.return_value = mock_traversal
        
        # Create mock vertex/edge for successful operations
        mock_vertex = Mock()
        mock_vertex.id = "test-id"
        mock_traversal.addV.return_value.property.return_value.next.return_value = mock_vertex
        
        mock_edge = Mock()
        mock_edge.id = "edge-id"
        mock_traversal.V.return_value.addE.return_value.to.return_value.next.return_value = mock_edge
        
        return mock_traversal

@pytest.fixture
def graph_builder(mock_graph):
    """Create a GraphBuilder instance with mocked Neptune connection."""
    return GraphBuilder("dummy-endpoint")

def test_add_person(graph_builder):
    """Test adding a person vertex."""
    person_props = {
        "name": "John Doe",
        "title": "CEO",
        "age": 45,
        "nationality": "US",
        "occupation": ["Executive", "Board Member"],
        "lastUpdated": datetime.now()
    }
    
    vertex_id = graph_builder.add_person(person_props)
    assert vertex_id == "test-id"
    
    # Verify proper vertex creation calls
    graph_builder.g.addV.assert_called_once_with('Person')
    graph_builder.g.addV.return_value.property.assert_called_with('name', 'John Doe')

def test_add_organization(graph_builder):
    """Test adding an organization vertex."""
    org_props = {
        "orgName": "Tech Corp",
        "orgType": "Corporation",
        "industry": ["Technology", "Software"],
        "founded": datetime(2000, 1, 1),
        "employeeCount": 1000
    }
    
    vertex_id = graph_builder.add_organization(org_props)
    assert vertex_id == "test-id"
    
    graph_builder.g.addV.assert_called_once_with('Organization')
    graph_builder.g.addV.return_value.property.assert_called_with('orgName', 'Tech Corp')

def test_add_event(graph_builder):
    """Test adding an event vertex."""
    event_props = {
        "eventName": "Tech Conference 2025",
        "eventType": "Conference",
        "startDate": datetime(2025, 6, 1),
        "endDate": datetime(2025, 6, 3),
        "location": "San Francisco",
        "keywords": ["technology", "innovation"]
    }
    
    vertex_id = graph_builder.add_event(event_props)
    assert vertex_id == "test-id"
    
    graph_builder.g.addV.assert_called_once_with('Event')
    graph_builder.g.addV.return_value.property.assert_called_with('eventName', 'Tech Conference 2025')

def test_add_article(graph_builder):
    """Test adding an article vertex."""
    article_props = {
        "headline": "New Technology Breakthrough",
        "url": "https://example.com/article",
        "publishDate": datetime(2025, 5, 1),
        "author": ["Jane Smith"],
        "source": "Tech News"
    }
    
    vertex_id = graph_builder.add_article(article_props)
    assert vertex_id == "test-id"
    
    graph_builder.g.addV.assert_called_once_with('Article')
    graph_builder.g.addV.return_value.property.assert_called_with('headline', 'New Technology Breakthrough')

def test_add_relationship(graph_builder):
    """Test adding a relationship between vertices."""
    from_id = "person-1"
    to_id = "org-1"
    label = "WORKS_FOR"
    props = {
        "role": "CEO",
        "startDate": datetime(2020, 1, 1)
    }
    
    edge_id = graph_builder.add_relationship(from_id, to_id, label, props)
    assert edge_id == "edge-id"
    
    graph_builder.g.V.assert_called_once_with(from_id)
    graph_builder.g.V.return_value.addE.assert_called_once_with(label)

def test_batch_insert(graph_builder):
    """Test batch insertion of entities and relationships."""
    entities = [
        {
            "type": "Person",
            "properties": {
                "name": "John Doe",
                "title": "CEO"
            }
        },
        {
            "type": "Organization",
            "properties": {
                "orgName": "Tech Corp",
                "industry": ["Technology"]
            }
        }
    ]
    
    relationships = [
        {
            "from_id": "person-1",
            "to_id": "org-1",
            "label": "WORKS_FOR",
            "properties": {
                "role": "CEO"
            }
        }
    ]
    
    entity_ids, rel_ids = graph_builder.batch_insert(entities, relationships)
    assert len(entity_ids) == 2
    assert len(rel_ids) == 1

def test_property_cleaning(graph_builder):
    """Test property cleaning and validation."""
    props = {
        "name": "John Doe",
        "age": 45,
        "skills": ["Python", "AWS"],
        "startDate": datetime(2020, 1, 1),
        "metadata": {"key": "value"},
        "nullField": None,
        "complexObject": object()
    }
    
    cleaned = graph_builder._clean_properties(props)
    
    assert cleaned["name"] == "John Doe"
    assert cleaned["age"] == 45
    assert "nullField" not in cleaned
    assert "complexObject" not in cleaned
    assert isinstance(cleaned["skills"], str)
    assert isinstance(cleaned["metadata"], str)
    assert isinstance(cleaned["startDate"], str)

def test_connection_error():
    """Test handling of connection errors."""
    with patch('src.knowledge_graph.graph_builder.DriverRemoteConnection') as mock_conn:
        mock_conn.side_effect = Exception("Connection failed")
        
        with pytest.raises(Exception) as exc:
            GraphBuilder("bad-endpoint")
        
        assert "Connection failed" in str(exc.value)

def test_get_or_create_person(graph_builder):
    """Test get_or_create_person functionality."""
    # Mock existing person lookup
    mock_person = Mock()
    mock_person.id = "existing-id"
    graph_builder.g.V.return_value.hasLabel.return_value.has.return_value.next.return_value = mock_person
    
    # Test getting existing person
    person_id = graph_builder.get_or_create_person("John Doe")
    assert person_id == "existing-id"
    
    # Test creating new person when not found
    graph_builder.g.V.return_value.hasLabel.return_value.has.return_value.next.side_effect = StopIteration
    new_id = graph_builder.get_or_create_person("Jane Smith", {"title": "CTO"})
    assert new_id == "test-id"