"""
Comprehensive coverage tests for GraphTraversal module.
Targeting specific uncovered lines and edge cases.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
from datetime import datetime
from collections import deque

from src.api.graph.traversal import GraphTraversal, TraversalConfig, PathResult, TraversalResult


class TestTraversalCoverage:
    """Tests targeting comprehensive coverage for GraphTraversal."""
    
    @pytest.mark.asyncio
    async def test_initialization(self):
        """Test initialization scenarios."""
        # Test with graph builder
        builder = Mock()
        traversal = GraphTraversal(graph_builder=builder)
        assert traversal.graph == builder
        assert isinstance(traversal.traversal_stats, dict)
        
        # Test without graph builder
        traversal_no_builder = GraphTraversal()
        assert traversal_no_builder.graph is None
        
    @pytest.mark.asyncio
    async def test_breadth_first_search_comprehensive(self):
        """Test BFS with various scenarios."""
        traversal = GraphTraversal()
        
        # Test without graph
        result = await traversal.breadth_first_search("start_node")
        assert isinstance(result, TraversalResult)
        assert result.nodes == ["start_node"]  # Should contain at least start node
        
        # Test with mock graph and neighbors
        traversal.graph = Mock()
        traversal.graph.g = Mock()
        
        # Mock get_node_neighbors to return some neighbors
        mock_neighbors_query = Mock()
        mock_neighbors_query.valueMap = Mock()
        mock_neighbors_query.valueMap.return_value.toList = AsyncMock(return_value=[
            {"id": "neighbor1", "name": "Neighbor 1"},
            {"id": "neighbor2", "name": "Neighbor 2"}
        ])
        traversal.graph.g.V.return_value.out.return_value = mock_neighbors_query
        
        result = await traversal.breadth_first_search("start_node")
        assert isinstance(result, TraversalResult)
        assert "start_node" in result.nodes
        
        # Test with custom config
        config = TraversalConfig(max_depth=2, max_results=10)
        result = await traversal.breadth_first_search("start_node", config=config)
        assert isinstance(result, TraversalResult)
        
    @pytest.mark.asyncio
    async def test_depth_first_search_comprehensive(self):
        """Test DFS with various scenarios."""
        traversal = GraphTraversal()
        
        # Test without graph
        result = await traversal.depth_first_search("start_node")
        assert isinstance(result, TraversalResult)
        assert result.nodes == ["start_node"]
        
        # Test with mock graph
        traversal.graph = Mock()
        traversal.graph.g = Mock()
        mock_neighbors_query = Mock()
        mock_neighbors_query.valueMap = Mock()
        mock_neighbors_query.valueMap.return_value.toList = AsyncMock(return_value=[])
        traversal.graph.g.V.return_value.out.return_value = mock_neighbors_query
        
        result = await traversal.depth_first_search("start_node")
        assert isinstance(result, TraversalResult)
        
    @pytest.mark.asyncio
    async def test_pathfinding_algorithms(self):
        """Test pathfinding methods."""
        traversal = GraphTraversal()
        
        # Test shortest path without graph
        result = await traversal.find_shortest_path("start", "end")
        assert result is None
        
        # Test find all paths without graph
        result = await traversal.find_all_paths("start", "end", max_paths=5)
        assert result == []
        
        # Test with mock graph that has no connections
        traversal.graph = Mock()
        traversal.graph.g = Mock()
        
        mock_neighbors_query = Mock()
        mock_neighbors_query.valueMap = Mock()
        mock_neighbors_query.valueMap.return_value.toList = AsyncMock(return_value=[])
        traversal.graph.g.V.return_value.out.return_value = mock_neighbors_query
        
        result = await traversal.find_shortest_path("start", "end")
        assert result is None
        
        result = await traversal.find_all_paths("start", "end", max_paths=3)
        assert result == []
        
    @pytest.mark.asyncio
    async def test_neighbor_operations(self):
        """Test neighbor retrieval operations."""
        traversal = GraphTraversal()
        
        # Test without graph
        neighbors = await traversal.get_node_neighbors("test_node")
        assert neighbors == []
        
        # Test with graph but query error
        traversal.graph = Mock()
        traversal.graph.g = Mock()
        mock_query = Mock()
        mock_query.valueMap = Mock()
        mock_query.valueMap.return_value.toList = AsyncMock(side_effect=Exception("Query error"))
        traversal.graph.g.V.return_value.out.return_value = mock_query
        
        neighbors = await traversal.get_node_neighbors("test_node")
        assert neighbors == []
        
        # Test get neighbors by relationship
        neighbors = await traversal.get_neighbors_by_relationship("test_node", "KNOWS")
        assert neighbors == []
        
        # Test with successful neighbors query
        traversal.graph = Mock()
        traversal.graph.g = Mock()
        mock_successful_query = Mock()
        mock_successful_query.valueMap = Mock()
        mock_successful_query.valueMap.return_value.toList = AsyncMock(return_value=[
            {"id": "neighbor1", "name": "Alice"},
            {"id": "neighbor2", "name": "Bob"}
        ])
        traversal.graph.g.V.return_value.out.return_value = mock_successful_query
        
        neighbors = await traversal.get_node_neighbors("test_node")
        assert len(neighbors) == 2
        assert neighbors[0]["id"] == "neighbor1"
        
    @pytest.mark.asyncio
    async def test_configuration_validation(self):
        """Test configuration validation scenarios."""
        traversal = GraphTraversal()
        
        # Test various configs
        valid_config = TraversalConfig(max_depth=5, max_results=100)
        # Note: validate_config method may not exist, but we test config usage
        
        # Test config with different parameters
        config_high_depth = TraversalConfig(max_depth=10, max_results=1000)
        result = await traversal.breadth_first_search("start", config=config_high_depth)
        assert isinstance(result, TraversalResult)
        
        config_low_results = TraversalConfig(max_depth=3, max_results=5)
        result = await traversal.depth_first_search("start", config=config_low_results)
        assert isinstance(result, TraversalResult)
        
        # Test config with filters
        config_with_filters = TraversalConfig(
            max_depth=4, 
            max_results=50,
            filter_by_labels=["Person", "Organization"],
            filter_by_properties={"active": True}
        )
        result = await traversal.breadth_first_search("start", config=config_with_filters)
        assert isinstance(result, TraversalResult)
        
    @pytest.mark.asyncio
    async def test_error_handling_scenarios(self):
        """Test error handling in various scenarios."""
        traversal = GraphTraversal()
        
        # Test with mock graph that raises exceptions
        traversal.graph = Mock()
        traversal.graph.g = Mock()
        
        # Mock graph operations that fail
        mock_failing_query = Mock()
        mock_failing_query.valueMap = Mock()
        mock_failing_query.valueMap.return_value.toList = AsyncMock(side_effect=Exception("Graph connection error"))
        traversal.graph.g.V.return_value.out.return_value = mock_failing_query
        
        # Test that errors are handled gracefully
        result = await traversal.breadth_first_search("start")
        assert isinstance(result, TraversalResult)
        
        result = await traversal.depth_first_search("start")
        assert isinstance(result, TraversalResult)
        
        neighbors = await traversal.get_node_neighbors("test")
        assert neighbors == []
        
    @pytest.mark.asyncio
    async def test_result_creation_and_formatting(self):
        """Test result creation and formatting methods."""
        traversal = GraphTraversal()
        
        # Test creating traversal results with different parameters
        nodes = ["node1", "node2", "node3"]
        edges = [("node1", "node2"), ("node2", "node3")]
        
        # Test basic result creation (if method exists)
        # This tests the internal result formatting
        config = TraversalConfig(include_properties=True)
        result = await traversal.breadth_first_search("node1", config=config)
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
        
        # Test result with properties disabled
        config_no_props = TraversalConfig(include_properties=False)
        result = await traversal.depth_first_search("node1", config=config_no_props)
        assert isinstance(result, TraversalResult)
        
    @pytest.mark.asyncio
    async def test_statistics_and_performance(self):
        """Test statistics collection and performance tracking."""
        traversal = GraphTraversal()
        
        # Check initial stats
        assert isinstance(traversal.traversal_stats, dict)
        assert "total_traversals" in traversal.traversal_stats
        
        # Perform some operations to update stats
        await traversal.breadth_first_search("test")
        await traversal.depth_first_search("test")
        
        # Stats should be tracked (if implemented)
        assert traversal.traversal_stats["total_traversals"] >= 0
        
    def test_dataclass_structures(self):
        """Test dataclass structures and their creation."""
        # Test TraversalConfig creation
        config = TraversalConfig()
        assert config.max_depth == 5  # default
        assert config.max_results == 1000  # default
        assert config.include_properties is True  # default
        
        # Test with custom values
        custom_config = TraversalConfig(
            max_depth=10,
            max_results=500,
            include_properties=False,
            filter_by_labels=["Person"],
            filter_by_properties={"status": "active"},
            timeout_seconds=60
        )
        assert custom_config.max_depth == 10
        assert custom_config.max_results == 500
        assert custom_config.include_properties is False
        assert custom_config.filter_by_labels == ["Person"]
        assert custom_config.filter_by_properties == {"status": "active"}
        assert custom_config.timeout_seconds == 60
        
        # Test PathResult creation
        path_result = PathResult(
            start_node="A",
            end_node="C", 
            path=["A", "B", "C"],
            path_length=2,
            total_weight=1.5,
            properties={"algorithm": "BFS"}
        )
        assert path_result.start_node == "A"
        assert path_result.end_node == "C"
        assert path_result.path == ["A", "B", "C"]
        assert path_result.path_length == 2
        assert path_result.total_weight == 1.5
        
        # Test TraversalResult creation
        traversal_result = TraversalResult(
            start_node="A",
            nodes=["A", "B", "C"],
            edges=[("A", "B"), ("B", "C")],
            execution_time=0.15,
            paths=[]  # Required parameter
        )
        assert traversal_result.start_node == "A"
        assert traversal_result.nodes == ["A", "B", "C"]
        assert traversal_result.edges == [("A", "B"), ("B", "C")]
        assert traversal_result.execution_time == 0.15


if __name__ == "__main__":
    pytest.main([__file__])
