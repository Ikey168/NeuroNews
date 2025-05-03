"""
Tests for knowledge graph API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from src.api.routes.graph_routes import router, graph

# Setup test client
client = TestClient(router)

@pytest.fixture
def mock_graph():
    """Create a mock graph with test data."""
    mock = Mock()
    
    # Mock vertex values
    org_values = {
        'orgName': ['Google'],
        'orgType': ['Technology'],
        'founded': [datetime(1998, 9, 4)]
    }
    
    person_values = {
        'name': ['Sundar Pichai'],
        'title': ['CEO']
    }
    
    event_values = {
        'eventName': ['AI Summit 2025'],
        'startDate': [datetime(2025, 6, 1)],
        'location': ['San Francisco'],
        'keywords': ['AI Regulation']
    }
    
    article_values = {
        'headline': ['Google Announces New AI Policy'],
        'publishDate': [datetime.now()],
        'url': ['https://example.com/article']
    }
    
    # Mock related entities query results
    mock.V().hasLabel().has().aggregate().out().dedup().project()\
        .by().by().by().by().toList.return_value = [
            {
                'entity': org_values,
                'type': 'Organization',
                'relationships': {'PARTNERS_WITH': 3, 'HOSTED': 2},
                'articles': [article_values]
            }
        ]
    
    # Mock timeline query results
    mock.V().hasLabel().has().project()\
        .by().by().by().by().by().by().toList.return_value = [
            {
                'event': 'AI Summit 2025',
                'date': datetime(2025, 6, 1),
                'location': 'San Francisco',
                'organizations': [org_values],
                'people': [person_values],
                'articles': [article_values]
            }
        ]
    
    return mock

@pytest.fixture
def mock_graph_builder(mock_graph):
    """Create a mock GraphBuilder instance."""
    with patch('src.api.routes.graph_routes.graph') as mock_builder:
        mock_builder.g = mock_graph
        yield mock_builder

def test_get_related_entities(mock_graph_builder):
    """Test getting related entities for an organization."""
    response = client.get("/graph/related_entities", params={
        "entity": "Google",
        "entity_type": "Organization",
        "max_depth": 2
    })
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["entity"] == "Google"
    assert len(data["related_entities"]) > 0
    
    # Verify entity structure
    entity = data["related_entities"][0]
    assert "name" in entity
    assert "type" in entity
    assert "relationship_counts" in entity
    assert "mentioned_in" in entity

def test_get_related_entities_validation():
    """Test input validation for related entities endpoint."""
    # Test missing required parameter
    response = client.get("/graph/related_entities")
    assert response.status_code == 422
    
    # Test invalid max_depth
    response = client.get("/graph/related_entities", params={
        "entity": "Google",
        "max_depth": 0
    })
    assert response.status_code == 422

def test_get_event_timeline(mock_graph_builder):
    """Test getting event timeline for a topic."""
    response = client.get("/graph/event_timeline", params={
        "topic": "AI Regulation",
        "start_date": "2024-01-01T00:00:00Z"
    })
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["topic"] == "AI Regulation"
    assert "events" in data
    
    # Verify event structure
    if data["events"]:
        event = data["events"][0]
        assert "name" in event
        assert "date" in event
        assert "location" in event
        assert "organizations" in event
        assert "people" in event
        assert "coverage" in event

def test_event_timeline_date_filtering(mock_graph_builder):
    """Test date filtering in event timeline."""
    # Test with both start and end dates
    response = client.get("/graph/event_timeline", params={
        "topic": "AI Regulation",
        "start_date": "2024-01-01T00:00:00Z",
        "end_date": "2025-12-31T23:59:59Z"
    })
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify dates are within range
    for event in data["events"]:
        event_date = datetime.fromisoformat(event["date"].replace('Z', '+00:00'))
        assert event_date >= datetime(2024, 1, 1)
        assert event_date <= datetime(2025, 12, 31, 23, 59, 59)

def test_event_timeline_validation():
    """Test input validation for event timeline endpoint."""
    # Test missing required parameter
    response = client.get("/graph/event_timeline")
    assert response.status_code == 422
    
    # Test invalid date format
    response = client.get("/graph/event_timeline", params={
        "topic": "AI Regulation",
        "start_date": "invalid-date"
    })
    assert response.status_code == 422

@pytest.mark.parametrize("endpoint", [
    "/graph/related_entities",
    "/graph/event_timeline"
])
def test_error_handling(endpoint, mock_graph_builder):
    """Test error handling in graph endpoints."""
    # Mock graph error
    mock_graph_builder.g.V.side_effect = Exception("Database error")
    
    # Test endpoints with minimal valid parameters
    params = {
        "/graph/related_entities": {"entity": "Google"},
        "/graph/event_timeline": {"topic": "AI Regulation"}
    }
    
    response = client.get(endpoint, params=params[endpoint])
    assert response.status_code == 500
    assert "detail" in response.json()

def test_health_check(mock_graph_builder):
    """Test health check endpoint."""
    # Test successful health check
    response = client.get("/graph/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    
    # Test failed health check
    mock_graph_builder.g.V.side_effect = Exception("Connection failed")
    response = client.get("/graph/health")
    assert response.status_code == 503