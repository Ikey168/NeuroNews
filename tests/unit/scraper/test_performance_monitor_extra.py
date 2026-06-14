"""Additional tests covering uncovered logic in scraper/performance_monitor.py."""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper.performance_monitor import PerformanceDashboard  # noqa: E402


@pytest.fixture
def dash():
    return PerformanceDashboard(update_interval=1)


class TestPerformancePoints:
    def test_record_and_peak(self, dash):
        assert dash.get_peak_performance() == {}
        dash.record_performance_point(articles_per_minute=10)
        dash.record_performance_point(articles_per_minute=30)
        dash.record_performance_point(articles_per_minute=20)
        peak = dash.get_peak_performance()
        assert peak["articles_per_minute"] == 30
        assert "timestamp" in peak


class TestAlerts:
    def test_no_thresholds_no_alerts(self, dash):
        dash.record_request(False, source="bbc")
        assert dash.check_performance_alerts() == []

    def test_response_time_alert(self, dash):
        dash.set_alert_thresholds(max_response_time=1.0)
        dash.record_article("bbc", response_time=5.0)
        alerts = dash.check_performance_alerts()
        assert any(a["type"] == "response_time" and a["observed"] == 5.0 for a in alerts)

    def test_error_rate_alert(self, dash):
        dash.set_alert_thresholds(max_error_rate=0.1)
        dash.record_request(False, source="bbc")  # 100% error rate
        alerts = dash.check_performance_alerts()
        assert any(a["type"] == "error_rate" for a in alerts)

    def test_success_rate_alert(self, dash):
        dash.set_alert_thresholds(min_success_rate=0.9)
        dash.record_request(False, source="bbc")
        alerts = dash.check_performance_alerts()
        assert any(a["type"] == "success_rate" for a in alerts)


class TestBaselineAndRegression:
    def test_baseline_empty(self, dash):
        base = dash.calculate_baseline_performance()
        assert base["average_response_time"] == 0.0
        assert base["sample_count"] == 0

    def test_baseline_and_current(self, dash):
        for t in (1.0, 2.0, 3.0):
            dash.record_article("bbc", response_time=t)
        base = dash.calculate_baseline_performance()
        assert base["average_response_time"] == 2.0
        assert base["sample_count"] == 3
        cur = dash.get_current_performance(window=2)
        assert cur["sample_count"] == 2

    def test_regression_detection(self, dash):
        base = {"average_response_time": 1.0}
        assert dash.detect_performance_regression(base, {"average_response_time": 1.5}) is True
        assert dash.detect_performance_regression(base, {"average_response_time": 1.1}) is False
        assert dash.detect_performance_regression(
            {"average_response_time": 0.0}, {"average_response_time": 99}
        ) is False


class TestExportReset:
    def test_export_metrics(self, dash):
        dash.record_article("bbc", response_time=1.0)
        exported = dash.export_metrics()
        assert exported["counters"]["total_articles"] == 1
        assert exported["source_metrics"]["bbc"]["articles"] == 1
        assert "timestamp" in exported

    def test_reset_metrics(self, dash):
        dash.record_article("bbc", response_time=1.0)
        dash.add_custom_metric("x", 5)
        dash.reset_metrics()
        assert dash.counters["total_articles"] == 0
        assert dash.custom_metrics == {}
        assert len(dash.source_metrics) == 0


class TestCustomMetrics:
    def test_custom_metric_lifecycle(self, dash):
        dash.add_custom_metric("cache_hits", 10)
        assert dash.get_custom_metric("cache_hits") == 10
        dash.increment_custom_metric("cache_hits", 5)
        assert dash.get_custom_metric("cache_hits") == 15
        dash.increment_custom_metric("new_metric")
        assert dash.get_custom_metric("new_metric") == 1
        assert dash.get_custom_metric("missing") is None


class TestPercentiles:
    def test_empty(self, dash):
        assert dash.calculate_response_time_percentiles("bbc") == {
            "p50": 0.0, "p95": 0.0, "p99": 0.0
        }

    def test_with_data(self, dash):
        for t in range(1, 101):
            dash.record_article("bbc", response_time=float(t))
        pct = dash.calculate_response_time_percentiles("bbc")
        assert pct["p50"] <= pct["p95"] <= pct["p99"]
        assert pct["p99"] >= 99.0


class TestAliasesAndCounters:
    def test_record_aliases(self, dash):
        dash.record_article_scraped("bbc", 1.0)
        dash.record_request_made("bbc", success=True, response_time=1.0)
        assert dash.counters["total_articles"] == 1
        assert dash.counters["successful_requests"] == 1

    def test_connection_thread_updates(self, dash):
        dash.update_concurrent_connections(7)
        dash.update_active_threads(3)
        assert dash.counters["concurrent_connections"] == 7
        assert dash.counters["active_threads"] == 3

    def test_uptime_and_error_rate(self, dash):
        assert dash.get_uptime() >= 0
        assert dash.get_error_rate() == 0.0
        dash.record_request(False, source="bbc")
        assert dash.get_error_rate() == 1.0


class TestReports:
    def test_get_current_metrics(self, dash):
        dash.record_article("bbc", response_time=1.0)
        m = dash.get_current_metrics()
        assert m["counters"]["total_articles"] == 1
        assert "bbc" in m["sources"]
        assert "avg_cpu" in m["system"]

    def test_get_performance_stats(self, dash):
        dash.record_article("bbc", response_time=2.0)
        dash.record_request(True, response_time=2.0, source="bbc")
        stats = dash.get_performance_stats()
        assert stats["total_articles"] == 1
        assert stats["avg_response_time"] == 2.0

    def test_metrics_history_empty(self, dash):
        assert dash.get_metrics_history(minutes=10) == []

    def test_generate_performance_report(self, dash):
        dash.record_article("bbc", response_time=1.0)
        report = dash.generate_performance_report()
        assert "current_metrics" in report
        assert "insights" in report
        assert isinstance(report["insights"], list)


class TestSystemMetrics:
    def test_collect_system_metrics_mocked(self, dash):
        with patch("scraper.performance_monitor.psutil") as ps:
            ps.cpu_percent.return_value = 12.5
            ps.virtual_memory.return_value = MagicMock(percent=40.0)
            ps.net_io_counters.return_value = MagicMock(bytes_sent=1, bytes_recv=2)
            ps.disk_io_counters.return_value = MagicMock(read_bytes=3, write_bytes=4)
            dash._collect_system_metrics()
        assert list(dash.system_metrics["cpu_usage"]) == [12.5]
        assert list(dash.system_metrics["memory_usage"]) == [40.0]
        assert dash.system_metrics["network_io"][-1]["bytes_sent"] == 1
        assert dash.system_metrics["disk_io"][-1]["read_bytes"] == 3
