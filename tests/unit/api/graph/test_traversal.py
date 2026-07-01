"""
Tests for Graph Traversal Module

This test suite exercises the traversal algorithms, pathfinding methods, and
edge cases of src/api/graph/traversal.py. Tests are aligned to the current
source API.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.api.graph.traversal import (
    GraphTraversal,
    TraversalConfig,
    PathResult,
    TraversalResult,
)


@pytest.fixture
def graph_traversal():
    """Create a GraphTraversal instance backed by a mock graph builder."""
    mock_graph = Mock()
    mock_graph.g = Mock()
    return GraphTraversal(mock_graph)


@pytest.fixture
def mock_graph_traversal():
    """Create a GraphTraversal instance without a graph builder (mock mode)."""
    return GraphTraversal()


class TestTraversalConfig:
    """Test TraversalConfig dataclass."""

    def test_traversal_config_default(self):
        """Test TraversalConfig with default values."""
        config = TraversalConfig()

        assert config.max_depth == 5
        assert config.max_results == 1000
        assert config.include_properties is True
        assert config.filter_by_labels is None
        assert config.filter_by_properties is None
        assert config.timeout_seconds == 30

    def test_traversal_config_custom(self):
        """Test TraversalConfig with custom values."""
        config = TraversalConfig(
            max_depth=5,
            max_results=500,
            include_properties=False,
            filter_by_labels=["Person"],
            filter_by_properties={"weight": 0.5},
            timeout_seconds=15,
        )

        assert config.max_depth == 5
        assert config.max_results == 500
        assert config.include_properties is False
        assert config.filter_by_labels == ["Person"]
        assert config.filter_by_properties == {"weight": 0.5}
        assert config.timeout_seconds == 15


class TestPathResult:
    """Test PathResult dataclass."""

    def test_path_result_creation(self):
        """Test PathResult creation."""
        path_result = PathResult(
            start_node="node_1",
            end_node="node_3",
            path=["node_1", "node_2", "node_3"],
            path_length=2,
            total_weight=1.5,
            properties={"name": "demo"},
        )

        assert path_result.start_node == "node_1"
        assert path_result.end_node == "node_3"
        assert path_result.path == ["node_1", "node_2", "node_3"]
        assert path_result.path_length == 2
        assert path_result.total_weight == 1.5
        assert path_result.properties == {"name": "demo"}


class TestTraversalResult:
    """Test TraversalResult dataclass."""

    def test_traversal_result_creation(self):
        """Test TraversalResult creation."""
        paths = [
            PathResult(
                start_node="node_1",
                end_node="node_3",
                path=["node_1", "node_2", "node_3"],
                path_length=2,
                total_weight=2.0,
                properties={},
            )
        ]
        result = TraversalResult(
            start_node="node_1",
            visited_nodes=["node_1", "node_2", "node_3"],
            traversal_depth=2,
            total_nodes=3,
            execution_time=0.5,
            paths=paths,
        )

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) == 3
        assert result.traversal_depth == 2
        assert result.total_nodes == 3
        assert result.execution_time == 0.5
        assert len(result.paths) == 1


class TestGraphTraversal:
    """Test GraphTraversal class methods."""

    def test_initialization(self, graph_traversal):
        """Test GraphTraversal initialization with graph."""
        assert graph_traversal.graph is not None
        assert hasattr(graph_traversal, "traversal_stats")
        assert graph_traversal.traversal_stats["total_traversals"] == 0

    def test_initialization_without_graph(self, mock_graph_traversal):
        """Test GraphTraversal initialization without graph."""
        assert mock_graph_traversal.graph is None
        assert hasattr(mock_graph_traversal, "traversal_stats")

    @pytest.mark.asyncio
    async def test_breadth_first_search_mock_basic(self, mock_graph_traversal):
        """Test basic BFS with the mock implementation."""
        config = TraversalConfig(max_depth=2)

        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) > 0
        assert result.traversal_depth <= 2
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_breadth_first_search_mock_with_filters(self, mock_graph_traversal):
        """Test BFS with label and property filters in mock mode."""
        config = TraversalConfig(
            max_depth=3,
            filter_by_labels=["Person"],
            filter_by_properties={"relationship": "FRIENDS"},
        )

        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) >= 1

    @pytest.mark.asyncio
    async def test_breadth_first_search_with_graph(self, graph_traversal):
        """Test BFS with the real graph implementation path."""
        # Mock graph responses. valueMap(True).next() supplies properties,
        # both()...id().toList() supplies neighbors.
        value_map = Mock()
        value_map.next = AsyncMock(return_value={"name": ["Mock"]})

        neighbors_query = Mock()
        neighbors_query.id = Mock(return_value=neighbors_query)
        neighbors_query.toList = AsyncMock(return_value=["node_2", "node_3"])

        vertex = Mock()
        vertex.valueMap = Mock(return_value=value_map)
        vertex.both = Mock(return_value=neighbors_query)

        graph_traversal.graph.g.V = Mock(return_value=vertex)

        config = TraversalConfig(max_depth=2)
        result = await graph_traversal.breadth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) > 0
        assert "node_1" in result.visited_nodes

    @pytest.mark.asyncio
    async def test_breadth_first_search_max_results_limit(self, mock_graph_traversal):
        """Test BFS respects the max_results limit in mock mode."""
        config = TraversalConfig(max_depth=10, max_results=2)

        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        # Mock implementation caps visited nodes at min(10, max_results).
        assert len(result.visited_nodes) <= 2

    @pytest.mark.asyncio
    async def test_depth_first_search_mock_basic(self, mock_graph_traversal):
        """Test basic DFS with the mock implementation."""
        config = TraversalConfig(max_depth=3)

        result = await mock_graph_traversal.depth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) > 0
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_depth_first_search_produces_paths(self, mock_graph_traversal):
        """Test DFS mock produces path results starting from the start node."""
        config = TraversalConfig(max_depth=2)

        result = await mock_graph_traversal.depth_first_search("node_1", config)

        assert result.paths is not None
        assert len(result.paths) > 0
        for path_result in result.paths:
            assert isinstance(path_result, PathResult)
            assert path_result.start_node == "node_1"
            assert path_result.path[0] == "node_1"

    @pytest.mark.asyncio
    async def test_depth_first_search_with_graph(self, graph_traversal):
        """Test DFS with the real graph implementation path."""
        value_map = Mock()
        value_map.next = AsyncMock(return_value={"name": ["Mock"]})

        neighbors_query = Mock()
        neighbors_query.id = Mock(return_value=neighbors_query)
        neighbors_query.toList = AsyncMock(return_value=["node_2", "node_3"])

        vertex = Mock()
        vertex.valueMap = Mock(return_value=value_map)
        vertex.both = Mock(return_value=neighbors_query)

        graph_traversal.graph.g.V = Mock(return_value=vertex)

        config = TraversalConfig(max_depth=2)
        result = await graph_traversal.depth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) > 0

    @pytest.mark.asyncio
    async def test_find_shortest_path_mock_basic(self, mock_graph_traversal):
        """Test basic shortest path finding with the mock implementation."""
        result = await mock_graph_traversal.find_shortest_path("node_1", "node_3")

        assert result.start_node == "node_1"
        assert result.end_node == "node_3"
        assert result.path is not None
        assert len(result.path) >= 2  # At least source and target
        assert result.path[0] == "node_1"
        assert result.path[-1] == "node_3"
        assert result.path_length >= 0

    @pytest.mark.asyncio
    async def test_find_shortest_path_same_node(self, mock_graph_traversal):
        """Test shortest path when source equals target."""
        result = await mock_graph_traversal.find_shortest_path("node_1", "node_1")

        assert result.start_node == "node_1"
        assert result.end_node == "node_1"
        assert result.path == ["node_1"]
        assert result.path_length == 0
        assert result.total_weight == 0.0

    @pytest.mark.asyncio
    async def test_find_shortest_path_no_path_with_graph(self, graph_traversal):
        """Test shortest path returns None when the target is unreachable."""
        neighbors_query = Mock()
        neighbors_query.id = Mock(return_value=neighbors_query)
        neighbors_query.toList = AsyncMock(return_value=[])  # No neighbors

        vertex = Mock()
        vertex.both = Mock(return_value=neighbors_query)

        graph_traversal.graph.g.V = Mock(return_value=vertex)

        result = await graph_traversal.find_shortest_path("node_1", "unreachable")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_shortest_path_with_graph(self, graph_traversal):
        """Test shortest path with the real graph implementation path."""
        # node_1 -> node_2 -> node_3
        def neighbors_for(node_id):
            mapping = {
                "node_1": ["node_2"],
                "node_2": ["node_3"],
                "node_3": [],
            }
            query = Mock()
            query.both = Mock(return_value=query)
            query.id = Mock(return_value=query)
            query.toList = AsyncMock(return_value=mapping.get(node_id, []))
            return query

        graph_traversal.graph.g.V = Mock(side_effect=neighbors_for)

        result = await graph_traversal.find_shortest_path("node_1", "node_3")

        assert result is not None
        assert result.start_node == "node_1"
        assert result.end_node == "node_3"
        assert len(result.path) >= 2
        assert result.path[0] == "node_1"
        assert result.path[-1] == "node_3"

    @pytest.mark.asyncio
    async def test_find_all_paths_mock_basic(self, mock_graph_traversal):
        """Test finding all paths with the mock implementation."""
        result = await mock_graph_traversal.find_all_paths("node_1", "node_3", max_depth=3)

        assert isinstance(result, list)
        assert len(result) > 0
        for path in result:
            assert isinstance(path, PathResult)
            assert path.start_node == "node_1"
            assert path.end_node == "node_3"

    @pytest.mark.asyncio
    async def test_find_all_paths_respects_max_paths(self, mock_graph_traversal):
        """Test that find_all_paths respects the max_paths limit."""
        result = await mock_graph_traversal.find_all_paths(
            "node_1", "node_4", max_depth=2, max_paths=2
        )

        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_find_all_paths_same_node(self, mock_graph_traversal):
        """Test finding all paths when source equals target."""
        result = await mock_graph_traversal.find_all_paths("node_1", "node_1", max_depth=5)

        # Should include the trivial path (just the node itself).
        trivial_paths = [path for path in result if len(path.path) == 1]
        assert len(trivial_paths) >= 1
        assert trivial_paths[0].path == ["node_1"]
        assert trivial_paths[0].path_length == 0

    @pytest.mark.asyncio
    async def test_find_all_paths_with_graph(self, graph_traversal):
        """Test finding all paths with the real graph implementation path."""
        # node_1 connects to node_2 and node_4, both of which connect to node_3.
        def neighbors_for(node_id):
            mapping = {
                "node_1": ["node_2", "node_4"],
                "node_2": ["node_3"],
                "node_4": ["node_3"],
                "node_3": [],
            }
            query = Mock()
            query.both = Mock(return_value=query)
            query.id = Mock(return_value=query)
            query.toList = AsyncMock(return_value=mapping.get(node_id, []))
            return query

        graph_traversal.graph.g.V = Mock(side_effect=neighbors_for)

        result = await graph_traversal.find_all_paths("node_1", "node_3", max_depth=5)

        assert len(result) >= 1
        for path in result:
            assert path.start_node == "node_1"
            assert path.end_node == "node_3"

    @pytest.mark.asyncio
    async def test_get_node_neighbors_mock(self, mock_graph_traversal):
        """Test get_node_neighbors with the mock implementation."""
        neighbors = await mock_graph_traversal.get_node_neighbors("node_1")

        assert isinstance(neighbors, list)
        assert len(neighbors) >= 1
        for neighbor in neighbors:
            assert "id" in neighbor
            assert "label" in neighbor

    @pytest.mark.asyncio
    async def test_get_node_neighbors_with_labels(self, mock_graph_traversal):
        """Test get_node_neighbors applies the requested label in mock mode."""
        neighbors = await mock_graph_traversal.get_node_neighbors(
            "node_1", direction="out", labels=["Person"]
        )

        assert all(neighbor["label"] == "Person" for neighbor in neighbors)

    @pytest.mark.asyncio
    async def test_get_node_neighbors_with_graph_direction(self, graph_traversal):
        """Test get_node_neighbors uses the requested direction with a real graph."""
        query = Mock()
        query.hasLabel = Mock(return_value=query)
        query.valueMap = Mock(return_value=query)
        query.toList = AsyncMock(return_value=[{"id": ["node_2"]}])

        vertex = Mock()
        vertex.out = Mock(return_value=query)
        vertex.in_ = Mock(return_value=query)
        vertex.both = Mock(return_value=query)

        graph_traversal.graph.g.V = Mock(return_value=vertex)

        await graph_traversal.get_node_neighbors("node_1", direction="out")
        vertex.out.assert_called()

    @pytest.mark.asyncio
    async def test_analyze_graph_connectivity_mock(self, mock_graph_traversal):
        """Test connectivity analysis with the mock implementation."""
        result = await mock_graph_traversal.analyze_graph_connectivity()

        assert "total_nodes" in result
        assert "total_edges" in result
        assert "average_degree" in result
        assert "connected_components" in result
        assert result["total_nodes"] >= 0

    @pytest.mark.asyncio
    async def test_graph_exception_handling(self, graph_traversal):
        """Test that neighbor-fetch errors are caught and the traversal still
        records the start node rather than crashing."""
        graph_traversal.graph.g.V = Mock(side_effect=Exception("Graph connection error"))

        config = TraversalConfig()

        # The current source swallows per-node neighbor errors (logged as a
        # warning) and the start node is still visited.
        result = await graph_traversal.breadth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert result.visited_nodes == ["node_1"]
        assert result.total_nodes == 1
        assert result.paths == []

    def test_get_traversal_statistics(self, mock_graph_traversal):
        """Test traversal statistics retrieval returns the expected structure."""
        stats = mock_graph_traversal.get_traversal_statistics()

        assert "total_traversals" in stats
        assert "avg_execution_time" in stats
        assert "total_nodes_visited" in stats

    def test_reset_statistics(self, mock_graph_traversal):
        """Test resetting traversal statistics."""
        mock_graph_traversal.traversal_stats["total_traversals"] = 5
        mock_graph_traversal.reset_statistics()

        assert mock_graph_traversal.traversal_stats["total_traversals"] == 0
        assert mock_graph_traversal.traversal_stats["total_nodes_visited"] == 0

    def test_traversal_config_validation(self):
        """Test TraversalConfig accepts edge-case parameter values."""
        # Extreme values should be accepted as-is.
        config = TraversalConfig(max_depth=0, max_results=0)
        assert config.max_depth == 0
        assert config.max_results == 0


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling scenarios."""

    @pytest.mark.asyncio
    async def test_bfs_mock_limited_by_max_results(self, mock_graph_traversal):
        """Test mock BFS visited node count is bounded by max_results."""
        config = TraversalConfig(max_depth=5, max_results=1)
        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) <= 1
        assert result.total_nodes == len(result.visited_nodes)

    @pytest.mark.asyncio
    async def test_very_large_max_depth(self, mock_graph_traversal):
        """Test traversal with a very large max_depth bounded by max_results."""
        config = TraversalConfig(max_depth=1000000, max_results=5)

        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        # Should be limited by max_results, not max_depth.
        assert len(result.visited_nodes) <= 5

    @pytest.mark.asyncio
    async def test_find_shortest_path_empty_node_ids(self, mock_graph_traversal):
        """Test shortest path with empty (and equal) node IDs."""
        result = await mock_graph_traversal.find_shortest_path("", "")

        assert result.start_node == ""
        assert result.end_node == ""
        assert result.path == [""]  # Same node case
        assert result.path_length == 0

    @pytest.mark.asyncio
    async def test_filters_complex_conditions(self, mock_graph_traversal):
        """Test traversal with multiple property filter conditions."""
        config = TraversalConfig(
            filter_by_properties={"type": "Person", "age": 25, "active": True},
            max_depth=3,
        )

        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) >= 1

    @pytest.mark.asyncio
    async def test_label_filters(self, mock_graph_traversal):
        """Test DFS traversal with label filters."""
        config = TraversalConfig(
            filter_by_labels=["Person", "Topic"],
            max_depth=2,
        )

        result = await mock_graph_traversal.depth_first_search("node_1", config)

        assert result.start_node == "node_1"
        assert len(result.visited_nodes) >= 1


class TestPerformanceAndScalability:
    """Test performance-related scenarios."""

    @pytest.mark.asyncio
    async def test_large_graph_simulation(self, mock_graph_traversal):
        """Test traversal with a simulated larger result cap."""
        config = TraversalConfig(max_depth=10, max_results=100)

        result = await mock_graph_traversal.breadth_first_search("node_1", config)

        assert len(result.visited_nodes) <= 100
        assert result.execution_time > 0

    @pytest.mark.asyncio
    async def test_deep_path_finding(self, mock_graph_traversal):
        """Test path finding returns PathResult objects in mock mode."""
        result = await mock_graph_traversal.find_all_paths(
            "start", "deep_end", max_depth=10
        )

        assert isinstance(result, list)
        for path in result:
            assert isinstance(path, PathResult)
            assert path.start_node == "start"
            assert path.end_node == "deep_end"


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple traversal operations."""

    @pytest.mark.asyncio
    async def test_bfs_then_dfs_comparison(self, mock_graph_traversal):
        """Test and compare BFS vs DFS results."""
        config = TraversalConfig(max_depth=3, max_results=20)

        bfs_result = await mock_graph_traversal.breadth_first_search("node_1", config)
        dfs_result = await mock_graph_traversal.depth_first_search("node_1", config)

        # Both should report the same starting node.
        assert bfs_result.start_node == dfs_result.start_node
        assert len(bfs_result.visited_nodes) >= 1
        assert len(dfs_result.visited_nodes) >= 1

    @pytest.mark.asyncio
    async def test_shortest_path_then_all_paths(self, mock_graph_traversal):
        """Test finding shortest path then all paths between the same nodes."""
        shortest = await mock_graph_traversal.find_shortest_path("node_1", "node_5")
        all_paths = await mock_graph_traversal.find_all_paths("node_1", "node_5", max_depth=5)

        assert shortest.start_node == "node_1"
        assert shortest.end_node == "node_5"
        assert isinstance(all_paths, list)
        for path in all_paths:
            assert path.start_node == "node_1"
            assert path.end_node == "node_5"

    @pytest.mark.asyncio
    async def test_connectivity_analysis_structure(self, mock_graph_traversal):
        """Test connectivity analysis returns the expected structure."""
        result = await mock_graph_traversal.analyze_graph_connectivity()

        assert "total_nodes" in result
        assert "total_edges" in result
        assert "average_degree" in result
        assert "connected_components" in result
        assert "analysis_time" in result
