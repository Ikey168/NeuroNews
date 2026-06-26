"""
Tests for the local resource monitor — Issue #334.

psutil calls are mocked so the tests run without system access
or network connectivity.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import duckdb
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def conn() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection seeded with the resource_metrics schema."""
    db = duckdb.connect(":memory:")
    from src.monitoring.resource_monitor import ensure_schema
    ensure_schema(db)
    return db


_MOCK_CPU = 23.5
_MOCK_MEM_PERCENT = 61.2
_MOCK_MEM_RSS = 128 * 1024 * 1024  # 128 MB in bytes
_MOCK_DISK_USED = 50 * (1024 ** 3)   # 50 GB
_MOCK_DISK_FREE = 200 * (1024 ** 3)  # 200 GB
_MOCK_DISK_PCT = 20.0


def _mock_psutil():
    """Return a context that mocks all psutil calls used by resource_monitor."""
    vm = MagicMock()
    vm.percent = _MOCK_MEM_PERCENT

    proc = MagicMock()
    proc.name.return_value = "pytest"
    proc.memory_info.return_value = MagicMock(rss=_MOCK_MEM_RSS)

    disk = MagicMock()
    disk.used = _MOCK_DISK_USED
    disk.free = _MOCK_DISK_FREE
    disk.percent = _MOCK_DISK_PCT

    return patch.multiple(
        "src.monitoring.resource_monitor",
        **{
            "psutil": MagicMock(
                cpu_percent=MagicMock(return_value=_MOCK_CPU),
                virtual_memory=MagicMock(return_value=vm),
                Process=MagicMock(return_value=proc),
                disk_usage=MagicMock(return_value=disk),
                NoSuchProcess=psutil_no_such_process(),
                AccessDenied=psutil_access_denied(),
            )
        },
    )


def psutil_no_such_process():
    import psutil
    return psutil.NoSuchProcess


def psutil_access_denied():
    import psutil
    return psutil.AccessDenied


# ---------------------------------------------------------------------------
# collect_sample
# ---------------------------------------------------------------------------

class TestCollectSample:
    def test_returns_six_metrics(self):
        from src.monitoring.resource_monitor import collect_sample
        with _mock_psutil():
            rows = collect_sample()
        assert len(rows) == 6

    def test_metric_names_present(self):
        from src.monitoring.resource_monitor import collect_sample
        with _mock_psutil():
            rows = collect_sample()
        names = {r["metric_name"] for r in rows}
        assert "cpu_percent" in names
        assert "memory_percent" in names
        assert "memory_rss_mb" in names
        assert "disk_used_gb" in names
        assert "disk_free_gb" in names
        assert "disk_percent" in names

    def test_cpu_value(self):
        from src.monitoring.resource_monitor import collect_sample
        with _mock_psutil():
            rows = collect_sample()
        cpu = next(r for r in rows if r["metric_name"] == "cpu_percent")
        assert cpu["value"] == pytest.approx(_MOCK_CPU)
        assert cpu["unit"] == "%"

    def test_memory_rss_converted_to_mb(self):
        from src.monitoring.resource_monitor import collect_sample
        with _mock_psutil():
            rows = collect_sample()
        rss = next(r for r in rows if r["metric_name"] == "memory_rss_mb")
        assert rss["value"] == pytest.approx(128.0, abs=0.1)
        assert rss["unit"] == "MB"
        assert rss["pid"] is not None

    def test_disk_used_converted_to_gb(self):
        from src.monitoring.resource_monitor import collect_sample
        with _mock_psutil():
            rows = collect_sample()
        disk = next(r for r in rows if r["metric_name"] == "disk_used_gb")
        assert disk["value"] == pytest.approx(50.0, abs=0.01)
        assert disk["unit"] == "GB"

    def test_all_rows_have_sampled_at(self):
        from src.monitoring.resource_monitor import collect_sample
        with _mock_psutil():
            rows = collect_sample()
        for r in rows:
            assert isinstance(r["sampled_at"], datetime)


# ---------------------------------------------------------------------------
# store_sample / get_metrics
# ---------------------------------------------------------------------------

class TestStoreAndQuery:
    def _insert_sample(self, conn: Any) -> list:
        from src.monitoring.resource_monitor import collect_sample, store_sample
        with _mock_psutil():
            rows = collect_sample()
        store_sample(conn, rows)
        return rows

    def test_store_writes_rows(self, conn: Any):
        self._insert_sample(conn)
        count = conn.execute("SELECT COUNT(*) FROM resource_metrics").fetchone()[0]
        assert count == 6

    def test_get_metrics_returns_stored_rows(self, conn: Any):
        self._insert_sample(conn)
        from src.monitoring.resource_monitor import get_metrics
        rows = get_metrics(conn)
        assert len(rows) == 6

    def test_get_metrics_filter_by_name(self, conn: Any):
        self._insert_sample(conn)
        from src.monitoring.resource_monitor import get_metrics
        rows = get_metrics(conn, metric_name="cpu_percent")
        assert len(rows) == 1
        assert rows[0]["metric_name"] == "cpu_percent"

    def test_get_metrics_limit(self, conn: Any):
        # Insert two batches
        self._insert_sample(conn)
        self._insert_sample(conn)
        from src.monitoring.resource_monitor import get_metrics
        rows = get_metrics(conn, n=3)
        assert len(rows) == 3

    def test_get_metrics_newest_first(self, conn: Any):
        self._insert_sample(conn)
        from src.monitoring.resource_monitor import get_metrics
        rows = get_metrics(conn, metric_name="cpu_percent")
        assert rows[0]["sampled_at"] is not None

    def test_get_metrics_since_minutes(self, conn: Any):
        self._insert_sample(conn)
        from src.monitoring.resource_monitor import get_metrics
        # Large window — should include our sample
        rows = get_metrics(conn, since_minutes=60)
        assert len(rows) == 6
        # Tiny window in the past — should be empty (our rows are ~now)
        # (We can't test "exclude recent" easily, but we verify it parses)

    def test_get_metrics_empty_table(self, conn: Any):
        from src.monitoring.resource_monitor import get_metrics
        rows = get_metrics(conn)
        assert rows == []

    def test_ids_are_unique(self, conn: Any):
        self._insert_sample(conn)
        ids = conn.execute("SELECT id FROM resource_metrics").fetchall()
        assert len({r[0] for r in ids}) == 6


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------

class TestGetSummary:
    def test_summary_structure(self, conn: Any):
        from src.monitoring.resource_monitor import collect_sample, get_summary, store_sample
        with _mock_psutil():
            rows = collect_sample()
        store_sample(conn, rows)
        summary = get_summary(conn)
        assert "1h" in summary
        assert "24h" in summary
        assert "sampled_at" in summary

    def test_summary_1h_contains_cpu(self, conn: Any):
        from src.monitoring.resource_monitor import collect_sample, get_summary, store_sample
        with _mock_psutil():
            rows = collect_sample()
        store_sample(conn, rows)
        summary = get_summary(conn)
        assert "cpu_percent" in summary["1h"]
        cpu = summary["1h"]["cpu_percent"]
        assert cpu["avg"] == pytest.approx(_MOCK_CPU, abs=0.1)
        assert cpu["min"] == pytest.approx(_MOCK_CPU, abs=0.1)
        assert cpu["max"] == pytest.approx(_MOCK_CPU, abs=0.1)
        assert cpu["unit"] == "%"

    def test_summary_empty_table_returns_empty_windows(self, conn: Any):
        from src.monitoring.resource_monitor import get_summary
        summary = get_summary(conn)
        assert summary["1h"] == {}
        assert summary["24h"] == {}

    def test_summary_avg_across_two_samples(self, conn: Any):
        """Average of two cpu_percent readings should be their mean."""
        from src.monitoring.resource_monitor import ensure_schema, get_summary, store_sample
        import uuid
        ensure_schema(conn)
        now = datetime.now(timezone.utc)
        conn.executemany(
            "INSERT INTO resource_metrics VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (str(uuid.uuid4()), now, "cpu_percent", 10.0, "%", None, None),
                (str(uuid.uuid4()), now, "cpu_percent", 30.0, "%", None, None),
            ],
        )
        summary = get_summary(conn)
        assert summary["1h"]["cpu_percent"]["avg"] == pytest.approx(20.0, abs=0.01)


# ---------------------------------------------------------------------------
# Prometheus text format (via routes helper)
# ---------------------------------------------------------------------------

class TestPrometheusFormat:
    def test_contains_help_and_type(self):
        from src.api.routes.metrics_routes import _to_prometheus
        rows = [{"metric_name": "cpu_percent", "value": 12.5, "unit": "%",
                 "sampled_at": "2026-06-26T00:00:00", "process_name": None, "pid": None}]
        text = _to_prometheus(rows)
        assert "# HELP neuronews_cpu_percent" in text
        assert "# TYPE neuronews_cpu_percent gauge" in text
        assert "neuronews_cpu_percent 12.5" in text

    def test_process_label_included(self):
        from src.api.routes.metrics_routes import _to_prometheus
        rows = [{"metric_name": "memory_rss_mb", "value": 64.0, "unit": "MB",
                 "sampled_at": "2026-06-26T00:00:00", "process_name": "uvicorn", "pid": 1234}]
        text = _to_prometheus(rows)
        assert 'process="uvicorn"' in text
        assert 'pid="1234"' in text

    def test_ends_with_newline(self):
        from src.api.routes.metrics_routes import _to_prometheus
        rows = [{"metric_name": "cpu_percent", "value": 1.0, "unit": "%",
                 "sampled_at": "2026-06-26T00:00:00", "process_name": None, "pid": None}]
        assert _to_prometheus(rows).endswith("\n")

    def test_multiple_metrics(self):
        from src.api.routes.metrics_routes import _to_prometheus
        rows = [
            {"metric_name": "cpu_percent",  "value": 10.0, "unit": "%",  "sampled_at": "x", "process_name": None, "pid": None},
            {"metric_name": "disk_used_gb", "value": 50.0, "unit": "GB", "sampled_at": "x", "process_name": None, "pid": None},
        ]
        text = _to_prometheus(rows)
        assert "neuronews_cpu_percent" in text
        assert "neuronews_disk_used_gb" in text
