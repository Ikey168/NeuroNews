"""Comprehensive tests for src/api/graph/metrics.py."""

import os
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from api.graph.metrics import (  # noqa: E402
    GraphMetrics,
    GraphMetricsCalculator,
    NodeMetrics,
)


# A small triangle graph: n1-n2-n3-n1, plus n4 connected to n1
NODES = [{"id": f"n{i}"} for i in range(1, 5)]
EDGES = [
    {"source": "n1", "target": "n2"},
    {"source": "n2", "target": "n3"},
    {"source": "n3", "target": "n1"},
    {"source": "n1", "target": "n4"},
]


@pytest.fixture
def calc():
    return GraphMetricsCalculator()


class TestAdjacency:
    def test_build_adjacency(self, calc):
        adj = calc._build_adjacency(NODES, EDGES)
        assert adj["n1"] == {"n2", "n3", "n4"}
        assert adj["n2"] == {"n1", "n3"}
        assert adj["n4"] == {"n1"}

    def test_from_node_to_node_keys(self, calc):
        adj = calc._build_adjacency(
            [{"id": "a"}, {"id": "b"}],
            [{"from_node": "a", "to_node": "b"}],
        )
        assert adj["a"] == {"b"}


class TestDensity:
    def test_density(self, calc):
        # 4 nodes, 4 edges: density = 2*E / (N*(N-1)) = 8/12
        assert calc._calculate_density(4, 4) == pytest.approx(8 / 12)

    def test_density_zero_nodes(self, calc):
        assert calc._calculate_density(0, 0) == 0

    def test_density_single_node(self, calc):
        assert calc._calculate_density(1, 0) == 0


class TestNodeClusteringAndTriangles:
    def test_clustering_in_triangle(self, calc):
        adj = calc._build_adjacency(NODES, EDGES)
        # n2's neighbors are n1,n3 which are connected -> clustering 1.0
        assert calc._calculate_node_clustering(adj, "n2") == pytest.approx(1.0)

    def test_triangles(self, calc):
        adj = calc._build_adjacency(NODES, EDGES)
        assert calc._count_node_triangles(adj, "n1") >= 1


class TestConnectivity:
    def test_connected_components_single(self, calc):
        adj = calc._build_adjacency(NODES, EDGES)
        assert calc._count_connected_components(adj) == 1

    def test_connected_components_split(self, calc):
        nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}]
        edges = [{"source": "a", "target": "b"}, {"source": "c", "target": "d"}]
        adj = calc._build_adjacency(nodes, edges)
        assert calc._count_connected_components(adj) == 2

    def test_path_exists(self, calc):
        adj = calc._build_adjacency(NODES, EDGES)
        assert calc._path_exists(adj, "n4", "n3") is True

    def test_path_not_exists(self, calc):
        nodes = [{"id": "a"}, {"id": "z"}]
        adj = calc._build_adjacency(nodes, [])
        assert calc._path_exists(adj, "a", "z") is False


class TestPagerank:
    def test_pagerank_per_node(self, calc):
        adj = calc._build_adjacency(NODES, EDGES)
        pr = {n: calc._calculate_pagerank(adj, n) for n in adj}
        assert all(v > 0 for v in pr.values())
        # n1 (highest in-degree) should have the highest pagerank
        assert pr["n1"] == max(pr.values())


class TestAsyncMetrics:
    @pytest.mark.asyncio
    async def test_calculate_node_metrics(self, calc):
        m = await calc.calculate_node_metrics(NODES, EDGES, "n1")
        assert isinstance(m, NodeMetrics)
        assert m.degree == 3
        assert set(m.neighbors) == {"n2", "n3", "n4"}

    @pytest.mark.asyncio
    async def test_node_metrics_missing_node(self, calc):
        with pytest.raises(ValueError):
            await calc.calculate_node_metrics(NODES, EDGES, "nonexistent")

    @pytest.mark.asyncio
    async def test_calculate_graph_metrics(self, calc):
        m = await calc.calculate_graph_metrics(NODES, EDGES)
        assert isinstance(m, GraphMetrics)
        assert m.node_count == 4
        assert m.edge_count == 4
        assert m.connected_components == 1
        assert 0 <= m.density <= 1

    @pytest.mark.asyncio
    async def test_empty_graph(self, calc):
        m = await calc.calculate_graph_metrics([], [])
        assert m.node_count == 0
        assert m.density == 0


class TestStatsAndCache:
    def test_get_metric_statistics(self, calc):
        assert isinstance(calc.get_metric_statistics(), dict)

    def test_clear_cache(self, calc):
        calc.clear_cache()  # should not raise
