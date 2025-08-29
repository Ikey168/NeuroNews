from neuronews.ml.monitoring.metrics import PerformanceMonitor, DriftMonitor


def test_performance_monitor_basic():
    pm = PerformanceMonitor(window=5)
    for v in [10, 20, 15]:
        pm.record(v)
    s = pm.summary()
    assert s["count"] == 3
    assert 10 <= s["avg"] <= 20


def test_drift_monitor_detection():
    dm = DriftMonitor(baseline_mean=10.0, threshold=0.1)
    for v in [10, 11, 12, 13]:
        dm.record(v)
    assert dm.is_drifted() is True

    dm2 = DriftMonitor(baseline_mean=10.0, threshold=0.5)
    for v in [10, 10.2, 9.8]:
        dm2.record(v)
    assert dm2.is_drifted() is False
