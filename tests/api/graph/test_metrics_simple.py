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
    def sample_graph_data(self):
        """Sample graph data for testing."""
        return {
            "nodes": [
                {"id": "node1", "type": "person"},
                {"id": "node2", "type": "person"},
                {"id": "node3", "type": "person"},
                {"id": "node4", "type": "person"}
            ],
            "edges": [
                {"id": "edge1", "source": "node1", "target": "node2"},
                {"id": "edge2", "source": "node2", "target": "node3"},
                {"id": "edge3", "source": "node3", "target": "node4"},
                {"id": "edge4", "source": "node1", "target": "node3"}
            ]
        }
    
    @pytest.fixture
    def calculator(self):
        """Create GraphMetricsCalculator instance."""
        return GraphMetricsCalculator()
    
    def test_calculator_initialization(self, calculator):
        """Test GraphMetricsCalculator initialization."""
        assert calculator is not None
    
    @pytest.mark.asyncio
    async def test_calculate_centrality(self, calculator, sample_graph_data):
        """Test centrality calculation."""
        result = await calculator.calculate_centrality(
            sample_graph_data, CentralityMeasure.DEGREE
        )
        assert isinstance(result, dict)
        assert "node1" in result
        assert isinstance(result["node1"], (int, float))
    
    @pytest.mark.asyncio
    async def test_calculate_graph_metrics(self, calculator, sample_graph_data):
        """Test overall graph metrics calculation."""
        result = await calculator.calculate_graph_metrics(sample_graph_data)
        assert isinstance(result, dict)
        assert "node_count" in result or "density" in result
    
    @pytest.mark.asyncio
    async def test_calculate_clustering(self, calculator, sample_graph_data):
        """Test clustering coefficient calculation."""
        result = await calculator.calculate_clustering(sample_graph_data)
        assert isinstance(result, dict)
        # Should contain clustering coefficients for nodes
        for node_id in result:
            assert isinstance(result[node_id], (int, float))
            assert 0 <= result[node_id] <= 1
    
    @pytest.mark.asyncio
    async def test_centrality_measures(self, calculator):
        """Test centrality measure types."""
        assert CentralityMeasure.DEGREE.value == "degree"
        assert CentralityMeasure.BETWEENNESS.value == "betweenness"
        assert CentralityMeasure.CLOSENESS.value == "closeness"
        assert CentralityMeasure.EIGENVECTOR.value == "eigenvector"
    
    @pytest.mark.asyncio
    async def test_metric_types(self, calculator):
        """Test metric type enums."""
        assert MetricType.CENTRALITY.value == "centrality"
        assert MetricType.CLUSTERING.value == "clustering"
        assert MetricType.CONNECTIVITY.value == "connectivity"
    
    @pytest.mark.asyncio
    async def test_empty_graph_metrics(self, calculator):
        """Test metrics calculation on empty graph."""
        empty_graph = {"nodes": [], "edges": []}
        result = await calculator.calculate_graph_metrics(empty_graph)
        assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_single_node_metrics(self, calculator):
        """Test metrics calculation on single node graph."""
        single_node_graph = {
            "nodes": [{"id": "node1"}],
            "edges": []
        }
        result = await calculator.calculate_centrality(
            single_node_graph, CentralityMeasure.DEGREE
        )
        assert isinstance(result, dict)
        assert "node1" in result
        assert result["node1"] == 0  # Single node has degree 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
