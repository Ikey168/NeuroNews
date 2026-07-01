"""
Simple test suite for Graph Visualization module.
Target: Improve test coverage for src/api/graph/visualization.py
"""

import pytest
import sys
import os
import asyncio

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.visualization import (
    LayoutConfig,
    LayoutAlgorithm,
    NodeShape,
    NodeStyle,
    EdgeStyle,
    Position,
    GraphVisualizer,
    GraphVisualization,
)


class TestLayoutConfig:
    """Test LayoutConfig dataclass."""

    def test_layout_config_creation(self):
        """Test LayoutConfig creation."""
        config = LayoutConfig()

        # Test default values
        assert hasattr(config, "algorithm")
        assert hasattr(config, "iterations")
        assert hasattr(config, "repulsion_strength")
        assert config.algorithm == LayoutAlgorithm.FORCE_DIRECTED
        assert config.iterations == 100

    def test_layout_config_custom(self):
        """Test LayoutConfig with custom values."""
        config = LayoutConfig(
            algorithm=LayoutAlgorithm.SPRING,
            iterations=200,
            repulsion_strength=50.0,
        )

        assert config.algorithm == LayoutAlgorithm.SPRING
        assert config.iterations == 200
        assert config.repulsion_strength == 50.0


class TestNodeStyle:
    """Test NodeStyle dataclass."""

    def test_node_style_creation(self):
        """Test NodeStyle creation."""
        style = NodeStyle(
            color="#ff0000",
            size=10,
            shape=NodeShape.SQUARE,
        )

        assert style.color == "#ff0000"
        assert style.size == 10
        assert style.shape == NodeShape.SQUARE

    def test_node_style_defaults(self):
        """Test NodeStyle defaults."""
        style = NodeStyle()

        # Should have default values
        assert hasattr(style, "color")
        assert hasattr(style, "size")
        assert hasattr(style, "shape")
        assert style.shape == NodeShape.CIRCLE
        assert style.size == 10.0
        assert style.color == "#3498db"


class TestEdgeStyle:
    """Test EdgeStyle dataclass."""

    def test_edge_style_creation(self):
        """Test EdgeStyle creation."""
        style = EdgeStyle(
            color="#0000ff",
            width=2,
            style="solid",
        )

        assert style.color == "#0000ff"
        assert style.width == 2
        assert style.style == "solid"

    def test_edge_style_defaults(self):
        """Test EdgeStyle defaults."""
        style = EdgeStyle()

        # Should have default values
        assert hasattr(style, "color")
        assert hasattr(style, "width")
        assert hasattr(style, "style")
        assert style.color == "#95a5a6"
        assert style.width == 1.0
        assert style.style == "solid"


class TestGraphVisualizer:
    """Test GraphVisualizer class."""

    @pytest.fixture
    def visualizer(self):
        """Create GraphVisualizer instance."""
        return GraphVisualizer()

    def test_visualizer_initialization(self, visualizer):
        """Test GraphVisualizer initialization."""
        assert visualizer.graph is None
        assert hasattr(visualizer, "default_node_style")
        assert hasattr(visualizer, "default_edge_style")
        assert isinstance(visualizer.default_node_style, NodeStyle)
        assert isinstance(visualizer.default_edge_style, EdgeStyle)

    def test_create_node_style_default(self, visualizer):
        """Test creating a node style from data with no overrides."""
        style = visualizer._create_node_style({"id": "A"})

        assert isinstance(style, NodeStyle)
        assert style.shape == NodeShape.CIRCLE

    def test_create_node_style_overrides(self, visualizer):
        """Test that node style data overrides defaults."""
        node_data = {
            "id": "A",
            "style": {"shape": "square", "size": 15, "color": "#ff0000"},
        }
        style = visualizer._create_node_style(node_data)

        assert style.shape == NodeShape.SQUARE
        assert style.size == 15
        assert style.color == "#ff0000"

    def test_create_edge_style_default(self, visualizer):
        """Test creating an edge style from data with no overrides."""
        style = visualizer._create_edge_style({"id": "e1"})

        assert isinstance(style, EdgeStyle)
        assert style.color == "#95a5a6"

    def test_create_edge_style_overrides(self, visualizer):
        """Test that edge style data overrides defaults."""
        edge_data = {"id": "e1", "style": {"color": "#0000ff", "width": 3}}
        style = visualizer._create_edge_style(edge_data)

        assert style.color == "#0000ff"
        assert style.width == 3

    def test_create_visualization_basic(self, visualizer):
        """Test basic visualization creation."""
        nodes = [
            {"id": "A", "label": "Person"},
            {"id": "B", "label": "Person"},
            {"id": "C", "label": "Organization"},
        ]
        edges = [
            {"id": "e1", "source": "A", "target": "B", "label": "KNOWS"},
            {"id": "e2", "source": "A", "target": "C", "label": "WORKS_FOR"},
        ]

        config = LayoutConfig(algorithm=LayoutAlgorithm.FORCE_DIRECTED)
        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))

        assert isinstance(vis, GraphVisualization)
        assert len(vis.nodes) == 3
        assert len(vis.edges) == 2
        # Every node should have a position set by the layout algorithm
        node_ids = {node.id for node in vis.nodes}
        assert node_ids == {"A", "B", "C"}
        for node in vis.nodes:
            assert isinstance(node.position, Position)

    def test_create_visualization_default_config(self, visualizer):
        """Test visualization creation falls back to a default config."""
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"id": "e1", "source": "A", "target": "B"}]

        vis = asyncio.run(visualizer.create_visualization(nodes, edges))

        assert isinstance(vis.layout_config, LayoutConfig)
        assert vis.metadata["node_count"] == 2
        assert vis.metadata["edge_count"] == 1

    def test_create_visualization_different_algorithms(self, visualizer):
        """Test different layout algorithms produce a valid visualization."""
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"id": "e1", "source": "A", "target": "B"}]

        algorithms = [
            LayoutAlgorithm.FORCE_DIRECTED,
            LayoutAlgorithm.CIRCULAR,
            LayoutAlgorithm.HIERARCHICAL,
            LayoutAlgorithm.GRID,
            LayoutAlgorithm.RANDOM,
            LayoutAlgorithm.SPRING,
        ]

        for algorithm in algorithms:
            config = LayoutConfig(algorithm=algorithm)
            vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))
            assert isinstance(vis, GraphVisualization)
            assert len(vis.nodes) == 2
            assert vis.metadata["algorithm"] == algorithm.value

    def test_render_to_dict_basic(self, visualizer):
        """Test basic graph rendering to a dictionary."""
        nodes = [{"id": "node1", "label": "Test"}]
        edges = []
        config = LayoutConfig()

        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))
        result = visualizer.render_to_dict(vis)

        # Should return a serializable dict representation
        assert result is not None
        assert isinstance(result, dict)
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "node1"

    def test_render_to_dict_with_styles(self, visualizer):
        """Test rendering with custom per-node/edge styles."""
        nodes = [
            {"id": "A", "label": "Person", "style": {"color": "#ff0000", "size": 20}},
            {"id": "B", "label": "Person"},
        ]
        edges = [
            {
                "id": "e1",
                "source": "A",
                "target": "B",
                "label": "KNOWS",
                "style": {"color": "#0000ff", "width": 3},
            }
        ]

        config = LayoutConfig()
        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))
        result = visualizer.render_to_dict(vis)

        assert result is not None
        node_a = next(n for n in result["nodes"] if n["id"] == "A")
        assert node_a["style"]["color"] == "#ff0000"
        assert node_a["style"]["size"] == 20
        edge = result["edges"][0]
        assert edge["style"]["color"] == "#0000ff"
        assert edge["style"]["width"] == 3

    def test_render_to_dict_is_json_serializable(self, visualizer):
        """Test that the rendered dict can be serialized to JSON."""
        import json

        nodes = [{"id": "test"}]
        edges = []
        config = LayoutConfig()

        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))
        result = visualizer.render_to_dict(vis)

        serialized = json.dumps(result)
        assert isinstance(serialized, str)
        assert "test" in serialized

    def test_update_layout(self, visualizer):
        """Test updating the layout of an existing visualization."""
        nodes = [{"id": "A"}, {"id": "B"}]
        edges = [{"id": "e1", "source": "A", "target": "B"}]
        config = LayoutConfig(algorithm=LayoutAlgorithm.FORCE_DIRECTED)

        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))

        new_config = LayoutConfig(algorithm=LayoutAlgorithm.CIRCULAR)
        updated = asyncio.run(visualizer.update_layout(vis, new_config))

        assert updated.layout_config.algorithm == LayoutAlgorithm.CIRCULAR
        assert updated.metadata["layout_updated"] is True
        assert updated.metadata["algorithm"] == LayoutAlgorithm.CIRCULAR.value

    def test_extract_subgraph(self, visualizer):
        """Test extracting a subgraph centered on a node."""
        nodes = [{"id": "A"}, {"id": "B"}, {"id": "C"}]
        edges = [
            {"id": "e1", "source": "A", "target": "B"},
            {"id": "e2", "source": "B", "target": "C"},
        ]
        config = LayoutConfig()

        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))
        subgraph = asyncio.run(visualizer.extract_subgraph(vis, "A", max_distance=1))

        sub_ids = {node.id for node in subgraph.nodes}
        # Center node plus its direct neighbour
        assert "A" in sub_ids
        assert "B" in sub_ids
        assert subgraph.metadata["center_node"] == "A"

    def test_extract_subgraph_invalid_center(self, visualizer):
        """Test that extracting a subgraph for a missing center raises."""
        nodes = [{"id": "A"}]
        edges = []
        config = LayoutConfig()

        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))

        with pytest.raises(ValueError):
            asyncio.run(visualizer.extract_subgraph(vis, "missing"))

    def test_search_nodes(self, visualizer):
        """Test searching for nodes by query string."""
        nodes = [
            {"id": "A", "label": "Alice"},
            {"id": "B", "label": "Bob"},
        ]
        edges = []
        config = LayoutConfig()

        vis = asyncio.run(visualizer.create_visualization(nodes, edges, config))
        matches = asyncio.run(visualizer.search_nodes(vis, "alice"))

        assert matches == ["A"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
