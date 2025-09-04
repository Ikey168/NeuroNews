"""
Comprehensive coverage tests for GraphOperations module.
Targeting specific uncovered lines and edge cases.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
from datetime import datetime

from src.api.graph.operations import GraphOperations, NodeData, EdgeData, ValidationResult


class TestOperationsCoverage:
    """Tests targeting comprehensive coverage for GraphOperations."""
    
    @pytest.mark.asyncio
    async def test_initialization_and_builder(self):
        """Test initialization with and without graph builder."""
        # Test with graph builder
        builder = Mock()
        ops = GraphOperations(graph_builder=builder)
        assert ops.graph == builder
        
        # Test without graph builder
        ops_no_builder = GraphOperations()
        assert ops_no_builder.graph is None
        
    @pytest.mark.asyncio
    async def test_node_validation_comprehensive(self):
        """Test all node validation paths."""
        ops = GraphOperations()
        
        # Valid node
        valid_node = NodeData(
            id="test_id",
            label="Person", 
            properties={"name": "Test User", "age": 30}
        )
        result = ops.validate_node(valid_node)
        assert result.is_valid
        
        # Node without label
        invalid_node1 = NodeData(id="test", label="", properties={"name": "test"})
        result1 = ops.validate_node(invalid_node1)
        assert not result1.is_valid
        assert "Node label is required" in result1.errors
        
        # Node without properties
        invalid_node2 = NodeData(id="test", label="Person", properties={})
        result2 = ops.validate_node(invalid_node2)
        assert not result2.is_valid
        assert "Node properties cannot be empty" in result2.errors
        
        # Node without name property
        invalid_node3 = NodeData(id="test", label="Person", properties={"age": 30})
        result3 = ops.validate_node(invalid_node3)
        assert not result3.is_valid
        assert "Node must have a 'name' property" in result3.errors
        
        # Node with unsupported type
        unsupported_node = NodeData(id="test", label="CustomType", properties={"name": "test"})
        result4 = ops.validate_node(unsupported_node)
        assert result4.is_valid  # Should still be valid but with warning
        assert len(result4.warnings) > 0
        
        # Node with reserved properties
        reserved_node = NodeData(
            id="test", 
            label="Person", 
            properties={"name": "test", "id": "reserved_id", "created_at": "reserved"}
        )
        result5 = ops.validate_node(reserved_node)
        assert result5.is_valid
        assert len(result5.warnings) > 0  # Should have warnings about reserved props
        
    @pytest.mark.asyncio
    async def test_edge_validation_comprehensive(self):
        """Test all edge validation paths."""
        ops = GraphOperations()
        
        # Valid edge
        valid_edge = EdgeData(
            id="edge_id",
            label="MENTIONS",  # Use a supported relationship type
            from_node="person1", 
            to_node="person2",
            properties={"since": "2020", "strength": 0.8}
        )
        result = ops.validate_edge(valid_edge)
        assert result.is_valid
        
        # Edge without label
        invalid_edge1 = EdgeData(
            id="edge", label="", from_node="p1", to_node="p2", properties={}
        )
        result1 = ops.validate_edge(invalid_edge1)
        assert not result1.is_valid
        assert "Edge label is required" in result1.errors
        
        # Edge without from_node
        invalid_edge2 = EdgeData(
            id="edge", label="MENTIONS", from_node="", to_node="p2", properties={}
        )
        result2 = ops.validate_edge(invalid_edge2)
        assert not result2.is_valid
        assert "From node is required" in result2.errors
        
        # Edge without to_node
        invalid_edge3 = EdgeData(
            id="edge", label="MENTIONS", from_node="p1", to_node="", properties={}
        )
        result3 = ops.validate_edge(invalid_edge3)
        assert not result3.is_valid
        assert "To node is required" in result3.errors
        
    @pytest.mark.asyncio
    async def test_node_creation_scenarios(self):
        """Test node creation with various scenarios."""
        ops = GraphOperations()
        
        # Test creation without graph (should return None)
        node = NodeData(id="test", label="Person", properties={"name": "Test"})
        result = await ops.create_node(node)
        assert result is None
        
        # Test creation with validation failure
        invalid_node = NodeData(id="test", label="", properties={})
        with pytest.raises(ValueError):
            await ops.create_node(invalid_node)
        
        # Test creation with graph but mock failure
        ops.graph = Mock()
        ops.graph.g = Mock()
        mock_traversal = Mock()
        mock_traversal.next = AsyncMock(side_effect=Exception("Graph error"))
        ops.graph.g.addV.return_value.property.return_value = mock_traversal
        
        valid_node = NodeData(id="test", label="Person", properties={"name": "Test"})
        result = await ops.create_node(valid_node)
        assert result is None  # Should return None on graph error
        
    @pytest.mark.asyncio
    async def test_edge_creation_scenarios(self):
        """Test edge creation with various scenarios."""
        ops = GraphOperations()
        
        # Test creation without graph
        edge = EdgeData(
            id="edge", label="KNOWS", from_node="p1", to_node="p2", properties={}
        )
        result = await ops.create_edge(edge)
        assert result is None
        
        # Test creation with validation failure
        invalid_edge = EdgeData(
            id="edge", label="", from_node="", to_node="", properties={}
        )
        with pytest.raises(ValueError):
            await ops.create_edge(invalid_edge)
            
    @pytest.mark.asyncio
    async def test_update_and_delete_operations(self):
        """Test update and delete operations."""
        ops = GraphOperations()
        
        # Test operations without graph
        result = await ops.update_node("test", {"prop": "value"})
        assert result is None
        
        result = await ops.delete_node("test")
        assert result is None
        
        # Test with mock graph
        ops.graph = Mock()
        ops.graph.g = Mock()
        
        # Mock successful update
        mock_update = Mock()
        mock_update.next = AsyncMock(return_value={"id": "test", "updated": True})
        ops.graph.g.V.return_value.has.return_value.property.return_value = mock_update
        
        result = await ops.update_node("test", {"name": "Updated"})
        assert result is not None
        
        # Mock successful delete
        mock_delete = Mock()
        mock_delete.next = AsyncMock(return_value=None)
        ops.graph.g.V.return_value.has.return_value.drop.return_value = mock_delete
        
        result = await ops.delete_node("test")
        assert result is True
        
    @pytest.mark.asyncio
    async def test_import_export_operations(self):
        """Test data import and export operations."""
        ops = GraphOperations()
        
        # Test export without graph
        result = await ops.export_graph_data()
        assert result == {"nodes": [], "edges": []}
        
        # Test export with mock graph error
        ops.graph = Mock()
        ops.graph.g = Mock()
        mock_query = Mock()
        mock_query.valueMap = Mock(return_value=Mock(toList=AsyncMock(side_effect=Exception("Export error"))))
        ops.graph.g.V = Mock(return_value=mock_query)
        
        result = await ops.export_graph_data()
        assert result == {"nodes": [], "edges": []}
        
        # Test import with invalid data
        invalid_data = {
            "nodes": [{"id": "test", "invalid": "data"}],  # Missing required fields
            "edges": []
        }
        result = await ops.import_graph_data(invalid_data)
        assert result is False
        
        # Test import with node creation failure
        ops.graph = Mock()
        with patch.object(ops, 'create_node', return_value=None):
            valid_data = {
                "nodes": [{"id": "test", "label": "Test", "properties": {"name": "Test"}}],
                "edges": []
            }
            result = await ops.import_graph_data(valid_data)
            assert result is False
            
    @pytest.mark.asyncio
    async def test_graph_consistency_validation(self):
        """Test graph consistency validation."""
        ops = GraphOperations()
        
        # Test without graph
        result = await ops.validate_graph_consistency()
        assert isinstance(result, dict)
        assert result["is_valid"] is False
        
        # Test with mock graph
        ops.graph = Mock()
        ops.graph.g = Mock()
        
        # Mock node count
        mock_node_count = Mock()
        mock_node_count.next = AsyncMock(return_value=10)
        ops.graph.g.V.return_value.count.return_value = mock_node_count
        
        # Mock edge count  
        mock_edge_count = Mock()
        mock_edge_count.next = AsyncMock(return_value=15)
        ops.graph.g.E.return_value.count.return_value = mock_edge_count
        
        result = await ops.validate_graph_consistency()
        assert isinstance(result, dict)
        assert "node_count" in result
        assert "edge_count" in result
        
    def test_utility_methods(self):
        """Test utility and helper methods."""
        ops = GraphOperations()
        
        # Test supported types
        node_types = ops.get_supported_node_types()
        assert isinstance(node_types, set)
        assert "Person" in node_types
        
        rel_types = ops.get_supported_relationship_types()
        assert isinstance(rel_types, set)
        assert "KNOWS" in rel_types or "MENTIONS" in rel_types


if __name__ == "__main__":
    pytest.main([__file__])
