"""
Graph Metrics Module

This module provides graph analysis and metrics calculation including:
- Network topology metrics (centrality, clustering, connectivity)
- Graph statistics and performance metrics
- Community detection and analysis
- Graph comparison operations
- Performance profiling and monitoring
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple, Set, Union
from dataclasses import dataclass
from enum import Enum
import asyncio
from datetime import datetime
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class CentralityMeasure(Enum):
    """Available centrality measures."""
    DEGREE = "degree"
    BETWEENNESS = "betweenness"
    CLOSENESS = "closeness"
    EIGENVECTOR = "eigenvector"
    PAGERANK = "pagerank"


class MetricType(Enum):
    """Types of graph metrics."""
    NODE_LEVEL = "node_level"
    EDGE_LEVEL = "edge_level"
    GRAPH_LEVEL = "graph_level"
    COMMUNITY_LEVEL = "community_level"


@dataclass
class NodeMetrics:
    """Metrics for individual nodes."""
    node_id: str
    degree: int
    in_degree: int
    out_degree: int
    clustering_coefficient: float
    betweenness_centrality: float
    closeness_centrality: float
    eigenvector_centrality: float
    pagerank: float
    neighbors: List[str]
    triangles: int


@dataclass
class EdgeMetrics:
    """Metrics for individual edges."""
    edge_id: str
    source: str
    target: str
    weight: float
    betweenness: float
    is_bridge: bool
    clustering_contribution: float


@dataclass
class GraphMetrics:
    """Overall graph metrics."""
    node_count: int
    edge_count: int
    density: float
    average_degree: float
    average_clustering: float
    diameter: int
    radius: int
    connected_components: int
    strongly_connected_components: int
    average_path_length: float
    transitivity: float
    assortativity: float
    modularity: float
    small_world_coefficient: float


@dataclass
class CommunityMetrics:
    """Community analysis metrics."""
    community_id: str
    node_count: int
    internal_edges: int
    external_edges: int
    modularity_contribution: float
    conductance: float
    density: float
    average_clustering: float
    nodes: List[str]


@dataclass
class ComparisonResult:
    """Result of graph comparison."""
    similarity_score: float
    node_overlap: float
    edge_overlap: float
    structural_similarity: float
    metric_differences: Dict[str, float]
    common_nodes: List[str]
    common_edges: List[Tuple[str, str]]
    unique_nodes_a: List[str]
    unique_nodes_b: List[str]


class GraphMetricsCalculator:
    """Main graph metrics calculation engine."""
    
    def __init__(self, graph_builder=None):
        """Initialize the metrics calculator."""
        self.graph = graph_builder
        self.cached_metrics = {}
        self.calculation_stats = {
            "total_calculations": 0,
            "cache_hits": 0,
            "average_calculation_time": 0.0
        }
        logger.info("GraphMetricsCalculator initialized")
    
    async def calculate_node_metrics(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        node_id: str
    ) -> NodeMetrics:
        """
        Calculate comprehensive metrics for a specific node.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            node_id: ID of node to analyze
            
        Returns:
            NodeMetrics object with calculated metrics
        """
        start_time = asyncio.get_event_loop().time()
        
        # Build adjacency structures
        adjacency = self._build_adjacency(nodes, edges)
        
        if node_id not in adjacency:
            raise ValueError(f"Node {node_id} not found in graph")
        
        neighbors = list(adjacency[node_id])
        degree = len(neighbors)
        
        # Calculate in/out degree for directed graphs
        in_degree, out_degree = self._calculate_directed_degrees(edges, node_id)
        
        # Calculate clustering coefficient
        clustering = self._calculate_node_clustering(adjacency, node_id)
        
        # Calculate centrality measures
        centralities = await self._calculate_centralities(adjacency, node_id)
        
        # Count triangles
        triangles = self._count_node_triangles(adjacency, node_id)
        
        calculation_time = asyncio.get_event_loop().time() - start_time
        self._update_calculation_stats(calculation_time)
        
        metrics = NodeMetrics(
            node_id=node_id,
            degree=degree,
            in_degree=in_degree,
            out_degree=out_degree,
            clustering_coefficient=clustering,
            betweenness_centrality=centralities["betweenness"],
            closeness_centrality=centralities["closeness"],
            eigenvector_centrality=centralities["eigenvector"],
            pagerank=centralities["pagerank"],
            neighbors=neighbors,
            triangles=triangles
        )
        
        logger.info(f"Calculated metrics for node {node_id} in {calculation_time:.3f}s")
        return metrics
    
    async def calculate_graph_metrics(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> GraphMetrics:
        """
        Calculate comprehensive metrics for the entire graph.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            
        Returns:
            GraphMetrics object with calculated metrics
        """
        start_time = asyncio.get_event_loop().time()
        
        adjacency = self._build_adjacency(nodes, edges)
        node_count = len(nodes)
        edge_count = len(edges)
        
        # Basic metrics
        density = self._calculate_density(node_count, edge_count)
        average_degree = (2 * edge_count) / node_count if node_count > 0 else 0
        
        # Clustering metrics
        average_clustering = await self._calculate_average_clustering(adjacency)
        transitivity = self._calculate_transitivity(adjacency)
        
        # Distance metrics
        diameter, radius, avg_path_length = await self._calculate_distance_metrics(adjacency)
        
        # Connectivity metrics
        connected_components = self._count_connected_components(adjacency)
        strongly_connected = self._count_strongly_connected_components(adjacency, edges)
        
        # Advanced metrics
        assortativity = self._calculate_assortativity(adjacency)
        modularity = await self._calculate_modularity(adjacency)
        small_world = self._calculate_small_world_coefficient(
            average_clustering, avg_path_length, node_count, edge_count
        )
        
        calculation_time = asyncio.get_event_loop().time() - start_time
        self._update_calculation_stats(calculation_time)
        
        metrics = GraphMetrics(
            node_count=node_count,
            edge_count=edge_count,
            density=density,
            average_degree=average_degree,
            average_clustering=average_clustering,
            diameter=diameter,
            radius=radius,
            connected_components=connected_components,
            strongly_connected_components=strongly_connected,
            average_path_length=avg_path_length,
            transitivity=transitivity,
            assortativity=assortativity,
            modularity=modularity,
            small_world_coefficient=small_world
        )
        
        logger.info(f"Calculated graph metrics for {node_count} nodes, {edge_count} edges in {calculation_time:.3f}s")
        return metrics
    
    async def detect_communities(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        algorithm: str = "louvain"
    ) -> List[CommunityMetrics]:
        """
        Detect communities in the graph and calculate community metrics.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            algorithm: Community detection algorithm
            
        Returns:
            List of CommunityMetrics objects
        """
        adjacency = self._build_adjacency(nodes, edges)
        
        # Simple community detection (modularity-based)
        communities = self._detect_communities_simple(adjacency)
        
        community_metrics = []
        for i, community_nodes in enumerate(communities):
            metrics = await self._calculate_community_metrics(
                community_nodes, adjacency, f"community_{i}"
            )
            community_metrics.append(metrics)
        
        logger.info(f"Detected {len(communities)} communities")
        return community_metrics
    
    async def compare_graphs(
        self,
        nodes_a: List[Dict[str, Any]],
        edges_a: List[Dict[str, Any]],
        nodes_b: List[Dict[str, Any]],
        edges_b: List[Dict[str, Any]]
    ) -> ComparisonResult:
        """
        Compare two graphs and calculate similarity metrics.
        
        Args:
            nodes_a: First graph's nodes
            edges_a: First graph's edges
            nodes_b: Second graph's nodes
            edges_b: Second graph's edges
            
        Returns:
            ComparisonResult with similarity metrics
        """
        # Calculate basic overlap
        nodes_a_ids = {n.get("id") for n in nodes_a}
        nodes_b_ids = {n.get("id") for n in nodes_b}
        common_nodes = list(nodes_a_ids & nodes_b_ids)
        
        edges_a_tuples = {(e.get("source", e.get("from_node")), e.get("target", e.get("to_node"))) for e in edges_a}
        edges_b_tuples = {(e.get("source", e.get("from_node")), e.get("target", e.get("to_node"))) for e in edges_b}
        common_edges = list(edges_a_tuples & edges_b_tuples)
        
        # Calculate overlap ratios
        node_overlap = len(common_nodes) / max(len(nodes_a_ids | nodes_b_ids), 1)
        edge_overlap = len(common_edges) / max(len(edges_a_tuples | edges_b_tuples), 1)
        
        # Calculate structural similarity
        metrics_a = await self.calculate_graph_metrics(nodes_a, edges_a)
        metrics_b = await self.calculate_graph_metrics(nodes_b, edges_b)
        
        structural_similarity = self._calculate_structural_similarity(metrics_a, metrics_b)
        
        # Overall similarity score
        similarity_score = (node_overlap + edge_overlap + structural_similarity) / 3
        
        # Metric differences
        metric_differences = {
            "density_diff": abs(metrics_a.density - metrics_b.density),
            "clustering_diff": abs(metrics_a.average_clustering - metrics_b.average_clustering),
            "path_length_diff": abs(metrics_a.average_path_length - metrics_b.average_path_length)
        }
        
        result = ComparisonResult(
            similarity_score=similarity_score,
            node_overlap=node_overlap,
            edge_overlap=edge_overlap,
            structural_similarity=structural_similarity,
            metric_differences=metric_differences,
            common_nodes=common_nodes,
            common_edges=common_edges,
            unique_nodes_a=list(nodes_a_ids - nodes_b_ids),
            unique_nodes_b=list(nodes_b_ids - nodes_a_ids)
        )
        
        logger.info(f"Graph comparison completed: {similarity_score:.3f} similarity score")
        return result
    
    async def calculate_performance_profile(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate performance profiling metrics for graph operations.
        
        Args:
            nodes: List of node dictionaries
            edges: List of edge dictionaries
            
        Returns:
            Performance profile dictionary
        """
        start_time = asyncio.get_event_loop().time()
        
        # Memory usage estimation
        node_memory = len(nodes) * 100  # Rough estimate
        edge_memory = len(edges) * 80
        total_memory = node_memory + edge_memory
        
        # Complexity estimations
        adjacency_build_complexity = len(nodes) + len(edges)
        shortest_path_complexity = len(nodes) ** 3  # Floyd-Warshall worst case
        centrality_complexity = len(nodes) * len(edges)
        
        # Calculate actual metrics to measure performance
        adjacency = self._build_adjacency(nodes, edges)
        build_time = asyncio.get_event_loop().time() - start_time
        
        profile = {
            "graph_size": {
                "nodes": len(nodes),
                "edges": len(edges),
                "density": self._calculate_density(len(nodes), len(edges))
            },
            "memory_estimation": {
                "nodes_mb": node_memory / (1024 * 1024),
                "edges_mb": edge_memory / (1024 * 1024),
                "total_mb": total_memory / (1024 * 1024)
            },
            "complexity_estimates": {
                "adjacency_build": adjacency_build_complexity,
                "shortest_paths": shortest_path_complexity,
                "centrality": centrality_complexity
            },
            "performance_metrics": {
                "adjacency_build_time": build_time,
                "estimated_centrality_time": centrality_complexity / 1000000,  # Rough estimate
                "estimated_clustering_time": len(nodes) / 100000
            },
            "cache_stats": self.calculation_stats.copy(),
            "recommendations": self._generate_performance_recommendations(len(nodes), len(edges))
        }
        
        logger.info(f"Performance profile calculated for {len(nodes)} nodes, {len(edges)} edges")
        return profile
    
    def get_metric_statistics(self) -> Dict[str, Any]:
        """Get statistics about metric calculations."""
        return {
            "calculation_stats": self.calculation_stats.copy(),
            "cache_size": len(self.cached_metrics),
            "available_metrics": [
                "node_metrics",
                "graph_metrics", 
                "community_metrics",
                "comparison_metrics",
                "performance_profile"
            ]
        }
    
    def clear_cache(self):
        """Clear the metrics cache."""
        self.cached_metrics.clear()
        logger.info("Metrics cache cleared")
    
    # Private helper methods
    
    def _build_adjacency(
        self, 
        nodes: List[Dict[str, Any]], 
        edges: List[Dict[str, Any]]
    ) -> Dict[str, Set[str]]:
        """Build adjacency list representation."""
        adjacency = defaultdict(set)
        
        # Initialize all nodes
        for node in nodes:
            node_id = node.get("id", "")
            adjacency[node_id] = set()
        
        # Add edges
        for edge in edges:
            source = edge.get("source", edge.get("from_node", ""))
            target = edge.get("target", edge.get("to_node", ""))
            if source and target:
                adjacency[source].add(target)
                adjacency[target].add(source)  # Treat as undirected for now
        
        return dict(adjacency)
    
    def _calculate_directed_degrees(
        self, 
        edges: List[Dict[str, Any]], 
        node_id: str
    ) -> Tuple[int, int]:
        """Calculate in-degree and out-degree for directed graphs."""
        in_degree = sum(1 for e in edges if e.get("target", e.get("to_node")) == node_id)
        out_degree = sum(1 for e in edges if e.get("source", e.get("from_node")) == node_id)
        return in_degree, out_degree
    
    def _calculate_node_clustering(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> float:
        """Calculate clustering coefficient for a node."""
        neighbors = adjacency.get(node_id, set())
        if len(neighbors) < 2:
            return 0.0
        
        # Count triangles
        triangles = 0
        neighbor_list = list(neighbors)
        for i in range(len(neighbor_list)):
            for j in range(i + 1, len(neighbor_list)):
                if neighbor_list[j] in adjacency.get(neighbor_list[i], set()):
                    triangles += 1
        
        # Possible triangles
        possible_triangles = len(neighbors) * (len(neighbors) - 1) // 2
        return triangles / possible_triangles if possible_triangles > 0 else 0.0
    
    async def _calculate_centralities(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> Dict[str, float]:
        """Calculate various centrality measures for a node."""
        # Simple implementations - in practice would use more sophisticated algorithms
        
        # Betweenness centrality (simplified)
        betweenness = self._calculate_betweenness_centrality(adjacency, node_id)
        
        # Closeness centrality (simplified)
        closeness = self._calculate_closeness_centrality(adjacency, node_id)
        
        # Eigenvector centrality (simplified)
        eigenvector = self._calculate_eigenvector_centrality(adjacency, node_id)
        
        # PageRank (simplified)
        pagerank = self._calculate_pagerank(adjacency, node_id)
        
        return {
            "betweenness": betweenness,
            "closeness": closeness,
            "eigenvector": eigenvector,
            "pagerank": pagerank
        }
    
    def _calculate_betweenness_centrality(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> float:
        """Calculate betweenness centrality (simplified implementation)."""
        # This is a simplified version - full implementation would use algorithms like Brandes'
        total_paths = 0
        paths_through_node = 0
        
        nodes = list(adjacency.keys())
        for source in nodes:
            if source == node_id:
                continue
            for target in nodes:
                if target == node_id or target == source:
                    continue
                
                # Find if shortest path goes through node_id
                path_exists = self._path_exists(adjacency, source, target)
                if path_exists:
                    total_paths += 1
                    path_through_node = (
                        self._path_exists(adjacency, source, node_id) and 
                        self._path_exists(adjacency, node_id, target)
                    )
                    if path_through_node:
                        paths_through_node += 1
        
        return paths_through_node / total_paths if total_paths > 0 else 0.0
    
    def _calculate_closeness_centrality(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> float:
        """Calculate closeness centrality."""
        distances = self._calculate_shortest_distances(adjacency, node_id)
        if not distances:
            return 0.0
        
        total_distance = sum(distances.values())
        return len(distances) / total_distance if total_distance > 0 else 0.0
    
    def _calculate_eigenvector_centrality(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> float:
        """Calculate eigenvector centrality (simplified)."""
        # Simplified version - real implementation would use power iteration
        neighbors = adjacency.get(node_id, set())
        score = len(neighbors)  # Start with degree
        
        # Add neighbor scores (simplified iteration)
        for neighbor in neighbors:
            neighbor_degree = len(adjacency.get(neighbor, set()))
            score += neighbor_degree * 0.1  # Simplified weighting
        
        # Normalize
        max_possible_score = len(adjacency) ** 2
        return score / max_possible_score if max_possible_score > 0 else 0.0
    
    def _calculate_pagerank(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> float:
        """Calculate PageRank (simplified implementation)."""
        # Simplified PageRank - real implementation would use iterative algorithm
        damping_factor = 0.85
        nodes = list(adjacency.keys())
        n = len(nodes)
        
        if n == 0:
            return 0.0
        
        # Start with uniform distribution
        pagerank = 1.0 / n
        
        # Add contribution from incoming links
        incoming_contribution = 0.0
        for node in nodes:
            if node_id in adjacency.get(node, set()):
                out_degree = len(adjacency.get(node, set()))
                if out_degree > 0:
                    incoming_contribution += (1.0 / n) / out_degree  # Simplified
        
        pagerank = (1 - damping_factor) / n + damping_factor * incoming_contribution
        return pagerank
    
    def _count_node_triangles(
        self, 
        adjacency: Dict[str, Set[str]], 
        node_id: str
    ) -> int:
        """Count triangles involving a specific node."""
        neighbors = adjacency.get(node_id, set())
        triangles = 0
        
        neighbor_list = list(neighbors)
        for i in range(len(neighbor_list)):
            for j in range(i + 1, len(neighbor_list)):
                if neighbor_list[j] in adjacency.get(neighbor_list[i], set()):
                    triangles += 1
        
        return triangles
    
    def _calculate_density(self, node_count: int, edge_count: int) -> float:
        """Calculate graph density."""
        if node_count < 2:
            return 0.0
        max_edges = node_count * (node_count - 1) // 2  # For undirected graph
        return edge_count / max_edges if max_edges > 0 else 0.0
    
    async def _calculate_average_clustering(
        self, 
        adjacency: Dict[str, Set[str]]
    ) -> float:
        """Calculate average clustering coefficient."""
        if not adjacency:
            return 0.0
        
        total_clustering = 0.0
        for node_id in adjacency:
            clustering = self._calculate_node_clustering(adjacency, node_id)
            total_clustering += clustering
        
        return total_clustering / len(adjacency)
    
    def _calculate_transitivity(self, adjacency: Dict[str, Set[str]]) -> float:
        """Calculate graph transitivity."""
        total_triangles = 0
        total_triplets = 0
        
        for node in adjacency:
            neighbors = list(adjacency[node])
            degree = len(neighbors)
            if degree >= 2:
                # Count triangles and triplets for this node
                triangles = self._count_node_triangles(adjacency, node)
                triplets = degree * (degree - 1) // 2
                
                total_triangles += triangles
                total_triplets += triplets
        
        return (3 * total_triangles) / total_triplets if total_triplets > 0 else 0.0
    
    async def _calculate_distance_metrics(
        self, 
        adjacency: Dict[str, Set[str]]
    ) -> Tuple[int, int, float]:
        """Calculate diameter, radius, and average path length."""
        if not adjacency:
            return 0, 0, 0.0
        
        all_distances = []
        max_distances = []
        
        for node in adjacency:
            distances = self._calculate_shortest_distances(adjacency, node)
            if distances:
                node_distances = list(distances.values())
                all_distances.extend(node_distances)
                max_distances.append(max(node_distances))
        
        diameter = max(max_distances) if max_distances else 0
        radius = min(max_distances) if max_distances else 0
        avg_path_length = sum(all_distances) / len(all_distances) if all_distances else 0.0
        
        return diameter, radius, avg_path_length
    
    def _calculate_shortest_distances(
        self, 
        adjacency: Dict[str, Set[str]], 
        start_node: str
    ) -> Dict[str, int]:
        """Calculate shortest distances from start_node to all other nodes using BFS."""
        distances = {start_node: 0}
        queue = deque([start_node])
        
        while queue:
            current = queue.popleft()
            current_distance = distances[current]
            
            for neighbor in adjacency.get(current, set()):
                if neighbor not in distances:
                    distances[neighbor] = current_distance + 1
                    queue.append(neighbor)
        
        # Remove start node from results
        distances.pop(start_node, None)
        return distances
    
    def _path_exists(
        self, 
        adjacency: Dict[str, Set[str]], 
        start: str, 
        end: str
    ) -> bool:
        """Check if path exists between two nodes."""
        if start == end:
            return True
        
        visited = set()
        queue = deque([start])
        
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            
            if current == end:
                return True
            
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        
        return False
    
    def _count_connected_components(self, adjacency: Dict[str, Set[str]]) -> int:
        """Count connected components in the graph."""
        visited = set()
        components = 0
        
        for node in adjacency:
            if node not in visited:
                # Start DFS from this node
                stack = [node]
                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        stack.extend(adjacency.get(current, set()) - visited)
                components += 1
        
        return components
    
    def _count_strongly_connected_components(
        self, 
        adjacency: Dict[str, Set[str]], 
        edges: List[Dict[str, Any]]
    ) -> int:
        """Count strongly connected components (simplified for undirected graphs)."""
        # For undirected graphs, SCC count equals connected component count
        return self._count_connected_components(adjacency)
    
    def _calculate_assortativity(self, adjacency: Dict[str, Set[str]]) -> float:
        """Calculate degree assortativity."""
        # Simplified implementation
        degrees = {node: len(neighbors) for node, neighbors in adjacency.items()}
        
        sum_products = 0
        sum_degrees1 = 0
        sum_degrees2 = 0
        sum_squares1 = 0
        sum_squares2 = 0
        edge_count = 0
        
        for node, neighbors in adjacency.items():
            node_degree = degrees[node]
            for neighbor in neighbors:
                neighbor_degree = degrees[neighbor]
                sum_products += node_degree * neighbor_degree
                sum_degrees1 += node_degree
                sum_degrees2 += neighbor_degree
                sum_squares1 += node_degree * node_degree
                sum_squares2 += neighbor_degree * neighbor_degree
                edge_count += 1
        
        if edge_count == 0:
            return 0.0
        
        # Pearson correlation coefficient
        numerator = (sum_products / edge_count) - (sum_degrees1 / edge_count) * (sum_degrees2 / edge_count)
        denominator_sq = ((sum_squares1 / edge_count) - (sum_degrees1 / edge_count) ** 2) * \
                        ((sum_squares2 / edge_count) - (sum_degrees2 / edge_count) ** 2)
        
        return numerator / math.sqrt(denominator_sq) if denominator_sq > 0 else 0.0
    
    async def _calculate_modularity(self, adjacency: Dict[str, Set[str]]) -> float:
        """Calculate modularity (simplified implementation)."""
        # For now, return a placeholder - full implementation would require community detection
        return 0.5  # Placeholder value
    
    def _calculate_small_world_coefficient(
        self, 
        clustering: float, 
        path_length: float, 
        node_count: int, 
        edge_count: int
    ) -> float:
        """Calculate small world coefficient."""
        if node_count < 2 or path_length == 0:
            return 0.0
        
        # Compare to random graph
        p = edge_count / (node_count * (node_count - 1) / 2)  # Connection probability
        random_clustering = p
        random_path_length = math.log(node_count) / math.log(node_count * p) if p > 0 else float('inf')
        
        if random_clustering == 0 or random_path_length == 0:
            return 0.0
        
        normalized_clustering = clustering / random_clustering if random_clustering > 0 else 0
        normalized_path_length = path_length / random_path_length if random_path_length != float('inf') else 0
        
        return normalized_clustering / normalized_path_length if normalized_path_length > 0 else 0.0
    
    def _detect_communities_simple(
        self, 
        adjacency: Dict[str, Set[str]]
    ) -> List[List[str]]:
        """Simple community detection based on connected components."""
        visited = set()
        communities = []
        
        for node in adjacency:
            if node not in visited:
                community = []
                stack = [node]
                while stack:
                    current = stack.pop()
                    if current not in visited:
                        visited.add(current)
                        community.append(current)
                        stack.extend(adjacency.get(current, set()) - visited)
                communities.append(community)
        
        return communities
    
    async def _calculate_community_metrics(
        self, 
        community_nodes: List[str], 
        adjacency: Dict[str, Set[str]], 
        community_id: str
    ) -> CommunityMetrics:
        """Calculate metrics for a specific community."""
        node_count = len(community_nodes)
        community_set = set(community_nodes)
        
        internal_edges = 0
        external_edges = 0
        
        for node in community_nodes:
            for neighbor in adjacency.get(node, set()):
                if neighbor in community_set:
                    internal_edges += 1
                else:
                    external_edges += 1
        
        internal_edges //= 2  # Each edge counted twice
        
        density = internal_edges / (node_count * (node_count - 1) / 2) if node_count > 1 else 0.0
        conductance = external_edges / (internal_edges + external_edges) if (internal_edges + external_edges) > 0 else 0.0
        
        # Calculate average clustering within community
        total_clustering = 0.0
        for node in community_nodes:
            clustering = self._calculate_node_clustering(adjacency, node)
            total_clustering += clustering
        
        average_clustering = total_clustering / node_count if node_count > 0 else 0.0
        
        return CommunityMetrics(
            community_id=community_id,
            node_count=node_count,
            internal_edges=internal_edges,
            external_edges=external_edges,
            modularity_contribution=0.0,  # Placeholder
            conductance=conductance,
            density=density,
            average_clustering=average_clustering,
            nodes=community_nodes
        )
    
    def _calculate_structural_similarity(
        self, 
        metrics_a: GraphMetrics, 
        metrics_b: GraphMetrics
    ) -> float:
        """Calculate structural similarity between two graph metrics."""
        # Normalize metrics and calculate similarity
        similarities = []
        
        # Density similarity
        max_density = max(metrics_a.density, metrics_b.density, 0.001)
        density_sim = 1 - abs(metrics_a.density - metrics_b.density) / max_density
        similarities.append(density_sim)
        
        # Clustering similarity
        max_clustering = max(metrics_a.average_clustering, metrics_b.average_clustering, 0.001)
        clustering_sim = 1 - abs(metrics_a.average_clustering - metrics_b.average_clustering) / max_clustering
        similarities.append(clustering_sim)
        
        # Path length similarity
        max_path_length = max(metrics_a.average_path_length, metrics_b.average_path_length, 0.001)
        path_sim = 1 - abs(metrics_a.average_path_length - metrics_b.average_path_length) / max_path_length
        similarities.append(path_sim)
        
        return sum(similarities) / len(similarities)
    
    def _generate_performance_recommendations(
        self, 
        node_count: int, 
        edge_count: int
    ) -> List[str]:
        """Generate performance recommendations based on graph size."""
        recommendations = []
        
        if node_count > 10000:
            recommendations.append("Consider using sampling for large-scale metrics")
            recommendations.append("Use parallel processing for centrality calculations")
        
        if edge_count > 50000:
            recommendations.append("Consider edge filtering for performance")
            recommendations.append("Use approximation algorithms for complex metrics")
        
        density = self._calculate_density(node_count, edge_count)
        if density > 0.1:
            recommendations.append("Dense graph detected - consider sparse algorithms")
        
        if not recommendations:
            recommendations.append("Graph size is optimal for standard algorithms")
        
        return recommendations
    
    def _update_calculation_stats(self, calculation_time: float):
        """Update calculation statistics."""
        self.calculation_stats["total_calculations"] += 1
        current_avg = self.calculation_stats["average_calculation_time"]
        total = self.calculation_stats["total_calculations"]
        self.calculation_stats["average_calculation_time"] = (
            (current_avg * (total - 1) + calculation_time) / total
        )
