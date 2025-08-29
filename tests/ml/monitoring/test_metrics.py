"""Tests for monitoring metrics module."""
import pytest
from neuronews.ml.monitoring.metrics import PerformanceMonitor, DriftMonitor


def test_performance_monitor_empty():
    """Test performance monitor with no data."""
    monitor = PerformanceMonitor()
    summary = monitor.summary()
    
    assert summary["count"] == 0
    assert summary["avg"] == 0.0
    assert summary["p95"] == 0.0


def test_drift_monitor_empty():
    """Test drift monitor with no data."""
    monitor = DriftMonitor(baseline_mean=10.0)
    
    assert monitor.is_drifted() is False


def test_drift_monitor_zero_baseline():
    """Test drift monitor with zero baseline to avoid division by zero."""
    monitor = DriftMonitor(baseline_mean=0.0)
    
    # Add some values
    monitor.record(5.0)
    monitor.record(10.0)
    
    # Should not drift when baseline is zero (avoids div by zero)
    assert monitor.is_drifted() is False


def test_drift_monitor_summary():
    """Test drift monitor summary method."""
    monitor = DriftMonitor(baseline_mean=10.0)
    
    # Test empty summary
    summary = monitor.summary()
    assert "drift" in summary
    assert "count" in summary
    assert summary["count"] == 0
    
    # Add data and test again
    monitor.record(15.0)
    summary = monitor.summary()
    assert summary["count"] == 1
