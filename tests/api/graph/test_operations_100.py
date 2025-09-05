"""
Enhanced comprehensive test suite for Graph Operations module.
Target: 100% test coverage for src/api/graph/operations.py
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock

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
        assert node_data.created_at is None
        assert node_data.updated_at is None
    
    def test_node_data_with_timestamps(self):
        """Test NodeData with timestamps."""
        now = datetime.now()
        node_data = NodeData(
            id="node456",
            label="Company",
            properties={"name": "TechCorp"},
            created_at=now,
            updated_at=now
        )
        
        assert node_data.created_at == now
        assert node_data.updated_at == now
    
    def test_node_data_minimal(self):
        """Test NodeData with minimal required fields."""
        node_data = NodeData(
            id=None,
            label="Event",
            properties={}
        )
        
        assert node_data.id is None
        assert node_data.label == "Event"
        assert node_data.properties == {}


class TestEdgeData:
    """Test EdgeData dataclass."""
    
    def test_edge_data_creation(self):
        """Test EdgeData creation."""
        edge_data = EdgeData(
            id="edge123",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={"since": "2020", "strength": 0.8}
        )
        
        assert edge_data.id == "edge123"
        assert edge_data.label == "KNOWS"
        assert edge_data.from_node == "node1"
        assert edge_data.to_node == "node2"
        assert edge_data.properties["since"] == "2020"
        assert edge_data.properties["strength"] == 0.8
    
    def test_edge_data_with_timestamps(self):
        """Test EdgeData with timestamps."""
        now = datetime.now()
        edge_data = EdgeData(
            id="edge456",
            label="WORKS_FOR",
            from_node="person1",
            to_node="company1",
            properties={"position": "Engineer"},
            created_at=now,
            updated_at=now
        )
        
        assert edge_data.created_at == now
        assert edge_data.updated_at == now
    
    def test_edge_data_minimal(self):
        """Test EdgeData with minimal required fields."""
        edge_data = EdgeData(
            id=None,
            label="RELATES_TO",
            from_node="node1",
            to_node="node2",
            properties={}
        )
        
        assert edge_data.id is None
        assert edge_data.label == "RELATES_TO"
        assert edge_data.properties == {}


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
        assert result.warnings[0] == "Minor issue"
    
    def test_validation_result_invalid(self):
        """Test invalid ValidationResult."""
        result = ValidationResult(
            is_valid=False,
            errors=["Missing required field", "Invalid data type"],
            warnings=[]
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 0
    
    def test_validation_result_with_both(self):
        """Test ValidationResult with both errors and warnings."""
        result = ValidationResult(
            is_valid=False,
            errors=["Critical error"],
            warnings=["Warning message", "Another warning"]
        )
        
        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 2


class TestGraphOperations:
    """Test GraphOperations class."""
    
    @pytest.fixture
    def graph_operations(self):
        """Create GraphOperations instance."""
        return GraphOperations()
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Create mock graph builder."""
        mock_builder = Mock()
        mock_builder.g = Mock()
        return mock_builder
    
    @pytest.fixture
    def graph_operations_with_builder(self, mock_graph_builder):
        """Create GraphOperations instance with mock builder."""
        return GraphOperations(graph_builder=mock_graph_builder)
    
    def test_initialization_default(self, graph_operations):
        """Test GraphOperations default initialization."""
        assert graph_operations.graph is None
        assert isinstance(graph_operations.supported_node_types, set)
        assert isinstance(graph_operations.supported_relationship_types, set)
        
        # Check default supported types
        assert 'Person' in graph_operations.supported_node_types
        assert 'Organization' in graph_operations.supported_node_types
        assert 'Location' in graph_operations.supported_node_types
        assert 'MENTIONS' in graph_operations.supported_relationship_types
        assert 'WORKS_FOR' in graph_operations.supported_relationship_types
    
    def test_initialization_with_builder(self, mock_graph_builder):
        """Test GraphOperations initialization with graph builder."""
        operations = GraphOperations(graph_builder=mock_graph_builder)
        assert operations.graph == mock_graph_builder
    
    def test_validate_node_success(self, graph_operations):
        """Test successful node validation."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_node_missing_label(self, graph_operations):
        """Test node validation with missing label."""
        node_data = NodeData(
            id="test_node",
            label="",
            properties={"name": "Test"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert "Node label is required" in result.errors
    
    def test_validate_node_empty_properties(self, graph_operations):
        """Test node validation with empty properties."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties=None
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert "Node properties cannot be empty" in result.errors
    
    def test_validate_node_missing_name(self, graph_operations):
        """Test node validation with missing name property."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={"age": 30}  # Missing name
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert "Node must have a 'name' property" in result.errors
    
    def test_validate_node_unsupported_type(self, graph_operations):
        """Test node validation with unsupported node type."""
        node_data = NodeData(
            id="test_node",
            label="UnsupportedType",
            properties={"name": "Test"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is True  # Warning, not error
        assert any("Unsupported node type" in warning for warning in result.warnings)
    
    def test_validate_node_reserved_properties(self, graph_operations):
        """Test node validation with reserved property names."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={
                "name": "Test",
                "id": "reserved_id",
                "created_at": "reserved_timestamp"
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is True  # Warnings, not errors
        assert len(result.warnings) >= 2  # At least 2 warnings for reserved props
    
    def test_validate_node_empty_property_values(self, graph_operations):
        """Test node validation with empty property values."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={
                "name": "Test",
                "empty_field": "",
                "null_field": None
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is True
        assert len(result.warnings) >= 2  # Warnings for empty values
    
    def test_validate_node_invalid_data_types(self, graph_operations):
        """Test node validation with invalid data types."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={
                "name": "Test",
                "invalid_obj": object(),  # Unsupported type
                "valid_list": [1, 2, 3],
                "valid_dict": {"nested": "value"}
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert any("unsupported data type" in error for error in result.errors)
    
    def test_validate_edge_success(self, graph_operations):
        """Test successful edge validation."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={"since": "2020"}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_edge_missing_label(self, graph_operations):
        """Test edge validation with missing label."""
        edge_data = EdgeData(
            id="test_edge",
            label="",
            from_node="node1",
            to_node="node2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert "Edge label is required" in result.errors
    
    def test_validate_edge_missing_from_node(self, graph_operations):
        """Test edge validation with missing from_node."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="",
            to_node="node2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert "From node is required" in result.errors
    
    def test_validate_edge_missing_to_node(self, graph_operations):
        """Test edge validation with missing to_node."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert "To node is required" in result.errors
    
    def test_validate_edge_self_reference(self, graph_operations):
        """Test edge validation with self-referencing edge."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="node1",  # Same as from_node
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is True  # Warning, not error
        assert any("Self-referencing edge" in warning for warning in result.warnings)
    
    def test_validate_edge_unsupported_type(self, graph_operations):
        """Test edge validation with unsupported relationship type."""
        edge_data = EdgeData(
            id="test_edge",
            label="UNSUPPORTED_RELATIONSHIP",
            from_node="node1",
            to_node="node2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is True  # Warning, not error
        assert any("Unsupported relationship type" in warning for warning in result.warnings)
    
    def test_validate_edge_invalid_property_types(self, graph_operations):
        """Test edge validation with invalid property types."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={
                "valid_prop": "test",
                "invalid_prop": object()  # Unsupported type
            }
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert any("unsupported data type" in error for error in result.errors)
    
    @pytest.mark.asyncio
    async def test_create_node_mock_success(self, graph_operations):
        """Test successful node creation with mock implementation."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        result = await graph_operations.create_node(node_data)
        
        assert isinstance(result, dict)
        assert 'id' in result
        assert result['label'] == "Person"
        assert result['properties']['name'] == "John Doe"
        assert 'created_at' in result
        assert 'validation_warnings' in result
    
    @pytest.mark.asyncio
    async def test_create_node_validation_failure(self, graph_operations):
        """Test node creation with validation failure."""
        node_data = NodeData(
            id="test_node",
            label="",  # Missing label
            properties={"name": "John Doe"}
        )
        
        with pytest.raises(ValueError) as exc_info:
            await graph_operations.create_node(node_data)
        
        assert "Node validation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_node_with_graph_builder(self, graph_operations_with_builder):
        """Test node creation with actual graph builder."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={"name": "John Doe"}
        )
        
        # Mock the graph traversal
        mock_traversal = Mock()
        mock_next_result = Mock()
        mock_traversal.next = AsyncMock(return_value=[mock_next_result])
        
        # Chain the mocks
        graph_operations_with_builder.graph.g.addV.return_value = mock_traversal
        mock_traversal.property.return_value = mock_traversal
        
        result = await graph_operations_with_builder.create_node(node_data)
        
        assert isinstance(result, dict)
        assert 'id' in result
    
    @pytest.mark.asyncio
    async def test_create_edge_mock_success(self, graph_operations):
        """Test successful edge creation with mock implementation."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="node1",
            to_node="node2",
            properties={"since": "2020"}
        )
        
        result = await graph_operations.create_edge(edge_data)
        
        assert isinstance(result, dict)
        assert 'id' in result
        assert result['label'] == "KNOWS"
        assert result['from_node'] == "node1"
        assert result['to_node'] == "node2"
        assert 'created_at' in result
    
    @pytest.mark.asyncio
    async def test_create_edge_validation_failure(self, graph_operations):
        """Test edge creation with validation failure."""
        edge_data = EdgeData(
            id="test_edge",
            label="KNOWS",
            from_node="",  # Missing from_node
            to_node="node2",
            properties={}
        )
        
        with pytest.raises(ValueError) as exc_info:
            await graph_operations.create_edge(edge_data)
        
        assert "Edge validation failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_exception_handling_node_creation(self, graph_operations_with_builder):
        """Test exception handling in node creation."""
        node_data = NodeData(
            id="test_node",
            label="Person",
            properties={"name": "Test"}
        )
        
        # Mock graph to raise an exception
        graph_operations_with_builder.graph.g.addV.side_effect = Exception("Graph error")
        
        with pytest.raises(Exception):
            await graph_operations_with_builder.create_node(node_data)
    
    def test_complex_validation_scenarios(self, graph_operations):
        """Test complex validation scenarios."""
        # Node with complex nested properties
        complex_node = NodeData(
            id="complex",
            label="Person",
            properties={
                "name": "Complex User",
                "profile": {
                    "personal": {"age": 30, "location": "NYC"},
                    "professional": {"skills": ["Python", "ML"], "experience": 5}
                },
                "metrics": [95, 87, 92],
                "active": True,
                "score": 85.5
            }
        )
        
        result = graph_operations.validate_node(complex_node)
        assert result.is_valid is True
        
        # Edge with complex properties
        complex_edge = EdgeData(
            id="complex_edge",
            label="COLLABORATION",
            from_node="person1",
            to_node="person2",
            properties={
                "projects": ["ProjectA", "ProjectB"],
                "duration": {"start": "2020-01", "end": "2023-12"},
                "rating": 4.5,
                "active": False
            }
        )
        
        result = graph_operations.validate_edge(complex_edge)
        assert result.is_valid is True
    
    def test_supported_types_coverage(self, graph_operations):
        """Test coverage of all supported node and relationship types."""
        # Test all supported node types
        for node_type in graph_operations.supported_node_types:
            node_data = NodeData(
                id=f"test_{node_type.lower()}",
                label=node_type,
                properties={"name": f"Test {node_type}"}
            )
            result = graph_operations.validate_node(node_data)
            assert result.is_valid is True
        
        # Test all supported relationship types  
        for rel_type in graph_operations.supported_relationship_types:
            edge_data = EdgeData(
                id=f"test_{rel_type.lower()}",
                label=rel_type,
                from_node="node1",
                to_node="node2",
                properties={"type": f"Test {rel_type}"}
            )
            result = graph_operations.validate_edge(edge_data)
            assert result.is_valid is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
