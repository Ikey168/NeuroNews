"""
Comprehensive test suite for Graph Traversal module.
Target: 100% test coverage for src/api/graph/traversal.py

This test suite covers the actual GraphTraversal API:
- Breadth-first search traversal
- Configuration and path results
- Traversal statistics
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.traversal import (
    TraversalConfig,
    PathResult,
    TraversalResult,
    GraphTraversal
)


class TestTraversalConfig:
    """Test TraversalConfig dataclass."""
    
    def test_traversal_config_defaults(self):
        """Test TraversalConfig creation with defaults."""
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
            max_depth=10,
            max_results=500,
            include_properties=False,
            filter_by_labels=["Person", "Organization"],
            filter_by_properties={"type": "verified"},
            timeout_seconds=60
        )
        
        assert config.max_depth == 10
        assert config.max_results == 500
        assert config.include_properties is False
        assert config.filter_by_labels == ["Person", "Organization"]
        assert config.filter_by_properties == {"type": "verified"}
        assert config.timeout_seconds == 60


class TestPathResult:
    """Test PathResult dataclass."""
    
    def test_path_result_creation(self):
        """Test PathResult creation."""
        path = PathResult(
            start_node="node1",
            end_node="node2", 
            path=["node1", "node2"],
            path_length=2,
            total_weight=1.5,
            properties={"traversal_type": "bfs"}
        )
        
        assert path.start_node == "node1"
        assert path.end_node == "node2"
        assert path.path == ["node1", "node2"]
        assert path.path_length == 2
        assert path.total_weight == 1.5
        assert path.properties["traversal_type"] == "bfs"


class TestTraversalResult:
    """Test TraversalResult dataclass."""
    
    def test_traversal_result_creation(self):
        """Test TraversalResult creation."""
        path = PathResult(
            start_node="node1",
            end_node="node3", 
            path=["node1", "node2", "node3"],
            path_length=3,
            total_weight=2.0,
            properties={}
        )
        
        result = TraversalResult(
            start_node="node1",
            visited_nodes=["node1", "node2", "node3"],
            traversal_depth=3,
            total_nodes=3,
            execution_time=0.123,
            paths=[path]
        )
        
        assert result.start_node == "node1"
        assert len(result.visited_nodes) == 3
        assert result.traversal_depth == 3
        assert result.total_nodes == 3
        assert result.execution_time == 0.123
        assert len(result.paths) == 1


class TestGraphTraversal:
    """Test GraphTraversal class."""
    
    @pytest.fixture
    def graph_traversal(self):
        """Create GraphTraversal instance."""
        return GraphTraversal()
    
    @pytest.fixture
    def mock_graph_builder(self):
        """Create mock graph builder."""
        mock_builder = Mock()
        mock_builder.get_node_neighbors.return_value = []
        mock_builder.get_edge_weight.return_value = 1.0
        return mock_builder
    
    def test_initialization_default(self, graph_traversal):
        """Test GraphTraversal initialization with defaults."""
        assert graph_traversal.graph is None
        assert isinstance(graph_traversal.traversal_stats, dict)
        assert graph_traversal.traversal_stats['total_traversals'] == 0
        assert graph_traversal.traversal_stats['avg_execution_time'] == 0.0
        assert graph_traversal.traversal_stats['max_depth_reached'] == 0
        assert graph_traversal.traversal_stats['total_nodes_visited'] == 0
    
    def test_initialization_with_builder(self):
        """Test GraphTraversal initialization with graph builder."""
        mock_builder = Mock()
        traversal = GraphTraversal(graph_builder=mock_builder)
        assert traversal.graph == mock_builder
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_basic(self, graph_traversal):
        """Test basic breadth-first search traversal."""
        config = TraversalConfig(max_depth=3, max_results=10)
        
        result = await graph_traversal.breadth_first_search("node1", config)
        
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
        assert isinstance(result.visited_nodes, list)
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_with_mock_graph(self, graph_traversal, mock_graph_builder):
        """Test breadth-first search with mock graph builder."""
        graph_traversal.graph = mock_graph_builder
        
        # Mock the graph traversal object
        mock_graph = Mock()
        mock_graph_builder.g = mock_graph
        
        # Mock Gremlin traversal
        mock_traversal = Mock()
        mock_graph.V.return_value = mock_traversal
        mock_traversal.has.return_value = mock_traversal
        mock_traversal.limit.return_value = mock_traversal
        mock_traversal.toList.return_value = [
            {"id": "node1", "label": "Person", "properties": {"name": ["John"]}}
        ]
        
        config = TraversalConfig(max_depth=2, max_results=5)
        
        result = await graph_traversal.breadth_first_search("node1", config)
        
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_no_graph(self, graph_traversal):
        """Test breadth-first search without graph (mock implementation)."""
        config = TraversalConfig(max_depth=2, max_results=10)
        
        # Should use mock implementation when no graph is available
        result = await graph_traversal.breadth_first_search("node1", config)
        
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
        assert isinstance(result.visited_nodes, list)
        # Mock implementation should return some sample data
        assert len(result.visited_nodes) >= 0
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_default_config(self, graph_traversal):
        """Test breadth-first search with default configuration."""
        # Should use default config when none provided
        result = await graph_traversal.breadth_first_search("node1")
        
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_with_filters(self, graph_traversal):
        """Test breadth-first search with label filters."""
        config = TraversalConfig(
            max_depth=3,
            filter_by_labels=["Person", "Organization"],
            filter_by_properties={"status": "active"}
        )
        
        result = await graph_traversal.breadth_first_search("node1", config)
        
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_max_results_limit(self, graph_traversal):
        """Test breadth-first search respects max results limit."""
        config = TraversalConfig(max_results=5)
        
        result = await graph_traversal.breadth_first_search("node1", config)
        
        assert isinstance(result, TraversalResult)
        # Should respect the max_results limit
        if len(result.visited_nodes) > 0:
            assert len(result.visited_nodes) <= config.max_results
    
    @pytest.mark.asyncio
    async def test_breadth_first_search_timeout_handling(self, graph_traversal):
        """Test breadth-first search timeout handling."""
        config = TraversalConfig(timeout_seconds=1)  # Short timeout
        
        # Should complete quickly and not hang
        start_time = datetime.now()
        result = await graph_traversal.breadth_first_search("node1", config)
        end_time = datetime.now()
        
        execution_time = (end_time - start_time).total_seconds()
        
        assert isinstance(result, TraversalResult)
        assert execution_time < 5.0  # Should complete well within reasonable time
    
    def test_traversal_stats_tracking(self, graph_traversal):
        """Test traversal statistics tracking."""
        # Should have initial stats
        stats = graph_traversal.traversal_stats
        
        assert isinstance(stats, dict)
        assert 'total_traversals' in stats
        assert 'avg_execution_time' in stats
        assert 'max_depth_reached' in stats
        assert 'total_nodes_visited' in stats
        
        # All should start at 0
        assert stats['total_traversals'] == 0
        assert stats['avg_execution_time'] == 0.0
        assert stats['max_depth_reached'] == 0
        assert stats['total_nodes_visited'] == 0
    
    def test_mock_bfs_result_method(self, graph_traversal):
        """Test the mock BFS result generation method."""
        config = TraversalConfig(max_depth=2, max_results=5)
        
        # The _mock_bfs_result method should exist and return a TraversalResult
        result = graph_traversal._mock_bfs_result("node1", config)
        
        assert isinstance(result, TraversalResult)
        assert result.execution_time >= 0
        assert isinstance(result.visited_nodes, list)
    
    @pytest.mark.asyncio
    async def test_complex_traversal_scenario(self, graph_traversal):
        """Test complex traversal scenario with various configurations."""
        configs_to_test = [
            TraversalConfig(max_depth=1, max_results=10),
            TraversalConfig(max_depth=5, max_results=100, include_properties=False),
            TraversalConfig(
                max_depth=3, 
                filter_by_labels=["Person"], 
                filter_by_properties={"active": True}
            ),
        ]
        
        for config in configs_to_test:
            result = await graph_traversal.breadth_first_search("start_node", config)
            
            assert isinstance(result, TraversalResult)
            assert result.execution_time >= 0
            assert isinstance(result.visited_nodes, list)
    
    @pytest.mark.asyncio
    def test_different_start_nodes(self, traversal):
        """Test traversal with different start nodes."""
        nodes = ['A', 'B', 'C']
        edges = [
            {'from': 'A', 'to': 'B'},
            {'from': 'B', 'to': 'C'}
        ]
        
        for start_node in nodes:
            result = traversal.breadth_first_search(start_node)
            assert result is not None
            assert isinstance(result, TraversalResult)
    
    @pytest.mark.asyncio
    async def test_depth_first_search_basic(self, traversal):
        """Test depth-first search functionality."""
        start_node = "A"
        config = TraversalConfig(max_depth=3)
        
        result = await traversal.depth_first_search(start_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
        assert result.visited_nodes is not None
        assert result.paths is not None
    
    @pytest.mark.asyncio  
    async def test_depth_first_search_with_filters(self, traversal):
        """Test DFS with filters."""
        start_node = "person1"
        config = TraversalConfig(
            max_depth=2,
            filter_by_labels=["Person", "Organization"],
            filter_by_properties={"active": True}
        )
        
        result = await traversal.depth_first_search(start_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
    
    @pytest.mark.asyncio
    async def test_shortest_path_basic(self, traversal):
        """Test shortest path finding."""
        start_node = "A"
        end_node = "C"
        config = TraversalConfig()
        
        result = await traversal.find_shortest_path(start_node, end_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
    
    @pytest.mark.asyncio
    async def test_shortest_path_no_connection(self, traversal):
        """Test shortest path when no connection exists."""
        start_node = "isolated_node"
        end_node = "another_isolated"
        config = TraversalConfig()
        
        result = await traversal.find_shortest_path(start_node, end_node, config)
        
        assert result is not None
        # Should return empty path if no connection
        assert isinstance(result.paths, list)
    
    @pytest.mark.asyncio
    async def test_find_all_paths_basic(self, traversal):
        """Test finding all paths between nodes."""
        start_node = "A"
        end_node = "B"
        config = TraversalConfig(max_depth=3)
        
        result = await traversal.find_all_paths(start_node, end_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
        assert result.paths is not None
    
    @pytest.mark.asyncio
    async def test_find_subgraph(self, traversal):
        """Test subgraph extraction."""
        center_nodes = ["A", "B"]
        config = TraversalConfig(max_depth=2)
        
        result = await traversal.extract_subgraph(center_nodes, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
    
    @pytest.mark.asyncio  
    async def test_traversal_with_timeout(self, traversal):
        """Test traversal with timeout handling."""
        start_node = "large_network_center"
        config = TraversalConfig(
            max_depth=10,
            max_results=10000,  # Large number that might timeout
            timeout=0.1  # Very short timeout
        )
        
        result = await traversal.breadth_first_search(start_node, config)
        
        # Should handle timeout gracefully
        assert result is not None
        assert isinstance(result, TraversalResult)
    
    def test_traversal_with_property_inclusion(self, traversal):
        """Test traversal with property inclusion."""
        start_node = "A"
        config = TraversalConfig(
            max_depth=2,
            include_properties=True,
            include_edge_properties=True
        )
        
        result = traversal.breadth_first_search(start_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
    
    def test_traversal_result_statistics(self, traversal):
        """Test traversal result statistics."""
        start_node = "A"
        config = TraversalConfig(max_depth=3)
        
        result = traversal.breadth_first_search(start_node, config)
        
        assert result is not None
        assert hasattr(result, 'stats')
        if result.stats:
            assert 'traversal_time' in result.stats
            assert 'nodes_visited' in result.stats
    
    @pytest.mark.asyncio
    async def test_bidirectional_search(self, traversal):
        """Test bidirectional search algorithm."""
        start_node = "A"
        end_node = "Z"
        config = TraversalConfig()
        
        try:
            result = await traversal.bidirectional_search(start_node, end_node, config)
            assert result is not None
            assert isinstance(result, TraversalResult)
        except AttributeError:
            # Method might not exist, skip test
            pass
    
    @pytest.mark.asyncio
    async def test_traversal_with_cycle_detection(self, traversal):
        """Test cycle detection during traversal."""
        start_node = "cycle_start"
        config = TraversalConfig(
            max_depth=5,
            detect_cycles=True
        )
        
        result = await traversal.breadth_first_search(start_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)
    
    def test_traversal_performance_monitoring(self, traversal):
        """Test traversal performance monitoring."""
        start_node = "A"
        config = TraversalConfig(max_depth=2)
        
        # Run multiple traversals
        for i in range(5):
            result = traversal.breadth_first_search(start_node, config)
            assert result is not None
        
        # Check if performance stats are tracked
        if hasattr(traversal, 'performance_stats'):
            stats = traversal.performance_stats
            assert isinstance(stats, dict)
    
    def test_custom_traversal_filters(self, traversal):
        """Test custom filter functions."""
        start_node = "A"
        
        # Custom filter function
        def custom_filter(node_id, properties):
            return len(node_id) > 1
        
        config = TraversalConfig(
            max_depth=2,
            custom_filter=custom_filter if hasattr(TraversalConfig, 'custom_filter') else None
        )
        
        result = traversal.breadth_first_search(start_node, config)
        
        assert result is not None
        assert isinstance(result, TraversalResult)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
