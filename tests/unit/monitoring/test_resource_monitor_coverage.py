"""Coverage tests for src/monitoring/resource_monitor.py.

Targets the remaining uncovered branches:
  * lines 76-78  -- psutil.NoSuchProcess/AccessDenied fallback in collect_sample
  * lines 85-86  -- disk_usage(repo) raising -> fallback to "/"
  * lines 167-172 -- collect_and_store swallowing a store_sample exception
  * lines 283-290 -- _run_collector loop body (one iteration + error handling)
  * lines 300-311 -- start_background_collector idempotency / thread start
psutil is patched where it is looked up (module-level ``psutil`` in the source).
"""
from __future__ import annotations

import importlib

import pytest

psutil = pytest.importorskip("psutil")

from src.monitoring import resource_monitor as rm


class _FakeMem:
    def __init__(self, rss=None, percent=None):
        self.rss = rss
        self.percent = percent


class _FakeProc:
    def __init__(self, name="pytest", rss=123 * 1024 * 1024):
        self._name = name
        self._rss = rss

    def name(self):
        return self._name

    def memory_info(self):
        return _FakeMem(rss=self._rss)


class _FakeDisk:
    used = 10 * (1024 ** 3)
    free = 5 * (1024 ** 3)
    percent = 42.0


@pytest.fixture(autouse=True)
def _reset_collector_flag():
    """Reset the module-global started flag around each test."""
    rm._collector_started = False
    yield
    rm._collector_started = False


def _patch_common_psutil(monkeypatch, *, disk=None):
    """Patch the always-called psutil helpers with deterministic values."""
    monkeypatch.setattr(rm.psutil, "cpu_percent", lambda interval=0.1: 12.5)
    monkeypatch.setattr(
        rm.psutil, "virtual_memory", lambda: _FakeMem(percent=55.0)
    )
    if disk is not None:
        monkeypatch.setattr(rm.psutil, "disk_usage", disk)


def test_collect_sample_process_error_uses_unknown(monkeypatch):
    """Lines 76-78: NoSuchProcess -> proc_name 'unknown', rss 0.0."""

    def _boom(_pid):
        raise psutil.NoSuchProcess(_pid)

    monkeypatch.setattr(rm.psutil, "Process", _boom)
    _patch_common_psutil(monkeypatch, disk=lambda _p: _FakeDisk())

    rows = rm.collect_sample()
    rss_row = next(r for r in rows if r["metric_name"] == "memory_rss_mb")
    assert rss_row["value"] == 0.0
    assert rss_row["process_name"] == "unknown"
    # sampled_at is stamped on every row.
    assert all("sampled_at" in r for r in rows)


def test_collect_sample_access_denied_uses_unknown(monkeypatch):
    """Lines 76-78 (AccessDenied variant)."""

    def _denied(_pid):
        raise psutil.AccessDenied(_pid)

    monkeypatch.setattr(rm.psutil, "Process", _denied)
    _patch_common_psutil(monkeypatch, disk=lambda _p: _FakeDisk())

    rows = rm.collect_sample()
    rss_row = next(r for r in rows if r["metric_name"] == "memory_rss_mb")
    assert rss_row["value"] == 0.0
    assert rss_row["process_name"] == "unknown"


def test_collect_sample_disk_repo_error_falls_back_to_root(monkeypatch):
    """Lines 85-86: disk_usage(repo) raises -> retried with '/'."""
    monkeypatch.setattr(rm.psutil, "Process", lambda _pid: _FakeProc())
    _patch_common_psutil(monkeypatch)

    calls = []

    def _disk_usage(path):
        calls.append(path)
        if path == "/":
            return _FakeDisk()
        raise OSError("repo path unavailable")

    monkeypatch.setattr(rm.psutil, "disk_usage", _disk_usage)

    rows = rm.collect_sample()
    # Both the repo path (which raised) and the "/" fallback were attempted.
    assert calls[-1] == "/"
    assert len(calls) == 2
    disk_used = next(r for r in rows if r["metric_name"] == "disk_used_gb")
    assert disk_used["value"] == pytest.approx(10.0, abs=0.01)
    disk_pct = next(r for r in rows if r["metric_name"] == "disk_percent")
    assert disk_pct["value"] == 42.0


def test_collect_sample_happy_path_metric_shape(monkeypatch):
    """Sanity: normal collection yields the six expected metrics."""
    monkeypatch.setattr(rm.psutil, "Process", lambda _pid: _FakeProc())
    _patch_common_psutil(monkeypatch, disk=lambda _p: _FakeDisk())

    rows = rm.collect_sample()
    names = {r["metric_name"] for r in rows}
    assert names == {
        "cpu_percent",
        "memory_percent",
        "memory_rss_mb",
        "disk_used_gb",
        "disk_free_gb",
        "disk_percent",
    }
    cpu = next(r for r in rows if r["metric_name"] == "cpu_percent")
    assert cpu["value"] == 12.5 and cpu["unit"] == "%"


def test_collect_and_store_swallows_store_error(monkeypatch):
    """Lines 167-172: store_sample raising is logged, rows still returned."""
    monkeypatch.setattr(rm, "collect_sample", lambda: [{"metric_name": "x"}])

    def _bad_store(conn, rows):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(rm, "store_sample", _bad_store)

    rows = rm.collect_and_store(conn=object())
    assert rows == [{"metric_name": "x"}]


def test_collect_and_store_persists_on_success(monkeypatch):
    """Line 169 (success branch): store_sample is invoked with the rows."""
    sentinel_rows = [{"metric_name": "cpu_percent", "value": 1.0}]
    monkeypatch.setattr(rm, "collect_sample", lambda: sentinel_rows)
    captured = {}

    def _store(conn, rows):
        captured["conn"] = conn
        captured["rows"] = rows

    monkeypatch.setattr(rm, "store_sample", _store)

    conn = object()
    result = rm.collect_and_store(conn)
    assert result is sentinel_rows
    assert captured["conn"] is conn
    assert captured["rows"] is sentinel_rows


def test_run_collector_single_iteration(monkeypatch):
    """Lines 283-290: exercise one loop iteration then break via sleep."""
    fake_conn = object()

    # Patch the lazily-imported shared connection factory.
    import src.database.local_analytics_connector as lac

    monkeypatch.setattr(lac, "get_shared_connection", lambda: fake_conn)

    collected = []
    monkeypatch.setattr(
        rm, "collect_and_store", lambda conn: collected.append(conn)
    )

    class _StopLoop(Exception):
        pass

    def _sleep(_interval):
        raise _StopLoop

    monkeypatch.setattr(rm.time, "sleep", _sleep)

    with pytest.raises(_StopLoop):
        rm._run_collector(interval=60)

    assert collected == [fake_conn]


def test_run_collector_logs_collect_error_then_sleeps(monkeypatch):
    """Lines 287-290: collect_and_store error is caught, loop reaches sleep."""
    import src.database.local_analytics_connector as lac

    monkeypatch.setattr(lac, "get_shared_connection", lambda: object())

    def _boom(conn):
        raise RuntimeError("collector failure")

    monkeypatch.setattr(rm, "collect_and_store", _boom)

    class _StopLoop(Exception):
        pass

    slept = []

    def _sleep(interval):
        slept.append(interval)
        raise _StopLoop

    monkeypatch.setattr(rm.time, "sleep", _sleep)

    with pytest.raises(_StopLoop):
        rm._run_collector(interval=7)

    # We reached time.sleep despite the collect error -> error path executed.
    assert slept == [7]


def test_start_background_collector_starts_thread(monkeypatch):
    """Lines 300-311: first start spawns a daemon thread and sets the flag."""
    started = {}

    class _FakeThread:
        def __init__(self, target, args, daemon, name):
            started["target"] = target
            started["args"] = args
            started["daemon"] = daemon
            started["name"] = name

        def start(self):
            started["started"] = True

    monkeypatch.setattr(rm.threading, "Thread", _FakeThread)

    assert rm._collector_started is False
    rm.start_background_collector(interval=42)

    assert rm._collector_started is True
    assert started["started"] is True
    assert started["daemon"] is True
    assert started["name"] == "resource-monitor"
    assert started["args"] == (42,)
    assert started["target"] is rm._run_collector


def test_start_background_collector_is_idempotent(monkeypatch):
    """Lines 300-302: second call returns immediately, no new thread."""
    thread_count = {"n": 0}

    class _FakeThread:
        def __init__(self, *a, **k):
            thread_count["n"] += 1

        def start(self):
            pass

    monkeypatch.setattr(rm.threading, "Thread", _FakeThread)

    rm.start_background_collector(interval=5)
    rm.start_background_collector(interval=5)  # should early-return

    assert thread_count["n"] == 1
    assert rm._collector_started is True
