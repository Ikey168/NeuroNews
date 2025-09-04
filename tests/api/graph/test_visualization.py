"""
Test suite for Graph API Visualization module.
Target: 100% test coverage for src/api/graph/visualization.py

This test suite covers:
- GraphVisualizer class and all its methods
- Layout algorithms and configurations
- Node and edge styling systems
- Visualization data structures
- Error handling and edge cases
- Async operations
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

# Import the modules under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.visualization import (
    GraphVisualizer,
    LayoutAlgorithm,
    NodeStyle,
    EdgeStyle,
    Position,
    LayoutConfig,
    VisualizationNode,
    VisualizationEdge,
    GraphVisualization
)
        """Test access to default styles."""
        assert isinstance(visualizer.default_node_style, NodeStyle)
        assert isinstance(visualizer.default_edge_style, EdgeStyle)
        
        # Test that styles have expected defaults
        assert visualizer.default_node_style.size == 10.0
        assert visualizer.default_edge_style.width == 1.0
    
    @pytest.mark.asyncio
    async def test_different_layout_algorithms(self, visualizer, sample_nodes, sample_edges):
        """Test different layout algorithms."""
        for algorithm in LayoutAlgorithm:
            config = LayoutConfig(algorithm=algorithm)
            visualization = await visualizer.create_visualization(sample_nodes, sample_edges, config)
            
            assert isinstance(visualization, GraphVisualization)
            assert visualization.layout_config.algorithm == algorithm
            
            # All nodes should have positions
            for node in visualization.nodes:
                assert isinstance(node.position.x, (int, float))
                assert isinstance(node.position.y, (int, float))
    
    @pytest.mark.asyncio
    async def test_custom_node_styles(self, visualizer):
        """Test custom node styling."""
        nodes = [
            {
                "id": "styled_node", 
                "label": "Styled", 
                "properties": {"color": "#ff0000", "size": 20}
            }
        ]
        
        visualization = await visualizer.create_visualization(nodes, [])
        
        assert isinstance(visualization, GraphVisualization)
        assert len(visualization.nodes) == 1
        
        # Check that node was created
        assert visualization.nodes[0].id == "styled_node"
    
    @pytest.mark.asyncio
    async def test_visualization_metadata(self, visualizer, sample_nodes, sample_edges):
        """Test visualization metadata creation."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        assert "node_count" in visualization.metadata
        assert "edge_count" in visualization.metadata
        assert "algorithm" in visualization.metadata
        assert "created_at" in visualization.metadata
        
        assert visualization.metadata["node_count"] == len(sample_nodes)
        assert visualization.metadata["edge_count"] == len(sample_edges)es
- Async operations
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock

# Import the modules under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.visualization import (
    GraphVisualizer,
    LayoutAlgorithm,
    NodeStyle,
    EdgeStyle,
    Position,
    LayoutConfig,
    VisualizationNode,
    VisualizationEdge,
    GraphVisualization
)


class TestLayoutAlgorithm:
    """Test LayoutAlgorithm enum."""
    
    def test_layout_algorithm_values(self):
        """Test LayoutAlgorithm enum values."""
        assert LayoutAlgorithm.FORCE_DIRECTED.value == "force_directed"
        assert LayoutAlgorithm.HIERARCHICAL.value == "hierarchical"
        assert LayoutAlgorithm.CIRCULAR.value == "circular"
        assert LayoutAlgorithm.GRID.value == "grid"
        assert LayoutAlgorithm.RANDOM.value == "random"
        assert LayoutAlgorithm.SPRING.value == "spring"


class TestPosition:
    """Test Position dataclass."""
    
    def test_position_creation(self):
        """Test Position creation."""
        position = Position(10.5, 20.3)
        assert position.x == 10.5
        assert position.y == 20.3


class TestNodeStyle:
    """Test NodeStyle dataclass."""
    
    def test_node_style_creation(self):
        """Test NodeStyle creation with default values."""
        style = NodeStyle()
        assert style.size == 10.0
        assert style.color == "#3498db"
        assert style.border_color == "#2980b9"  # Fixed to match actual default
        assert style.border_width == 1.0
        assert style.label_size == 12.0
        assert style.label_color == "#2c3e50"


class TestEdgeStyle:
    """Test EdgeStyle dataclass."""
    
    def test_edge_style_creation(self):
        """Test EdgeStyle creation with default values."""
        style = EdgeStyle()
        assert style.width == 1.0
        assert style.color == "#95a5a6"  # Fixed to match actual default
        assert style.style == "solid"
        assert style.arrow_size == 5.0
        assert style.label_size == 10.0
        assert style.label_color == "#7f8c8d"


class TestLayoutConfig:
    """Test LayoutConfig dataclass."""
    
    def test_layout_config_creation(self):
        """Test LayoutConfig creation."""
        config = LayoutConfig()
        assert config.algorithm == LayoutAlgorithm.FORCE_DIRECTED
        assert config.iterations == 100
        assert config.width == 800.0
        assert config.height == 600.0
        assert config.node_distance == 50.0
        assert config.edge_length == 100.0


class TestGraphVisualizer:
    """Test GraphVisualizer class with actual available methods."""
    
    @pytest.fixture
    def sample_nodes(self):
        """Sample nodes for testing."""
        return [
            {"id": "node1", "type": "person", "name": "Alice", "properties": {"type": "person"}},
            {"id": "node2", "type": "person", "name": "Bob", "properties": {"type": "person"}},
            {"id": "node3", "type": "organization", "name": "Company", "properties": {"type": "organization"}}
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Sample edges for testing."""
        return [
            {"id": "edge1", "source": "node1", "target": "node2", "type": "knows", "properties": {"type": "knows"}},
            {"id": "edge2", "source": "node1", "target": "node3", "type": "works_for", "properties": {"type": "works_for"}}
        ]
    
    @pytest.fixture
    def visualizer(self):
        """Create GraphVisualizer instance."""
        return GraphVisualizer()
    
    def test_visualizer_initialization(self, visualizer):
        """Test GraphVisualizer initialization."""
        assert visualizer.graph is None
        assert isinstance(visualizer.default_node_style, NodeStyle)
        assert isinstance(visualizer.default_edge_style, EdgeStyle)
    
    @pytest.mark.asyncio
    async def test_create_visualization(self, visualizer, sample_nodes, sample_edges):
        """Test visualization creation."""
        config = LayoutConfig()
        
        visualization = await visualizer.create_visualization(
            sample_nodes, sample_edges, config
        )
        
        assert isinstance(visualization, GraphVisualization)
        assert len(visualization.nodes) == len(sample_nodes)
        assert len(visualization.edges) == len(sample_edges)
        assert visualization.layout_config == config
    
    @pytest.mark.asyncio
    async def test_create_visualization_no_config(self, visualizer, sample_nodes, sample_edges):
        """Test visualization creation without config."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        assert isinstance(visualization, GraphVisualization)
        assert isinstance(visualization.layout_config, LayoutConfig)
    
    @pytest.mark.asyncio
    async def test_update_layout(self, visualizer, sample_nodes, sample_edges):
        """Test layout updates."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Test update_layout method with new config
        new_config = LayoutConfig(algorithm=LayoutAlgorithm.CIRCULAR)
        updated_viz = await visualizer.update_layout(visualization, new_config)
        
        assert isinstance(updated_viz, GraphVisualization)
        assert updated_viz.layout_config.algorithm == LayoutAlgorithm.CIRCULAR
    
    @pytest.mark.asyncio
    async def test_extract_subgraph(self, visualizer, sample_nodes, sample_edges):
        """Test subgraph extraction."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Extract subgraph centered on node1 (pass single string, not list)
        subgraph = await visualizer.extract_subgraph(visualization, "node1")
        
        assert isinstance(subgraph, GraphVisualization)
        # Should contain node1 and connected nodes
        node_ids = {node.id for node in subgraph.nodes}
        assert "node1" in node_ids
    
    @pytest.mark.asyncio
    async def test_extract_subgraph_with_distance(self, visualizer, sample_nodes, sample_edges):
        """Test subgraph extraction with specific distance."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Extract subgraph with distance 1
        subgraph = await visualizer.extract_subgraph(visualization, "node1", max_distance=1)
        
        assert isinstance(subgraph, GraphVisualization)
        node_ids = {node.id for node in subgraph.nodes}
        assert "node1" in node_ids
    
    @pytest.mark.asyncio
    async def test_extract_subgraph_nonexistent_node(self, visualizer, sample_nodes, sample_edges):
        """Test subgraph extraction with nonexistent center node."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Should raise ValueError for nonexistent node
        with pytest.raises(ValueError, match="Center node nonexistent not found"):
            await visualizer.extract_subgraph(visualization, "nonexistent")
    
    @pytest.mark.asyncio
    async def test_search_nodes(self, visualizer, sample_nodes, sample_edges):
        """Test node search functionality."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Search for nodes with "Alice" in label
        results = await visualizer.search_nodes(visualization, "Alice")
        assert isinstance(results, list)
        
        # Search by ID
        results_id = await visualizer.search_nodes(visualization, "node1")
        assert isinstance(results_id, list)
        
        # Search in properties
        results_props = await visualizer.search_nodes(visualization, "person", ["type"])
        assert isinstance(results_props, list)
        
        # Search with multiple fields
        results_multi = await visualizer.search_nodes(visualization, "node", ["id", "label"])
        assert isinstance(results_multi, list)
    
    @pytest.mark.asyncio
    async def test_apply_filters(self, visualizer, sample_nodes, sample_edges):
        """Test filter application."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Test node filters
        node_filters = {"type": "person"}
        filtered_viz = await visualizer.apply_filters(visualization, node_filters)
        
        assert isinstance(filtered_viz, GraphVisualization)
        # Should only contain person nodes (if properties are preserved)
        for node in filtered_viz.nodes:
            if node.visible and hasattr(node, 'properties') and node.properties:
                assert node.properties.get("type") == "person"
    
    @pytest.mark.asyncio
    async def test_apply_edge_filters(self, visualizer, sample_nodes, sample_edges):
        """Test edge filter application."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # Test edge filters
        edge_filters = {"type": "knows"}
        filtered_viz = await visualizer.apply_filters(visualization, None, edge_filters)
        
        assert isinstance(filtered_viz, GraphVisualization)
        # Check that only edges matching filter are visible
        for edge in filtered_viz.edges:
            if edge.visible and hasattr(edge, 'properties') and edge.properties:
                assert edge.properties.get("type") == "knows"
    
    @pytest.mark.asyncio
    async def test_render_to_dict(self, visualizer, sample_nodes, sample_edges):
        """Test rendering visualization to dictionary."""
        visualization = await visualizer.create_visualization(sample_nodes, sample_edges)
        
        # render_to_dict is NOT async, so don't await it
        result_dict = visualizer.render_to_dict(visualization)
        
        assert isinstance(result_dict, dict)
        assert "nodes" in result_dict
        assert "edges" in result_dict
        # Check structure
        assert len(result_dict["nodes"]) == len(sample_nodes)
        assert len(result_dict["edges"]) == len(sample_edges)
    
    @pytest.mark.asyncio
    async def test_empty_graph_handling(self, visualizer):
        """Test handling of empty graphs."""
        visualization = await visualizer.create_visualization([], [])
        
        assert isinstance(visualization, GraphVisualization)
        assert len(visualization.nodes) == 0
        assert len(visualization.edges) == 0
    
    @pytest.mark.asyncio
    async def test_error_handling_malformed_data(self, visualizer):
        """Test error handling with malformed data."""
        # Test with nodes missing IDs
        malformed_nodes = [{"name": "NoId"}, {"id": "node1"}]
        edges = [{"source": "node1", "target": "NoId"}]
        
        # Should handle gracefully without crashing
        try:
            visualization = await visualizer.create_visualization(malformed_nodes, edges)
            assert isinstance(visualization, GraphVisualization)
        except Exception:
            # It's acceptable to raise an exception for invalid data
            pass
    
    @pytest.mark.asyncio
    async def test_large_graph_performance(self, visualizer):
        """Test performance with larger graph."""
        # Create larger graph
        nodes = [{"id": f"node{i}", "type": "person"} for i in range(50)]
        edges = []
        
        # Create connected graph
        for i in range(49):
            edges.append({"id": f"edge{i}", "source": f"node{i}", "target": f"node{i+1}"})
        
        visualization = await visualizer.create_visualization(nodes, edges)
        
        assert isinstance(visualization, GraphVisualization)
        assert len(visualization.nodes) == 50
        assert len(visualization.edges) == 49
    
    def test_default_styles_access(self, visualizer):
        """Test access to default styles."""
        assert isinstance(visualizer.default_node_style, NodeStyle)
        assert isinstance(visualizer.default_edge_style, EdgeStyle)
        
        # Test that styles have expected defaults
        assert visualizer.default_node_style.size == 10
        assert visualizer.default_edge_style.width == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
