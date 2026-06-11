"""
Comprehensive tests for Graph Operations Module

This test suite achieves 100% coverage for src/api/graph/operations.py
by testing all functions, edge cases, error conditions, and validation logic.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import json

from src.api.graph.operations import (
    GraphOperations, 
    NodeData, 
    EdgeData, 
    ValidationResult
)


@pytest.fixture
def graph_operations():
    """Create a GraphOperations instance for testing."""
    mock_graph = Mock()
    mock_graph.g = Mock()
    return GraphOperations(mock_graph)


@pytest.fixture  
def mock_graph_operations():
    """Create a GraphOperations instance without graph builder for testing."""
    return GraphOperations()


class TestNodeData:
    """Test NodeData dataclass."""
    
    def test_node_data_creation(self):
        """Test NodeData creation with all parameters."""
        created_at = datetime.now()
        updated_at = datetime.now()
        
        node = NodeData(
            id="node_123",
            label="Person",
            properties={"name": "John", "age": 30},
            created_at=created_at,
            updated_at=updated_at
        )
        
        assert node.id == "node_123"
        assert node.label == "Person"
        assert node.properties == {"name": "John", "age": 30}
        assert node.created_at == created_at
        assert node.updated_at == updated_at
    
    def test_node_data_minimal_creation(self):
        """Test NodeData creation with minimal parameters."""
        node = NodeData(
            id=None,
            label="Topic",
            properties={"title": "AI Research"}
        )
        
        assert node.id is None
        assert node.label == "Topic"
        assert node.properties == {"title": "AI Research"}
        assert node.created_at is None
        assert node.updated_at is None


class TestEdgeData:
    """Test EdgeData dataclass."""
    
    def test_edge_data_creation(self):
        """Test EdgeData creation with all parameters."""
        created_at = datetime.now()
        updated_at = datetime.now()
        
        edge = EdgeData(
            id="edge_456",
            label="WORKS_FOR",
            from_node="person_1",
            to_node="org_1",
            properties={"since": "2020", "role": "Engineer"},
            created_at=created_at,
            updated_at=updated_at
        )
        
        assert edge.id == "edge_456"
        assert edge.label == "WORKS_FOR"
        assert edge.from_node == "person_1"
        assert edge.to_node == "org_1"
        assert edge.properties == {"since": "2020", "role": "Engineer"}
        assert edge.created_at == created_at
        assert edge.updated_at == updated_at


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
            errors=["Required field missing", "Invalid type"],
            warnings=[]
        )
        
        assert result.is_valid is False
        assert result.errors == ["Required field missing", "Invalid type"]
        assert result.warnings == []


class TestGraphOperations:
    """Test GraphOperations class methods."""
    
    def test_initialization(self, graph_operations):
        """Test GraphOperations initialization."""
        assert graph_operations.graph is not None
        assert 'Person' in graph_operations.supported_node_types
        assert 'MENTIONS' in graph_operations.supported_relationship_types
    
    def test_initialization_without_graph(self, mock_graph_operations):
        """Test GraphOperations initialization without graph builder."""
        assert mock_graph_operations.graph is None
        assert len(mock_graph_operations.supported_node_types) > 0
        assert len(mock_graph_operations.supported_relationship_types) > 0

    def test_validate_node_success(self, graph_operations):
        """Test successful node validation."""
        node_data = NodeData(
            id="node_1",
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
    
    def test_validate_node_missing_label(self, graph_operations):
        """Test node validation with missing label."""
        node_data = NodeData(
            id="node_1",
            label="",
            properties={"name": "John Doe"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert "Node label is required" in result.errors
    
    def test_validate_node_empty_properties(self, graph_operations):
        """Test node validation with empty properties."""
        node_data = NodeData(
            id="node_1",
            label="Person",
            properties={}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert "Node properties cannot be empty" in result.errors
    
    def test_validate_node_missing_name_property(self, graph_operations):
        """Test node validation with missing name property."""
        node_data = NodeData(
            id="node_1",
            label="Person",
            properties={"age": 30}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert "Node must have a 'name' property" in result.errors
    
    def test_validate_node_unsupported_type(self, graph_operations):
        """Test node validation with unsupported node type."""
        node_data = NodeData(
            id="node_1",
            label="UnsupportedType",
            properties={"name": "Test"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is True  # Should still be valid, just warning
        assert "Unsupported node type: UnsupportedType" in result.warnings
    
    def test_validate_node_reserved_properties(self, graph_operations):
        """Test node validation with reserved property names."""
        node_data = NodeData(
            id="node_1",
            label="Person",
            properties={"name": "John", "id": "override", "label": "override"}
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is True
        assert any("reserved" in warning for warning in result.warnings)
    
    def test_validate_node_invalid_property_types(self, graph_operations):
        """Test node validation with invalid property types."""
        node_data = NodeData(
            id="node_1",
            label="Person",
            properties={
                "name": "John",
                "invalid_prop": object(),  # Invalid type
                "none_prop": None
            }
        )
        
        result = graph_operations.validate_node(node_data)
        
        assert result.is_valid is False
        assert any("unsupported data type" in error for error in result.errors)
        assert any("empty value" in warning for warning in result.warnings)
    
    def test_validate_edge_success(self, graph_operations):
        """Test successful edge validation."""
        edge_data = EdgeData(
            id="edge_1",
            label="KNOWS",
            from_node="person_1",
            to_node="person_2",
            properties={"since": "2020"}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is True
        assert len(result.errors) == 0
    
    def test_validate_edge_missing_required_fields(self, graph_operations):
        """Test edge validation with missing required fields."""
        edge_data = EdgeData(
            id="edge_1",
            label="",
            from_node="",
            to_node="person_2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert "Edge label is required" in result.errors
        assert "From node is required" in result.errors
    
    def test_validate_edge_self_reference(self, graph_operations):
        """Test edge validation with self-referencing edge."""
        edge_data = EdgeData(
            id="edge_1",
            label="KNOWS",
            from_node="person_1",
            to_node="person_1",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is True
        assert "Self-referencing edge detected" in result.warnings
    
    def test_validate_edge_unsupported_relationship_type(self, graph_operations):
        """Test edge validation with unsupported relationship type."""
        edge_data = EdgeData(
            id="edge_1",
            label="UNSUPPORTED_REL",
            from_node="person_1",
            to_node="person_2",
            properties={}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is True
        assert "Unsupported relationship type: UNSUPPORTED_REL" in result.warnings
    
    def test_validate_edge_invalid_property_types(self, graph_operations):
        """Test edge validation with invalid property types."""
        edge_data = EdgeData(
            id="edge_1",
            label="KNOWS",
            from_node="person_1",
            to_node="person_2",
            properties={"invalid": object()}
        )
        
        result = graph_operations.validate_edge(edge_data)
        
        assert result.is_valid is False
        assert any("unsupported data type" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_create_node_mock_success(self, mock_graph_operations):
        """Test successful node creation with mock implementation."""
        node_data = NodeData(
            id=None,
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        result = await mock_graph_operations.create_node(node_data)
        
        assert result['label'] == "Person"
        assert result['properties']['name'] == "John Doe"
        assert 'id' in result
        assert 'created_at' in result
        assert 'validation_warnings' in result

    @pytest.mark.asyncio
    async def test_create_node_validation_failure(self, mock_graph_operations):
        """Test node creation with validation failure."""
        node_data = NodeData(
            id=None,
            label="",  # Invalid - empty label
            properties={"name": "John"}
        )
        
        with pytest.raises(ValueError) as exc_info:
            await mock_graph_operations.create_node(node_data)
        
        assert "Node validation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_node_with_graph(self, graph_operations):
        """Test node creation with real graph implementation."""
        # Mock the graph traversal
        mock_traversal = Mock()
        mock_traversal.property = Mock(return_value=mock_traversal)
        mock_traversal.next = AsyncMock(return_value=("node_123",))
        
        graph_operations.graph.g.addV = Mock(return_value=mock_traversal)
        
        node_data = NodeData(
            id=None,
            label="Person",
            properties={"name": "John Doe"}
        )
        
        result = await graph_operations.create_node(node_data)
        
        assert result['id'] == "node_123"
        assert result['label'] == "Person"
        graph_operations.graph.g.addV.assert_called_once_with("Person")

    @pytest.mark.asyncio
    async def test_create_node_with_graph_exception(self, graph_operations):
        """Test node creation with graph exception."""
        # Mock the graph to raise an exception
        graph_operations.graph.g.addV = Mock(side_effect=Exception("Graph error"))
        
        node_data = NodeData(
            id=None,
            label="Person",
            properties={"name": "John Doe"}
        )
        
        with pytest.raises(Exception) as exc_info:
            await graph_operations.create_node(node_data)
        
        assert "Graph error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_edge_mock_success(self, mock_graph_operations):
        """Test successful edge creation with mock implementation."""
        edge_data = EdgeData(
            id=None,
            label="KNOWS",
            from_node="person_1",
            to_node="person_2",
            properties={"since": "2020"}
        )
        
        result = await mock_graph_operations.create_edge(edge_data)
        
        assert result['label'] == "KNOWS"
        assert result['from_node'] == "person_1"
        assert result['to_node'] == "person_2"
        assert 'id' in result
        assert 'created_at' in result

    @pytest.mark.asyncio
    async def test_create_edge_validation_failure(self, mock_graph_operations):
        """Test edge creation with validation failure."""
        edge_data = EdgeData(
            id=None,
            label="",  # Invalid - empty label
            from_node="person_1",
            to_node="person_2",
            properties={}
        )
        
        with pytest.raises(ValueError) as exc_info:
            await mock_graph_operations.create_edge(edge_data)
        
        assert "Edge validation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_edge_with_graph(self, graph_operations):
        """Test edge creation with real graph implementation."""
        # Mock the graph traversal
        mock_traversal = Mock()
        mock_traversal.to = Mock(return_value=mock_traversal)
        mock_traversal.property = Mock(return_value=mock_traversal)
        mock_traversal.next = AsyncMock(return_value=("edge_456",))
        
        mock_v = Mock()
        mock_v.addE = Mock(return_value=mock_traversal)
        
        graph_operations.graph.g.V = Mock(return_value=mock_v)
        
        edge_data = EdgeData(
            id=None,
            label="KNOWS",
            from_node="person_1",
            to_node="person_2",
            properties={"since": "2020"}
        )
        
        result = await graph_operations.create_edge(edge_data)
        
        assert result['id'] == "edge_456"
        assert result['label'] == "KNOWS"

    @pytest.mark.asyncio
    async def test_update_node_mock_success(self, mock_graph_operations):
        """Test successful node update with mock implementation."""
        updates = {"name": "Jane Doe", "age": 25}
        
        result = await mock_graph_operations.update_node("node_123", updates)
        
        assert result['id'] == "node_123"
        assert result['updated_properties'] == updates
        assert 'updated_at' in result

    @pytest.mark.asyncio
    async def test_update_node_empty_updates(self, mock_graph_operations):
        """Test node update with empty updates."""
        with pytest.raises(ValueError) as exc_info:
            await mock_graph_operations.update_node("node_123", {})
        
        assert "Updates cannot be empty" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_node_with_graph(self, graph_operations):
        """Test node update with real graph implementation."""
        mock_traversal = Mock()
        mock_traversal.property = Mock(return_value=mock_traversal)
        mock_traversal.valueMap = Mock(return_value=mock_traversal)
        mock_traversal.next = AsyncMock(return_value={"name": "Jane", "age": 25})
        
        graph_operations.graph.g.V = Mock(return_value=mock_traversal)
        
        updates = {"name": "Jane Doe"}
        result = await graph_operations.update_node("node_123", updates)
        
        assert result['id'] == "node_123"
        assert 'current_properties' in result

    @pytest.mark.asyncio
    async def test_delete_node_mock_success(self, mock_graph_operations):
        """Test successful node deletion with mock implementation."""
        result = await mock_graph_operations.delete_node("node_123", cascade=True)
        
        assert result['deleted_node_id'] == "node_123"
        assert result['cascade_delete'] is True
        assert 'deleted_at' in result

    @pytest.mark.asyncio
    async def test_delete_node_with_graph_cascade(self, graph_operations):
        """Test node deletion with cascade and real graph."""
        mock_v_traversal = Mock()
        mock_v_traversal.bothE = Mock(return_value=mock_v_traversal)
        mock_v_traversal.drop = Mock(return_value=mock_v_traversal)
        mock_v_traversal.iterate = AsyncMock()
        
        graph_operations.graph.g.V = Mock(return_value=mock_v_traversal)
        
        result = await graph_operations.delete_node("node_123", cascade=True)
        
        assert result['deleted_node_id'] == "node_123"
        assert result['cascade_delete'] is True
        # Verify cascade delete called bothE().drop()
        mock_v_traversal.bothE.assert_called()
        assert mock_v_traversal.drop.call_count == 2  # Once for edges, once for node

    @pytest.mark.asyncio
    async def test_delete_node_with_graph_no_cascade(self, graph_operations):
        """Test node deletion without cascade."""
        mock_v_traversal = Mock()
        mock_v_traversal.drop = Mock(return_value=mock_v_traversal)
        mock_v_traversal.iterate = AsyncMock()
        
        graph_operations.graph.g.V = Mock(return_value=mock_v_traversal)
        
        result = await graph_operations.delete_node("node_123", cascade=False)
        
        assert result['cascade_delete'] is False
        # Verify no cascade operations
        mock_v_traversal.bothE.assert_not_called() if hasattr(mock_v_traversal, 'bothE') else None

    @pytest.mark.asyncio
    async def test_export_graph_data_mock(self, mock_graph_operations):
        """Test graph data export with mock implementation."""
        result = await mock_graph_operations.export_graph_data("json")
        
        assert result['format'] == "json"
        assert result['nodes'] == []
        assert result['edges'] == []
        assert result['total_nodes'] == 0
        assert result['total_edges'] == 0
        assert 'exported_at' in result

    @pytest.mark.asyncio
    async def test_export_graph_data_invalid_format(self, mock_graph_operations):
        """Test graph data export with invalid format."""
        with pytest.raises(ValueError) as exc_info:
            await mock_graph_operations.export_graph_data("invalid_format")
        
        assert "Unsupported export format" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_export_graph_data_with_graph(self, graph_operations):
        """Test graph data export with real graph implementation."""
        # Mock nodes and edges data
        mock_nodes = [{"id": "node_1", "label": "Person", "name": "John"}]
        mock_edges = [{"id": "edge_1", "label": "KNOWS", "weight": 1.0}]
        
        mock_v_traversal = Mock()
        mock_v_traversal.valueMap = Mock(return_value=mock_v_traversal)
        mock_v_traversal.toList = AsyncMock(return_value=mock_nodes)
        
        mock_e_traversal = Mock()
        mock_e_traversal.valueMap = Mock(return_value=mock_e_traversal)
        mock_e_traversal.toList = AsyncMock(return_value=mock_edges)
        
        graph_operations.graph.g.V = Mock(return_value=mock_v_traversal)
        graph_operations.graph.g.E = Mock(return_value=mock_e_traversal)
        
        result = await graph_operations.export_graph_data("graphml")
        
        assert result['format'] == "graphml"
        assert result['nodes'] == mock_nodes
        assert result['edges'] == mock_edges
        assert result['total_nodes'] == 1
        assert result['total_edges'] == 1

    @pytest.mark.asyncio
    async def test_import_graph_data_success(self, mock_graph_operations):
        """Test successful graph data import."""
        import_data = {
            'nodes': [
                {'id': 'node_1', 'label': 'Person', 'properties': {'name': 'John'}},
                {'id': 'node_2', 'label': 'Person', 'properties': {'name': 'Jane'}}
            ],
            'edges': [
                {'id': 'edge_1', 'label': 'KNOWS', 'from_node': 'node_1', 'to_node': 'node_2', 'properties': {}}
            ]
        }
        
        result = await mock_graph_operations.import_graph_data(import_data)
        
        assert result['imported_nodes'] == 2
        assert result['imported_edges'] == 1
        assert result['total_errors'] == 0
        assert 'imported_at' in result

    @pytest.mark.asyncio
    async def test_import_graph_data_invalid_structure(self, mock_graph_operations):
        """Test graph data import with invalid structure."""
        invalid_data = {'invalid_key': 'invalid_value'}
        
        with pytest.raises(ValueError) as exc_info:
            await mock_graph_operations.import_graph_data(invalid_data)
        
        assert "must contain 'nodes' and 'edges' keys" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_import_graph_data_with_errors(self, mock_graph_operations):
        """Test graph data import with some errors."""
        # Patch create_node to fail for some nodes
        original_create_node = mock_graph_operations.create_node
        
        async def mock_create_node(node_data):
            if node_data.properties.get('name') == 'Invalid':
                raise Exception("Invalid node data")
            return await original_create_node(node_data)
        
        mock_graph_operations.create_node = mock_create_node
        
        import_data = {
            'nodes': [
                {'id': 'node_1', 'label': 'Person', 'properties': {'name': 'John'}},
                {'id': 'node_2', 'label': 'Person', 'properties': {'name': 'Invalid'}}  # This will fail
            ],
            'edges': []
        }
        
        result = await mock_graph_operations.import_graph_data(import_data)
        
        assert result['imported_nodes'] == 1
        assert result['total_errors'] == 1
        assert len(result['errors']) == 1

    def test_get_supported_node_types(self, graph_operations):
        """Test getting supported node types."""
        types = graph_operations.get_supported_node_types()
        
        assert isinstance(types, list)
        assert 'Person' in types
        assert 'Organization' in types
        assert len(types) > 0

    def test_get_supported_relationship_types(self, graph_operations):
        """Test getting supported relationship types."""
        types = graph_operations.get_supported_relationship_types()
        
        assert isinstance(types, list)
        assert 'MENTIONS' in types
        assert 'WORKS_FOR' in types
        assert len(types) > 0

    def test_validate_graph_consistency(self, graph_operations):
        """Test graph consistency validation."""
        result = graph_operations.validate_graph_consistency()
        
        assert result['is_consistent'] is True
        assert result['orphaned_nodes'] == 0
        assert 'validation_time' in result
        assert 'issues' in result


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_create_node_with_none_properties(self, mock_graph_operations):
        """Test node creation with None properties."""
        node_data = NodeData(
            id=None,
            label="Test",
            properties=None
        )
        
        with pytest.raises(ValueError):
            await mock_graph_operations.create_node(node_data)

    @pytest.mark.asyncio
    async def test_create_edge_with_none_properties(self, mock_graph_operations):
        """Test edge creation with None properties."""
        edge_data = EdgeData(
            id=None,
            label="CONNECTS",
            from_node="node_1",
            to_node="node_2",
            properties=None
        )
        
        with pytest.raises(ValueError):
            await mock_graph_operations.create_edge(edge_data)

    def test_validate_node_with_complex_property_types(self, graph_operations):
        """Test node validation with complex but valid property types."""
        node_data = NodeData(
            id="node_1",
            label="Person",
            properties={
                "name": "John",
                "tags": ["tag1", "tag2"],  # List type
                "metadata": {"key": "value"},  # Dict type
                "active": True,  # Boolean type
                "score": 95.5,  # Float type
                "count": 10  # Integer type
            }
        )
        
        result = graph_operations.validate_node(node_data)
        assert result.is_valid is True

    def test_validate_edge_with_empty_properties_dict(self, graph_operations):
        """Test edge validation with empty but not None properties."""
        edge_data = EdgeData(
            id="edge_1",
            label="CONNECTS",
            from_node="node_1", 
            to_node="node_2",
            properties={}  # Empty dict, not None
        )
        
        result = graph_operations.validate_edge(edge_data)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_operations_with_various_supported_formats(self, mock_graph_operations):
        """Test export with all supported formats."""
        formats = ["json", "graphml", "csv"]
        
        for format_type in formats:
            result = await mock_graph_operations.export_graph_data(format_type)
            assert result['format'] == format_type


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple operations."""
    
    @pytest.mark.asyncio
    async def test_complete_node_lifecycle(self, mock_graph_operations):
        """Test complete node lifecycle: create, update, delete."""
        # Create node
        node_data = NodeData(
            id=None,
            label="Person",
            properties={"name": "John Doe", "age": 30}
        )
        
        create_result = await mock_graph_operations.create_node(node_data)
        node_id = create_result['id']
        
        # Update node
        update_result = await mock_graph_operations.update_node(node_id, {"age": 31})
        assert update_result['id'] == node_id
        
        # Delete node
        delete_result = await mock_graph_operations.delete_node(node_id)
        assert delete_result['deleted_node_id'] == node_id

    @pytest.mark.asyncio  
    async def test_export_import_cycle(self, mock_graph_operations):
        """Test export followed by import."""
        # Export empty graph
        export_result = await mock_graph_operations.export_graph_data("json")
        
        # Import the exported data
        import_result = await mock_graph_operations.import_graph_data(export_result)
        
        assert import_result['imported_nodes'] == 0
        assert import_result['imported_edges'] == 0
        assert import_result['total_errors'] == 0
