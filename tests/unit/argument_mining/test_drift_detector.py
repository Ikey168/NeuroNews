"""
Unit tests for src/argument_mining/drift_detector.py (#102).

All DB interactions are mocked so these run offline.
"""
from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, call


def _make_conn(rows=None):
    conn = MagicMock()
    conn._lock = threading.Lock()
    cursor = MagicMock()
    cursor.fetchall.return_value = rows or []
    conn.execute.return_value = cursor
    return conn


def _row(source="Reuters", source_type="news", topic="Economy", stance="supportive",
         doc_count=10, conf=0.75, window_start="2026-06-01"):
    return (source, source_type, topic, stance, doc_count, conf, window_start)


class TestRunDriftDetectionEmpty(unittest.TestCase):
    def test_returns_zero_when_no_rows(self):
        from src.argument_mining.drift_detector import run_drift_detection

        conn = _make_conn(rows=[])
        result = run_drift_detection(conn, threading.Lock())
        self.assertEqual(result, {"events_written": 0})

    def test_returns_zero_when_only_one_window(self):
        from src.argument_mining.drift_detector import run_drift_detection

        conn = _make_conn(rows=[_row(window_start="2026-06-01")])
        result = run_drift_detection(conn, threading.Lock())
        self.assertEqual(result, {"events_written": 0})


class TestRunDriftDetectionNoDrift(unittest.TestCase):
    def test_no_event_when_same_stance_small_delta(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            _row(stance="supportive", conf=0.70, window_start="2026-06-01"),
            _row(stance="supportive", conf=0.75, window_start="2026-06-08"),
        ]
        conn = _make_conn(rows=rows)
        result = run_drift_detection(conn, threading.Lock())
        self.assertEqual(result["events_written"], 0)
        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list if c.args]
        self.assertFalse(any("INSERT" in s for s in sql_calls))


class TestRunDriftDetectionWithDrift(unittest.TestCase):
    def test_event_written_when_dominant_stance_changes(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            _row(stance="supportive", conf=0.80, window_start="2026-06-01", doc_count=10),
            _row(stance="critical",   conf=0.75, window_start="2026-06-01", doc_count=1),
            _row(stance="critical",   conf=0.80, window_start="2026-06-08", doc_count=10),
            _row(stance="supportive", conf=0.75, window_start="2026-06-08", doc_count=1),
        ]
        conn = _make_conn(rows=rows)
        result = run_drift_detection(conn, threading.Lock())
        self.assertEqual(result["events_written"], 1)

    def test_event_written_when_confidence_delta_exceeds_threshold(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            _row(stance="supportive", conf=0.90, window_start="2026-06-01"),
            _row(stance="supportive", conf=0.60, window_start="2026-06-08"),
        ]
        conn = _make_conn(rows=rows)
        result = run_drift_detection(conn, threading.Lock())
        self.assertEqual(result["events_written"], 1)

    def test_delete_before_insert(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            _row(stance="supportive", window_start="2026-06-01"),
            _row(stance="critical",   window_start="2026-06-08"),
        ]
        conn = _make_conn(rows=rows)
        run_drift_detection(conn, threading.Lock())

        sql_calls = [str(c.args[0]) for c in conn.execute.call_args_list if c.args]
        deletes = [i for i, s in enumerate(sql_calls) if "DELETE" in s]
        inserts = [i for i, s in enumerate(sql_calls) if "INSERT" in s]
        self.assertTrue(deletes, "Expected at least one DELETE")
        self.assertTrue(inserts, "Expected at least one INSERT")
        self.assertLess(deletes[0], inserts[0])

    def test_insert_contains_correct_stances(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            _row(stance="neutral",  conf=0.70, window_start="2026-06-01", doc_count=8),
            _row(stance="critical", conf=0.70, window_start="2026-06-08", doc_count=8),
        ]
        conn = _make_conn(rows=rows)
        run_drift_detection(conn, threading.Lock())

        insert_calls = [c for c in conn.execute.call_args_list if "INSERT" in str(c.args[0] if c.args else "")]
        self.assertTrue(insert_calls)
        insert_params = insert_calls[0].args[1]
        # from_stance=neutral, to_stance=critical
        self.assertEqual(insert_params[3], "neutral")
        self.assertEqual(insert_params[4], "critical")

    def test_multiple_source_topic_pairs_produce_independent_events(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            # Reuters / Economy: stance flip
            ("Reuters", "news", "Economy", "supportive", 10, 0.80, "2026-06-01"),
            ("Reuters", "news", "Economy", "critical",   10, 0.80, "2026-06-08"),
            # Bloomberg / Tech: no change
            ("Bloomberg", "news", "Tech", "neutral", 10, 0.70, "2026-06-01"),
            ("Bloomberg", "news", "Tech", "neutral", 10, 0.72, "2026-06-08"),
        ]
        conn = _make_conn(rows=rows)
        result = run_drift_detection(conn, threading.Lock())
        self.assertEqual(result["events_written"], 1)

    def test_window_pair_format(self):
        from src.argument_mining.drift_detector import run_drift_detection

        rows = [
            _row(stance="supportive", window_start="2026-06-01"),
            _row(stance="critical",   window_start="2026-06-08"),
        ]
        conn = _make_conn(rows=rows)
        run_drift_detection(conn, threading.Lock())

        insert_calls = [c for c in conn.execute.call_args_list if "INSERT" in str(c.args[0] if c.args else "")]
        insert_params = insert_calls[0].args[1]
        self.assertEqual(insert_params[7], "2026-06-01:2026-06-08")


class TestScheduleDriftJob(unittest.TestCase):
    def test_registers_job_with_scheduler(self):
        from src.argument_mining.drift_detector import schedule_drift_job

        scheduler = MagicMock()
        schedule_drift_job(scheduler, hour=4)
        scheduler.add_job.assert_called_once()
        kwargs = scheduler.add_job.call_args[1]
        self.assertEqual(kwargs.get("id"), "stance_drift_detection")

    def test_replace_existing_true(self):
        from src.argument_mining.drift_detector import schedule_drift_job

        scheduler = MagicMock()
        schedule_drift_job(scheduler)
        kwargs = scheduler.add_job.call_args[1]
        self.assertTrue(kwargs.get("replace_existing"))


if __name__ == "__main__":
    unittest.main()
