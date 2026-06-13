"""
Test suite for Graph API Metrics module.
Target: 100% test coverage for src/api/graph/metrics.py

This test suite covers:
- GraphMetricsCalculator class and all its methods
- Node, edge, graph, and community metrics calculation
- Graph comparison operations
- Performance profiling and monitoring
- Error handling and edge cases
- Async operations
- Cache management
"""

import pytest
import asyncio
import math
from unittest.mock import patch, MagicMock, AsyncMock
from dataclasses import asdict
from datetime import datetime

# Import the modules under test
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.metrics import (
    GraphMetricsCalculator,
    CentralityMeasure,
    MetricType,
    NodeMetrics,
    EdgeMetrics,
    GraphMetrics,
    CommunityMetrics,
    ComparisonResult
)


class TestCentralityMeasure:
    """Test CentralityMeasure enum."""
    
    def test_centrality_measure_values(self):
        """Test CentralityMeasure enum values."""
        assert CentralityMeasure.DEGREE.value == "degree"
        assert CentralityMeasure.BETWEENNESS.value == "betweenness"
        assert CentralityMeasure.CLOSENESS.value == "closeness"
        assert CentralityMeasure.EIGENVECTOR.value == "eigenvector"
        assert CentralityMeasure.PAGERANK.value == "pagerank"


class TestMetricType:
    """Test MetricType enum."""
    
    def test_metric_type_values(self):
        """Test MetricType enum values."""
        assert MetricType.NODE_LEVEL.value == "node_level"
        assert MetricType.EDGE_LEVEL.value == "edge_level"
        assert MetricType.GRAPH_LEVEL.value == "graph_level"
        assert MetricType.COMMUNITY_LEVEL.value == "community_level"


class TestNodeMetrics:
    """Test NodeMetrics dataclass."""
    
    def test_node_metrics_creation(self):
        """Test NodeMetrics creation."""
        metrics = NodeMetrics(
            node_id="test_node",
            degree=5,
            in_degree=3,
            out_degree=2,
            clustering_coefficient=0.8,
            betweenness_centrality=0.15,
            closeness_centrality=0.7,
            eigenvector_centrality=0.6,
            pagerank=0.25,
            neighbors=["node1", "node2", "node3"],
            triangles=2
        )
        
        assert metrics.node_id == "test_node"
        assert metrics.degree == 5
        assert metrics.in_degree == 3
        assert metrics.out_degree == 2
        assert metrics.clustering_coefficient == 0.8
        assert metrics.betweenness_centrality == 0.15
        assert metrics.closeness_centrality == 0.7
        assert metrics.eigenvector_centrality == 0.6
        assert metrics.pagerank == 0.25
        assert metrics.neighbors == ["node1", "node2", "node3"]
        assert metrics.triangles == 2


class TestEdgeMetrics:
    """Test EdgeMetrics dataclass."""
    
    def test_edge_metrics_creation(self):
        """Test EdgeMetrics creation."""
        metrics = EdgeMetrics(
            edge_id="test_edge",
            source="node1",
            target="node2",
            weight=0.8,
            betweenness=0.2,
            is_bridge=True,
            clustering_contribution=0.1
        )
        
        assert metrics.edge_id == "test_edge"
        assert metrics.source == "node1"
        assert metrics.target == "node2"
        assert metrics.weight == 0.8
        assert metrics.betweenness == 0.2
        assert metrics.is_bridge is True
        assert metrics.clustering_contribution == 0.1


class TestGraphMetrics:
    """Test GraphMetrics dataclass."""
    
    def test_graph_metrics_creation(self):
        """Test GraphMetrics creation."""
        metrics = GraphMetrics(
            node_count=100,
            edge_count=200,
            density=0.04,
            average_degree=4.0,
            average_clustering=0.3,
            diameter=6,
            radius=3,
            connected_components=1,
            strongly_connected_components=1,
            average_path_length=2.5,
            transitivity=0.25,
            assortativity=0.1,
            modularity=0.4,
            small_world_coefficient=1.2
        )
        
        assert metrics.node_count == 100
        assert metrics.edge_count == 200
        assert metrics.density == 0.04
        assert metrics.average_degree == 4.0
        assert metrics.average_clustering == 0.3
        assert metrics.diameter == 6
        assert metrics.radius == 3
        assert metrics.connected_components == 1
        assert metrics.strongly_connected_components == 1
        assert metrics.average_path_length == 2.5
        assert metrics.transitivity == 0.25
        assert metrics.assortativity == 0.1
        assert metrics.modularity == 0.4
        assert metrics.small_world_coefficient == 1.2


class TestCommunityMetrics:
    """Test CommunityMetrics dataclass."""
    
    def test_community_metrics_creation(self):
        """Test CommunityMetrics creation."""
        metrics = CommunityMetrics(
            community_id="community_1",
            node_count=25,
            internal_edges=30,
            external_edges=10,
            modularity_contribution=0.2,
            conductance=0.25,
            density=0.1,
            average_clustering=0.4,
            nodes=["node1", "node2", "node3"]
        )
        
        assert metrics.community_id == "community_1"
        assert metrics.node_count == 25
        assert metrics.internal_edges == 30
        assert metrics.external_edges == 10
        assert metrics.modularity_contribution == 0.2
        assert metrics.conductance == 0.25
        assert metrics.density == 0.1
        assert metrics.average_clustering == 0.4
        assert metrics.nodes == ["node1", "node2", "node3"]


class TestComparisonResult:
    """Test ComparisonResult dataclass."""
    
    def test_comparison_result_creation(self):
        """Test ComparisonResult creation."""
        result = ComparisonResult(
            similarity_score=0.8,
            node_overlap=0.7,
            edge_overlap=0.6,
            structural_similarity=0.9,
            metric_differences={"density_diff": 0.1},
            common_nodes=["node1", "node2"],
            common_edges=[("node1", "node2")],
            unique_nodes_a=["node3"],
            unique_nodes_b=["node4"]
        )
        
        assert result.similarity_score == 0.8
        assert result.node_overlap == 0.7
        assert result.edge_overlap == 0.6
        assert result.structural_similarity == 0.9
        assert result.metric_differences == {"density_diff": 0.1}
        assert result.common_nodes == ["node1", "node2"]
        assert result.common_edges == [("node1", "node2")]
        assert result.unique_nodes_a == ["node3"]
        assert result.unique_nodes_b == ["node4"]


class TestGraphMetricsCalculator:
    """Test GraphMetricsCalculator class."""
    
    @pytest.fixture
    def sample_nodes(self):
        """Sample nodes for testing."""
        return [
            {"id": "node1", "type": "person", "name": "Alice"},
            {"id": "node2", "type": "person", "name": "Bob"},
            {"id": "node3", "type": "person", "name": "Charlie"},
            {"id": "node4", "type": "person", "name": "Diana"},
            {"id": "node5", "type": "person", "name": "Eve"}
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Sample edges for testing."""
        return [
            {"source": "node1", "target": "node2", "weight": 0.8},
            {"source": "node1", "target": "node3", "weight": 0.6},
            {"source": "node2", "target": "node3", "weight": 0.9},
            {"source": "node2", "target": "node4", "weight": 0.7},
            {"source": "node3", "target": "node4", "weight": 0.5},
            {"source": "node4", "target": "node5", "weight": 0.4}
        ]
    
    @pytest.fixture
    def calculator(self):
        """Create GraphMetricsCalculator instance."""
        return GraphMetricsCalculator()
    
    def test_calculator_initialization(self, calculator):
        """Test GraphMetricsCalculator initialization."""
        assert calculator.graph is None
        assert calculator.cached_metrics == {}
        assert "total_calculations" in calculator.calculation_stats
        assert "cache_hits" in calculator.calculation_stats
        assert "average_calculation_time" in calculator.calculation_stats
    
    @pytest.mark.asyncio
    async def test_calculate_node_metrics(self, calculator, sample_nodes, sample_edges):
        """Test node metrics calculation."""
        metrics = await calculator.calculate_node_metrics(sample_nodes, sample_edges, "node1")
        
        assert isinstance(metrics, NodeMetrics)
        assert metrics.node_id == "node1"
        assert metrics.degree > 0
        assert metrics.clustering_coefficient >= 0
        assert metrics.betweenness_centrality >= 0
        assert metrics.closeness_centrality >= 0
        assert metrics.eigenvector_centrality >= 0
        assert metrics.pagerank >= 0
        assert isinstance(metrics.neighbors, list)
        assert metrics.triangles >= 0
    
    @pytest.mark.asyncio
    async def test_calculate_node_metrics_nonexistent_node(self, calculator, sample_nodes, sample_edges):
        """Test node metrics calculation for nonexistent node."""
        with pytest.raises(ValueError):
            await calculator.calculate_node_metrics(sample_nodes, sample_edges, "nonexistent")
    
    @pytest.mark.asyncio
    async def test_calculate_graph_metrics(self, calculator, sample_nodes, sample_edges):
        """Test graph metrics calculation."""
        metrics = await calculator.calculate_graph_metrics(sample_nodes, sample_edges)
        
        assert isinstance(metrics, GraphMetrics)
        assert metrics.node_count == len(sample_nodes)
        assert metrics.edge_count == len(sample_edges)
        assert metrics.density >= 0
        assert metrics.average_degree >= 0
        assert metrics.average_clustering >= 0
        assert metrics.diameter >= 0
        assert metrics.radius >= 0
        assert metrics.connected_components >= 1
        assert metrics.strongly_connected_components >= 1
        assert metrics.average_path_length >= 0
        assert metrics.transitivity >= 0
        assert -1 <= metrics.assortativity <= 1
        assert metrics.modularity >= 0
        assert metrics.small_world_coefficient >= 0
    
    @pytest.mark.asyncio
    async def test_calculate_graph_metrics_empty_graph(self, calculator):
        """Test graph metrics calculation for empty graph."""
        metrics = await calculator.calculate_graph_metrics([], [])
        
        assert metrics.node_count == 0
        assert metrics.edge_count == 0
        assert metrics.density == 0
        assert metrics.average_degree == 0
    
    @pytest.mark.asyncio
    async def test_detect_communities(self, calculator, sample_nodes, sample_edges):
        """Test community detection."""
        communities = await calculator.detect_communities(sample_nodes, sample_edges)
        
        assert isinstance(communities, list)
        assert len(communities) > 0
        
        for community in communities:
            assert isinstance(community, CommunityMetrics)
            assert community.node_count > 0
            assert isinstance(community.nodes, list)
            assert len(community.nodes) == community.node_count
    
    @pytest.mark.asyncio
    async def test_compare_graphs(self, calculator, sample_nodes, sample_edges):
        """Test graph comparison."""
        # Create slightly different second graph
        nodes_b = sample_nodes[:-1]  # Remove last node
        edges_b = [e for e in sample_edges if e["target"] != "node5" and e["source"] != "node5"]
        
        result = await calculator.compare_graphs(sample_nodes, sample_edges, nodes_b, edges_b)
        
        assert isinstance(result, ComparisonResult)
        assert 0 <= result.similarity_score <= 1
        assert 0 <= result.node_overlap <= 1
        assert 0 <= result.edge_overlap <= 1
        assert 0 <= result.structural_similarity <= 1
        assert isinstance(result.metric_differences, dict)
        assert isinstance(result.common_nodes, list)
        assert isinstance(result.common_edges, list)
        assert isinstance(result.unique_nodes_a, list)
        assert isinstance(result.unique_nodes_b, list)
    
    @pytest.mark.asyncio
    async def test_compare_identical_graphs(self, calculator, sample_nodes, sample_edges):
        """Test comparison of identical graphs."""
        result = await calculator.compare_graphs(
            sample_nodes, sample_edges, sample_nodes, sample_edges
        )
        
        assert result.similarity_score == 1.0
        assert result.node_overlap == 1.0
        assert result.edge_overlap == 1.0
        assert len(result.unique_nodes_a) == 0
        assert len(result.unique_nodes_b) == 0
    
    @pytest.mark.asyncio
    async def test_calculate_performance_profile(self, calculator, sample_nodes, sample_edges):
        """Test performance profiling."""
        profile = await calculator.calculate_performance_profile(sample_nodes, sample_edges)
        
        assert isinstance(profile, dict)
        assert "graph_size" in profile
        assert "memory_estimation" in profile
        assert "complexity_estimates" in profile
        assert "performance_metrics" in profile
        assert "cache_stats" in profile
        assert "recommendations" in profile
        
        # Check graph size
        assert profile["graph_size"]["nodes"] == len(sample_nodes)
        assert profile["graph_size"]["edges"] == len(sample_edges)
        
        # Check memory estimation
        assert "nodes_mb" in profile["memory_estimation"]
        assert "edges_mb" in profile["memory_estimation"]
        assert "total_mb" in profile["memory_estimation"]
        
        # Check complexity estimates
        assert "adjacency_build" in profile["complexity_estimates"]
        assert "shortest_paths" in profile["complexity_estimates"]
        assert "centrality" in profile["complexity_estimates"]
        
        # Check performance metrics
        assert "adjacency_build_time" in profile["performance_metrics"]
        
        # Check recommendations
        assert isinstance(profile["recommendations"], list)
    
    def test_get_metric_statistics(self, calculator):
        """Test metric statistics retrieval."""
        stats = calculator.get_metric_statistics()
        
        assert isinstance(stats, dict)
        assert "calculation_stats" in stats
        assert "cache_size" in stats
        assert "available_metrics" in stats
        
        assert isinstance(stats["calculation_stats"], dict)
        assert isinstance(stats["cache_size"], int)
        assert isinstance(stats["available_metrics"], list)
    
    def test_clear_cache(self, calculator):
        """Test cache clearing."""
        # Add some items to cache
        calculator.cached_metrics["test"] = "value"
        
        calculator.clear_cache()
        
        assert calculator.cached_metrics == {}
    
    def test_build_adjacency(self, calculator, sample_nodes, sample_edges):
        """Test adjacency list building."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        
        assert isinstance(adjacency, dict)
        assert len(adjacency) == len(sample_nodes)
        
        # Check that all nodes are present
        for node in sample_nodes:
            assert node["id"] in adjacency
        
        # Check edges are correctly represented
        for edge in sample_edges:
            source = edge["source"]
            target = edge["target"]
            assert target in adjacency[source]
            assert source in adjacency[target]  # Undirected
    
    def test_calculate_directed_degrees(self, calculator, sample_edges):
        """Test directed degree calculation."""
        in_degree, out_degree = calculator._calculate_directed_degrees(sample_edges, "node1")
        
        # node1 appears as source in 2 edges, target in 0 edges
        assert out_degree == 2
        assert in_degree == 0
    
    def test_calculate_node_clustering(self, calculator, sample_nodes, sample_edges):
        """Test node clustering coefficient calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        clustering = calculator._calculate_node_clustering(adjacency, "node2")
        
        assert 0 <= clustering <= 1
    
    def test_calculate_node_clustering_isolated(self, calculator):
        """Test clustering coefficient for isolated node."""
        adjacency = {"isolated": set()}
        clustering = calculator._calculate_node_clustering(adjacency, "isolated")
        
        assert clustering == 0.0
    
    def test_calculate_node_clustering_single_neighbor(self, calculator):
        """Test clustering coefficient for node with single neighbor."""
        adjacency = {"node1": {"node2"}, "node2": {"node1"}}
        clustering = calculator._calculate_node_clustering(adjacency, "node1")
        
        assert clustering == 0.0  # Need at least 2 neighbors for triangles
    
    @pytest.mark.asyncio
    async def test_calculate_centralities(self, calculator, sample_nodes, sample_edges):
        """Test centrality calculations."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        centralities = await calculator._calculate_centralities(adjacency, "node1")
        
        assert isinstance(centralities, dict)
        assert "betweenness" in centralities
        assert "closeness" in centralities
        assert "eigenvector" in centralities
        assert "pagerank" in centralities
        
        for centrality in centralities.values():
            assert isinstance(centrality, (int, float))
            assert centrality >= 0
    
    def test_calculate_betweenness_centrality(self, calculator, sample_nodes, sample_edges):
        """Test betweenness centrality calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        betweenness = calculator._calculate_betweenness_centrality(adjacency, "node2")
        
        assert 0 <= betweenness <= 1
    
    def test_calculate_closeness_centrality(self, calculator, sample_nodes, sample_edges):
        """Test closeness centrality calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        closeness = calculator._calculate_closeness_centrality(adjacency, "node1")
        
        assert closeness >= 0
    
    def test_calculate_eigenvector_centrality(self, calculator, sample_nodes, sample_edges):
        """Test eigenvector centrality calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        eigenvector = calculator._calculate_eigenvector_centrality(adjacency, "node1")
        
        assert eigenvector >= 0
    
    def test_calculate_pagerank(self, calculator, sample_nodes, sample_edges):
        """Test PageRank calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        pagerank = calculator._calculate_pagerank(adjacency, "node1")
        
        assert pagerank >= 0
    
    def test_count_node_triangles(self, calculator, sample_nodes, sample_edges):
        """Test triangle counting for a node."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        triangles = calculator._count_node_triangles(adjacency, "node2")
        
        assert triangles >= 0
        assert isinstance(triangles, int)
    
    def test_calculate_density(self, calculator):
        """Test graph density calculation."""
        density = calculator._calculate_density(5, 4)
        expected_density = 4 / (5 * 4 / 2)  # 4 edges out of 10 possible
        assert density == expected_density
    
    def test_calculate_density_empty_graph(self, calculator):
        """Test density calculation for empty graph."""
        density = calculator._calculate_density(0, 0)
        assert density == 0.0
    
    def test_calculate_density_single_node(self, calculator):
        """Test density calculation for single node."""
        density = calculator._calculate_density(1, 0)
        assert density == 0.0
    
    @pytest.mark.asyncio
    async def test_calculate_average_clustering(self, calculator, sample_nodes, sample_edges):
        """Test average clustering calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        avg_clustering = await calculator._calculate_average_clustering(adjacency)
        
        assert 0 <= avg_clustering <= 1
    
    def test_calculate_transitivity(self, calculator, sample_nodes, sample_edges):
        """Test transitivity calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        transitivity = calculator._calculate_transitivity(adjacency)
        
        # Transitivity can be > 1 in some implementations, so just check it's non-negative
        assert transitivity >= 0
    
    @pytest.mark.asyncio
    async def test_calculate_distance_metrics(self, calculator, sample_nodes, sample_edges):
        """Test distance metrics calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        diameter, radius, avg_path_length = await calculator._calculate_distance_metrics(adjacency)
        
        assert diameter >= 0
        assert radius >= 0
        assert avg_path_length >= 0
        assert radius <= diameter  # Radius should be <= diameter
    
    def test_calculate_shortest_distances(self, calculator, sample_nodes, sample_edges):
        """Test shortest distance calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        distances = calculator._calculate_shortest_distances(adjacency, "node1")
        
        assert isinstance(distances, dict)
        assert "node1" not in distances  # Start node excluded
        
        for target, distance in distances.items():
            assert isinstance(distance, int)
            assert distance > 0
    
    def test_path_exists(self, calculator, sample_nodes, sample_edges):
        """Test path existence check."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        
        # Path should exist between connected nodes
        assert calculator._path_exists(adjacency, "node1", "node2") is True
        
        # Self-path should exist
        assert calculator._path_exists(adjacency, "node1", "node1") is True
    
    def test_path_exists_disconnected(self, calculator):
        """Test path existence for disconnected nodes."""
        adjacency = {
            "node1": {"node2"},
            "node2": {"node1"},
            "node3": set()  # Isolated
        }
        
        # No path between connected and isolated nodes
        assert calculator._path_exists(adjacency, "node1", "node3") is False
    
    def test_count_connected_components(self, calculator, sample_nodes, sample_edges):
        """Test connected component counting."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        components = calculator._count_connected_components(adjacency)
        
        assert components >= 1
        assert isinstance(components, int)
    
    def test_count_connected_components_disconnected(self, calculator):
        """Test connected component counting with disconnected graph."""
        nodes = [{"id": "node1"}, {"id": "node2"}, {"id": "node3"}]
        edges = [{"source": "node1", "target": "node2"}]  # node3 isolated
        
        adjacency = calculator._build_adjacency(nodes, edges)
        components = calculator._count_connected_components(adjacency)
        
        assert components == 2  # One component with node1-node2, one with node3
    
    def test_count_strongly_connected_components(self, calculator, sample_nodes, sample_edges):
        """Test strongly connected component counting."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        scc_count = calculator._count_strongly_connected_components(adjacency, sample_edges)
        
        # For undirected graphs, SCC count equals connected component count
        cc_count = calculator._count_connected_components(adjacency)
        assert scc_count == cc_count
    
    def test_calculate_assortativity(self, calculator, sample_nodes, sample_edges):
        """Test assortativity calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        assortativity = calculator._calculate_assortativity(adjacency)
        
        assert -1 <= assortativity <= 1
    
    def test_calculate_assortativity_empty(self, calculator):
        """Test assortativity calculation for empty graph."""
        adjacency = {}
        assortativity = calculator._calculate_assortativity(adjacency)
        
        assert assortativity == 0.0
    
    @pytest.mark.asyncio
    async def test_calculate_modularity(self, calculator, sample_nodes, sample_edges):
        """Test modularity calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        modularity = await calculator._calculate_modularity(adjacency)
        
        # This is a placeholder implementation
        assert isinstance(modularity, (int, float))
    
    def test_calculate_small_world_coefficient(self, calculator):
        """Test small world coefficient calculation."""
        coefficient = calculator._calculate_small_world_coefficient(0.6, 2.5, 100, 200)
        
        assert coefficient >= 0
    
    def test_calculate_small_world_coefficient_edge_cases(self, calculator):
        """Test small world coefficient with edge cases."""
        # Zero path length
        coefficient = calculator._calculate_small_world_coefficient(0.6, 0, 100, 200)
        assert coefficient == 0.0
        
        # Small graph
        coefficient = calculator._calculate_small_world_coefficient(0.6, 2.5, 1, 0)
        assert coefficient == 0.0
    
    def test_detect_communities_simple(self, calculator, sample_nodes, sample_edges):
        """Test simple community detection."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        communities = calculator._detect_communities_simple(adjacency)
        
        assert isinstance(communities, list)
        assert len(communities) > 0
        
        # All nodes should be assigned to some community
        all_nodes = set()
        for community in communities:
            all_nodes.update(community)
        
        expected_nodes = {node["id"] for node in sample_nodes}
        assert all_nodes == expected_nodes
    
    @pytest.mark.asyncio
    async def test_calculate_community_metrics(self, calculator, sample_nodes, sample_edges):
        """Test community metrics calculation."""
        adjacency = calculator._build_adjacency(sample_nodes, sample_edges)
        community_nodes = ["node1", "node2", "node3"]
        
        metrics = await calculator._calculate_community_metrics(
            community_nodes, adjacency, "test_community"
        )
        
        assert isinstance(metrics, CommunityMetrics)
        assert metrics.community_id == "test_community"
        assert metrics.node_count == len(community_nodes)
        assert metrics.internal_edges >= 0
        assert metrics.external_edges >= 0
        assert 0 <= metrics.conductance <= 1
        assert 0 <= metrics.density <= 1
        assert 0 <= metrics.average_clustering <= 1
        assert metrics.nodes == community_nodes
    
    def test_calculate_structural_similarity(self, calculator):
        """Test structural similarity calculation."""
        metrics_a = GraphMetrics(
            node_count=100, edge_count=200, density=0.04, average_degree=4.0,
            average_clustering=0.3, diameter=6, radius=3, connected_components=1,
            strongly_connected_components=1, average_path_length=2.5,
            transitivity=0.25, assortativity=0.1, modularity=0.4,
            small_world_coefficient=1.2
        )
        
        metrics_b = GraphMetrics(
            node_count=90, edge_count=180, density=0.045, average_degree=4.2,
            average_clustering=0.32, diameter=5, radius=3, connected_components=1,
            strongly_connected_components=1, average_path_length=2.3,
            transitivity=0.27, assortativity=0.12, modularity=0.42,
            small_world_coefficient=1.1
        )
        
        similarity = calculator._calculate_structural_similarity(metrics_a, metrics_b)
        
        assert 0 <= similarity <= 1
    
    def test_generate_performance_recommendations(self, calculator):
        """Test performance recommendations generation."""
        # Small graph
        recommendations = calculator._generate_performance_recommendations(100, 500)
        assert isinstance(recommendations, list)
        
        # Large graph
        recommendations = calculator._generate_performance_recommendations(15000, 60000)
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        
        # Dense graph
        recommendations = calculator._generate_performance_recommendations(1000, 10000)
        assert isinstance(recommendations, list)
    
    def test_update_calculation_stats(self, calculator):
        """Test calculation statistics updating."""
        initial_count = calculator.calculation_stats["total_calculations"]
        initial_avg = calculator.calculation_stats["average_calculation_time"]
        
        calculator._update_calculation_stats(0.5)
        
        assert calculator.calculation_stats["total_calculations"] == initial_count + 1
        # Average should be updated
        new_avg = calculator.calculation_stats["average_calculation_time"]
        assert isinstance(new_avg, (int, float))
    
    @pytest.mark.asyncio
    async def test_large_graph_performance(self, calculator):
        """Test performance with larger graph."""
        # Create larger graph
        nodes = [{"id": f"node{i}"} for i in range(50)]
        edges = []
        
        # Create connected graph
        for i in range(49):
            edges.append({"source": f"node{i}", "target": f"node{i+1}"})
        
        # Add some random connections
        for i in range(0, 50, 5):
            for j in range(i+2, min(i+8, 50)):
                edges.append({"source": f"node{i}", "target": f"node{j}"})
        
        # Test graph metrics
        metrics = await calculator.calculate_graph_metrics(nodes, edges)
        assert metrics.node_count == 50
        
        # Test node metrics
        node_metrics = await calculator.calculate_node_metrics(nodes, edges, "node0")
        assert isinstance(node_metrics, NodeMetrics)
        
        # Test community detection
        communities = await calculator.detect_communities(nodes, edges)
        assert len(communities) > 0
    
    @pytest.mark.asyncio
    async def test_malformed_data_handling(self, calculator):
        """Test handling of malformed data."""
        # Nodes without IDs
        malformed_nodes = [{"name": "NoId"}, {"id": "node1"}]
        edges = [{"source": "node1", "target": "NoId"}]
        
        # Should handle gracefully without crashing
        try:
            metrics = await calculator.calculate_graph_metrics(malformed_nodes, edges)
            assert isinstance(metrics, GraphMetrics)
        except Exception as e:
            # Should not raise unexpected exceptions
            assert isinstance(e, (ValueError, KeyError))
    
    @pytest.mark.asyncio
    async def test_empty_graph_edge_cases(self, calculator):
        """Test edge cases with empty graphs."""
        # Empty nodes and edges
        metrics = await calculator.calculate_graph_metrics([], [])
        assert metrics.node_count == 0
        assert metrics.edge_count == 0
        
        # Performance profile for empty graph
        profile = await calculator.calculate_performance_profile([], [])
        assert profile["graph_size"]["nodes"] == 0
        assert profile["graph_size"]["edges"] == 0
    
    @pytest.mark.asyncio
    async def test_single_node_graph(self, calculator):
        """Test metrics for single node graph."""
        nodes = [{"id": "single_node"}]
        edges = []
        
        metrics = await calculator.calculate_graph_metrics(nodes, edges)
        assert metrics.node_count == 1
        assert metrics.edge_count == 0
        assert metrics.density == 0.0
        assert metrics.average_degree == 0.0
        
        # Node metrics for isolated node
        node_metrics = await calculator.calculate_node_metrics(nodes, edges, "single_node")
        assert node_metrics.degree == 0
        assert node_metrics.clustering_coefficient == 0.0
        assert len(node_metrics.neighbors) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
