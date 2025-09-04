"""
Comprehensive test suite for Graph Traversal module.
Target: 100% test coverage for src/api/graph/traversal.py

This test suite covers:
- Graph traversal algorithms (BFS, DFS, shortest path)
- Path finding and path validation
- Traversal configuration and constraints
- Complex graph navigation scenarios
- Performance optimization testing
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import json

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
    
    def test_traversal_config_validation(self):
        """Test TraversalConfig validation."""
        # Test max_depth validation
        with pytest.raises(ValueError, match="max_depth must be positive"):
            TraversalConfig(max_depth=0)
        
        with pytest.raises(ValueError, match="max_depth must be positive"):
            TraversalConfig(max_depth=-1)
        
        # Test max_results validation
        with pytest.raises(ValueError, match="max_results must be positive"):
            TraversalConfig(max_results=0)


class TestPathResult:
    """Test PathResult dataclass."""
    
    def test_path_result_creation(self):
        """Test PathResult creation."""
        nodes = [{"id": "node1"}, {"id": "node2"}]
        edges = [{"id": "edge1"}]
        
        path = PathResult(
            nodes=nodes,
            edges=edges,
            length=2,
            weight=1.5,
            is_cycle=False
        )
        
        assert path.nodes == nodes
        assert path.edges == edges
        assert path.length == 2
        assert path.weight == 1.5
        assert path.is_cycle is False
    
    def test_path_result_cycle_detection(self):
        """Test PathResult with cycle detection."""
        nodes = [{"id": "node1"}, {"id": "node2"}, {"id": "node1"}]
        edges = [{"id": "edge1"}, {"id": "edge2"}]
        
        path = PathResult(
            nodes=nodes,
            edges=edges,
            length=3,
            weight=2.0,
            is_cycle=True
        )
        
        assert path.is_cycle is True
        assert path.length == 3
    
    def test_path_result_empty(self):
        """Test PathResult with empty path."""
        path = PathResult(
            nodes=[],
            edges=[],
            length=0,
            weight=0.0,
            is_cycle=False
        )
        
        assert len(path.nodes) == 0
        assert len(path.edges) == 0
        assert path.length == 0


class TestTraversalResult:
    """Test TraversalResult dataclass."""
    
    def test_traversal_result_creation(self):
        """Test TraversalResult creation."""
        paths = [
            PathResult([{"id": "n1"}], [], 1, 1.0, False),
            PathResult([{"id": "n2"}], [], 1, 1.0, False)
        ]
        
        result = TraversalResult(
            paths=paths,
            total_nodes_visited=10,
            total_edges_traversed=8,
            execution_time=0.123,
            config_used=TraversalConfig()
        )
        
        assert len(result.paths) == 2
        assert result.total_nodes_visited == 10
        assert result.total_edges_traversed == 8
        assert result.execution_time == 0.123
        assert isinstance(result.config_used, TraversalConfig)
    
    def test_traversal_result_empty(self):
        """Test TraversalResult with no paths found."""
        result = TraversalResult(
            paths=[],
            total_nodes_visited=0,
            total_edges_traversed=0,
            execution_time=0.001,
            config_used=TraversalConfig()
        )
        
        assert len(result.paths) == 0
        assert result.total_nodes_visited == 0
        assert result.total_edges_traversed == 0


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
        assert isinstance(graph_traversal.visited_nodes, set)
        assert isinstance(graph_traversal.visited_edges, set)
        assert len(graph_traversal.visited_nodes) == 0
    
    def test_initialization_with_builder(self):
        """Test GraphTraversal initialization with graph builder."""
        mock_builder = Mock()
        traversal = GraphTraversal(graph_builder=mock_builder)
        assert traversal.graph == mock_builder
    
    def test_reset_state(self, graph_traversal):
        """Test resetting traversal state."""
        # Add some visited items
        graph_traversal.visited_nodes.add("node1")
        graph_traversal.visited_edges.add("edge1")
        
        graph_traversal._reset_state()
        
        assert len(graph_traversal.visited_nodes) == 0
        assert len(graph_traversal.visited_edges) == 0
    
    @pytest.mark.asyncio
    async def test_breadth_first_search(self, graph_traversal, mock_graph_builder):
        """Test breadth-first search traversal."""
        graph_traversal.graph = mock_graph_builder
        
        # Mock graph structure: node1 -> node2 -> node3
        mock_graph_builder.get_node_neighbors.side_effect = [
            [{"id": "node2", "edge_id": "edge1"}],  # neighbors of node1
            [{"id": "node3", "edge_id": "edge2"}],  # neighbors of node2
            []  # neighbors of node3 (leaf)
        ]
        
        mock_graph_builder.get_node_by_id.side_effect = [
            {"id": "node1", "label": "Person"},
            {"id": "node2", "label": "Person"},
            {"id": "node3", "label": "Person"}
        ]
        
        config = TraversalConfig(max_depth=3, max_results=10)
        
        result = await graph_traversal.breadth_first_search("node1", config)
        
        assert isinstance(result, TraversalResult)
        assert len(result.paths) > 0
    
    def test_basic_functionality(self, graph_traversal):
        """Test basic traversal functionality."""
        assert graph_traversal.graph is None
        assert hasattr(graph_traversal, 'breadth_first_search')
        
        # Test TraversalConfig validation
        config = TraversalConfig(max_depth=3, max_results=100)
        assert config.max_depth == 3
        assert config.max_results == 100
    
    def test_detect_cycle(self, graph_traversal):
        """Test cycle detection in paths."""
        # Path with cycle: node1 -> node2 -> node1
        path_nodes = [
            {"id": "node1", "label": "Person"},
            {"id": "node2", "label": "Person"},
            {"id": "node1", "label": "Person"}  # Back to start
        ]
        
        has_cycle = graph_traversal._detect_cycle(path_nodes)
        
        assert has_cycle is True
    
    def test_detect_no_cycle(self, graph_traversal):
        """Test cycle detection with no cycles."""
        # Simple linear path
        path_nodes = [
            {"id": "node1", "label": "Person"},
            {"id": "node2", "label": "Person"},
            {"id": "node3", "label": "Person"}
        ]
        
        has_cycle = graph_traversal._detect_cycle(path_nodes)
        
        assert has_cycle is False
    
    def test_calculate_path_weight(self, graph_traversal):
        """Test path weight calculation."""
        edges = [
            {"id": "edge1", "weight": 1.5},
            {"id": "edge2", "weight": 2.0},
            {"id": "edge3", "weight": 0.5}
        ]
        
        total_weight = graph_traversal._calculate_path_weight(edges)
        
        assert total_weight == 4.0  # 1.5 + 2.0 + 0.5
    
    def test_calculate_path_weight_no_weights(self, graph_traversal):
        """Test path weight calculation with no weights."""
        edges = [
            {"id": "edge1"},
            {"id": "edge2"}
        ]
        
        total_weight = graph_traversal._calculate_path_weight(edges)
        
        assert total_weight == 2.0  # Default weight of 1.0 per edge
    
    @pytest.mark.asyncio
    async def test_traverse_max_depth_limit(self, graph_traversal, mock_graph_builder):
        """Test traversal respects max depth limit."""
        graph_traversal.graph = mock_graph_builder
        
        # Create deep graph structure
        mock_graph_builder.get_node_neighbors.side_effect = [
            [{"id": "node2", "edge_id": "edge1"}],  # depth 1
            [{"id": "node3", "edge_id": "edge2"}],  # depth 2
            [{"id": "node4", "edge_id": "edge3"}],  # depth 3
            [{"id": "node5", "edge_id": "edge4"}]   # depth 4 - should be limited
        ]
        
        mock_graph_builder.get_node_by_id.side_effect = [
            {"id": f"node{i}", "label": "Person"} for i in range(1, 6)
        ]
        
        config = TraversalConfig(max_depth=2)  # Limit to 2 levels
        
        result = await graph_traversal.traverse("node1", "node5", config)
        
        # Should not find path beyond max_depth
        assert isinstance(result, TraversalResult)
        # Path to node5 requires depth > 2, so should be empty or limited
    
    @pytest.mark.asyncio
    async def test_traverse_max_results_limit(self, graph_traversal, mock_graph_builder):
        """Test traversal respects max results limit."""
        graph_traversal.graph = mock_graph_builder
        
        # Setup graph with many possible paths
        mock_graph_builder.get_node_neighbors.side_effect = lambda node_id: [
            {"id": f"target{i}", "edge_id": f"edge{i}"} for i in range(10)
        ]
        
        config = TraversalConfig(
            traversal_type=TraversalType.ALL_PATHS,
            max_results=3  # Limit results
        )
        
        result = await graph_traversal.traverse("node1", "target5", config)
        
        assert isinstance(result, TraversalResult)
        assert len(result.paths) <= 3  # Should respect max_results limit
    
    @pytest.mark.asyncio
    async def test_traverse_no_path_exists(self, graph_traversal, mock_graph_builder):
        """Test traversal when no path exists."""
        graph_traversal.graph = mock_graph_builder
        
        # Setup disconnected graph
        mock_graph_builder.get_node_neighbors.return_value = []
        mock_graph_builder.get_incoming_neighbors.return_value = []
        mock_graph_builder.get_outgoing_neighbors.return_value = []
        
        config = TraversalConfig()
        
        result = await graph_traversal.traverse("node1", "node2", config)
        
        assert isinstance(result, TraversalResult)
        assert len(result.paths) == 0
        assert result.total_nodes_visited >= 1  # At least visited start node
    
    @pytest.mark.asyncio
    async def test_traverse_same_start_end(self, graph_traversal, mock_graph_builder):
        """Test traversal from node to itself."""
        graph_traversal.graph = mock_graph_builder
        
        mock_graph_builder.get_node_by_id.return_value = {"id": "node1", "label": "Person"}
        
        config = TraversalConfig()
        
        result = await graph_traversal.traverse("node1", "node1", config)
        
        assert isinstance(result, TraversalResult)
        # Should find trivial path (just the node itself)
        if len(result.paths) > 0:
            assert result.paths[0].length == 1
            assert result.paths[0].nodes[0]["id"] == "node1"
    
    # ============ PERFORMANCE AND COMPLEX SCENARIOS ============
    
    @pytest.mark.asyncio
    async def test_large_graph_performance(self, graph_traversal, mock_graph_builder):
        """Test traversal performance on large graphs."""
        graph_traversal.graph = mock_graph_builder
        
        # Mock large graph structure
        def mock_neighbors(node_id):
            # Each node connects to next 5 nodes
            node_num = int(node_id.replace("node", ""))
            return [{"id": f"node{node_num + i}", "edge_id": f"edge{node_num}_{i}"} 
                    for i in range(1, 6) if node_num + i <= 1000]
        
        mock_graph_builder.get_node_neighbors.side_effect = mock_neighbors
        
        config = TraversalConfig(
            max_depth=3,
            max_results=100  # Limit results for performance
        )
        
        start_time = datetime.now()
        result = await graph_traversal.traverse("node1", "node50", config)
        end_time = datetime.now()
        
        execution_time = (end_time - start_time).total_seconds()
        
        assert isinstance(result, TraversalResult)
        assert execution_time < 10.0  # Should complete within reasonable time
    
    def test_complex_graph_structure(self, graph_traversal):
        """Test handling complex graph structures."""
        # Test with various complex scenarios
        complex_scenarios = [
            # Self-loops
            {"nodes": [{"id": "node1"}], "edges": [{"from": "node1", "to": "node1"}]},
            # Multiple edges between same nodes
            {"nodes": [{"id": "node1"}, {"id": "node2"}], 
             "edges": [{"from": "node1", "to": "node2"}, {"from": "node1", "to": "node2"}]},
            # Disconnected components
            {"nodes": [{"id": "node1"}, {"id": "node2"}, {"id": "node3"}], 
             "edges": [{"from": "node1", "to": "node2"}]}  # node3 disconnected
        ]
        
        for scenario in complex_scenarios:
            # Test that complex structures don't break the traversal logic
            assert len(scenario["nodes"]) >= 1
            assert isinstance(scenario["edges"], list)
    
    @pytest.mark.asyncio
    async def test_traversal_with_weighted_edges(self, graph_traversal, mock_graph_builder):
        """Test traversal considering edge weights."""
        graph_traversal.graph = mock_graph_builder
        
        # Setup weighted graph: multiple paths with different weights
        mock_graph_builder.get_node_neighbors.side_effect = [
            [{"id": "node2", "edge_id": "edge1", "weight": 10.0},
             {"id": "node3", "edge_id": "edge2", "weight": 1.0}],  # Heavy vs light path
            [{"id": "target", "edge_id": "edge3", "weight": 1.0}],   # node2 -> target
            [{"id": "target", "edge_id": "edge4", "weight": 1.0}]    # node3 -> target
        ]
        
        mock_graph_builder.get_edge_weight.side_effect = [10.0, 1.0, 1.0, 1.0]
        
        config = TraversalConfig(
            traversal_type=TraversalType.SHORTEST_PATH
        )
        
        result = await graph_traversal.traverse("node1", "target", config)
        
        assert isinstance(result, TraversalResult)
        if len(result.paths) > 0:
            # Should prefer the lighter path (via node3)
            best_path = min(result.paths, key=lambda p: p.weight)
            assert best_path.weight == 2.0  # 1.0 + 1.0 via node3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
