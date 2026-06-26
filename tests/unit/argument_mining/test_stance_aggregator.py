"""
Unit tests for src/argument_mining/stance_aggregator.py (#99).

All classifier calls are mocked so these run offline without trained models.
"""
from __future__ import annotations

import threading
import unittest
from dataclasses import dataclass
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal stubs so the import doesn't require full service stack
# ---------------------------------------------------------------------------

@dataclass
class _FakePred:
    stance: str
    confidence: float


def _make_conn(rows: list | None = None):
    """Return a minimal DuckDB-alike mock."""
    conn = MagicMock()
    conn._lock = threading.Lock()
    cursor = MagicMock()
    cursor.fetchall.return_value = rows or []
    conn.execute.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# run_stance_aggregation — no documents
# ---------------------------------------------------------------------------

class TestRunStanceAggregationEmpty(unittest.TestCase):
    def test_returns_zero_when_no_docs(self):
        from src.argument_mining.stance_aggregator import run_stance_aggregation

        conn = _make_conn(rows=[])
        lock = threading.Lock()

        result = run_stance_aggregation(conn, lock)

        self.assertEqual(result, {"documents": 0, "rows_written": 0})
        # The execute was called to fetch documents but no DELETE/INSERT should follow
        # (at least no more than the initial SELECT)
        calls_after = [str(c) for c in conn.execute.call_args_list]
        insert_calls = [c for c in calls_after if "INSERT" in c]
        self.assertEqual(len(insert_calls), 0)


# ---------------------------------------------------------------------------
# run_stance_aggregation — with documents, mocked classifier
# ---------------------------------------------------------------------------

class TestRunStanceAggregationWithDocs(unittest.TestCase):
    def _make_docs(self):
        return [
            ("art-001", "Title A", "content A", "Reuters",   "Economy"),
            ("art-002", "Title B", "content B", "Reuters",   "Economy"),
            ("art-003", "Title C", "content C", "Bloomberg", "Technology"),
        ]

    def _mock_clf(self, stance: str = "supportive", confidence: float = 0.75):
        clf = MagicMock()
        clf.predict.return_value = [_FakePred(stance=stance, confidence=confidence)]
        return clf

    @patch("src.argument_mining.models.get_stance_classifier")
    def test_writes_rows_for_each_source_topic_stance(self, mock_get_clf):
        from src.argument_mining.stance_aggregator import run_stance_aggregation

        mock_get_clf.return_value = self._mock_clf(stance="supportive")
        conn = _make_conn(rows=self._make_docs())
        lock = threading.Lock()

        result = run_stance_aggregation(conn, lock)

        self.assertEqual(result["documents"], 3)
        self.assertGreater(result["rows_written"], 0)

    @patch("src.argument_mining.models.get_stance_classifier")
    def test_skips_docs_with_no_content(self, mock_get_clf):
        from src.argument_mining.stance_aggregator import run_stance_aggregation

        mock_get_clf.return_value = self._mock_clf()
        conn = _make_conn(rows=[
            ("art-001", "Title", None,        "Reuters", "Economy"),  # no content
            ("art-002", "Title", "content",   None,      "Economy"),  # no source
            ("art-003", "Title", "content B", "FT",      "Economy"),  # valid
        ])
        lock = threading.Lock()

        result = run_stance_aggregation(conn, lock)

        self.assertEqual(result["documents"], 3)
        # Only the third row produces a write: 1 (source, source_type, topic) × 1 stance
        self.assertEqual(result["rows_written"], 1)

    @patch("src.argument_mining.models.get_stance_classifier")
    def test_aggregates_counts_across_docs_same_source_topic(self, mock_get_clf):
        from src.argument_mining.stance_aggregator import run_stance_aggregation

        clf = MagicMock()
        call_count = {"n": 0}

        def alt_predict(doc, topic):
            call_count["n"] += 1
            return [_FakePred("supportive" if call_count["n"] % 2 == 1 else "critical", 0.7)]

        clf.predict.side_effect = alt_predict
        mock_get_clf.return_value = clf

        conn = _make_conn(rows=[
            ("art-001", "T", "c1", "Reuters", "Economy"),
            ("art-002", "T", "c2", "Reuters", "Economy"),
        ])
        lock = threading.Lock()
        result = run_stance_aggregation(conn, lock)

        self.assertEqual(result["documents"], 2)
        # supportive=1 + critical=1 → 2 non-zero stances → 2 rows
        self.assertEqual(result["rows_written"], 2)

    @patch("src.argument_mining.models.get_stance_classifier")
    def test_delete_before_insert_called(self, mock_get_clf):
        from src.argument_mining.stance_aggregator import run_stance_aggregation

        mock_get_clf.return_value = self._mock_clf()
        conn = _make_conn(rows=[("art-001", "T", "c", "Reuters", "Economy")])
        lock = threading.Lock()

        run_stance_aggregation(conn, lock)

        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list if c.args]
        delete_calls = [s for s in sql_calls if "DELETE" in s]
        insert_calls = [s for s in sql_calls if "INSERT" in s]

        self.assertGreater(len(delete_calls), 0, "Expected at least one DELETE")
        self.assertGreater(len(insert_calls), 0, "Expected at least one INSERT")
        # DELETE must precede INSERT
        first_delete = next(i for i, s in enumerate(sql_calls) if "DELETE" in s)
        first_insert = next(i for i, s in enumerate(sql_calls) if "INSERT" in s)
        self.assertLess(first_delete, first_insert)

    @patch("src.argument_mining.models.get_stance_classifier")
    def test_uses_category_general_when_none(self, mock_get_clf):
        from src.argument_mining.stance_aggregator import run_stance_aggregation

        mock_get_clf.return_value = self._mock_clf()
        conn = _make_conn(rows=[("art-001", "T", "content", "Reuters", None)])
        lock = threading.Lock()
        run_stance_aggregation(conn, lock)

        insert_calls = [c for c in conn.execute.call_args_list if "INSERT" in str(c.args[0] if c.args else "")]
        self.assertTrue(any("general" in str(c) for c in insert_calls))


# ---------------------------------------------------------------------------
# schedule_stance_job
# ---------------------------------------------------------------------------

class TestScheduleStanceJob(unittest.TestCase):
    def test_registers_job_with_scheduler(self):
        from src.argument_mining.stance_aggregator import schedule_stance_job

        scheduler = MagicMock()
        schedule_stance_job(scheduler, hour=4)
        scheduler.add_job.assert_called_once()
        call_kwargs = scheduler.add_job.call_args
        self.assertEqual(call_kwargs.kwargs.get("id") or call_kwargs[1].get("id"), "stance_aggregation")

    def test_replace_existing_true(self):
        from src.argument_mining.stance_aggregator import schedule_stance_job

        scheduler = MagicMock()
        schedule_stance_job(scheduler)
        kwargs = scheduler.add_job.call_args[1]
        self.assertTrue(kwargs.get("replace_existing"))


if __name__ == "__main__":
    unittest.main()
