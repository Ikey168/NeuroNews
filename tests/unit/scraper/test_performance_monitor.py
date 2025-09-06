"""
Comprehensive tests for PerformanceMonitor.
Tests performance tracking, metrics collection, and dashboard functionality.
"""

import pytest
import time
import threading
from unittest.mock import MagicMock, patch
from collections import deque
from datetime import datetime

# Import with proper path handling
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'src'))

from scraper.performance_monitor import PerformanceDashboard


class TestPerformanceDashboard:
    """Test suite for PerformanceDashboard class."""

    @pytest.fixture
    def dashboard(self):
        """PerformanceDashboard fixture for testing."""
        return PerformanceDashboard(update_interval=1)  # Short interval for testing

    def test_dashboard_initialization(self, dashboard):
        """Test PerformanceDashboard initialization."""
        assert dashboard.update_interval == 1
        assert dashboard.start_time > 0
        assert len(dashboard.metrics_history) == 0
        assert dashboard.counters["total_articles"] == 0
        assert dashboard.counters["total_requests"] == 0

    def test_record_article_scraped(self, dashboard):
        """Test recording scraped articles."""
        source = "test_source"
        response_time = 0.5
        
        dashboard.record_article_scraped(source, response_time)
        
        assert dashboard.counters["total_articles"] == 1
        assert dashboard.source_metrics[source]["articles"] == 1
        assert len(dashboard.source_metrics[source]["response_times"]) == 1
        assert dashboard.source_metrics[source]["response_times"][0] == response_time

    def test_record_request_made(self, dashboard):
        """Test recording requests."""
        dashboard.record_request_made("test_source", success=True, response_time=0.3)
        
        assert dashboard.counters["total_requests"] == 1
        assert dashboard.counters["successful_requests"] == 1
        assert dashboard.counters["failed_requests"] == 0

    def test_record_failed_request(self, dashboard):
        """Test recording failed requests."""
        dashboard.record_request_made("test_source", success=False, response_time=2.0)
        
        assert dashboard.counters["total_requests"] == 1
        assert dashboard.counters["successful_requests"] == 0
        assert dashboard.counters["failed_requests"] == 1

    def test_record_error(self, dashboard):
        """Test recording errors."""
        source = "test_source"
        error_msg = "Connection timeout"
        
        dashboard.record_error(source, error_msg)
        
        assert dashboard.source_metrics[source]["errors"] == 1

    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    def test_collect_system_metrics(self, mock_memory, mock_cpu, dashboard):
        """Test system metrics collection."""
        # Mock system metrics
        mock_cpu.return_value = 45.5
        mock_memory.return_value = MagicMock(percent=67.8)
        
        dashboard._collect_system_metrics()
        
        assert len(dashboard.system_metrics["cpu_usage"]) == 1
        assert len(dashboard.system_metrics["memory_usage"]) == 1
        assert dashboard.system_metrics["cpu_usage"][0] == 45.5
        assert dashboard.system_metrics["memory_usage"][0] == 67.8

    def test_calculate_rates(self, dashboard):
        """Test rate calculations."""
        # Add some test data
        dashboard.counters["total_articles"] = 100
        dashboard.counters["successful_requests"] = 150
        dashboard.start_time = time.time() - 60  # 1 minute ago
        
        rates = dashboard.get_current_rates()
        
        assert "articles_per_minute" in rates
        assert "requests_per_minute" in rates
        assert rates["articles_per_minute"] > 0
        assert rates["requests_per_minute"] > 0

    def test_get_performance_summary(self, dashboard):
        """Test performance summary generation."""
        # Add test data
        dashboard.record_article_scraped("source1", 0.5)
        dashboard.record_article_scraped("source2", 1.0)
        dashboard.record_request_made("source1", True, 0.3)
        dashboard.record_request_made("source2", False, 2.0)
        
        summary = dashboard.get_performance_summary()
        
        assert "total_articles" in summary
        assert "total_requests" in summary
        assert "success_rate" in summary
        assert "average_response_time" in summary
        assert summary["total_articles"] == 2
        assert summary["total_requests"] == 2

    def test_source_specific_metrics(self, dashboard):
        """Test source-specific metrics tracking."""
        source1 = "npr.org"
        source2 = "bbc.com"
        
        dashboard.record_article_scraped(source1, 0.5)
        dashboard.record_article_scraped(source1, 0.7)
        dashboard.record_article_scraped(source2, 1.2)
        dashboard.record_error(source1, "Timeout")
        
        source1_metrics = dashboard.get_source_metrics(source1)
        source2_metrics = dashboard.get_source_metrics(source2)
        
        assert source1_metrics["articles"] == 2
        assert source1_metrics["errors"] == 1
        assert source2_metrics["articles"] == 1
        assert source2_metrics["errors"] == 0

    def test_response_time_tracking(self, dashboard):
        """Test response time tracking and analysis."""
        response_times = [0.1, 0.5, 0.3, 1.2, 0.8, 0.4, 0.6]
        source = "test_source"
        
        for rt in response_times:
            dashboard.record_request_made(source, True, rt)
        
        metrics = dashboard.get_source_metrics(source)
        avg_response_time = dashboard.calculate_average_response_time(source)
        
        assert len(metrics["response_times"]) == len(response_times)
        assert abs(avg_response_time - sum(response_times) / len(response_times)) < 0.01

    def test_concurrent_connections_tracking(self, dashboard):
        """Test concurrent connections tracking."""
        dashboard.increment_concurrent_connections()
        dashboard.increment_concurrent_connections()
        
        assert dashboard.counters["concurrent_connections"] == 2
        
        dashboard.decrement_concurrent_connections()
        
        assert dashboard.counters["concurrent_connections"] == 1

    def test_active_threads_tracking(self, dashboard):
        """Test active threads tracking."""
        dashboard.set_active_threads(5)
        
        assert dashboard.counters["active_threads"] == 5

    def test_metrics_history_limit(self, dashboard):
        """Test metrics history size limit."""
        # Add more than the maxlen items
        for i in range(150):
            dashboard.metrics_history.append({"timestamp": i})
        
        # Should be limited to 100 items
        assert len(dashboard.metrics_history) == 100
        # Should keep the most recent items
        assert dashboard.metrics_history[-1]["timestamp"] == 149

    def test_get_uptime(self, dashboard):
        """Test uptime calculation."""
        # Set start time to 1 hour ago
        dashboard.start_time = time.time() - 3600
        
        uptime = dashboard.get_uptime()
        
        assert uptime >= 3600
        assert uptime < 3610  # Allow some variance

    def test_error_rate_calculation(self, dashboard):
        """Test error rate calculation."""
        # Add successful and failed requests
        for _ in range(8):
            dashboard.record_request_made("test", True, 0.5)
        for _ in range(2):
            dashboard.record_request_made("test", False, 1.0)
        
        error_rate = dashboard.get_error_rate()
        
        assert abs(error_rate - 0.2) < 0.01  # 20% error rate

    def test_peak_performance_tracking(self, dashboard):
        """Test peak performance tracking."""
        # Simulate varying performance
        dashboard.record_performance_point(articles_per_minute=50)
        dashboard.record_performance_point(articles_per_minute=75)
        dashboard.record_performance_point(articles_per_minute=60)
        
        peak_performance = dashboard.get_peak_performance()
        
        assert peak_performance["articles_per_minute"] == 75

    def test_performance_alerts(self, dashboard):
        """Test performance alerting system."""
        dashboard.set_alert_thresholds(
            max_response_time=1.0,
            max_error_rate=0.1,
            min_success_rate=0.9
        )
        
        # Trigger response time alert
        dashboard.record_request_made("slow_source", True, 2.0)
        alerts = dashboard.check_performance_alerts()
        
        assert len(alerts) > 0
        assert any("response_time" in alert["type"] for alert in alerts)

    def test_memory_usage_tracking(self, dashboard):
        """Test memory usage tracking."""
        with patch('psutil.virtual_memory') as mock_memory:
            mock_memory.return_value = MagicMock(
                percent=75.5,
                used=8000000000,  # 8GB
                available=2000000000  # 2GB
            )
            
            dashboard._collect_system_metrics()
            
            assert len(dashboard.system_metrics["memory_usage"]) == 1
            assert dashboard.system_metrics["memory_usage"][0] == 75.5

    def test_cpu_usage_tracking(self, dashboard):
        """Test CPU usage tracking."""
        with patch('psutil.cpu_percent') as mock_cpu:
            mock_cpu.return_value = 42.3
            
            dashboard._collect_system_metrics()
            
            assert len(dashboard.system_metrics["cpu_usage"]) == 1
            assert dashboard.system_metrics["cpu_usage"][0] == 42.3

    def test_network_io_tracking(self, dashboard):
        """Test network I/O tracking."""
        with patch('psutil.net_io_counters') as mock_net:
            mock_net.return_value = MagicMock(
                bytes_sent=1000000,
                bytes_recv=5000000
            )
            
            dashboard._collect_network_metrics()
            
            assert "network_io" in dashboard.system_metrics

    def test_disk_io_tracking(self, dashboard):
        """Test disk I/O tracking."""
        with patch('psutil.disk_io_counters') as mock_disk:
            mock_disk.return_value = MagicMock(
                read_bytes=10000000,
                write_bytes=2000000
            )
            
            dashboard._collect_disk_metrics()
            
            assert "disk_io" in dashboard.system_metrics

    def test_real_time_updates(self, dashboard):
        """Test real-time metrics updates."""
        # Start monitoring
        dashboard.start_monitoring()
        
        # Add some activity
        dashboard.record_article_scraped("test", 0.5)
        
        # Wait for update
        time.sleep(1.5)  # Longer than update interval
        
        # Stop monitoring
        dashboard.stop_monitoring()
        
        # Should have captured metrics
        assert len(dashboard.metrics_history) > 0

    def test_performance_regression_detection(self, dashboard):
        """Test performance regression detection."""
        # Add baseline performance data
        for _ in range(10):
            dashboard.record_request_made("test", True, 0.5)
        
        baseline = dashboard.calculate_baseline_performance()
        
        # Add slower performance data
        for _ in range(5):
            dashboard.record_request_made("test", True, 1.5)
        
        current = dashboard.get_current_performance()
        regression = dashboard.detect_performance_regression(baseline, current)
        
        assert regression is True

    def test_export_metrics(self, dashboard):
        """Test metrics export functionality."""
        # Add test data
        dashboard.record_article_scraped("source1", 0.5)
        dashboard.record_request_made("source1", True, 0.3)
        
        exported_data = dashboard.export_metrics()
        
        assert "counters" in exported_data
        assert "source_metrics" in exported_data
        assert "system_metrics" in exported_data
        assert "timestamp" in exported_data

    def test_dashboard_reset(self, dashboard):
        """Test dashboard metrics reset."""
        # Add test data
        dashboard.record_article_scraped("test", 0.5)
        dashboard.record_request_made("test", True, 0.3)
        
        assert dashboard.counters["total_articles"] == 1
        
        dashboard.reset_metrics()
        
        assert dashboard.counters["total_articles"] == 0
        assert len(dashboard.metrics_history) == 0
        assert len(dashboard.source_metrics) == 0

    def test_custom_metric_tracking(self, dashboard):
        """Test custom metric tracking."""
        dashboard.add_custom_metric("custom_counter", 0)
        dashboard.increment_custom_metric("custom_counter", 5)
        
        assert dashboard.get_custom_metric("custom_counter") == 5
        
        dashboard.increment_custom_metric("custom_counter", 3)
        
        assert dashboard.get_custom_metric("custom_counter") == 8

    def test_thread_safety(self, dashboard):
        """Test thread safety of metrics collection."""
        def worker():
            for _ in range(100):
                dashboard.record_article_scraped("thread_test", 0.1)
        
        # Start multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have recorded all articles without race conditions
        assert dashboard.counters["total_articles"] == 500
        assert dashboard.source_metrics["thread_test"]["articles"] == 500

    def test_performance_percentiles(self, dashboard):
        """Test response time percentile calculations."""
        response_times = [0.1, 0.2, 0.3, 0.5, 0.7, 1.0, 1.2, 1.5, 2.0, 3.0]
        
        for rt in response_times:
            dashboard.record_request_made("test", True, rt)
        
        percentiles = dashboard.calculate_response_time_percentiles("test")
        
        assert "p50" in percentiles  # Median
        assert "p95" in percentiles  # 95th percentile
        assert "p99" in percentiles  # 99th percentile
        
        # Basic sanity checks
        assert percentiles["p50"] <= percentiles["p95"]
        assert percentiles["p95"] <= percentiles["p99"]