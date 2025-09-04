"""
Comprehensive test suite for Graph Operations module.
Target: 100% test coverage for src/api/graph/operations.py

This test suite covers:
- Node and edge creation/validation
- Graph operations and modifications
- Data structures and error handling
- All validation scenarios and edge cases
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.operations import (
    NodeData,
    EdgeData,
    ValidationResult,
    GraphOperations
)


class TestNodeData:
    """Test NodeData dataclass."""
    
    def test_node_data_creation(self):
        """Test NodeData creation with all fields."""
        node_data = NodeData(
            id="node123",
            label="Person",
            properties={
                "name": "John Doe",
                "age": 30,
                "email": "john@example.com"
            }
        )
        
        assert node_data.id == "node123"
        assert node_data.label == "Person"
        assert node_data.properties["name"] == "John Doe"
        assert node_data.properties["age"] == 30
    
    def test_node_data_minimal(self):
        """Test NodeData with minimal required fields."""
        node_data = NodeData(
            id=None,
            label="Person",
            properties={"name": "Jane"}
        )
        
        assert node_data.label == "Person"
        assert node_data.properties["name"] == "Jane"


class TestEdgeData:
    """Test EdgeData dataclass."""
    
    def test_edge_data_creation(self):
        """Test EdgeData creation with all fields."""
        edge_data = EdgeData(id=None, 
            id="edge123",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={
                "since": "2020-01-01",
                "strength": 0.8
            }
        )
        
        assert edge_data.id == "edge123"
        assert edge_data.label == "KNOWS"
        assert edge_data.from_node == "node1"
        assert edge_data.to_node == "node2"
        assert edge_data.properties["since"] == "2020-01-01"
    
    def test_edge_data_minimal(self):
        """Test EdgeData with minimal required fields."""
        edge_data = EdgeData(id=None, 
            label="WORKS_FOR",
            from_node="person1",
            to_node="org1",
            properties={}
        )
        
        assert edge_data.label == "WORKS_FOR"
        assert edge_data.from_node == "person1"
        assert edge_data.to_node == "org1"


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_valid(self):
        """Test ValidationResult for valid data."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor formatting issue"]
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1
    
    def test_validation_result_invalid(self):
        """Test ValidationResult for invalid data."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing required field"],
            warnings=[]
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 0


class TestGraphOperations:
    """Test GraphOperations class."""
    
    @pytest.fixture
    def graph_operations(self):
        """Create GraphOperations instance."""
        return GraphOperations()
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Create mock graph builder."""
        return Mock()
    
    def test_initialization(self, graph_operations):
        """Test GraphOperations initialization."""
        assert graph_operations.graph is None
        assert isinstance(graph_operations.supported_node_types, set)
        assert isinstance(graph_operations.supported_relationship_types, set)
    
    def test_initialization_with_builder(self):
        """Test GraphOperations initialization with graph builder."""
        mock_builder = Mock()
        operations = GraphOperations(graph_builder=mock_builder)
        assert operations.graph == mock_builder
    
    def test_validate_node_valid(self, graph_operations):
        """Test validation of a valid node."""
        node_data = NodeData(id=None, 
            label="Person",
            properties={
                "name": "John Doe",
                "age": 30
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_node_missing_label(self, graph_operations):
        """Test validation with missing label."""
        node_data = NodeData(id=None, 
            label="",
            properties={"name": "John"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert "label" in str(result.errors).lower()
    
    def test_validate_node_missing_properties(self, graph_operations):
        """Test validation with missing properties."""
        node_data = NodeData(id=None, 
            label="Person",
            properties=None
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_validate_node_unsupported_label(self, graph_operations):
        """Test validation with unsupported node label."""
        node_data = NodeData(id=None, 
            label="UnsupportedType",
            properties={"name": "Test"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        # Should still validate basic structure even if type is unsupported
        assert isinstance(result, ValidationResult)
    
    def test_validate_edge_valid(self, graph_operations):
        """Test validation of a valid edge."""
        edge_data = EdgeData(id=None, 
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties={"since": "2020"}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_edge_missing_label(self, graph_operations):
        """Test edge validation with missing label."""
        edge_data = EdgeData(id=None, 
            label="",
            from_node="node1",
            to_node="node2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_validate_edge_missing_from_node(self, graph_operations):
        """Test edge validation with missing from_node."""
        edge_data = EdgeData(id=None, 
            label="KNOWS",
            from_node="",
            to_node="node2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_validate_edge_missing_to_node(self, graph_operations):
        """Test edge validation with missing to_node."""
        edge_data = EdgeData(id=None, 
            label="KNOWS",
            from_node="node1",
            to_node="",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert len(result.errors) > 0
    
    def test_supported_node_types(self, graph_operations):
        """Test supported node types are properly defined."""
        node_types = graph_operations.supported_node_types
        
        assert isinstance(node_types, set)
        assert len(node_types) > 0
        # Should include common types
        common_types = {"Person", "Organization", "Location", "Article", "Topic", "Event"}
        assert len(common_types.intersection(node_types)) > 0
    
    def test_supported_relationship_types(self, graph_operations):
        """Test supported relationship types are properly defined."""
        rel_types = graph_operations.supported_relationship_types
        
        assert isinstance(rel_types, set)
        assert len(rel_types) > 0
        # Should include common relationships
        common_rels = {"KNOWS", "WORKS_FOR", "LOCATED_IN", "MENTIONS", "RELATES_TO"}
        assert len(common_rels.intersection(rel_types)) > 0
    
    def test_complex_validation_scenario(self, graph_operations):
        """Test complex validation with multiple checks."""
        # Valid node
        node = NodeData(id=None, 
            label="Person",
            properties={
                "name": "Alice Johnson",
                "age": 28,
                "email": "alice@example.com",
                "skills": ["Python", "Data Science"],
                "active": True
            }
        )
        
        result = graph_operations.validate_node(node)
        assert result.is_valid is True
        
        # Valid edge
        edge = EdgeData(id=None, 
            label="WORKS_FOR",
            from_node="person_alice",
            to_node="company_xyz",
            properties={
                "start_date": "2022-01-01",
                "position": "Data Scientist",
                "salary": 75000
            }
        )
        
        result = graph_operations.validate_edge(edge)
        assert result.is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
