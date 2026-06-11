"""
Graph Visualization Module

This module provides graph visualization capabilities including:
- Graph layout algorithms (force-directed, hierarchical, circular)
- Node and edge styling and positioning
- Interactive visualization rendering
- Subgraph extraction and filtering
- Visual analytics and exploration tools
"""

import logging
import json
import math
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class LayoutAlgorithm(Enum):
    """Available graph layout algorithms."""
    FORCE_DIRECTED = "force_directed"
    HIERARCHICAL = "hierarchical"
    CIRCULAR = "circular"
    GRID = "grid"
    RANDOM = "random"
    SPRING = "spring"


class NodeShape(Enum):
    """Available node shapes for visualization."""
    CIRCLE = "circle"
    SQUARE = "square"
    TRIANGLE = "triangle"
    DIAMOND = "diamond"
    HEXAGON = "hexagon"


@dataclass
class Position:
    """2D position coordinates."""
    x: float
    y: float


@dataclass
class NodeStyle:
    """Visual styling for graph nodes."""
    shape: NodeShape = NodeShape.CIRCLE
    size: float = 10.0
    color: str = "#3498db"
    border_color: str = "#2980b9"
    border_width: float = 1.0
    label_color: str = "#2c3e50"
    label_size: float = 12.0


@dataclass
class EdgeStyle:
    """Visual styling for graph edges."""
    color: str = "#95a5a6"
    width: float = 1.0
    arrow_size: float = 5.0
    style: str = "solid"  # solid, dashed, dotted
    label_color: str = "#7f8c8d"
    label_size: float = 10.0


@dataclass
class LayoutConfig:
    """Configuration for graph layout algorithms."""
    algorithm: LayoutAlgorithm = LayoutAlgorithm.FORCE_DIRECTED
    width: float = 800.0
    height: float = 600.0
    iterations: int = 100
    node_distance: float = 50.0
    edge_length: float = 100.0
    spring_strength: float = 0.1
    repulsion_strength: float = 0.5
    center_force: float = 0.01
    damping: float = 0.9


@dataclass
class VisualizationNode:
    """Node representation for visualization."""
    id: str
    label: str
    position: Position
    style: NodeStyle
    properties: Dict[str, Any]
    visible: bool = True


@dataclass
class VisualizationEdge:
    """Edge representation for visualization."""
    id: str
    source: str
    target: str
    label: Optional[str]
    style: EdgeStyle
    properties: Dict[str, Any]
    visible: bool = True


@dataclass
class GraphVisualization:
    """Complete graph visualization representation."""
    nodes: List[VisualizationNode]
    edges: List[VisualizationEdge]
    layout_config: LayoutConfig
    metadata: Dict[str, Any]
    viewport: Dict[str, float]  # x, y, zoom, rotation


class GraphVisualizer:
    """Main graph visualization engine."""
    
    def __init__(self, graph_builder=None):
        """Initialize the graph visualizer."""
        self.graph = graph_builder
        self.default_node_style = NodeStyle()
        self.default_edge_style = EdgeStyle()
        logger.info("GraphVisualizer initialized")
    
    async def create_visualization(
        self, 
        node_data: List[Dict[str, Any]], 
        edge_data: List[Dict[str, Any]],
        config: Optional[LayoutConfig] = None
    ) -> GraphVisualization:
        """
        Create a complete graph visualization from node and edge data.
        
        Args:
            node_data: List of node dictionaries
            edge_data: List of edge dictionaries
            config: Layout configuration
            
        Returns:
            GraphVisualization object with positioned nodes and edges
        """
        if config is None:
            config = LayoutConfig()
            
        # Convert data to visualization nodes and edges
        vis_nodes = []
        for node in node_data:
            vis_node = VisualizationNode(
                id=node.get("id", ""),
                label=node.get("label", node.get("id", "")),
                position=Position(0, 0),  # Will be set by layout algorithm
                style=self._create_node_style(node),
                properties=node.get("properties", {}),
                visible=node.get("visible", True)
            )
            vis_nodes.append(vis_node)
        
        vis_edges = []
        for edge in edge_data:
            vis_edge = VisualizationEdge(
                id=edge.get("id", ""),
                source=edge.get("source", edge.get("from_node", "")),
                target=edge.get("target", edge.get("to_node", "")),
                label=edge.get("label"),
                style=self._create_edge_style(edge),
                properties=edge.get("properties", {}),
                visible=edge.get("visible", True)
            )
            vis_edges.append(vis_edge)
        
        # Apply layout algorithm
        await self._apply_layout(vis_nodes, vis_edges, config)
        
        # Create visualization object
        visualization = GraphVisualization(
            nodes=vis_nodes,
            edges=vis_edges,
            layout_config=config,
            metadata={
                "node_count": len(vis_nodes),
                "edge_count": len(vis_edges),
                "algorithm": config.algorithm.value,
                "created_at": asyncio.get_event_loop().time()
            },
            viewport={
                "x": config.width / 2,
                "y": config.height / 2,
                "zoom": 1.0,
                "rotation": 0.0
            }
        )
        
        logger.info(f"Created visualization with {len(vis_nodes)} nodes and {len(vis_edges)} edges")
        return visualization
    
    async def apply_filters(
        self, 
        visualization: GraphVisualization,
        node_filters: Optional[Dict[str, Any]] = None,
        edge_filters: Optional[Dict[str, Any]] = None
    ) -> GraphVisualization:
        """
        Apply filters to hide/show nodes and edges in visualization.
        
        Args:
            visualization: Graph visualization to filter
            node_filters: Node property filters
            edge_filters: Edge property filters
            
        Returns:
            Updated GraphVisualization with filtered visibility
        """
        if node_filters:
            for node in visualization.nodes:
                node.visible = self._matches_filters(node.properties, node_filters)
        
        if edge_filters:
            for edge in visualization.edges:
                edge.visible = self._matches_filters(edge.properties, edge_filters)
        
        # Hide edges connected to invisible nodes
        visible_node_ids = {node.id for node in visualization.nodes if node.visible}
        for edge in visualization.edges:
            if edge.source not in visible_node_ids or edge.target not in visible_node_ids:
                edge.visible = False
        
        # Update metadata
        visible_nodes = sum(1 for node in visualization.nodes if node.visible)
        visible_edges = sum(1 for edge in visualization.edges if edge.visible)
        
        visualization.metadata.update({
            "visible_nodes": visible_nodes,
            "visible_edges": visible_edges,
            "filtered": True
        })
        
        logger.info(f"Applied filters: {visible_nodes}/{len(visualization.nodes)} nodes, {visible_edges}/{len(visualization.edges)} edges visible")
        return visualization
    
    async def extract_subgraph(
        self,
        visualization: GraphVisualization,
        center_node: str,
        max_distance: int = 2
    ) -> GraphVisualization:
        """
        Extract a subgraph centered on a specific node.
        
        Args:
            visualization: Source visualization
            center_node: ID of center node
            max_distance: Maximum distance from center node
            
        Returns:
            New GraphVisualization containing only the subgraph
        """
        if not any(node.id == center_node for node in visualization.nodes):
            raise ValueError(f"Center node {center_node} not found in visualization")
        
        # Find all nodes within max_distance
        included_nodes = set([center_node])
        current_level = set([center_node])
        
        for distance in range(max_distance):
            next_level = set()
            for edge in visualization.edges:
                if edge.source in current_level:
                    next_level.add(edge.target)
                if edge.target in current_level:
                    next_level.add(edge.source)
            
            included_nodes.update(next_level)
            current_level = next_level - included_nodes
            
            if not current_level:  # No more nodes to explore
                break
        
        # Create subgraph
        subgraph_nodes = [node for node in visualization.nodes if node.id in included_nodes]
        subgraph_edges = [
            edge for edge in visualization.edges 
            if edge.source in included_nodes and edge.target in included_nodes
        ]
        
        # Create new visualization
        subgraph = GraphVisualization(
            nodes=subgraph_nodes,
            edges=subgraph_edges,
            layout_config=visualization.layout_config,
            metadata={
                **visualization.metadata,
                "subgraph": True,
                "center_node": center_node,
                "max_distance": max_distance,
                "original_node_count": len(visualization.nodes),
                "original_edge_count": len(visualization.edges)
            },
            viewport=visualization.viewport.copy()
        )
        
        logger.info(f"Extracted subgraph: {len(subgraph_nodes)} nodes, {len(subgraph_edges)} edges")
        return subgraph
    
    async def update_layout(
        self, 
        visualization: GraphVisualization, 
        new_config: LayoutConfig
    ) -> GraphVisualization:
        """
        Update the layout of an existing visualization.
        
        Args:
            visualization: Visualization to update
            new_config: New layout configuration
            
        Returns:
            Updated GraphVisualization with new layout
        """
        visualization.layout_config = new_config
        await self._apply_layout(visualization.nodes, visualization.edges, new_config)
        
        visualization.metadata.update({
            "layout_updated": True,
            "algorithm": new_config.algorithm.value
        })
        
        logger.info(f"Updated layout using {new_config.algorithm.value} algorithm")
        return visualization
    
    def render_to_dict(self, visualization: GraphVisualization) -> Dict[str, Any]:
        """
        Convert visualization to dictionary format for JSON serialization.
        
        Args:
            visualization: Visualization to convert
            
        Returns:
            Dictionary representation suitable for JSON export
        """
        return {
            "nodes": [
                {
                    "id": node.id,
                    "label": node.label,
                    "x": node.position.x,
                    "y": node.position.y,
                    "visible": node.visible,
                    "style": {
                        "shape": node.style.shape.value,
                        "size": node.style.size,
                        "color": node.style.color,
                        "borderColor": node.style.border_color,
                        "borderWidth": node.style.border_width,
                        "labelColor": node.style.label_color,
                        "labelSize": node.style.label_size
                    },
                    "properties": node.properties
                }
                for node in visualization.nodes
            ],
            "edges": [
                {
                    "id": edge.id,
                    "source": edge.source,
                    "target": edge.target,
                    "label": edge.label,
                    "visible": edge.visible,
                    "style": {
                        "color": edge.style.color,
                        "width": edge.style.width,
                        "arrowSize": edge.style.arrow_size,
                        "style": edge.style.style,
                        "labelColor": edge.style.label_color,
                        "labelSize": edge.style.label_size
                    },
                    "properties": edge.properties
                }
                for edge in visualization.edges
            ],
            "layout": {
                "algorithm": visualization.layout_config.algorithm.value,
                "width": visualization.layout_config.width,
                "height": visualization.layout_config.height
            },
            "viewport": visualization.viewport,
            "metadata": visualization.metadata
        }
    
    async def search_nodes(
        self, 
        visualization: GraphVisualization, 
        query: str,
        search_fields: List[str] = None
    ) -> List[str]:
        """
        Search for nodes matching a query string.
        
        Args:
            visualization: Visualization to search
            query: Search query
            search_fields: Fields to search in (default: label, id)
            
        Returns:
            List of matching node IDs
        """
        if search_fields is None:
            search_fields = ["label", "id"]
        
        query_lower = query.lower()
        matching_nodes = []
        
        for node in visualization.nodes:
            # Search in specified fields
            for field in search_fields:
                if field == "label" and query_lower in node.label.lower():
                    matching_nodes.append(node.id)
                    break
                elif field == "id" and query_lower in node.id.lower():
                    matching_nodes.append(node.id)
                    break
                elif field in node.properties:
                    prop_value = str(node.properties[field]).lower()
                    if query_lower in prop_value:
                        matching_nodes.append(node.id)
                        break
        
        logger.info(f"Search for '{query}' found {len(matching_nodes)} matches")
        return matching_nodes
    
    # Private helper methods
    
    def _create_node_style(self, node_data: Dict[str, Any]) -> NodeStyle:
        """Create node style from node data."""
        style = NodeStyle()
        
        # Apply style overrides from node data
        if "style" in node_data:
            style_data = node_data["style"]
            if "shape" in style_data:
                style.shape = NodeShape(style_data["shape"])
            if "size" in style_data:
                style.size = style_data["size"]
            if "color" in style_data:
                style.color = style_data["color"]
        
        return style
    
    def _create_edge_style(self, edge_data: Dict[str, Any]) -> EdgeStyle:
        """Create edge style from edge data."""
        style = EdgeStyle()
        
        # Apply style overrides from edge data
        if "style" in edge_data:
            style_data = edge_data["style"]
            if "color" in style_data:
                style.color = style_data["color"]
            if "width" in style_data:
                style.width = style_data["width"]
        
        return style
    
    async def _apply_layout(
        self, 
        nodes: List[VisualizationNode], 
        edges: List[VisualizationEdge],
        config: LayoutConfig
    ):
        """Apply the specified layout algorithm to position nodes."""
        if config.algorithm == LayoutAlgorithm.FORCE_DIRECTED:
            await self._apply_force_directed_layout(nodes, edges, config)
        elif config.algorithm == LayoutAlgorithm.CIRCULAR:
            await self._apply_circular_layout(nodes, config)
        elif config.algorithm == LayoutAlgorithm.GRID:
            await self._apply_grid_layout(nodes, config)
        elif config.algorithm == LayoutAlgorithm.HIERARCHICAL:
            await self._apply_hierarchical_layout(nodes, edges, config)
        else:
            await self._apply_random_layout(nodes, config)
    
    async def _apply_force_directed_layout(
        self, 
        nodes: List[VisualizationNode], 
        edges: List[VisualizationEdge],
        config: LayoutConfig
    ):
        """Apply force-directed layout algorithm."""
        # Initialize positions randomly
        for i, node in enumerate(nodes):
            angle = 2 * math.pi * i / len(nodes)
            radius = min(config.width, config.height) * 0.3
            node.position.x = config.width / 2 + radius * math.cos(angle)
            node.position.y = config.height / 2 + radius * math.sin(angle)
        
        # Run force simulation
        for iteration in range(config.iterations):
            # Calculate forces
            for node in nodes:
                force_x, force_y = 0, 0
                
                # Repulsion between nodes
                for other_node in nodes:
                    if node.id != other_node.id:
                        dx = node.position.x - other_node.position.x
                        dy = node.position.y - other_node.position.y
                        distance = math.sqrt(dx*dx + dy*dy) or 1
                        
                        repulsion = config.repulsion_strength / (distance * distance)
                        force_x += repulsion * dx / distance
                        force_y += repulsion * dy / distance
                
                # Attraction along edges
                for edge in edges:
                    if edge.source == node.id:
                        other_node = next(n for n in nodes if n.id == edge.target)
                        dx = other_node.position.x - node.position.x
                        dy = other_node.position.y - node.position.y
                        distance = math.sqrt(dx*dx + dy*dy) or 1
                        
                        attraction = config.spring_strength * (distance - config.edge_length)
                        force_x += attraction * dx / distance
                        force_y += attraction * dy / distance
                
                # Center force
                center_x = config.width / 2
                center_y = config.height / 2
                force_x += config.center_force * (center_x - node.position.x)
                force_y += config.center_force * (center_y - node.position.y)
                
                # Update position
                node.position.x += force_x * config.damping
                node.position.y += force_y * config.damping
                
                # Keep within bounds
                node.position.x = max(10, min(config.width - 10, node.position.x))
                node.position.y = max(10, min(config.height - 10, node.position.y))
    
    async def _apply_circular_layout(self, nodes: List[VisualizationNode], config: LayoutConfig):
        """Apply circular layout algorithm."""
        if not nodes:
            return
        
        center_x = config.width / 2
        center_y = config.height / 2
        radius = min(config.width, config.height) * 0.4
        
        for i, node in enumerate(nodes):
            angle = 2 * math.pi * i / len(nodes)
            node.position.x = center_x + radius * math.cos(angle)
            node.position.y = center_y + radius * math.sin(angle)
    
    async def _apply_grid_layout(self, nodes: List[VisualizationNode], config: LayoutConfig):
        """Apply grid layout algorithm."""
        if not nodes:
            return
        
        cols = int(math.ceil(math.sqrt(len(nodes))))
        rows = int(math.ceil(len(nodes) / cols))
        
        cell_width = config.width / cols
        cell_height = config.height / rows
        
        for i, node in enumerate(nodes):
            col = i % cols
            row = i // cols
            node.position.x = (col + 0.5) * cell_width
            node.position.y = (row + 0.5) * cell_height
    
    async def _apply_hierarchical_layout(
        self, 
        nodes: List[VisualizationNode], 
        edges: List[VisualizationEdge],
        config: LayoutConfig
    ):
        """Apply hierarchical layout algorithm."""
        # Simple hierarchical layout - root at top, children below
        levels = self._calculate_hierarchy_levels(nodes, edges)
        
        for level, level_nodes in levels.items():
            y = config.height * (level + 1) / (len(levels) + 1)
            for i, node in enumerate(level_nodes):
                x = config.width * (i + 1) / (len(level_nodes) + 1)
                node.position.x = x
                node.position.y = y
    
    async def _apply_random_layout(self, nodes: List[VisualizationNode], config: LayoutConfig):
        """Apply random layout algorithm."""
        import random
        
        for node in nodes:
            node.position.x = random.uniform(50, config.width - 50)
            node.position.y = random.uniform(50, config.height - 50)
    
    def _calculate_hierarchy_levels(
        self, 
        nodes: List[VisualizationNode], 
        edges: List[VisualizationEdge]
    ) -> Dict[int, List[VisualizationNode]]:
        """Calculate hierarchy levels for nodes."""
        # Simple implementation - nodes with no incoming edges at level 0
        node_dict = {node.id: node for node in nodes}
        incoming_edges = {node.id: [] for node in nodes}
        
        for edge in edges:
            if edge.target in incoming_edges:
                incoming_edges[edge.target].append(edge.source)
        
        levels = {}
        level = 0
        remaining_nodes = set(node.id for node in nodes)
        
        while remaining_nodes:
            current_level_nodes = []
            for node_id in list(remaining_nodes):
                if not incoming_edges[node_id] or not any(source in remaining_nodes for source in incoming_edges[node_id]):
                    current_level_nodes.append(node_dict[node_id])
                    remaining_nodes.remove(node_id)
            
            if not current_level_nodes:
                # Handle remaining nodes (cycles or disconnected)
                current_level_nodes = [node_dict[node_id] for node_id in remaining_nodes]
                remaining_nodes.clear()
            
            levels[level] = current_level_nodes
            level += 1
        
        return levels
    
    def _matches_filters(self, properties: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """Check if properties match the given filters."""
        for key, expected_value in filters.items():
            if key not in properties:
                return False
            
            actual_value = properties[key]
            
            # Handle different filter types
            if isinstance(expected_value, dict):
                # Range or comparison filters
                if "$gt" in expected_value and actual_value <= expected_value["$gt"]:
                    return False
                if "$lt" in expected_value and actual_value >= expected_value["$lt"]:
                    return False
                if "$eq" in expected_value and actual_value != expected_value["$eq"]:
                    return False
            elif isinstance(expected_value, list):
                # "In" filter
                if actual_value not in expected_value:
                    return False
            else:
                # Exact match
                if actual_value != expected_value:
                    return False
        
        return True
