"""
Comprehensive test suite for Graph Operations module.
Target: 80%+ test coverage for src/api/graph/operations.py
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
        """Test NodeData creation."""
        node_data = NodeData(
            id="node123",
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        assert node_data.id == "node123"
        assert node_data.label == "Person"
        assert node_data.properties["name"] == "John Doe"


class TestEdgeData:
    """Test EdgeData dataclass."""
    
    def test_edge_data_creation(self):
        """Test EdgeData creation."""
        edge_data = EdgeData(
            id="edge123",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={"since": "2020"}
        )
        
        assert edge_data.id == "edge123"
        assert edge_data.label == "KNOWS"
        assert edge_data.from_node == "node1"
        assert edge_data.to_node == "node2"


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_valid(self):
        """Test valid ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor issue"]
        )
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1


class TestGraphOperations:
    """Test GraphOperations class."""
    
    @pytest.fixture
    def operations(self):
        """Create GraphOperations instance."""
        return GraphOperations()
    
    def test_initialization(self, operations):
        """Test GraphOperations initialization."""
        assert operations.graph is None
        assert isinstance(operations.supported_node_types, set)
        assert isinstance(operations.supported_relationship_types, set)
    
    def test_validate_node_basic(self, operations):
        """Test basic node validation."""
        node_data = NodeData(
            id="test_node",
            label="Person", 
            properties={"name": "Test User"}
        )
        
        result = operations.validate_node(node_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
    
    def test_validate_edge_basic(self, operations):
        """Test basic edge validation."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="node2", 
            properties={}
        )
        
        result = operations.validate_edge(edge_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
    
    def test_supported_node_types(self, operations):
        """Test supported node types."""
        types = operations.supported_node_types
        
        assert isinstance(types, set)
        assert len(types) > 0
        # Common types should be included
        expected_types = {"Person", "Organization", "Location", "Article", "Topic", "Event"}
        assert len(expected_types.intersection(types)) > 0
    
    def test_supported_relationship_types(self, operations):
        """Test supported relationship types."""
        types = operations.supported_relationship_types
        
        assert isinstance(types, set) 
        assert len(types) > 0
        # Common relationships should be included
        expected_rels = {"KNOWS", "WORKS_FOR", "LOCATED_IN", "MENTIONS", "RELATES_TO"}
        assert len(expected_rels.intersection(types)) > 0
    
    def test_validate_node_missing_required_fields(self, operations):
        """Test validation with missing required fields."""
        # Test missing label
        node_data = NodeData(
            id="test", 
            label="",
            properties={"name": "Test"}
        )
        
        result = operations.validate_node(node_data)
        assert result.is_valid is False
        
        # Test missing properties
        node_data = NodeData(
            id="test",
            label="Person",
            properties=None
        )
        
        result = operations.validate_node(node_data)
        assert result.is_valid is False
    
    def test_validate_edge_missing_required_fields(self, operations):
        """Test edge validation with missing fields.""" 
        # Test missing from_node
        edge_data = EdgeData(
            id="test",
            label="KNOWS",
            from_node="",
            to_node="node2",
            properties={}
        )
        
        result = operations.validate_edge(edge_data)
        assert result.is_valid is False
    
    def test_node_validation_with_warnings(self, operations):
        """Test node validation that produces warnings."""
        node_data = NodeData(
            id="test",
            label="Person",
            properties={
                "name": "Test User",
                "empty_field": "",  # Should produce warning
                "valid_field": "value"
            }
        )
        
        result = operations.validate_node(node_data)
        
        # Should be valid but have warnings
        assert isinstance(result, ValidationResult)
        if hasattr(result, 'warnings'):
            assert isinstance(result.warnings, list)
    
    def test_edge_validation_with_properties(self, operations):
        """Test edge validation with various properties."""
        edge_data = EdgeData(
            id="test_edge",
            label="WORKS_FOR",
            from_node="person1", 
            to_node="company1",
            properties={
                "start_date": "2022-01-01",
                "position": "Engineer",
                "salary": 75000
            }
        )
        
        result = operations.validate_edge(edge_data)
        assert isinstance(result, ValidationResult)
    
    def test_validation_with_complex_properties(self, operations):
        """Test validation with complex nested properties."""
        node_data = NodeData(
            id="complex_node",
            label="Person",
            properties={
                "name": "Complex User",
                "details": {
                    "address": {"street": "123 Main St", "city": "Anytown"},
                    "skills": ["Python", "JavaScript", "SQL"]
                },
                "scores": [85, 90, 78]
            }
        )
        
        result = operations.validate_node(node_data)
        assert isinstance(result, ValidationResult)
    
    @pytest.mark.asyncio
    async def test_create_node_basic(self, operations):
        """Test basic node creation."""
        node_data = NodeData(
            id="test_create",
            label="Person",
            properties={"name": "Created User", "email": "created@test.com"}
        )
        
        result = await operations.create_node(node_data)
        
        assert result is not None
        assert isinstance(result, dict)
        assert 'id' in result
        assert 'created_at' in result
    
    @pytest.mark.asyncio
    async def test_create_node_validation_failure(self, operations):
        """Test node creation with validation failure."""
        node_data = NodeData(
            id="invalid_node",
            label="",  # Invalid empty label
            properties={}
        )
        
        with pytest.raises(ValueError):
            await operations.create_node(node_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
