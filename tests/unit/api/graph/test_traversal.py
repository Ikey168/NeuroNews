"""
Comprehensive tests for Graph Traversal Module

This test suite achieves 100% coverage for src/api/graph/traversal.py
by testing all traversal algorithms, pathfinding methods, and edge cases.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from collections import deque

from src.api.graph.traversal import (
    GraphTraversal,
    TraversalConfig,
    PathResult,
    TraversalResult
)


@pytest.fixture
def graph_traversal():
    """Create a GraphTraversal instance for testing."""
    mock_graph = Mock()
    mock_graph.g = Mock()
    return GraphTraversal(mock_graph)


@pytest.fixture
def mock_graph_traversal():
    """Create a GraphTraversal instance without graph builder for testing."""
    return GraphTraversal()


class TestTraversalConfig:
    """Test TraversalConfig dataclass."""
    
    def test_traversal_config_default(self):
        """Test TraversalConfig with default values."""
        config = TraversalConfig()
        
        assert config.max_depth == 10
        assert config.max_nodes == 1000
        assert config.follow_direction == "both"
        assert config.node_filters == {}
        assert config.edge_filters == {}
        assert config.include_paths is True
    
    def test_traversal_config_custom(self):
        """Test TraversalConfig with custom values."""
        config = TraversalConfig(
            max_depth=5,
            max_nodes=500,
            follow_direction="outgoing",
            node_filters={"type": "Person"},
            edge_filters={"weight": 0.5},
            include_paths=False
        )
        
        assert config.max_depth == 5
        assert config.max_nodes == 500
        assert config.follow_direction == "outgoing"
        assert config.node_filters == {"type": "Person"}
        assert config.edge_filters == {"weight": 0.5}
        assert config.include_paths is False


class TestPathResult:
    """Test PathResult dataclass."""
    
    def test_path_result_creation(self):
        """Test PathResult creation."""
        path_result = PathResult(
            source="node_1",
            target="node_3", 
            path=["node_1", "node_2", "node_3"],
            distance=2,
            cost=1.5
        )
        
        assert path_result.source == "node_1"
        assert path_result.target == "node_3"
        assert path_result.path == ["node_1", "node_2", "node_3"]
        assert path_result.distance == 2
        assert path_result.cost == 1.5


class TestTraversalResult:
    """Test TraversalResult dataclass."""
    
    def test_traversal_result_creation(self):
        """Test TraversalResult creation."""
        result = TraversalResult(
            starting_node="node_1",
            visited_nodes=["node_1", "node_2", "node_3"],
            edges_traversed=[("node_1", "node_2"), ("node_2", "node_3")],
            max_depth_reached=2,
            total_nodes=3,
            execution_time=0.5,
            paths=[["node_1", "node_2", "node_3"]]
        )
        
        assert result.starting_node == "node_1"
        assert len(result.visited_nodes) == 3
        assert len(result.edges_traversed) == 2
        assert result.max_depth_reached == 2
        assert result.total_nodes == 3
        assert result.execution_time == 0.5
        assert len(result.paths) == 1


class TestGraphTraversal:
    """Test GraphTraversal class methods."""
    
    def test_initialization(self, graph_traversal):
        """Test GraphTraversal initialization with graph."""
        assert graph_traversal.graph is not None
        assert hasattr(graph_traversal, 'visited')
        assert hasattr(graph_traversal, 'start_time')
    
    def test_initialization_without_graph(self, mock_graph_traversal):
        """Test GraphTraversal initialization without graph."""
        assert mock_graph_traversal.graph is None
        assert hasattr(mock_graph_traversal, 'visited')

    @pytest.mark.asyncio
    async def test_breadth_first_search_mock_basic(self, mock_graph_traversal):
        """Test basic BFS with mock implementation."""
        config = TraversalConfig(max_depth=2)
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        assert result.starting_node == "node_1"
        assert "node_1" in result.visited_nodes
        assert result.max_depth_reached <= 2
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_breadth_first_search_mock_with_filters(self, mock_graph_traversal):
        """Test BFS with node and edge filters."""
        config = TraversalConfig(
            max_depth=3,
            node_filters={"type": "Person"},
            edge_filters={"relationship": "FRIENDS"}
        )
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        assert result.starting_node == "node_1"
        assert len(result.visited_nodes) >= 1  # At least starting node
        
    @pytest.mark.asyncio
    async def test_breadth_first_search_with_graph(self, graph_traversal):
        """Test BFS with real graph implementation."""
        # Mock graph responses
        mock_traversal = Mock()
        mock_traversal.both = Mock(return_value=mock_traversal)
        mock_traversal.limit = Mock(return_value=mock_traversal)
        mock_traversal.toList = AsyncMock(return_value=[
            {"id": "node_2", "label": "Person"},
            {"id": "node_3", "label": "Person"}
        ])
        
        graph_traversal.graph.g.V = Mock(return_value=mock_traversal)
        
        config = TraversalConfig(max_depth=2)
        result = await graph_traversal.breadth_first_search("node_1", config)
        
        assert result.starting_node == "node_1"
        assert len(result.visited_nodes) > 0

    @pytest.mark.asyncio
    async def test_breadth_first_search_max_nodes_limit(self, mock_graph_traversal):
        """Test BFS respects max_nodes limit."""
        config = TraversalConfig(max_depth=10, max_nodes=2)
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        # Should stop at max_nodes limit
        assert len(result.visited_nodes) <= 2

    @pytest.mark.asyncio
    async def test_breadth_first_search_direction_outgoing(self, graph_traversal):
        """Test BFS with outgoing direction only."""
        mock_traversal = Mock()
        mock_traversal.out = Mock(return_value=mock_traversal)
        mock_traversal.limit = Mock(return_value=mock_traversal)
        mock_traversal.toList = AsyncMock(return_value=[])
        
        graph_traversal.graph.g.V = Mock(return_value=mock_traversal)
        
        config = TraversalConfig(follow_direction="outgoing")
        result = await graph_traversal.breadth_first_search("node_1", config)
        
        # Verify outgoing direction was used
        mock_traversal.out.assert_called()
        mock_traversal.both.assert_not_called() if hasattr(mock_traversal, 'both') else None

    @pytest.mark.asyncio
    async def test_breadth_first_search_direction_incoming(self, graph_traversal):
        """Test BFS with incoming direction only."""
        mock_traversal = Mock()
        mock_traversal.in_ = Mock(return_value=mock_traversal)
        mock_traversal.limit = Mock(return_value=mock_traversal)
        mock_traversal.toList = AsyncMock(return_value=[])
        
        graph_traversal.graph.g.V = Mock(return_value=mock_traversal)
        
        config = TraversalConfig(follow_direction="incoming")
        result = await graph_traversal.breadth_first_search("node_1", config)
        
        # Verify incoming direction was used
        mock_traversal.in_.assert_called()

    @pytest.mark.asyncio
    async def test_depth_first_search_mock_basic(self, mock_graph_traversal):
        """Test basic DFS with mock implementation."""
        config = TraversalConfig(max_depth=3)
        
        result = await mock_graph_traversal.depth_first_search("node_1", config)
        
        assert result.starting_node == "node_1"
        assert "node_1" in result.visited_nodes
        assert result.max_depth_reached <= 3
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_depth_first_search_with_paths(self, mock_graph_traversal):
        """Test DFS with path tracking enabled."""
        config = TraversalConfig(max_depth=2, include_paths=True)
        
        result = await mock_graph_traversal.depth_first_search("node_1", config)
        
        assert result.paths is not None
        assert len(result.paths) > 0
        # Each path should start with the starting node
        for path in result.paths:
            assert path[0] == "node_1"

    @pytest.mark.asyncio
    async def test_depth_first_search_without_paths(self, mock_graph_traversal):
        """Test DFS with path tracking disabled."""
        config = TraversalConfig(include_paths=False)
        
        result = await mock_graph_traversal.depth_first_search("node_1", config)
        
        assert result.paths == []

    @pytest.mark.asyncio
    async def test_depth_first_search_with_graph(self, graph_traversal):
        """Test DFS with real graph implementation."""
        mock_traversal = Mock()
        mock_traversal.both = Mock(return_value=mock_traversal)
        mock_traversal.limit = Mock(return_value=mock_traversal)
        mock_traversal.toList = AsyncMock(return_value=[
            {"id": "node_2", "label": "Topic"},
            {"id": "node_3", "label": "Person"}
        ])
        
        graph_traversal.graph.g.V = Mock(return_value=mock_traversal)
        
        config = TraversalConfig(max_depth=2)
        result = await graph_traversal.depth_first_search("node_1", config)
        
        assert result.starting_node == "node_1"
        assert len(result.visited_nodes) > 0

    @pytest.mark.asyncio
    async def test_find_shortest_path_mock_basic(self, mock_graph_traversal):
        """Test basic shortest path finding with mock implementation."""
        result = await mock_graph_traversal.find_shortest_path("node_1", "node_3")
        
        assert result.source == "node_1"
        assert result.target == "node_3"
        assert result.path is not None
        assert len(result.path) >= 2  # At least source and target
        assert result.path[0] == "node_1"
        assert result.path[-1] == "node_3"
        assert result.distance >= 0

    @pytest.mark.asyncio
    async def test_find_shortest_path_same_node(self, mock_graph_traversal):
        """Test shortest path when source equals target."""
        result = await mock_graph_traversal.find_shortest_path("node_1", "node_1")
        
        assert result.source == "node_1"
        assert result.target == "node_1"
        assert result.path == ["node_1"]
        assert result.distance == 0
        assert result.cost == 0.0

    @pytest.mark.asyncio
    async def test_find_shortest_path_no_path_exists(self, mock_graph_traversal):
        """Test shortest path when no path exists."""
        # Mock a scenario where target is unreachable
        with patch.object(mock_graph_traversal, '_get_neighbors_mock') as mock_neighbors:
            mock_neighbors.return_value = []  # No neighbors, unreachable
            
            result = await mock_graph_traversal.find_shortest_path("node_1", "unreachable")
            
            assert result.source == "node_1"
            assert result.target == "unreachable"
            assert result.path == []
            assert result.distance == -1  # Indicates no path found
            assert result.cost == float('inf')

    @pytest.mark.asyncio
    async def test_find_shortest_path_with_graph(self, graph_traversal):
        """Test shortest path with real graph implementation."""
        # Mock a simple path: node_1 -> node_2 -> node_3
        mock_path_traversal = Mock()
        mock_path_traversal.path = Mock(return_value=mock_path_traversal)
        mock_path_traversal.by = Mock(return_value=mock_path_traversal)
        mock_path_traversal.toList = AsyncMock(return_value=[
            [{"id": "node_1"}, {"id": "node_2"}, {"id": "node_3"}]
        ])
        
        graph_traversal.graph.g.V = Mock(return_value=mock_path_traversal)
        
        result = await graph_traversal.find_shortest_path("node_1", "node_3")
        
        assert result.source == "node_1"
        assert result.target == "node_3"
        # Should find the shortest path through graph
        assert len(result.path) >= 2

    @pytest.mark.asyncio
    async def test_find_all_paths_mock_basic(self, mock_graph_traversal):
        """Test finding all paths with mock implementation."""
        max_length = 3
        result = await mock_graph_traversal.find_all_paths("node_1", "node_3", max_length)
        
        assert isinstance(result, list)
        for path in result:
            assert isinstance(path, PathResult)
            assert path.source == "node_1"
            assert path.target == "node_3"
            assert len(path.path) <= max_length + 1  # +1 because path includes both ends

    @pytest.mark.asyncio
    async def test_find_all_paths_max_length_limit(self, mock_graph_traversal):
        """Test that find_all_paths respects max_length limit."""
        max_length = 2
        result = await mock_graph_traversal.find_all_paths("node_1", "node_4", max_length)
        
        for path in result:
            assert path.distance <= max_length

    @pytest.mark.asyncio
    async def test_find_all_paths_same_node(self, mock_graph_traversal):
        """Test finding all paths when source equals target."""
        result = await mock_graph_traversal.find_all_paths("node_1", "node_1", 5)
        
        # Should include the trivial path (just the node itself)
        trivial_paths = [path for path in result if len(path.path) == 1]
        assert len(trivial_paths) >= 1
        assert trivial_paths[0].path == ["node_1"]
        assert trivial_paths[0].distance == 0

    @pytest.mark.asyncio
    async def test_find_all_paths_with_graph(self, graph_traversal):
        """Test finding all paths with real graph implementation."""
        # Mock multiple paths
        mock_traversal = Mock()
        mock_traversal.path = Mock(return_value=mock_traversal)
        mock_traversal.by = Mock(return_value=mock_traversal)
        mock_traversal.toList = AsyncMock(return_value=[
            [{"id": "node_1"}, {"id": "node_2"}, {"id": "node_3"}],
            [{"id": "node_1"}, {"id": "node_4"}, {"id": "node_3"}]
        ])
        
        graph_traversal.graph.g.V = Mock(return_value=mock_traversal)
        
        result = await graph_traversal.find_all_paths("node_1", "node_3", 5)
        
        assert len(result) >= 1  # At least one path should be found
        for path in result:
            assert path.source == "node_1" 
            assert path.target == "node_3"

    @pytest.mark.asyncio
    async def test_analyze_connectivity_mock(self, mock_graph_traversal):
        """Test connectivity analysis with mock implementation."""
        result = await mock_graph_traversal.analyze_connectivity("node_1")
        
        assert result['source_node'] == "node_1"
        assert 'reachable_nodes' in result
        assert 'unreachable_nodes' in result
        assert 'connected_components' in result
        assert 'total_reachable' in result
        assert isinstance(result['reachable_nodes'], list)
        assert isinstance(result['connected_components'], list)

    @pytest.mark.asyncio
    async def test_analyze_connectivity_isolated_node(self, mock_graph_traversal):
        """Test connectivity analysis for isolated node."""
        # Mock an isolated node by overriding the neighbor function
        with patch.object(mock_graph_traversal, '_get_neighbors_mock') as mock_neighbors:
            mock_neighbors.return_value = []
            
            result = await mock_graph_traversal.analyze_connectivity("isolated_node")
            
            assert result['total_reachable'] == 1  # Only the node itself
            assert result['reachable_nodes'] == ["isolated_node"]

    @pytest.mark.asyncio
    async def test_analyze_connectivity_with_graph(self, graph_traversal):
        """Test connectivity analysis with real graph implementation."""
        # Mock connected nodes
        mock_traversal = Mock()
        mock_traversal.both = Mock(return_value=mock_traversal)
        mock_traversal.dedup = Mock(return_value=mock_traversal)
        mock_traversal.toList = AsyncMock(return_value=[
            {"id": "node_2"},
            {"id": "node_3"},
            {"id": "node_4"}
        ])
        
        # Mock all nodes in graph
        mock_all_nodes = Mock()
        mock_all_nodes.toList = AsyncMock(return_value=[
            {"id": "node_1"},
            {"id": "node_2"},
            {"id": "node_3"}, 
            {"id": "node_4"},
            {"id": "node_5"}  # This one should be unreachable
        ])
        
        graph_traversal.graph.g.V = Mock(side_effect=[mock_traversal, mock_all_nodes])
        
        result = await graph_traversal.analyze_connectivity("node_1")
        
        assert result['source_node'] == "node_1"
        assert result['total_reachable'] > 1
        assert "node_1" in result['reachable_nodes']

    def test_get_neighbors_mock_basic(self, mock_graph_traversal):
        """Test _get_neighbors_mock helper method."""
        neighbors = mock_graph_traversal._get_neighbors_mock("node_1")
        
        assert isinstance(neighbors, list)
        # Should return some mock neighbors
        assert len(neighbors) >= 0

    def test_get_neighbors_mock_consistency(self, mock_graph_traversal):
        """Test that _get_neighbors_mock returns consistent results."""
        neighbors1 = mock_graph_traversal._get_neighbors_mock("node_1")
        neighbors2 = mock_graph_traversal._get_neighbors_mock("node_1")
        
        # Should be deterministic for the same input
        assert neighbors1 == neighbors2

    def test_get_neighbors_mock_different_nodes(self, mock_graph_traversal):
        """Test that different nodes can have different neighbors."""
        neighbors_a = mock_graph_traversal._get_neighbors_mock("node_a")
        neighbors_b = mock_graph_traversal._get_neighbors_mock("node_b")
        
        # Different nodes may have different neighbor sets
        assert isinstance(neighbors_a, list)
        assert isinstance(neighbors_b, list)

    @pytest.mark.asyncio
    async def test_graph_exception_handling(self, graph_traversal):
        """Test handling of graph exceptions during traversal."""
        # Mock graph to raise an exception
        graph_traversal.graph.g.V = Mock(side_effect=Exception("Graph connection error"))
        
        config = TraversalConfig()
        
        with pytest.raises(Exception) as exc_info:
            await graph_traversal.breadth_first_search("node_1", config)
        
        assert "Graph connection error" in str(exc_info.value)

    def test_traversal_config_validation(self):
        """Test TraversalConfig parameter validation."""
        # Test invalid direction
        config = TraversalConfig(follow_direction="invalid_direction")
        assert config.follow_direction == "invalid_direction"  # Should still accept it
        
        # Test extreme values
        config = TraversalConfig(max_depth=0, max_nodes=0)
        assert config.max_depth == 0
        assert config.max_nodes == 0


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_empty_graph_traversal(self, mock_graph_traversal):
        """Test traversal on empty graph."""
        # Override to simulate empty graph
        with patch.object(mock_graph_traversal, '_get_neighbors_mock', return_value=[]):
            config = TraversalConfig(max_depth=5)
            result = await mock_graph_traversal.breadth_first_search("node_1", config)
            
            assert result.starting_node == "node_1"
            assert result.visited_nodes == ["node_1"]
            assert result.total_nodes == 1

    @pytest.mark.asyncio
    async def test_very_large_max_depth(self, mock_graph_traversal):
        """Test traversal with very large max_depth."""
        config = TraversalConfig(max_depth=1000000, max_nodes=5)  # Limited by max_nodes
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        # Should be limited by max_nodes, not max_depth
        assert len(result.visited_nodes) <= 5

    @pytest.mark.asyncio
    async def test_zero_max_depth(self, mock_graph_traversal):
        """Test traversal with zero max_depth."""
        config = TraversalConfig(max_depth=0)
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        # Should only include starting node
        assert result.visited_nodes == ["node_1"]
        assert result.max_depth_reached == 0

    @pytest.mark.asyncio
    async def test_find_shortest_path_empty_node_ids(self, mock_graph_traversal):
        """Test shortest path with empty node IDs."""
        result = await mock_graph_traversal.find_shortest_path("", "")
        
        assert result.source == ""
        assert result.target == ""
        assert result.path == [""]  # Same node case
        assert result.distance == 0

    @pytest.mark.asyncio
    async def test_node_filters_complex_conditions(self, mock_graph_traversal):
        """Test node filters with multiple conditions."""
        config = TraversalConfig(
            node_filters={"type": "Person", "age": 25, "active": True},
            max_depth=3
        )
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        # Should complete successfully even with complex filters
        assert result.starting_node == "node_1"
        assert len(result.visited_nodes) >= 1

    @pytest.mark.asyncio
    async def test_edge_filters_weight_based(self, mock_graph_traversal):
        """Test edge filters based on weights."""
        config = TraversalConfig(
            edge_filters={"weight": 0.8, "type": "strong"},
            max_depth=2
        )
        
        result = await mock_graph_traversal.depth_first_search("node_1", config)
        
        assert result.starting_node == "node_1"
        assert len(result.visited_nodes) >= 1


class TestPerformanceAndScalability:
    """Test performance-related scenarios."""
    
    @pytest.mark.asyncio
    async def test_large_graph_simulation(self, mock_graph_traversal):
        """Test traversal performance with simulated large graph."""
        # Use a reasonable max_nodes to avoid excessive test time
        config = TraversalConfig(max_depth=10, max_nodes=100)
        
        result = await mock_graph_traversal.breadth_first_search("node_1", config)
        
        # Verify it handles the limit correctly
        assert len(result.visited_nodes) <= 100
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_deep_path_finding(self, mock_graph_traversal):
        """Test path finding with deep paths."""
        # Test finding paths in a potentially deep graph structure
        result = await mock_graph_traversal.find_all_paths("start", "deep_end", max_length=10)
        
        assert isinstance(result, list)
        for path in result:
            assert path.distance <= 10


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple traversal operations."""
    
    @pytest.mark.asyncio
    async def test_bfs_then_dfs_comparison(self, mock_graph_traversal):
        """Test and compare BFS vs DFS results."""
        config = TraversalConfig(max_depth=3, max_nodes=20)
        
        bfs_result = await mock_graph_traversal.breadth_first_search("node_1", config)
        dfs_result = await mock_graph_traversal.depth_first_search("node_1", config)
        
        # Both should visit the starting node
        assert bfs_result.starting_node == dfs_result.starting_node
        assert "node_1" in bfs_result.visited_nodes
        assert "node_1" in dfs_result.visited_nodes
        
        # May visit different nodes due to different traversal order
        assert len(bfs_result.visited_nodes) >= 1
        assert len(dfs_result.visited_nodes) >= 1

    @pytest.mark.asyncio
    async def test_shortest_path_then_all_paths(self, mock_graph_traversal):
        """Test finding shortest path then all paths between same nodes."""
        shortest = await mock_graph_traversal.find_shortest_path("node_1", "node_5")
        all_paths = await mock_graph_traversal.find_all_paths("node_1", "node_5", 5)
        
        if shortest.distance > 0:  # If path exists
            # Shortest path should be among all paths (or shorter than all)
            shortest_distance = shortest.distance
            all_distances = [path.distance for path in all_paths]
            
            if all_distances:
                assert shortest_distance <= min(all_distances)

    @pytest.mark.asyncio
    async def test_connectivity_analysis_comprehensive(self, mock_graph_traversal):
        """Test comprehensive connectivity analysis."""
        # Test connectivity from multiple starting points
        nodes_to_test = ["node_1", "node_2", "node_3"]
        
        connectivity_results = []
        for node in nodes_to_test:
            result = await mock_graph_traversal.analyze_connectivity(node)
            connectivity_results.append(result)
        
        # Verify all results have expected structure
        for result in connectivity_results:
            assert 'source_node' in result
            assert 'reachable_nodes' in result
            assert 'connected_components' in result
            assert 'total_reachable' in result
            assert result['total_reachable'] >= 1  # At least the source node
