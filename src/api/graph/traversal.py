"""
Knowledge Graph Traversal Module

This module provides graph traversal algorithms and path finding capabilities:
- Breadth-first and depth-first search
- Shortest path algorithms
- Graph traversal with filtering and constraints
- Performance optimization for large graphs
"""

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
from collections import deque
import heapq

logger = logging.getLogger(__name__)


@dataclass
class TraversalConfig:
    """Configuration for graph traversal operations."""
    max_depth: int = 5
    max_results: int = 1000
    include_properties: bool = True
    filter_by_labels: Optional[List[str]] = None
    filter_by_properties: Optional[Dict[str, Any]] = None
    timeout_seconds: int = 30


@dataclass
class PathResult:
    """Result of a path traversal."""
    start_node: str
    end_node: str
    path: List[str]
    path_length: int
    total_weight: float
    properties: Dict[str, Any]


@dataclass
class TraversalResult:
    """Result of a graph traversal operation."""
    start_node: str
    visited_nodes: List[str]
    traversal_depth: int
    total_nodes: int
    execution_time: float
    paths: List[PathResult]


class GraphTraversal:
    """Graph traversal algorithms and utilities."""

    def __init__(self, graph_builder=None):
        """Initialize graph traversal with graph builder."""
        self.graph = graph_builder
        self.traversal_stats = {
            'total_traversals': 0,
            'avg_execution_time': 0.0,
            'max_depth_reached': 0,
            'total_nodes_visited': 0
        }
        logger.info("GraphTraversal initialized")

    async def breadth_first_search(
        self, 
        start_node: str, 
        config: Optional[TraversalConfig] = None
    ) -> TraversalResult:
        """
        Perform breadth-first search from a starting node.
        
        Args:
            start_node: Starting node ID
            config: Traversal configuration
            
        Returns:
            TraversalResult with visited nodes and paths
        """
        config = config or TraversalConfig()
        start_time = datetime.now()
        
        try:
            if not self.graph:
                # Mock implementation for testing
                return self._mock_bfs_result(start_node, config)

            visited = set()
            queue = deque([(start_node, 0)])  # (node_id, depth)
            visited_nodes = []
            paths = []
            
            g = self.graph.g
            
            while queue and len(visited_nodes) < config.max_results:
                current_node, depth = queue.popleft()
                
                if current_node in visited or depth > config.max_depth:
                    continue
                
                visited.add(current_node)
                visited_nodes.append(current_node)
                
                # Get node properties if requested
                node_data = {}
                if config.include_properties:
                    try:
                        node_props = await g.V(current_node).valueMap(True).next()
                        node_data = dict(node_props)
                    except:
                        pass
                
                # Get neighbors
                try:
                    neighbors_query = g.V(current_node).both()
                    
                    # Apply label filters
                    if config.filter_by_labels:
                        neighbors_query = neighbors_query.hasLabel(*config.filter_by_labels)
                    
                    # Apply property filters
                    if config.filter_by_properties:
                        for prop, value in config.filter_by_properties.items():
                            neighbors_query = neighbors_query.has(prop, value)
                    
                    neighbors = await neighbors_query.id().toList()
                    
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            queue.append((neighbor, depth + 1))
                            
                            # Create path result
                            paths.append(PathResult(
                                start_node=start_node,
                                end_node=neighbor,
                                path=[start_node, current_node, neighbor] if current_node != start_node else [start_node, neighbor],
                                path_length=depth + 1,
                                total_weight=depth + 1.0,
                                properties=node_data
                            ))
                
                except Exception as e:
                    logger.warning(f"Error traversing from node {current_node}: {e}")
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Update stats
            self.traversal_stats['total_traversals'] += 1
            self.traversal_stats['total_nodes_visited'] += len(visited_nodes)
            
            return TraversalResult(
                start_node=start_node,
                visited_nodes=visited_nodes,
                traversal_depth=min(len(visited_nodes), config.max_depth),
                total_nodes=len(visited_nodes),
                execution_time=execution_time,
                paths=paths[:config.max_results]
            )

        except Exception as e:
            logger.error(f"BFS failed from node {start_node}: {e}")
            raise

    def _mock_bfs_result(self, start_node: str, config: TraversalConfig) -> TraversalResult:
        """Mock BFS result for testing."""
        mock_visited = [f"node_{i}" for i in range(min(10, config.max_results))]
        mock_paths = [
            PathResult(
                start_node=start_node,
                end_node=f"node_{i}",
                path=[start_node, f"node_{i}"],
                path_length=1,
                total_weight=1.0,
                properties={'name': f"Mock Node {i}"}
            ) for i in range(len(mock_visited))
        ]
        
        return TraversalResult(
            start_node=start_node,
            visited_nodes=mock_visited,
            traversal_depth=min(len(mock_visited), config.max_depth),
            total_nodes=len(mock_visited),
            execution_time=0.1,
            paths=mock_paths
        )

    async def depth_first_search(
        self, 
        start_node: str, 
        config: Optional[TraversalConfig] = None
    ) -> TraversalResult:
        """
        Perform depth-first search from a starting node.
        
        Args:
            start_node: Starting node ID
            config: Traversal configuration
            
        Returns:
            TraversalResult with visited nodes and paths
        """
        config = config or TraversalConfig()
        start_time = datetime.now()
        
        try:
            if not self.graph:
                # Mock implementation for testing
                return self._mock_dfs_result(start_node, config)

            visited = set()
            stack = [(start_node, 0, [start_node])]  # (node_id, depth, path)
            visited_nodes = []
            paths = []
            
            g = self.graph.g
            
            while stack and len(visited_nodes) < config.max_results:
                current_node, depth, path = stack.pop()
                
                if current_node in visited or depth > config.max_depth:
                    continue
                
                visited.add(current_node)
                visited_nodes.append(current_node)
                
                # Get node properties if requested
                node_data = {}
                if config.include_properties:
                    try:
                        node_props = await g.V(current_node).valueMap(True).next()
                        node_data = dict(node_props)
                    except:
                        pass
                
                # Get neighbors
                try:
                    neighbors_query = g.V(current_node).both()
                    
                    # Apply filters
                    if config.filter_by_labels:
                        neighbors_query = neighbors_query.hasLabel(*config.filter_by_labels)
                    
                    if config.filter_by_properties:
                        for prop, value in config.filter_by_properties.items():
                            neighbors_query = neighbors_query.has(prop, value)
                    
                    neighbors = await neighbors_query.id().toList()
                    
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            new_path = path + [neighbor]
                            stack.append((neighbor, depth + 1, new_path))
                            
                            # Create path result
                            paths.append(PathResult(
                                start_node=start_node,
                                end_node=neighbor,
                                path=new_path,
                                path_length=len(new_path) - 1,
                                total_weight=len(new_path) - 1.0,
                                properties=node_data
                            ))
                
                except Exception as e:
                    logger.warning(f"Error traversing from node {current_node}: {e}")
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return TraversalResult(
                start_node=start_node,
                visited_nodes=visited_nodes,
                traversal_depth=min(len(visited_nodes), config.max_depth),
                total_nodes=len(visited_nodes),
                execution_time=execution_time,
                paths=paths[:config.max_results]
            )

        except Exception as e:
            logger.error(f"DFS failed from node {start_node}: {e}")
            raise

    def _mock_dfs_result(self, start_node: str, config: TraversalConfig) -> TraversalResult:
        """Mock DFS result for testing."""
        mock_visited = [f"node_{i}" for i in range(min(8, config.max_results))]
        mock_paths = [
            PathResult(
                start_node=start_node,
                end_node=f"node_{i}",
                path=[start_node] + [f"node_{j}" for j in range(i+1)],
                path_length=i+1,
                total_weight=i+1.0,
                properties={'name': f"Mock Node {i}", 'depth': i}
            ) for i in range(len(mock_visited))
        ]
        
        return TraversalResult(
            start_node=start_node,
            visited_nodes=mock_visited,
            traversal_depth=len(mock_visited),
            total_nodes=len(mock_visited),
            execution_time=0.15,
            paths=mock_paths
        )

    async def find_shortest_path(
        self, 
        start_node: str, 
        end_node: str,
        max_depth: int = 10
    ) -> Optional[PathResult]:
        """
        Find the shortest path between two nodes using BFS.
        
        Args:
            start_node: Starting node ID
            end_node: Target node ID
            max_depth: Maximum search depth
            
        Returns:
            PathResult if path found, None otherwise
        """
        if start_node == end_node:
            return PathResult(
                start_node=start_node,
                end_node=end_node,
                path=[start_node],
                path_length=0,
                total_weight=0.0,
                properties={}
            )

        try:
            if not self.graph:
                # Mock implementation for testing
                return PathResult(
                    start_node=start_node,
                    end_node=end_node,
                    path=[start_node, "intermediate_node", end_node],
                    path_length=2,
                    total_weight=2.0,
                    properties={'algorithm': 'shortest_path_mock'}
                )

            visited = set()
            queue = deque([(start_node, [start_node], 0)])  # (node, path, depth)
            
            g = self.graph.g
            
            while queue:
                current_node, path, depth = queue.popleft()
                
                if depth > max_depth:
                    continue
                
                if current_node == end_node:
                    return PathResult(
                        start_node=start_node,
                        end_node=end_node,
                        path=path,
                        path_length=len(path) - 1,
                        total_weight=len(path) - 1.0,
                        properties={'algorithm': 'bfs_shortest_path'}
                    )
                
                if current_node in visited:
                    continue
                
                visited.add(current_node)
                
                # Get neighbors
                try:
                    neighbors = await g.V(current_node).both().id().toList()
                    
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            new_path = path + [neighbor]
                            queue.append((neighbor, new_path, depth + 1))
                
                except Exception as e:
                    logger.warning(f"Error getting neighbors for {current_node}: {e}")
            
            return None  # No path found

        except Exception as e:
            logger.error(f"Shortest path search failed: {e}")
            raise

    async def find_all_paths(
        self, 
        start_node: str, 
        end_node: str,
        max_depth: int = 5,
        max_paths: int = 10
    ) -> List[PathResult]:
        """
        Find all paths between two nodes up to max_depth.
        
        Args:
            start_node: Starting node ID
            end_node: Target node ID
            max_depth: Maximum path length
            max_paths: Maximum number of paths to return
            
        Returns:
            List of PathResult objects
        """
        if start_node == end_node:
            return [PathResult(
                start_node=start_node,
                end_node=end_node,
                path=[start_node],
                path_length=0,
                total_weight=0.0,
                properties={}
            )]

        try:
            if not self.graph:
                # Mock implementation for testing
                return [
                    PathResult(
                        start_node=start_node,
                        end_node=end_node,
                        path=[start_node, f"path_{i}_node", end_node],
                        path_length=2,
                        total_weight=2.0,
                        properties={'path_index': i}
                    ) for i in range(min(3, max_paths))
                ]

            all_paths = []
            stack = [(start_node, [start_node], set([start_node]))]
            
            g = self.graph.g
            
            while stack and len(all_paths) < max_paths:
                current_node, path, visited = stack.pop()
                
                if len(path) > max_depth:
                    continue
                
                if current_node == end_node and len(path) > 1:
                    all_paths.append(PathResult(
                        start_node=start_node,
                        end_node=end_node,
                        path=path,
                        path_length=len(path) - 1,
                        total_weight=len(path) - 1.0,
                        properties={'algorithm': 'all_paths_dfs'}
                    ))
                    continue
                
                # Get neighbors
                try:
                    neighbors = await g.V(current_node).both().id().toList()
                    
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            new_path = path + [neighbor]
                            new_visited = visited.copy()
                            new_visited.add(neighbor)
                            stack.append((neighbor, new_path, new_visited))
                
                except Exception as e:
                    logger.warning(f"Error getting neighbors for {current_node}: {e}")
            
            return all_paths

        except Exception as e:
            logger.error(f"All paths search failed: {e}")
            raise

    async def get_node_neighbors(
        self, 
        node_id: str, 
        direction: str = "both",
        labels: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get neighboring nodes of a specific node.
        
        Args:
            node_id: Node ID to get neighbors for
            direction: Direction of traversal ('in', 'out', 'both')
            labels: Filter neighbors by labels
            
        Returns:
            List of neighbor node data
        """
        try:
            if not self.graph:
                # Mock implementation for testing
                return [
                    {
                        'id': f"neighbor_{i}",
                        'label': labels[0] if labels else 'MockNode',
                        'properties': {'name': f"Neighbor {i}"}
                    } for i in range(3)
                ]

            g = self.graph.g
            
            # Build query based on direction
            if direction == "in":
                query = g.V(node_id).in_()
            elif direction == "out":
                query = g.V(node_id).out()
            else:  # both
                query = g.V(node_id).both()
            
            # Apply label filter if provided
            if labels:
                query = query.hasLabel(*labels)
            
            # Get neighbor data
            neighbors = await query.valueMap(True).toList()
            
            return [dict(neighbor) for neighbor in neighbors]

        except Exception as e:
            logger.error(f"Failed to get neighbors for node {node_id}: {e}")
            raise

    def get_traversal_statistics(self) -> Dict[str, Any]:
        """Get traversal performance statistics."""
        if self.traversal_stats['total_traversals'] > 0:
            self.traversal_stats['avg_execution_time'] = (
                self.traversal_stats['total_nodes_visited'] / 
                self.traversal_stats['total_traversals']
            )
        
        return self.traversal_stats.copy()

    def reset_statistics(self) -> None:
        """Reset traversal statistics."""
        self.traversal_stats = {
            'total_traversals': 0,
            'avg_execution_time': 0.0,
            'max_depth_reached': 0,
            'total_nodes_visited': 0
        }

    async def analyze_graph_connectivity(self) -> Dict[str, Any]:
        """
        Analyze graph connectivity patterns.
        
        Returns:
            Dictionary with connectivity analysis
        """
        try:
            if not self.graph:
                # Mock implementation for testing
                return {
                    'total_nodes': 100,
                    'total_edges': 250,
                    'average_degree': 2.5,
                    'max_degree': 10,
                    'connected_components': 1,
                    'diameter': 6,
                    'clustering_coefficient': 0.3,
                    'analysis_time': datetime.now().isoformat()
                }

            g = self.graph.g
            
            # Get basic counts
            node_count = await g.V().count().next()
            edge_count = await g.E().count().next()
            
            # Calculate average degree
            degrees = await g.V().bothE().count().toList()
            avg_degree = sum(degrees) / len(degrees) if degrees else 0
            max_degree = max(degrees) if degrees else 0
            
            return {
                'total_nodes': node_count,
                'total_edges': edge_count,
                'average_degree': avg_degree,
                'max_degree': max_degree,
                'connected_components': 1,  # Simplified
                'diameter': None,  # Would require complex calculation
                'clustering_coefficient': None,  # Would require complex calculation
                'analysis_time': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Graph connectivity analysis failed: {e}")
            raise
