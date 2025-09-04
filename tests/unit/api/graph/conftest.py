"""
Test configuration for Graph API tests.

This file ensures proper imports and test setup for the graph API modules.
"""

import sys
import os

# Add the src directory to the Python path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../src'))

# Import pytest fixtures that can be shared across tests
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_graph_builder():
    """Create a mock graph builder for testing."""
    mock_graph = Mock()
    mock_graph.g = Mock()
    return mock_graph

@pytest.fixture
def sample_node_data():
    """Sample node data for testing."""
    return {
        "id": "test_node_1",
        "label": "Person", 
        "properties": {
            "name": "John Doe",
            "age": 30,
            "email": "john@example.com"
        }
    }

@pytest.fixture  
def sample_edge_data():
    """Sample edge data for testing."""
    return {
        "id": "test_edge_1",
        "label": "KNOWS",
        "from_node": "person_1",
        "to_node": "person_2", 
        "properties": {
            "since": "2020-01-01",
            "strength": 0.8
        }
    }

@pytest.fixture
def sample_graph_data():
    """Sample graph data for import/export testing."""
    return {
        "nodes": [
            {
                "id": "node_1",
                "label": "Person",
                "properties": {"name": "Alice", "age": 28}
            },
            {
                "id": "node_2", 
                "label": "Person",
                "properties": {"name": "Bob", "age": 32}
            }
        ],
        "edges": [
            {
                "id": "edge_1",
                "label": "FRIENDS",
                "from_node": "node_1",
                "to_node": "node_2",
                "properties": {"since": "2019"}
            }
        ]
    }
