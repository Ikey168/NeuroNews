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

        # Without a graph backend, create_node returns the mock node dict.
        node = NodeData(id="test", label="Person", properties={"name": "Test"})
        result = await ops.create_node(node)
        assert isinstance(result, dict)
        assert result["label"] == "Person"
        assert result["properties"] == {"name": "Test"}

        # Test creation with validation failure
        invalid_node = NodeData(id="test", label="", properties={})
        with pytest.raises(ValueError):
            await ops.create_node(invalid_node)

        # With a graph backend that fails, create_node re-raises the error.
        # The source chains ``g.addV(label).property(...).property(...)`` once
        # per property (plus the injected timestamps), so the traversal mock
        # must return itself from ``.property`` and fail on the awaited ``next``.
        ops.graph = Mock()
        ops.graph.g = Mock()
        mock_traversal = Mock()
        mock_traversal.property = Mock(return_value=mock_traversal)
        mock_traversal.next = AsyncMock(side_effect=Exception("Graph error"))
        ops.graph.g.addV = Mock(return_value=mock_traversal)

        valid_node = NodeData(id="test", label="Person", properties={"name": "Test"})
        with pytest.raises(Exception) as exc_info:
            await ops.create_node(valid_node)
        assert "Graph error" in str(exc_info.value)
        
    @pytest.mark.asyncio
    async def test_edge_creation_scenarios(self):
        """Test edge creation with various scenarios."""
        ops = GraphOperations()

        # Without a graph backend, create_edge returns the mock edge dict.
        edge = EdgeData(
            id="edge", label="KNOWS", from_node="p1", to_node="p2", properties={}
        )
        result = await ops.create_edge(edge)
        assert isinstance(result, dict)
        assert result["label"] == "KNOWS"
        assert result["from_node"] == "p1"
        assert result["to_node"] == "p2"

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

        # Without a graph backend, update/delete return mock result dicts.
        result = await ops.update_node("test", {"prop": "value"})
        assert isinstance(result, dict)
        assert result["id"] == "test"
        assert result["updated_properties"] == {"prop": "value"}

        result = await ops.delete_node("test")
        assert isinstance(result, dict)
        assert result["deleted_node_id"] == "test"
        assert result["cascade_delete"] is False

        # Test with mock graph backend.
        ops.graph = Mock()
        ops.graph.g = Mock()

        # update_node chains ``g.V(id).property(...)...valueMap(True).next()``.
        trav = Mock()
        trav.property = Mock(return_value=trav)
        trav.valueMap = Mock(return_value=Mock(next=AsyncMock(return_value={"name": ["Updated"]})))
        ops.graph.g.V = Mock(return_value=trav)

        result = await ops.update_node("test", {"name": "Updated"})
        assert isinstance(result, dict)
        assert result["id"] == "test"

        # delete_node chains ``g.V(id).drop().iterate()`` (awaited).
        drop_trav = Mock()
        drop_trav.iterate = AsyncMock(return_value=None)
        ops.graph.g.V = Mock(return_value=Mock(drop=Mock(return_value=drop_trav)))

        result = await ops.delete_node("test")
        assert isinstance(result, dict)
        assert result["deleted_node_id"] == "test"
        
    @pytest.mark.asyncio
    async def test_import_export_operations(self):
        """Test data import and export operations."""
        ops = GraphOperations()

        # Without a graph backend, export returns an empty-but-structured dict.
        result = await ops.export_graph_data()
        assert result["nodes"] == []
        assert result["edges"] == []
        assert result["total_nodes"] == 0
        assert result["total_edges"] == 0
        assert result["format"] == "json"

        # With a graph backend that fails, export re-raises the error.
        ops.graph = Mock()
        ops.graph.g = Mock()
        mock_query = Mock()
        mock_query.valueMap = Mock(return_value=Mock(toList=AsyncMock(side_effect=Exception("Export error"))))
        ops.graph.g.V = Mock(return_value=mock_query)

        with pytest.raises(Exception) as exc_info:
            await ops.export_graph_data()
        assert "Export error" in str(exc_info.value)

        # Import requires 'nodes' and 'edges' keys; otherwise it raises.
        with pytest.raises(ValueError):
            await ops.import_graph_data({"nodes": []})

        # Import records per-node failures in the result rather than returning
        # a bool. The node below has empty properties so create_node validation
        # fails and the error is collected.
        ops_fresh = GraphOperations()
        invalid_data = {
            "nodes": [{"id": "test", "invalid": "data"}],  # no usable properties
            "edges": [],
        }
        result = await ops_fresh.import_graph_data(invalid_data)
        assert isinstance(result, dict)
        assert result["imported_nodes"] == 0
        assert result["total_errors"] >= 1

        # Import with a patched, failing create_node still returns a dict with
        # the failure recorded (no node successfully imported).
        with patch.object(ops_fresh, "create_node", new=AsyncMock(side_effect=Exception("create failed"))):
            valid_data = {
                "nodes": [{"id": "test", "label": "Person", "properties": {"name": "Test"}}],
                "edges": [],
            }
            result = await ops_fresh.import_graph_data(valid_data)
            assert isinstance(result, dict)
            assert result["imported_nodes"] == 0
            assert result["total_errors"] >= 1
            
    def test_graph_consistency_validation(self):
        """Test graph consistency validation.

        ``validate_graph_consistency`` is synchronous and returns a fixed
        consistency report dict (no graph counts are queried in the current
        source).
        """
        ops = GraphOperations()

        result = ops.validate_graph_consistency()
        assert isinstance(result, dict)
        assert result["is_consistent"] is True
        assert result["orphaned_nodes"] == 0
        assert result["invalid_relationships"] == 0
        assert "validation_time" in result
        assert isinstance(result["issues"], list)
        
    def test_utility_methods(self):
        """Test utility and helper methods."""
        ops = GraphOperations()
        
        # get_supported_*_types return lists in the current source.
        node_types = ops.get_supported_node_types()
        assert isinstance(node_types, list)
        assert "Person" in node_types

        rel_types = ops.get_supported_relationship_types()
        assert isinstance(rel_types, list)
        assert "MENTIONS" in rel_types


if __name__ == "__main__":
    pytest.main([__file__])
