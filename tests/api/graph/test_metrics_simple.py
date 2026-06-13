"""
Simplified test suite for Graph API Metrics module.
Target: 100% test coverage for src/api/graph/metrics.py
"""

import pytest
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../src"))

from api.graph.metrics import GraphMetricsCalculator, CentralityMeasure, MetricType


class TestGraphMetricsCalculator:
    """Test GraphMetricsCalculator class with actual available methods."""
    
    @pytest.fixture
    def sample_nodes(self):
        """Sample node data for testing."""
        return [
            {"id": "node1", "properties": {"type": "person", "name": "Alice"}},
            {"id": "node2", "properties": {"type": "person", "name": "Bob"}},
            {"id": "node3", "properties": {"type": "person", "name": "Charlie"}},
            {"id": "node4", "properties": {"type": "person", "name": "David"}}
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Sample edge data for testing."""
        return [
            {"id": "edge1", "source": "node1", "target": "node2", "properties": {"weight": 1.0}},
            {"id": "edge2", "source": "node2", "target": "node3", "properties": {"weight": 1.5}},
            {"id": "edge3", "source": "node3", "target": "node4", "properties": {"weight": 2.0}},
            {"id": "edge4", "source": "node1", "target": "node3", "properties": {"weight": 1.2}}
        ]
    
    @pytest.fixture
    def calculator(self):
        """Create GraphMetricsCalculator instance."""
        return GraphMetricsCalculator()
    
    def test_calculator_initialization(self, calculator):
        """Test GraphMetricsCalculator initialization."""
        assert calculator is not None
        assert hasattr(calculator, 'cached_metrics')
        assert hasattr(calculator, 'calculation_stats')
    
    @pytest.mark.asyncio
    async def test_calculate_node_metrics(self, calculator, sample_nodes, sample_edges):
        """Test node metrics calculation."""
        result = await calculator.calculate_node_metrics(sample_nodes, sample_edges, "node1")
        assert result.node_id == "node1"
        assert isinstance(result.degree, int)
        assert isinstance(result.clustering_coefficient, float)
        assert isinstance(result.betweenness_centrality, float)
        assert isinstance(result.closeness_centrality, float)
        assert isinstance(result.neighbors, list)
    
    @pytest.mark.asyncio
    async def test_calculate_graph_metrics(self, calculator, sample_nodes, sample_edges):
        """Test overall graph metrics calculation."""
        result = await calculator.calculate_graph_metrics(sample_nodes, sample_edges)
        assert result.node_count == 4
        assert result.edge_count == 4
        assert isinstance(result.density, float)
        assert isinstance(result.average_degree, float)
        assert isinstance(result.average_clustering, float)
        assert isinstance(result.connected_components, int)
    
    @pytest.mark.asyncio
    async def test_detect_communities(self, calculator, sample_nodes, sample_edges):
        """Test community detection."""
        communities = await calculator.detect_communities(sample_nodes, sample_edges)
        assert isinstance(communities, list)
        for community in communities:
            assert hasattr(community, 'community_id')
            assert hasattr(community, 'node_count')
            assert isinstance(community.nodes, list)
    
    @pytest.mark.asyncio
    async def test_compare_graphs(self, calculator, sample_nodes, sample_edges):
        """Test graph comparison."""
        # Create slightly different graph for comparison
        nodes_b = sample_nodes[:3]  # Fewer nodes
        edges_b = sample_edges[:2]  # Fewer edges
        
        result = await calculator.compare_graphs(
            sample_nodes, sample_edges, 
            nodes_b, edges_b
        )
        
        assert hasattr(result, 'similarity_score')
        assert hasattr(result, 'node_overlap')
        assert hasattr(result, 'edge_overlap')
        assert isinstance(result.common_nodes, list)
        assert isinstance(result.common_edges, list)
    
    @pytest.mark.asyncio
    async def test_performance_profile(self, calculator, sample_nodes, sample_edges):
        """Test performance profiling."""
        profile = await calculator.calculate_performance_profile(sample_nodes, sample_edges)
        assert "graph_size" in profile
        assert "memory_estimation" in profile
        assert "complexity_estimates" in profile
        assert "performance_metrics" in profile
        assert profile["graph_size"]["nodes"] == 4
        assert profile["graph_size"]["edges"] == 4
    
    def test_centrality_measures(self):
        """Test centrality measure enums."""
        assert CentralityMeasure.DEGREE.value == "degree"
        assert CentralityMeasure.BETWEENNESS.value == "betweenness"
        assert CentralityMeasure.CLOSENESS.value == "closeness"
        assert CentralityMeasure.EIGENVECTOR.value == "eigenvector"
        assert CentralityMeasure.PAGERANK.value == "pagerank"
    
    def test_metric_types(self):
        """Test metric type enums."""
        assert MetricType.NODE_LEVEL.value == "node_level"
        assert MetricType.EDGE_LEVEL.value == "edge_level"
        assert MetricType.GRAPH_LEVEL.value == "graph_level"
        assert MetricType.COMMUNITY_LEVEL.value == "community_level"
    
    @pytest.mark.asyncio
    async def test_empty_graph_metrics(self, calculator):
        """Test metrics calculation on empty graph."""
        result = await calculator.calculate_graph_metrics([], [])
        assert result.node_count == 0
        assert result.edge_count == 0
        assert result.density == 0.0
    
    @pytest.mark.asyncio
    async def test_single_node_metrics(self, calculator):
        """Test metrics calculation on single node graph."""
        single_node = [{"id": "node1", "properties": {}}]
        result = await calculator.calculate_node_metrics(single_node, [], "node1")
        assert result.node_id == "node1"
        assert result.degree == 0  # Single node has degree 0
        assert result.clustering_coefficient == 0.0
    
    def test_get_metric_statistics(self, calculator):
        """Test getting metric calculation statistics."""
        stats = calculator.get_metric_statistics()
        assert "calculation_stats" in stats
        assert "cache_size" in stats
        assert "available_metrics" in stats
        assert isinstance(stats["available_metrics"], list)
    
    def test_clear_cache(self, calculator):
        """Test clearing metrics cache."""
        calculator.clear_cache()
        assert len(calculator.cached_metrics) == 0
    
    @pytest.mark.asyncio
    async def test_invalid_node_metrics(self, calculator, sample_nodes, sample_edges):
        """Test error handling for invalid node ID."""
        with pytest.raises(ValueError, match="Node nonexistent not found"):
            await calculator.calculate_node_metrics(sample_nodes, sample_edges, "nonexistent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
