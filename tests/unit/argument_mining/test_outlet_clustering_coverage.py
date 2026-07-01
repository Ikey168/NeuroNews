"""
Coverage tests for src/argument_mining/outlet_clustering.py (#115).

Exercises the vector builder, the cluster-labelling helper, the real
sklearn-backed clustering (k-means + Ward + PCA + silhouette), persistence, and
the pipeline entry point. sklearn/numpy are real; DB access is mocked with a
SQL-routing fake connection so these run offline.
"""
from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock

import numpy as np
import pytest

pytest.importorskip("sklearn")

from src.argument_mining.outlet_clustering import (
    ClusterResult,
    FRAME_LABELS,
    OutletCluster,
    OutletVector,
    build_outlet_vectors,
    run_cluster_pipeline,
    run_clustering,
    store_clusters,
    _date_cutoff,
    _label_cluster,
)


# ---------------------------------------------------------------------------
# SQL-routing fake connection
# ---------------------------------------------------------------------------

class _RoutingConn:
    """DuckDB-alike: fetchall returns preset rows keyed by a substring found in
    the executed SQL (first match wins). Records executed statements."""

    def __init__(self, routes=None):
        self._routes = routes or []
        self.executed = []
        self._lock = threading.Lock()

    def _rows_for(self, sql):
        for needle, rows in self._routes:
            if needle in sql:
                return rows
        return []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        rows = self._rows_for(sql)
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.fetchone.return_value = rows[0] if rows else None
        return cur


def _lock():
    return threading.Lock()


def _make_outlets(vectors):
    """Build OutletVector list + stacked matrix from a list of 7-dim vectors."""
    outlets = []
    for i, v in enumerate(vectors):
        arr = np.asarray(v, dtype=np.float32)
        norm = np.linalg.norm(arr)
        if norm > 0:
            arr = arr / norm
        outlets.append(OutletVector(
            source=f"src{i}", source_type="news", doc_count=10, vector=arr,
        ))
    matrix = np.stack([o.vector for o in outlets])
    return outlets, matrix


# ---------------------------------------------------------------------------
# _date_cutoff
# ---------------------------------------------------------------------------

class TestDateCutoff(unittest.TestCase):
    def test_known_ranges_parse(self):
        import datetime as _dt
        for rng in ("7d", "30d", "90d", "180d", "365d"):
            _dt.date.fromisoformat(_date_cutoff(rng))

    def test_unknown_defaults_to_90d(self):
        self.assertEqual(_date_cutoff("weird"), _date_cutoff("90d"))


# ---------------------------------------------------------------------------
# _label_cluster
# ---------------------------------------------------------------------------

class TestLabelCluster(unittest.TestCase):
    def test_dominant_when_one_frame_over_threshold(self):
        # economic strongly dominant (> 0.50)
        centroid = np.zeros(len(FRAME_LABELS))
        centroid[0] = 0.9   # economic
        centroid[1] = 0.1
        label, dominant = _label_cluster(centroid)
        self.assertEqual(label, "economic-dominant")
        self.assertEqual(dominant, "economic")

    def test_balanced_when_top_two_close(self):
        # top two within _BALANCED_GAP (0.12), neither over 0.50
        centroid = np.zeros(len(FRAME_LABELS))
        centroid[0] = 0.30   # economic
        centroid[1] = 0.25   # security -> gap 0.05 < 0.12
        label, dominant = _label_cluster(centroid)
        self.assertTrue(label.startswith("balanced-economic-security"))
        self.assertEqual(dominant, "economic")

    def test_focused_when_clear_leader_below_threshold(self):
        # top below 0.50, gap to second >= 0.12 -> focused
        centroid = np.zeros(len(FRAME_LABELS))
        centroid[4] = 0.40   # political
        centroid[0] = 0.10
        label, dominant = _label_cluster(centroid)
        self.assertEqual(label, "political-focused")
        self.assertEqual(dominant, "political")


# ---------------------------------------------------------------------------
# build_outlet_vectors
# ---------------------------------------------------------------------------

class TestBuildOutletVectors(unittest.TestCase):
    def test_empty_returns_empty_matrix(self):
        conn = _RoutingConn(routes=[
            ("JOIN news_articles n ON df.document_id = n.id", []),
            ("WHERE df.source_type != 'news'", []),
        ])
        outlets, matrix = build_outlet_vectors(conn)
        self.assertEqual(outlets, [])
        self.assertEqual(matrix.shape, (0, len(FRAME_LABELS)))

    def test_builds_normalised_vectors_and_filters_small_outlets(self):
        # news rows: (source, source_type, frame, avg_score, doc_count)
        news = [
            ("Reuters", "news", "economic", 0.8, 10),
            ("Reuters", "news", "security", 0.2, 10),
            ("Tiny",    "news", "economic", 0.9, 2),   # < 3 docs -> excluded
        ]
        other = [
            ("blog", "blog", "political", 0.5, 5),
            ("blog", "blog", "economic", 0.5, 5),
        ]
        conn = _RoutingConn(routes=[
            ("JOIN news_articles n ON df.document_id = n.id", news),
            ("WHERE df.source_type != 'news'", other),
        ])
        outlets, matrix = build_outlet_vectors(conn, date_range="30d")
        srcs = {o.source for o in outlets}
        self.assertIn("Reuters", srcs)
        self.assertIn("blog", srcs)
        self.assertNotIn("Tiny", srcs)      # filtered by doc_count < 3
        self.assertEqual(matrix.shape[1], len(FRAME_LABELS))
        # Each retained vector is L2-normalised
        for o in outlets:
            self.assertAlmostEqual(float(np.linalg.norm(o.vector)), 1.0, places=4)

    def test_cutoff_clause_present_for_dated_range(self):
        conn = _RoutingConn(routes=[
            ("JOIN news_articles n ON df.document_id = n.id",
             [("Reuters", "news", "economic", 0.5, 5)]),
            ("WHERE df.source_type != 'news'", []),
        ])
        build_outlet_vectors(conn, date_range="7d")
        news_sql = conn.executed[0][0]
        self.assertIn("publish_date >=", news_sql)

    def test_zero_vector_not_normalised(self):
        # An outlet whose only frame score is 0 -> norm 0, vector left as zeros
        news = [("Zero", "news", "economic", 0.0, 5)]
        conn = _RoutingConn(routes=[
            ("JOIN news_articles n ON df.document_id = n.id", news),
            ("WHERE df.source_type != 'news'", []),
        ])
        outlets, matrix = build_outlet_vectors(conn)
        self.assertEqual(len(outlets), 1)
        self.assertEqual(float(np.linalg.norm(outlets[0].vector)), 0.0)


# ---------------------------------------------------------------------------
# run_clustering  (real sklearn)
# ---------------------------------------------------------------------------

class TestRunClustering(unittest.TestCase):
    def test_two_clear_groups(self):
        # Two well-separated clusters of economic- vs security-dominant outlets
        vecs = [
            [0.9, 0.1, 0, 0, 0, 0, 0],
            [0.85, 0.15, 0, 0, 0, 0, 0],
            [0.88, 0.12, 0, 0, 0, 0, 0],
            [0.1, 0.9, 0, 0, 0, 0, 0],
            [0.15, 0.85, 0, 0, 0, 0, 0],
            [0.12, 0.88, 0, 0, 0, 0, 0],
        ]
        outlets, matrix = _make_outlets(vecs)
        result = run_clustering(outlets, matrix, k_min=2, k_max=4)

        self.assertIsInstance(result, ClusterResult)
        self.assertEqual(result.n_outlets, 6)
        self.assertIn(result.method, ("kmeans", "hierarchical"))
        self.assertGreaterEqual(result.k, 2)
        self.assertGreater(result.silhouette, 0.0)   # clean separation
        self.assertEqual(len(result.outlets), 6)
        for oc in result.outlets:
            self.assertIsInstance(oc, OutletCluster)
            self.assertIsInstance(oc.pca_x, float)
            self.assertIsInstance(oc.pca_y, float)
            self.assertTrue(oc.cluster_label)
            self.assertIn(oc.dominant_frame, FRAME_LABELS)
        # The two economic outlets should share a cluster distinct from security ones
        cluster_of = {oc.source: oc.cluster_id for oc in result.outlets}
        econ = {cluster_of["src0"], cluster_of["src1"], cluster_of["src2"]}
        sec = {cluster_of["src3"], cluster_of["src4"], cluster_of["src5"]}
        self.assertEqual(len(econ), 1)
        self.assertEqual(len(sec), 1)
        self.assertNotEqual(econ, sec)

    def test_pca_projection_populated(self):
        vecs = [
            [0.9, 0.1, 0, 0, 0, 0, 0],
            [0.1, 0.9, 0, 0, 0, 0, 0],
            [0.5, 0.5, 0, 0, 0, 0, 0],
            [0.2, 0.1, 0.7, 0, 0, 0, 0],
        ]
        outlets, matrix = _make_outlets(vecs)
        result = run_clustering(outlets, matrix, k_min=2, k_max=3)
        # PCA coords must not all be zero for a non-degenerate matrix
        coords = [(o.pca_x, o.pca_y) for o in result.outlets]
        self.assertTrue(any(x != 0.0 or y != 0.0 for x, y in coords))

    def test_small_matrix_two_samples(self):
        # n=2 -> effective_kmax = 1, loop may not score; still returns a result
        vecs = [
            [0.9, 0.1, 0, 0, 0, 0, 0],
            [0.1, 0.9, 0, 0, 0, 0, 0],
        ]
        outlets, matrix = _make_outlets(vecs)
        result = run_clustering(outlets, matrix, k_min=2, k_max=8)
        self.assertEqual(result.n_outlets, 2)
        self.assertEqual(len(result.outlets), 2)
        # silhouette stays at the default (no valid multi-cluster scoring)
        self.assertIsInstance(result.silhouette, float)

    def test_nan_matrix_hits_except_branches(self):
        # NaN entries make both KMeans and AgglomerativeClustering raise, so the
        # try/except guards swallow them and silhouette stays at the default.
        import warnings
        outlets = [
            OutletVector("s0", "news", 10,
                         np.array([np.nan, 0, 0, 0, 0, 0, 0], dtype=np.float32)),
            OutletVector("s1", "news", 10,
                         np.array([0.1, 0.9, 0, 0, 0, 0, 0], dtype=np.float32)),
            OutletVector("s2", "news", 10,
                         np.array([0.5, 0.5, 0, 0, 0, 0, 0], dtype=np.float32)),
        ]
        matrix = np.stack([o.vector for o in outlets])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_clustering(outlets, matrix, k_min=2, k_max=3)
        self.assertEqual(result.n_outlets, 3)
        self.assertEqual(result.silhouette, -1.0)   # no valid scoring happened

    def test_single_outlet_pca_padded_to_2d(self):
        # n=1 -> PCA n_components = min(2, 7, 1) = 1 -> the 1-column result is
        # hstacked with a zero column so pca_y is 0.0. Exercises the pad branch.
        import warnings
        vecs = [[0.9, 0.1, 0, 0, 0, 0, 0]]
        outlets, matrix = _make_outlets(vecs)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = run_clustering(outlets, matrix, k_min=2, k_max=8)
        self.assertEqual(result.n_outlets, 1)
        self.assertEqual(len(result.outlets), 1)
        self.assertEqual(result.outlets[0].pca_y, 0.0)

    def test_returns_rounded_silhouette(self):
        vecs = [
            [0.9, 0.1, 0, 0, 0, 0, 0],
            [0.85, 0.15, 0, 0, 0, 0, 0],
            [0.1, 0.9, 0, 0, 0, 0, 0],
            [0.15, 0.85, 0, 0, 0, 0, 0],
        ]
        outlets, matrix = _make_outlets(vecs)
        result = run_clustering(outlets, matrix, k_min=2, k_max=3)
        self.assertEqual(round(result.silhouette, 4), result.silhouette)


# ---------------------------------------------------------------------------
# store_clusters
# ---------------------------------------------------------------------------

class TestStoreClusters(unittest.TestCase):
    def _result(self):
        outlets = [
            OutletCluster(
                source="Reuters", source_type="news", cluster_id=0,
                cluster_label="economic-dominant", pca_x=1.0, pca_y=-0.5,
                dominant_frame="economic", doc_count=12,
                computed_at="2026-06-01T00:00:00+00:00",
            ),
            OutletCluster(
                source="blog", source_type="blog", cluster_id=1,
                cluster_label="political-focused", pca_x=-0.2, pca_y=0.3,
                dominant_frame="political", doc_count=5,
                computed_at="2026-06-01T00:00:00+00:00",
            ),
        ]
        return ClusterResult(
            outlets=outlets, k=2, method="kmeans", silhouette=0.55,
            n_outlets=2, date_range="90d",
            computed_at="2026-06-01T00:00:00+00:00",
        )

    def test_delete_then_insert_each_outlet(self):
        conn = _RoutingConn()
        store_clusters(self._result(), conn)
        sqls = [c[0] for c in conn.executed]
        deletes = [i for i, s in enumerate(sqls) if "DELETE" in s]
        inserts = [i for i, s in enumerate(sqls) if "INSERT" in s]
        self.assertEqual(len(deletes), 1)
        self.assertEqual(len(inserts), 2)         # one per outlet
        self.assertLess(deletes[0], inserts[0])   # DELETE precedes INSERT
        self.assertIn("outlet_clusters", sqls[deletes[0]])
        # Insert params carry the source + cluster fields
        first_insert_params = conn.executed[inserts[0]][1]
        self.assertEqual(first_insert_params[0], "Reuters")
        self.assertIn("economic-dominant", first_insert_params)


# ---------------------------------------------------------------------------
# run_cluster_pipeline
# ---------------------------------------------------------------------------

class TestRunClusterPipeline(unittest.TestCase):
    def _clustering_routes(self):
        # 4 outlets, two clear groups, all >= 3 docs
        news = [
            ("A", "news", "economic", 0.9, 10), ("A", "news", "security", 0.1, 10),
            ("B", "news", "economic", 0.85, 10), ("B", "news", "security", 0.15, 10),
            ("C", "news", "security", 0.9, 10), ("C", "news", "economic", 0.1, 10),
            ("D", "news", "security", 0.85, 10), ("D", "news", "economic", 0.15, 10),
        ]
        return [
            ("JOIN news_articles n ON df.document_id = n.id", news),
            ("WHERE df.source_type != 'news'", []),
        ]

    def test_full_pipeline_success(self):
        conn = _RoutingConn(routes=self._clustering_routes())
        out = run_cluster_pipeline(conn, _lock(), date_range="90d", k_min=2, k_max=3)
        self.assertNotIn("error", out)
        self.assertEqual(out["n_outlets"], 4)
        self.assertEqual(out["date_range"], "90d")
        self.assertIn(out["method"], ("kmeans", "hierarchical"))
        self.assertIn("silhouette", out)
        self.assertIn("computed_at", out)
        # store_clusters ran -> DELETE + INSERTs present
        sqls = [c[0] for c in conn.executed]
        self.assertTrue(any("DELETE FROM outlet_clusters" in s for s in sqls))
        self.assertTrue(any("INSERT INTO outlet_clusters" in s for s in sqls))

    def test_not_enough_outlets(self):
        news = [("A", "news", "economic", 0.9, 10)]  # only 1 outlet
        conn = _RoutingConn(routes=[
            ("JOIN news_articles n ON df.document_id = n.id", news),
            ("WHERE df.source_type != 'news'", []),
        ])
        out = run_cluster_pipeline(conn, _lock())
        self.assertIn("error", out)
        self.assertEqual(out["n_outlets"], 1)

    def test_vector_build_failure_returns_error(self):
        class _BoomConn:
            _lock = threading.Lock()

            def execute(self, *a, **k):
                raise RuntimeError("db exploded")

        out = run_cluster_pipeline(_BoomConn(), _lock())
        self.assertIn("error", out)
        self.assertIn("vector build failed", out["error"])

    def test_store_failure_returns_error(self):
        class _StoreBoomConn(_RoutingConn):
            def execute(self, sql, params=None):
                if "DELETE FROM outlet_clusters" in sql or "INSERT INTO outlet_clusters" in sql:
                    raise RuntimeError("store exploded")
                return super().execute(sql, params)

        conn = _StoreBoomConn(routes=self._clustering_routes())
        out = run_cluster_pipeline(conn, _lock())
        self.assertIn("error", out)
        self.assertIn("store failed", out["error"])

    def test_clustering_failure_returns_error(self):
        # Patch run_clustering (as looked up in the module) to raise.
        import src.argument_mining.outlet_clustering as mod
        from unittest.mock import patch

        conn = _RoutingConn(routes=self._clustering_routes())
        with patch.object(mod, "run_clustering", side_effect=RuntimeError("bad k")):
            out = run_cluster_pipeline(conn, _lock())
        self.assertIn("error", out)
        self.assertIn("clustering failed", out["error"])


if __name__ == "__main__":
    unittest.main()
