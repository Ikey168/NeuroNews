"""
Coverage tests for src/argument_mining/outlet_scorer.py (#116).

Exercises the entropy helper, per-dimension extractors, the full scorer, the
persistence path, and the pipeline entry point. DB access is mocked with a
SQL-routing fake connection so these run offline.
"""
from __future__ import annotations

import math
import threading
import unittest
from unittest.mock import MagicMock

from src.argument_mining.outlet_scorer import (
    FRAME_LABELS,
    OutletScoreRow,
    compute_outlet_scores,
    run_scorer_batch,
    store_scores,
    _attribution_rate,
    _date_cutoff,
    _frame_diversity,
    _shannon_entropy,
    _stance_neutrality,
    _week_date,
)


# ---------------------------------------------------------------------------
# SQL-routing fake connection
# ---------------------------------------------------------------------------

class _RoutingConn:
    """DuckDB-alike: fetchall/fetchone return preset rows keyed by a substring
    found in the executed SQL (first match wins)."""

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


# ---------------------------------------------------------------------------
# _shannon_entropy
# ---------------------------------------------------------------------------

class TestShannonEntropy(unittest.TestCase):
    def test_uniform_distribution_is_one(self):
        counts = {f: 1.0 for f in FRAME_LABELS}
        e = _shannon_entropy(counts, n_bins=len(FRAME_LABELS))
        self.assertAlmostEqual(e, 1.0, places=6)

    def test_single_bucket_is_zero(self):
        counts = {"economic": 5.0, "security": 0.0, "legal": 0.0}
        e = _shannon_entropy(counts, n_bins=3)
        self.assertEqual(e, 0.0)

    def test_empty_total_returns_zero(self):
        self.assertEqual(_shannon_entropy({"a": 0.0, "b": 0.0}, n_bins=2), 0.0)
        self.assertEqual(_shannon_entropy({}, n_bins=4), 0.0)

    def test_intermediate_between_zero_and_one(self):
        counts = {"economic": 3.0, "security": 1.0}
        e = _shannon_entropy(counts, n_bins=2)
        self.assertGreater(e, 0.0)
        self.assertLess(e, 1.0)

    def test_matches_manual_two_bin_computation(self):
        counts = {"a": 3.0, "b": 1.0}
        p1, p2 = 0.75, 0.25
        expected = -(p1 * math.log(p1) + p2 * math.log(p2)) / math.log(2)
        self.assertAlmostEqual(_shannon_entropy(counts, 2), expected, places=6)


# ---------------------------------------------------------------------------
# _week_date / _date_cutoff
# ---------------------------------------------------------------------------

class TestWeekDate(unittest.TestCase):
    def test_override_passthrough(self):
        self.assertEqual(_week_date("2026-01-15"), "2026-01-15")

    def test_returns_monday_iso(self):
        d = _week_date()
        import datetime as _dt
        parsed = _dt.date.fromisoformat(d)
        self.assertEqual(parsed.weekday(), 0)  # Monday


class TestDateCutoff(unittest.TestCase):
    def test_known_ranges_parse_as_dates(self):
        import datetime as _dt
        for rng in ("7d", "30d", "90d", "365d"):
            _dt.date.fromisoformat(_date_cutoff(rng))  # raises if malformed

    def test_unknown_defaults_to_90d(self):
        self.assertEqual(_date_cutoff("bogus"), _date_cutoff("90d"))


# ---------------------------------------------------------------------------
# _frame_diversity
# ---------------------------------------------------------------------------

class TestFrameDiversity(unittest.TestCase):
    def test_news_source_computes_entropy(self):
        # rows: (frame, avg_score, doc_count)
        rows = [
            ("economic", 0.5, 10),
            ("security", 0.5, 8),
            ("legal", 0.5, 6),
        ]
        conn = _RoutingConn(routes=[("JOIN news_articles n", rows)])
        div, doc_count = _frame_diversity(conn, "Reuters", "news", "2026-01-01")
        self.assertGreater(div, 0.0)
        self.assertEqual(doc_count, 10)  # max of doc_counts

    def test_non_news_branch(self):
        rows = [("economic", 0.9, 4), ("security", 0.1, 4)]
        conn = _RoutingConn(routes=[
            ("WHERE source_type = ? AND classified_at", rows),
        ])
        div, doc_count = _frame_diversity(conn, "blog", "blog", "2026-01-01")
        self.assertGreaterEqual(div, 0.0)
        self.assertEqual(doc_count, 4)

    def test_no_rows_returns_zero(self):
        conn = _RoutingConn(routes=[])
        div, doc_count = _frame_diversity(conn, "X", "news", "2026-01-01")
        self.assertEqual((div, doc_count), (0.0, 0))


# ---------------------------------------------------------------------------
# _attribution_rate
# ---------------------------------------------------------------------------

class TestAttributionRate(unittest.TestCase):
    def test_news_rate(self):
        conn = _RoutingConn(routes=[("JOIN news_articles n", [(10, 7)])])
        rate, total = _attribution_rate(conn, "Reuters", "news", "2026-01-01")
        self.assertEqual(total, 10)
        self.assertEqual(rate, 0.7)

    def test_non_news_rate(self):
        conn = _RoutingConn(routes=[
            ("WHERE source_type = ? AND extracted_at", [(4, 1)]),
        ])
        rate, total = _attribution_rate(conn, "paper", "paper", "2026-01-01")
        self.assertEqual(total, 4)
        self.assertEqual(rate, 0.25)

    def test_zero_total_returns_zero_rate(self):
        conn = _RoutingConn(routes=[("JOIN news_articles n", [(0, 0)])])
        rate, total = _attribution_rate(conn, "Reuters", "news", "2026-01-01")
        self.assertEqual((rate, total), (0.0, 0))

    def test_none_row_handled(self):
        conn = _RoutingConn(routes=[("JOIN news_articles n", [])])
        rate, total = _attribution_rate(conn, "Reuters", "news", "2026-01-01")
        self.assertEqual((rate, total), (0.0, 0))


# ---------------------------------------------------------------------------
# _stance_neutrality
# ---------------------------------------------------------------------------

class TestStanceNeutrality(unittest.TestCase):
    def test_no_rows_returns_midpoint(self):
        conn = _RoutingConn(routes=[])
        self.assertEqual(_stance_neutrality(conn, "Reuters", "news"), 0.5)

    def test_balanced_stances_near_one(self):
        rows = [
            ("supportive", 5), ("critical", 5),
            ("neutral", 5), ("ambiguous", 5),
        ]
        conn = _RoutingConn(routes=[("FROM source_stances", rows)])
        n = _stance_neutrality(conn, "Reuters", "news")
        self.assertAlmostEqual(n, 1.0, places=3)

    def test_single_stance_is_zero(self):
        rows = [("supportive", 10)]
        conn = _RoutingConn(routes=[("FROM source_stances", rows)])
        n = _stance_neutrality(conn, "Reuters", "news")
        self.assertEqual(n, 0.0)

    def test_missing_labels_defaulted_zero(self):
        # Only two of four labels present -> intermediate neutrality
        rows = [("supportive", 3), ("critical", 1)]
        conn = _RoutingConn(routes=[("FROM source_stances", rows)])
        n = _stance_neutrality(conn, "Reuters", "news")
        self.assertGreater(n, 0.0)
        self.assertLess(n, 1.0)


# ---------------------------------------------------------------------------
# compute_outlet_scores
# ---------------------------------------------------------------------------

class TestComputeOutletScores(unittest.TestCase):
    def _full_routes(self, doc_count=10):
        """Routes covering enumerate + all three extractors for one news outlet."""
        return [
            # outlet enumeration (news)
            ("SELECT DISTINCT n.source AS source", [("Reuters", "news")]),
            # outlet enumeration (non-news)
            ("SELECT DISTINCT source_type AS source", []),
            # _frame_diversity (news)
            ("JOIN news_articles n ON df.document_id = n.id",
             [("economic", 0.5, doc_count), ("security", 0.5, doc_count),
              ("legal", 0.5, doc_count)]),
            # _attribution_rate (news)
            ("JOIN news_articles n ON c.document_id = n.id", [(10, 8)]),
            # _stance_neutrality
            ("FROM source_stances",
             [("supportive", 4), ("critical", 4), ("neutral", 4), ("ambiguous", 4)]),
        ]

    def test_produces_score_row(self):
        conn = _RoutingConn(routes=self._full_routes(doc_count=10))
        rows = compute_outlet_scores(conn, date_range="90d")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertIsInstance(r, OutletScoreRow)
        self.assertEqual(r.source, "Reuters")
        self.assertEqual(r.source_type, "news")
        self.assertEqual(r.doc_count, 10)
        self.assertEqual(r.claim_count, 10)
        # composite = mean of the three sub-scores
        expected = round(
            (r.frame_diversity + r.attribution_rate + r.stance_neutrality) / 3.0, 4
        )
        self.assertEqual(r.composite_score, expected)

    def test_excludes_outlet_with_too_few_docs(self):
        conn = _RoutingConn(routes=self._full_routes(doc_count=2))
        rows = compute_outlet_scores(conn, date_range="90d")
        self.assertEqual(rows, [])

    def test_score_date_override(self):
        conn = _RoutingConn(routes=self._full_routes(doc_count=5))
        rows = compute_outlet_scores(conn, score_date="2026-02-02")
        self.assertEqual(rows[0].score_date, "2026-02-02")

    def test_results_sorted_by_composite_desc(self):
        # Two outlets: Reuters (balanced -> high) and Tabloid (single frame -> low)
        routes = [
            ("SELECT DISTINCT n.source AS source",
             [("Reuters", "news"), ("Tabloid", "news")]),
            ("SELECT DISTINCT source_type AS source", []),
        ]

        # For frame diversity / attribution we must vary per source. Use a
        # connection that inspects params to decide which outlet is queried.
        class _PerSourceConn(_RoutingConn):
            def execute(self, sql, params=None):
                self.executed.append((sql, params))
                cur = MagicMock()
                if "SELECT DISTINCT n.source AS source" in sql:
                    cur.fetchall.return_value = [("Reuters", "news"),
                                                 ("Tabloid", "news")]
                elif "SELECT DISTINCT source_type AS source" in sql:
                    cur.fetchall.return_value = []
                elif "JOIN news_articles n ON df.document_id" in sql:
                    src = params[0]
                    if src == "Reuters":
                        cur.fetchall.return_value = [
                            ("economic", 0.5, 10), ("security", 0.5, 10),
                            ("legal", 0.5, 10), ("political", 0.5, 10),
                        ]
                    else:
                        cur.fetchall.return_value = [("economic", 1.0, 10)]
                elif "JOIN news_articles n ON c.document_id" in sql:
                    cur.fetchone.return_value = (10, 5)
                elif "FROM source_stances" in sql:
                    cur.fetchall.return_value = []
                else:
                    cur.fetchall.return_value = []
                    cur.fetchone.return_value = None
                return cur

        conn = _PerSourceConn(routes=routes)
        rows = compute_outlet_scores(conn)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].source, "Reuters")  # higher diversity first
        self.assertGreaterEqual(rows[0].composite_score, rows[1].composite_score)

    def test_extractor_exception_skips_outlet(self):
        # frame_diversity raises for the single outlet -> caught, skipped, [] returned
        class _BoomConn(_RoutingConn):
            def execute(self, sql, params=None):
                self.executed.append((sql, params))
                cur = MagicMock()
                if "SELECT DISTINCT n.source AS source" in sql:
                    cur.fetchall.return_value = [("Reuters", "news")]
                elif "SELECT DISTINCT source_type AS source" in sql:
                    cur.fetchall.return_value = []
                elif "JOIN news_articles n ON df.document_id" in sql:
                    raise RuntimeError("frame query failed")
                else:
                    cur.fetchall.return_value = []
                    cur.fetchone.return_value = None
                return cur

        conn = _BoomConn()
        rows = compute_outlet_scores(conn)
        self.assertEqual(rows, [])


# ---------------------------------------------------------------------------
# store_scores
# ---------------------------------------------------------------------------

class TestStoreScores(unittest.TestCase):
    def _row(self):
        return OutletScoreRow(
            source="Reuters", source_type="news", score_date="2026-06-01",
            frame_diversity=0.8, attribution_rate=0.7, stance_neutrality=0.9,
            composite_score=0.8, doc_count=12, claim_count=30,
            computed_at="2026-06-01T00:00:00+00:00",
        )

    def test_inserts_one_row_per_score(self):
        conn = _RoutingConn()
        store_scores([self._row(), self._row()], conn)
        inserts = [c for c in conn.executed if "INSERT" in c[0]]
        self.assertEqual(len(inserts), 2)
        self.assertIn("outlet_scores", inserts[0][0])
        # params carry the source + composite
        params = inserts[0][1]
        self.assertEqual(params[0], "Reuters")
        self.assertIn(0.8, params)

    def test_empty_list_no_inserts(self):
        conn = _RoutingConn()
        store_scores([], conn)
        self.assertFalse([c for c in conn.executed if "INSERT" in c[0]])


# ---------------------------------------------------------------------------
# run_scorer_batch
# ---------------------------------------------------------------------------

class TestRunScorerBatch(unittest.TestCase):
    def _full_routes(self, doc_count=10):
        return [
            ("SELECT DISTINCT n.source AS source", [("Reuters", "news")]),
            ("SELECT DISTINCT source_type AS source", []),
            ("JOIN news_articles n ON df.document_id = n.id",
             [("economic", 0.5, doc_count), ("security", 0.5, doc_count)]),
            ("JOIN news_articles n ON c.document_id = n.id", [(10, 8)]),
            ("FROM source_stances", []),  # midpoint neutrality
            ("INSERT OR REPLACE INTO outlet_scores", []),
        ]

    def test_success_summary(self):
        conn = _RoutingConn(routes=self._full_routes(doc_count=10))
        out = run_scorer_batch(conn, _lock(), date_range="90d")
        self.assertEqual(out["outlets_scored"], 1)
        self.assertEqual(out["top_outlet"], "Reuters")
        self.assertIsNotNone(out["top_composite"])
        self.assertIn("score_date", out)

    def test_no_outlets_message(self):
        conn = _RoutingConn(routes=[
            ("SELECT DISTINCT n.source AS source", []),
            ("SELECT DISTINCT source_type AS source", []),
        ])
        out = run_scorer_batch(conn, _lock(), date_override="2026-03-02")
        self.assertEqual(out["outlets_scored"], 0)
        self.assertEqual(out["score_date"], "2026-03-02")
        self.assertIn("message", out)

    def test_compute_exception_returns_error(self):
        class _BoomConn:
            _lock = threading.Lock()

            def execute(self, *a, **k):
                raise RuntimeError("db down")

        out = run_scorer_batch(_BoomConn(), _lock())
        self.assertIn("error", out)
        self.assertIn("score computation failed", out["error"])

    def test_store_exception_returns_error(self):
        # compute succeeds, store raises
        class _StoreBoomConn(_RoutingConn):
            def execute(self, sql, params=None):
                if "INSERT OR REPLACE INTO outlet_scores" in sql:
                    raise RuntimeError("write failed")
                return super().execute(sql, params)

        conn = _StoreBoomConn(routes=[
            ("SELECT DISTINCT n.source AS source", [("Reuters", "news")]),
            ("SELECT DISTINCT source_type AS source", []),
            ("JOIN news_articles n ON df.document_id = n.id",
             [("economic", 0.5, 10), ("security", 0.5, 10)]),
            ("JOIN news_articles n ON c.document_id = n.id", [(10, 8)]),
            ("FROM source_stances", []),
        ])
        out = run_scorer_batch(conn, _lock())
        self.assertIn("error", out)
        self.assertIn("store failed", out["error"])


if __name__ == "__main__":
    unittest.main()
