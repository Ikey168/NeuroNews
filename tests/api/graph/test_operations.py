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
    def test_validate_node_empty_property_values(self, graph_operations):
        """Test node validation with empty property values."""
        node_data = NodeData(
            label="Person",
            properties={
                "name": "John Doe",
                "empty_prop": "",
                "none_prop": None  # This should cause validation error
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        # Should fail due to None value (unsupported data type)
        assert result.is_valid is False
        assert len(result.errors) > 0
        assert len(result.warnings) >= 1  # Should warn about empty values
    
    def test_validate_node_unsupported_property_types(self, graph_operations):s and edge cases
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.operations import (
    GraphOperations,
    NodeData,
    EdgeData,
    ValidationResult
)


class TestNodeData:
    """Test NodeData dataclass."""
    
    def test_node_data_creation(self):
        """Test NodeData creation with all fields."""
        now = datetime.now()
        node = NodeData(
            id="test_id",
            label="Person",
            properties={"name": "John Doe", "age": 30},
            created_at=now,
            updated_at=now
        )
        
        assert node.id == "test_id"
        assert node.label == "Person"
        assert node.properties == {"name": "John Doe", "age": 30}
        assert node.created_at == now
        assert node.updated_at == now
    
    def test_node_data_minimal(self):
        """Test NodeData with minimal required fields."""
        node = NodeData(
            id=None,
            label="Person",
            properties={"name": "Jane Doe"}
        )
        
        assert node.id is None
        assert node.label == "Person"
        assert node.properties == {"name": "Jane Doe"}
        assert node.created_at is None
        assert node.updated_at is None


class TestEdgeData:
    """Test EdgeData dataclass."""
    
    def test_edge_data_creation(self):
        """Test EdgeData creation with all fields."""
        now = datetime.now()
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties={"since": "2020"},
            created_at=now,
            updated_at=now
        )
        
        assert edge.id == "edge_id"
        assert edge.label == "KNOWS"
        assert edge.from_node == "person1"
        assert edge.to_node == "person2"
        assert edge.properties == {"since": "2020"}
        assert edge.created_at == now
        assert edge.updated_at == now
    
    def test_edge_data_minimal(self):
        """Test EdgeData with minimal required fields."""
        edge = EdgeData(
            id=None,
            label="WORKS_FOR",
            from_node="person1",
            to_node="org1",
            properties={}
        )
        
        assert edge.id is None
        assert edge.label == "WORKS_FOR"
        assert edge.from_node == "person1"
        assert edge.to_node == "org1"
        assert edge.properties == {}


class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_valid(self):
        """Test ValidationResult for valid case."""
        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor warning"]
        )
        
        assert result.is_valid is True
        assert result.errors == []
        assert result.warnings == ["Minor warning"]
    
    def test_validation_result_invalid(self):
        """Test ValidationResult for invalid case."""
        result = ValidationResult(
            is_valid=False,
            errors=["Required field missing"],
            warnings=[]
        )
        
        assert result.is_valid is False
        assert result.errors == ["Required field missing"]
        assert result.warnings == []


class TestGraphOperations:
    """Test GraphOperations class."""
    
    @pytest.fixture
    def graph_ops(self):
        """Create GraphOperations instance."""
        return GraphOperations()
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Create mock graph builder."""
        return Mock()
    
    def test_initialization(self, graph_ops):
        """Test GraphOperations initialization."""
        assert graph_ops.graph is None
        assert 'Person' in graph_ops.supported_node_types
        assert 'Organization' in graph_ops.supported_node_types
        assert 'MENTIONS' in graph_ops.supported_relationship_types
        assert 'WORKS_FOR' in graph_ops.supported_relationship_types
    
    def test_initialization_with_builder(self):
        """Test GraphOperations initialization with graph builder."""
        mock_builder = Mock()
        ops = GraphOperations(graph_builder=mock_builder)
        assert ops.graph == mock_builder
    
    # ============ NODE VALIDATION TESTS ============
    
    def test_validate_node_valid(self, graph_ops):
        """Test validation of valid node."""
        node = NodeData(
            id="test_id",
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        # Might have warnings about property types
    
    def test_validate_node_missing_label(self, graph_ops):
        """Test validation of node with missing label."""
        node = NodeData(
            id="test_id",
            label="",
            properties={"name": "John Doe"}
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is False
        assert "Node label is required" in result.errors
    
    def test_validate_node_missing_properties(self, graph_ops):
        """Test validation of node with missing properties."""
        node = NodeData(
            id="test_id",
            label="Person",
            properties={}
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is False
        assert "Node properties cannot be empty" in result.errors
    
    def test_validate_node_no_properties_dict(self, graph_ops):
        """Test validation of node with None properties."""
        node = NodeData(
            id="test_id",
            label="Person",
            properties=None
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is False
        assert "Node properties cannot be empty" in result.errors
    
    def test_validate_node_unsupported_label(self, graph_ops):
        """Test validation of node with unsupported label."""
        node = NodeData(
            id="test_id",
            label="UnsupportedType",
            properties={"name": "Test"}
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is True  # Just warning, not error
        assert "Unsupported node type: UnsupportedType" in result.warnings
    
    def test_validate_node_missing_name_property(self, graph_ops):
        """Test validation of node missing name property."""
        node = NodeData(
            id="test_id",
            label="Person",
            properties={"age": 30}
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is False
        assert "Node must have a 'name' property" in result.errors
    
    def test_validate_node_reserved_properties(self, graph_ops):
        """Test validation of node with reserved property names."""
        node = NodeData(
            id="test_id",
            label="Person",
            properties={
                "name": "John",
                "id": "override_id",
                "label": "override_label",
                "created_at": "override_time"
            }
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is True
        assert any("Property 'id' is reserved" in w for w in result.warnings)
        assert any("Property 'label' is reserved" in w for w in result.warnings)
        assert any("Property 'created_at' is reserved" in w for w in result.warnings)
    
    def test_validate_node_empty_property_values(self, graph_ops):
        """Test validation of node with empty property values."""
        node = NodeData(
            id="test_id",
            label="Person",
            properties={
                "name": "John",
                "empty_prop": "",
                "none_prop": None
            }
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is True
        assert any("Property 'empty_prop' has empty value" in w for w in result.warnings)
        assert any("Property 'none_prop' has empty value" in w for w in result.warnings)
    
    def test_validate_node_unsupported_property_types(self, graph_ops):
        """Test validation of node with unsupported property types."""
        class CustomClass:
            pass
        
        node = NodeData(
            id="test_id",
            label="Person",
            properties={
                "name": "John",
                "valid_str": "string",
                "valid_int": 42,
                "valid_float": 3.14,
                "valid_bool": True,
                "valid_list": [1, 2, 3],
                "valid_dict": {"key": "value"},
                "invalid_object": CustomClass(),
                "invalid_set": {1, 2, 3}
            }
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is False
        error_messages = " ".join(result.errors)
        assert "invalid_object" in error_messages
        assert "invalid_set" in error_messages
        assert "unsupported data type" in error_messages
    
    # ============ EDGE VALIDATION TESTS ============
    
    def test_validate_edge_valid(self, graph_ops):
        """Test validation of valid edge."""
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties={"since": "2020"}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_edge_missing_label(self, graph_ops):
        """Test validation of edge with missing label."""
        edge = EdgeData(
            id="edge_id",
            label="",
            from_node="person1",
            to_node="person2",
            properties={}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is False
        assert "Edge label is required" in result.errors
    
    def test_validate_edge_missing_from_node(self, graph_ops):
        """Test validation of edge with missing from_node."""
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="",
            to_node="person2",
            properties={}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is False
        assert "From node is required" in result.errors
    
    def test_validate_edge_missing_to_node(self, graph_ops):
        """Test validation of edge with missing to_node."""
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="",
            properties={}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is False
        assert "To node is required" in result.errors
    
    def test_validate_edge_self_reference(self, graph_ops):
        """Test validation of self-referencing edge."""
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="person1",
            properties={}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is True  # Just warning
        assert "Self-referencing edge detected" in result.warnings
    
    def test_validate_edge_unsupported_relationship(self, graph_ops):
        """Test validation of edge with unsupported relationship type."""
        edge = EdgeData(
            id="edge_id",
            label="CUSTOM_RELATION",
            from_node="person1",
            to_node="person2",
            properties={}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is True  # Just warning
        assert "Unsupported relationship type: CUSTOM_RELATION" in result.warnings
    
    def test_validate_edge_unsupported_property_types(self, graph_ops):
        """Test validation of edge with unsupported property types."""
        class CustomClass:
            pass
        
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties={
                "valid_prop": "string",
                "invalid_prop": CustomClass()
            }
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is False
        assert any("invalid_prop" in error for error in result.errors)
        assert any("unsupported data type" in error for error in result.errors)
    
    def test_validate_edge_empty_properties(self, graph_ops):
        """Test validation of edge with empty properties."""
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties={}
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_edge_none_properties(self, graph_ops):
        """Test validation of edge with None properties."""
        edge = EdgeData(
            id="edge_id",
            label="KNOWS",
            from_node="person1",
            to_node="person2",
            properties=None
        )
        
        result = graph_ops.validate_edge(edge)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    # ============ COMPREHENSIVE EDGE CASES ============
    
    def test_all_supported_node_types(self, graph_ops):
        """Test validation with all supported node types."""
        supported_types = ['Person', 'Organization', 'Location', 'Event', 'Article', 'Topic']
        
        for node_type in supported_types:
            node = NodeData(
                id=f"test_{node_type.lower()}",
                label=node_type,
                properties={"name": f"Test {node_type}"}
            )
            
            result = graph_ops.validate_node(node)
            assert result.is_valid is True, f"Node type {node_type} should be valid"
    
    def test_all_supported_relationship_types(self, graph_ops):
        """Test validation with all supported relationship types."""
        supported_rels = [
            'MENTIONS', 'LOCATED_IN', 'WORKS_FOR', 'PARTICIPATED_IN',
            'RELATES_TO', 'FOLLOWS', 'CONTAINS', 'REFERENCES'
        ]
        
        for rel_type in supported_rels:
            edge = EdgeData(
                id=f"test_{rel_type.lower()}",
                label=rel_type,
                from_node="node1",
                to_node="node2",
                properties={}
            )
            
            result = graph_ops.validate_edge(edge)
            assert result.is_valid is True, f"Relationship type {rel_type} should be valid"
    
    def test_complex_property_validation(self, graph_ops):
        """Test validation with complex nested properties."""
        node = NodeData(
            id="complex_node",
            label="Person",
            properties={
                "name": "Complex Person",
                "nested_dict": {
                    "address": {"street": "123 Main St", "city": "Anytown"},
                    "contacts": [{"type": "email", "value": "test@example.com"}]
                },
                "list_of_values": [1, "two", 3.0, True],
                "mixed_types": {"int": 42, "str": "hello", "float": 3.14, "bool": False}
            }
        )
        
        result = graph_ops.validate_node(node)
        
        assert result.is_valid is True
        # Should not have errors for valid nested structures


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
