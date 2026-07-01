"""
Coverage-focused tests for src/scraper/performance_monitor.py.

Targets the remaining uncovered branches: monitoring loop and system-metric
collection error handling (psutil mocked), the metrics-history time filter,
report/insight/recommendation generation across all threshold branches,
console printing, file export, and the module-level dashboard accessor.
"""

import json
from datetime import datetime, timedelta

import pytest

import src.scraper.performance_monitor as pm
from src.scraper.performance_monitor import PerformanceDashboard, get_dashboard


@pytest.fixture()
def dash():
    return PerformanceDashboard(update_interval=0)


# --------------------------------------------------------------------------- #
# start/stop monitoring and the loop
# --------------------------------------------------------------------------- #

def test_start_monitoring_is_idempotent(dash):
    dash.monitoring = True  # pretend already running -> early return (line 67)
    dash.start_monitoring()
    assert dash.monitor_thread is None  # no thread created


def test_monitor_loop_handles_collection_error(dash, monkeypatch, caplog):
    calls = {"n": 0}

    def _boom(self):
        calls["n"] += 1
        # Stop after one iteration to avoid a busy loop.
        self.monitoring = False
        raise RuntimeError("collect fail")

    monkeypatch.setattr(PerformanceDashboard, "_collect_system_metrics", _boom)
    dash.monitoring = True
    dash.update_interval = 0
    dash._monitor_loop()
    assert calls["n"] == 1  # loop caught the error and exited


def test_stop_monitoring_joins_thread(dash):
    # No live thread; just exercise the stop path with a fake thread.
    class _T:
        def __init__(self):
            self.joined = False

        def join(self, timeout=None):
            self.joined = True

    t = _T()
    dash.monitor_thread = t
    dash.monitoring = True
    dash.stop_monitoring()
    assert dash.monitoring is False
    assert t.joined is True


# --------------------------------------------------------------------------- #
# system metric collection with mocked psutil
# --------------------------------------------------------------------------- #

def test_collect_system_metrics_success(dash, monkeypatch):
    class _VM:
        percent = 42.0

    class _Net:
        bytes_sent = 100
        bytes_recv = 200

    class _Disk:
        read_bytes = 5
        write_bytes = 6

    monkeypatch.setattr(pm.psutil, "cpu_percent", lambda: 12.5)
    monkeypatch.setattr(pm.psutil, "virtual_memory", lambda: _VM())
    monkeypatch.setattr(pm.psutil, "net_io_counters", lambda: _Net())
    monkeypatch.setattr(pm.psutil, "disk_io_counters", lambda: _Disk())

    dash._collect_system_metrics()
    assert list(dash.system_metrics["cpu_usage"]) == [12.5]
    assert list(dash.system_metrics["memory_usage"]) == [42.0]
    assert dash.system_metrics["network_io"][-1]["bytes_sent"] == 100
    assert dash.system_metrics["disk_io"][-1]["read_bytes"] == 5


def test_collect_system_metrics_outer_exception(dash, monkeypatch, caplog):
    def _boom():
        raise RuntimeError("cpu fail")

    monkeypatch.setattr(pm.psutil, "cpu_percent", _boom)
    # Should be caught and logged at debug level (lines 103-104).
    dash._collect_system_metrics()
    assert not dash.system_metrics["cpu_usage"]


def test_collect_network_metrics_error(dash, monkeypatch):
    def _boom():
        raise RuntimeError("net fail")

    monkeypatch.setattr(pm.psutil, "net_io_counters", _boom)
    dash._collect_network_metrics()  # exception swallowed (115-116)
    assert not dash.system_metrics["network_io"]


def test_collect_disk_metrics_error(dash, monkeypatch):
    def _boom():
        raise RuntimeError("disk fail")

    monkeypatch.setattr(pm.psutil, "disk_io_counters", _boom)
    dash._collect_disk_metrics()  # exception swallowed (129-130)
    assert not dash.system_metrics["disk_io"]


# --------------------------------------------------------------------------- #
# metrics history filtering
# --------------------------------------------------------------------------- #

def test_get_metrics_history_filters_by_time(dash):
    old = (datetime.now() - timedelta(minutes=120)).isoformat()
    recent = datetime.now().isoformat()
    dash.metrics_history.append({"timestamp": old, "marker": "old"})
    dash.metrics_history.append({"timestamp": recent, "marker": "new"})
    result = dash.get_metrics_history(minutes=30)
    markers = [m["marker"] for m in result]
    assert markers == ["new"]


# --------------------------------------------------------------------------- #
# report + insights + recommendations across threshold branches
# --------------------------------------------------------------------------- #

def _metrics(aps, success, mem, cpu, concurrent=1, sources=None):
    return {
        "articles_per_second": aps,
        "success_rate": success,
        "system": {"avg_memory": mem, "avg_cpu": cpu},
        "counters": {"concurrent_connections": concurrent},
        "sources": sources or {},
    }


def test_insights_high_end(dash):
    m = _metrics(aps=6, success=99, mem=1200, cpu=90)
    insights = dash._generate_insights(m, {"articles_per_second_trend": []})
    joined = " ".join(insights)
    assert "Excellent throughput" in joined
    assert "Excellent success rate" in joined
    assert "High memory usage" in joined
    assert "High CPU usage" in joined


def test_insights_mid_range(dash):
    m = _metrics(aps=3, success=90, mem=600, cpu=60)
    insights = dash._generate_insights(m, {"articles_per_second_trend": []})
    joined = " ".join(insights)
    assert "Good throughput" in joined
    assert "Good success rate" in joined
    assert "Moderate memory usage" in joined
    assert "Moderate CPU usage" in joined


def test_insights_low_end(dash):
    m = _metrics(aps=1, success=50, mem=100, cpu=10)
    insights = dash._generate_insights(m, {"articles_per_second_trend": []})
    joined = " ".join(insights)
    assert "Low throughput" in joined
    assert "Low success rate" in joined
    assert "Low memory usage" in joined
    assert "Low CPU usage" in joined


def test_insights_trend_upward(dash):
    trend = {"articles_per_second_trend": [1, 1, 1, 1, 1, 5, 5, 5, 5, 5]}
    m = _metrics(aps=5, success=99, mem=100, cpu=10)
    insights = dash._generate_insights(m, trend)
    assert any("improving" in i for i in insights)


def test_insights_trend_downward(dash):
    trend = {"articles_per_second_trend": [10, 10, 10, 10, 10, 1, 1, 1, 1, 1]}
    m = _metrics(aps=1, success=99, mem=100, cpu=10)
    insights = dash._generate_insights(m, trend)
    assert any("declining" in i for i in insights)


def test_recommendations_all_branches(dash):
    sources = {"badsrc": {"success_rate": 50}}
    m = _metrics(aps=1, success=80, mem=900, cpu=10, concurrent=2, sources=sources)
    recs = dash._generate_recommendations(m, [])
    joined = " ".join(recs)
    assert "retry delays" in joined            # low success rate
    assert "concurrent connections" in joined  # low throughput / memory
    assert "problematic sources" in joined      # bad source
    assert "badsrc" in joined


def test_recommendations_empty_when_healthy(dash):
    sources = {"ok": {"success_rate": 99}}
    m = _metrics(aps=10, success=99, mem=100, cpu=10, concurrent=20, sources=sources)
    recs = dash._generate_recommendations(m, [])
    assert recs == []


def test_generate_performance_report_uses_recent_history(dash):
    # Seed metrics_history with recent snapshots so the report walks trends.
    now = datetime.now().isoformat()
    dash.metrics_history.append(
        {
            "timestamp": now,
            "articles_per_second": 3.0,
            "success_rate": 92.0,
            "system": {"memory_mb": 400},
        }
    )
    report = dash.generate_performance_report()
    assert "current_metrics" in report
    assert report["trends"]["articles_per_second_trend"] == [3.0]
    assert report["trends"]["success_rate_trend"] == [92.0]
    assert report["trends"]["memory_usage_trend"] == [400]
    assert isinstance(report["insights"], list)
    assert isinstance(report["recommendations"], list)


# --------------------------------------------------------------------------- #
# console + file output
# --------------------------------------------------------------------------- #

def test_print_live_dashboard(dash, capsys):
    dash.record_article("bbc", response_time=0.5)
    dash.record_request(True, 0.5, "bbc")
    dash.print_live_dashboard()
    out = capsys.readouterr().out
    assert "LIVE PERFORMANCE DASHBOARD" in out
    assert "bbc" in out


def test_save_metrics_to_file(dash, tmp_path):
    dash.record_article("src", 0.1)
    path = tmp_path / "metrics.json"
    dash.save_metrics_to_file(str(path))
    data = json.loads(path.read_text())
    assert "counters" in data
    assert data["counters"]["total_articles"] == 1


def test_export_metrics_history(dash, tmp_path):
    dash.metrics_history.append(
        {"timestamp": datetime.now().isoformat(), "articles_per_second": 1.0}
    )
    path = tmp_path / "history.json"
    dash.export_metrics_history(str(path), hours=1)
    data = json.loads(path.read_text())
    assert data["period_hours"] == 1
    assert data["metrics_count"] == 1
    assert len(data["metrics_history"]) == 1


# --------------------------------------------------------------------------- #
# module-level accessor
# --------------------------------------------------------------------------- #

def test_get_dashboard_returns_global_instance():
    d = get_dashboard()
    assert isinstance(d, PerformanceDashboard)
    assert d is pm.performance_dashboard
