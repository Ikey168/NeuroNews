"""
Real-time performance monitoring dashboard for async scraper.
Provides live metrics visualization and performance tracking.
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List

import psutil


class PerformanceDashboard:
    """Real-time performance monitoring dashboard."""

    def __init__(self, update_interval: int = 5):
        self.update_interval = update_interval
        self.start_time = time.time()

        # Metrics storage
        self.metrics_history = deque(maxlen=100)  # Last 100 updates
        self.source_metrics = defaultdict(
            lambda: {
                "articles": 0,
                "errors": 0,
                "response_times": deque(maxlen=50),
                "last_updated": None,
            }
        )

        # System metrics
        self.system_metrics = {
            "cpu_usage": deque(maxlen=50),
            "memory_usage": deque(maxlen=50),
            "network_io": deque(maxlen=50),
            "disk_io": deque(maxlen=50),
        }

        # Performance counters
        self.counters = {
            "total_articles": 0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "concurrent_connections": 0,
            "active_threads": 0,
        }

        # Custom metrics, performance points, and alerting
        self.custom_metrics: Dict[str, Any] = {}
        self.performance_points: List[Dict[str, Any]] = []
        self.alert_thresholds: Dict[str, Any] = {}

        # Monitoring state
        self.monitoring = False
        self.monitor_thread = None

        self.logger = logging.getLogger(__name__)

    def start_monitoring(self):
        """Start performance monitoring."""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        self.logger.info(" Performance monitoring started")

    def stop_monitoring(self):
        """Stop performance monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)

        self.logger.info(" Performance monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop."""
        while self.monitoring:
            try:
                self._collect_system_metrics()
                self._update_metrics_history()
                time.sleep(self.update_interval)
            except Exception as e:
                self.logger.error("Monitoring error: {0}".format(e))

    def _collect_system_metrics(self):
        """Collect system performance metrics."""
        try:
            self.system_metrics["cpu_usage"].append(psutil.cpu_percent())
            self.system_metrics["memory_usage"].append(
                psutil.virtual_memory().percent
            )
            self._collect_network_metrics()
            self._collect_disk_metrics()
        except Exception as e:
            self.logger.debug("System metrics collection error: {0}".format(e))

    def _collect_network_metrics(self):
        """Collect network I/O metrics."""
        try:
            net_io = psutil.net_io_counters()
            if net_io:
                self.system_metrics["network_io"].append(
                    {"bytes_sent": net_io.bytes_sent,
                        "bytes_recv": net_io.bytes_recv}
                )
        except Exception as e:
            self.logger.debug("Network metrics collection error: {0}".format(e))

    def _collect_disk_metrics(self):
        """Collect disk I/O metrics."""
        try:
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.system_metrics["disk_io"].append(
                    {
                        "read_bytes": disk_io.read_bytes,
                        "write_bytes": disk_io.write_bytes,
                    }
                )
        except Exception as e:
            self.logger.debug("Disk metrics collection error: {0}".format(e))

    def _update_metrics_history(self):
        """Update metrics history."""
        current_time = time.time()
        elapsed_time = current_time - self.start_time

        # Calculate rates
        articles_per_second = self.counters["total_articles"] / \
            max(elapsed_time, 1)
        requests_per_second = self.counters["total_requests"] / \
            max(elapsed_time, 1)
        success_rate = (
            self.counters["successful_requests"]
            / max(self.counters["total_requests"], 1)
            * 100
        )

        # Create metrics snapshot
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "elapsed_time": elapsed_time,
            "articles_per_second": articles_per_second,
            "requests_per_second": requests_per_second,
            "success_rate": success_rate,
            "total_articles": self.counters["total_articles"],
            "total_requests": self.counters["total_requests"],
            "concurrent_connections": self.counters["concurrent_connections"],
            "active_threads": self.counters["active_threads"],
            "system": {
                "cpu_usage": (
                    list(self.system_metrics["cpu_usage"])[-1]
                    if self.system_metrics["cpu_usage"]
                    else 0
                ),
                "memory_mb": (
                    list(self.system_metrics["memory_usage"])[-1]
                    if self.system_metrics["memory_usage"]
                    else 0
                ),
            },
            "sources": dict(self.source_metrics),
        }

        self.metrics_history.append(metrics)

    def record_article(self, source: str, response_time: float = None):
        """Record a successfully scraped article."""
        self.counters["total_articles"] += 1
        self.source_metrics[source]["articles"] += 1
        self.source_metrics[source]["last_updated"] = datetime.now(
        ).isoformat()

        if response_time is not None:
            self.source_metrics[source]["response_times"].append(response_time)

    def record_request(
        self, success: bool, response_time: float = None, source: str = "unknown"
    ):
        """Record a request (successful or failed)."""
        self.counters["total_requests"] += 1

        if success:
            self.counters["successful_requests"] += 1
        else:
            self.counters["failed_requests"] += 1
            self.source_metrics[source]["errors"] += 1

        if response_time is not None:
            self.source_metrics[source]["response_times"].append(response_time)

    def get_current_rates(self) -> Dict[str, float]:
        """Per-minute article and request rates since startup."""
        elapsed_minutes = max(self.get_uptime() / 60, 1e-9)
        requests = max(
            self.counters["total_requests"],
            self.counters["successful_requests"] + self.counters["failed_requests"],
        )
        return {
            "articles_per_minute": self.counters["total_articles"] / elapsed_minutes,
            "requests_per_minute": requests / elapsed_minutes,
        }

    def record_error(self, source: str, error_message: str = None):
        """Record an error for a source."""
        self.source_metrics[source]["errors"] += 1
        if error_message:
            self.logger.debug("Error from {0}: {1}".format(source, error_message))

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of overall scraping performance."""
        total_requests = self.counters["total_requests"]
        success_rate = (
            self.counters["successful_requests"] / total_requests * 100
            if total_requests
            else 0.0
        )
        all_times = [
            t
            for metrics in self.source_metrics.values()
            for t in metrics["response_times"]
        ]
        return {
            "total_articles": self.counters["total_articles"],
            "total_requests": total_requests,
            "success_rate": success_rate,
            "average_response_time": (
                sum(all_times) / len(all_times) if all_times else 0.0
            ),
            "uptime_seconds": self.get_uptime(),
        }

    def get_source_metrics(self, source: str) -> Dict[str, Any]:
        """Get raw metrics for a single source."""
        return self.source_metrics[source]

    def calculate_average_response_time(self, source: str) -> float:
        """Average response time for a source."""
        times = self.source_metrics[source]["response_times"]
        return sum(times) / len(times) if times else 0.0

    def increment_concurrent_connections(self) -> None:
        self.counters["concurrent_connections"] += 1

    def decrement_concurrent_connections(self) -> None:
        if self.counters["concurrent_connections"] > 0:
            self.counters["concurrent_connections"] -= 1

    def set_active_threads(self, count: int) -> None:
        self.counters["active_threads"] = count

    def get_uptime(self) -> float:
        """Seconds since the dashboard was created."""
        return time.time() - self.start_time

    def get_error_rate(self) -> float:
        """Fraction of requests that failed (0.0 - 1.0)."""
        total = self.counters["total_requests"]
        return self.counters["failed_requests"] / total if total else 0.0

    def record_performance_point(self, **metrics) -> None:
        """Record an arbitrary performance data point."""
        point = dict(metrics)
        point["timestamp"] = time.time()
        self.performance_points.append(point)

    def get_peak_performance(self) -> Dict[str, Any]:
        """Return the recorded point with the highest articles_per_minute."""
        if not self.performance_points:
            return {}
        return max(
            self.performance_points,
            key=lambda p: p.get("articles_per_minute", 0),
        )

    def set_alert_thresholds(
        self,
        max_response_time: float = None,
        max_error_rate: float = None,
        min_success_rate: float = None,
    ) -> None:
        """Configure performance alerting thresholds."""
        self.alert_thresholds = {
            "max_response_time": max_response_time,
            "max_error_rate": max_error_rate,
            "min_success_rate": min_success_rate,
        }

    def check_performance_alerts(self) -> List[Dict[str, Any]]:
        """Evaluate current metrics against configured thresholds."""
        alerts = []
        thresholds = getattr(self, "alert_thresholds", {})

        max_rt = thresholds.get("max_response_time")
        if max_rt is not None:
            for source, metrics in self.source_metrics.items():
                slow = [t for t in metrics["response_times"] if t > max_rt]
                if slow:
                    alerts.append(
                        {
                            "type": "response_time",
                            "source": source,
                            "threshold": max_rt,
                            "observed": max(slow),
                        }
                    )

        max_err = thresholds.get("max_error_rate")
        if max_err is not None and self.get_error_rate() > max_err:
            alerts.append(
                {
                    "type": "error_rate",
                    "threshold": max_err,
                    "observed": self.get_error_rate(),
                }
            )

        min_success = thresholds.get("min_success_rate")
        total = self.counters["total_requests"]
        if min_success is not None and total:
            success_rate = self.counters["successful_requests"] / total
            if success_rate < min_success:
                alerts.append(
                    {
                        "type": "success_rate",
                        "threshold": min_success,
                        "observed": success_rate,
                    }
                )

        return alerts

    def calculate_baseline_performance(self) -> Dict[str, Any]:
        """Snapshot current averages to use as a performance baseline."""
        all_times = [
            t
            for metrics in self.source_metrics.values()
            for t in metrics["response_times"]
        ]
        return {
            "average_response_time": (
                sum(all_times) / len(all_times) if all_times else 0.0
            ),
            "sample_count": len(all_times),
        }

    def get_current_performance(self, window: int = 5) -> Dict[str, Any]:
        """Average over the most recent response times."""
        all_times = [
            t
            for metrics in self.source_metrics.values()
            for t in metrics["response_times"]
        ]
        recent = all_times[-window:] if all_times else []
        return {
            "average_response_time": (
                sum(recent) / len(recent) if recent else 0.0
            ),
            "sample_count": len(recent),
        }

    def detect_performance_regression(
        self,
        baseline: Dict[str, Any],
        current: Dict[str, Any],
        tolerance: float = 1.2,
    ) -> bool:
        """True when current response times exceed baseline by tolerance."""
        base = baseline.get("average_response_time", 0.0)
        cur = current.get("average_response_time", 0.0)
        if base <= 0:
            return False
        return cur > base * tolerance

    def export_metrics(self) -> Dict[str, Any]:
        """Export all metrics as a plain dictionary."""
        return {
            "counters": dict(self.counters),
            "source_metrics": {
                source: {
                    "articles": m["articles"],
                    "errors": m["errors"],
                    "response_times": list(m["response_times"]),
                    "last_updated": m["last_updated"],
                }
                for source, m in self.source_metrics.items()
            },
            "system_metrics": {
                k: list(v) for k, v in self.system_metrics.items()
            },
            "timestamp": datetime.now().isoformat(),
        }

    def reset_metrics(self) -> None:
        """Reset all counters, history, and per-source metrics."""
        for key in self.counters:
            self.counters[key] = 0
        self.metrics_history.clear()
        self.source_metrics.clear()
        self.performance_points.clear()
        self.custom_metrics.clear()

    def add_custom_metric(self, name: str, value: Any = 0) -> None:
        self.custom_metrics[name] = value

    def increment_custom_metric(self, name: str, delta: float = 1) -> None:
        self.custom_metrics[name] = self.custom_metrics.get(name, 0) + delta

    def get_custom_metric(self, name: str) -> Any:
        return self.custom_metrics.get(name)

    def calculate_response_time_percentiles(self, source: str) -> Dict[str, float]:
        """Calculate p50/p95/p99 response time percentiles for a source."""
        times = sorted(self.source_metrics[source]["response_times"])
        if not times:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}

        def percentile(p):
            idx = min(int(len(times) * p / 100), len(times) - 1)
            return times[idx]

        return {
            "p50": percentile(50),
            "p95": percentile(95),
            "p99": percentile(99),
        }

    def record_article_scraped(self, source: str, response_time: float = None):
        """Alias for record_article using (source, response_time) order."""
        self.record_article(source, response_time)

    def record_request_made(
        self, source: str = "unknown", success: bool = True, response_time: float = None
    ):
        """Alias for record_request using (source, success, response_time) order."""
        self.record_request(success, response_time, source)

    def update_concurrent_connections(self, count: int):
        """Update concurrent connections count."""
        self.counters["concurrent_connections"] = count

    def update_active_threads(self, count: int):
        """Update active threads count."""
        self.counters["active_threads"] = count

    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        current_time = time.time()
        elapsed_time = current_time - self.start_time

        return {
            "timestamp": datetime.now().isoformat(),
            "elapsed_time": elapsed_time,
            "articles_per_second": self.counters["total_articles"]
            / max(elapsed_time, 1),
            "requests_per_second": self.counters["total_requests"]
            / max(elapsed_time, 1),
            "success_rate": (
                self.counters["successful_requests"]
                / max(self.counters["total_requests"], 1)
                * 100
            ),
            "counters": self.counters.copy(),
            "system": {
                "cpu_usage": list(self.system_metrics["cpu_usage"]),
                "memory_usage": list(self.system_metrics["memory_usage"]),
                "avg_cpu": sum(self.system_metrics["cpu_usage"])
                / max(len(self.system_metrics["cpu_usage"]), 1),
                "avg_memory": sum(self.system_metrics["memory_usage"])
                / max(len(self.system_metrics["memory_usage"]), 1),
            },
            "sources": self._get_source_stats(),
        }

    def _get_source_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get detailed source statistics."""
        stats = {}

        for source, metrics in self.source_metrics.items():
            response_times = list(metrics["response_times"])

            stats[source] = {
                "articles": metrics["articles"],
                "errors": metrics["errors"],
                "avg_response_time": sum(response_times) / max(len(response_times), 1),
                "last_updated": metrics["last_updated"],
                "success_rate": (
                    metrics["articles"]
                    / max(metrics["articles"] + metrics["errors"], 1)
                    * 100
                ),
            }

        return stats

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get basic performance statistics for testing and monitoring."""
        total_requests = (
            self.counters["successful_requests"] +
                self.counters["failed_requests"]
        )

        # Calculate average response time
        avg_response_time = 0.0
        total_response_time = 0.0
        total_responses = 0

        for source_metrics in self.source_metrics.values():
            response_times = list(source_metrics["response_times"])
            if response_times:
                total_response_time += sum(response_times)
                total_responses += len(response_times)

        if total_responses > 0:
            avg_response_time = total_response_time / total_responses

        return {
            "total_articles": self.counters["total_articles"],
            "total_requests": total_requests,
            "successful_requests": self.counters["successful_requests"],
            "failed_requests": self.counters["failed_requests"],
            "avg_response_time": avg_response_time,
            "uptime_seconds": time.time() - self.start_time,
            "articles_per_second": self.counters["total_articles"]
            / max(time.time() - self.start_time, 1),
            "success_rate": (
                self.counters["successful_requests"] / max(total_requests, 1)
            )
            * 100,
        }

    def get_metrics_history(self, minutes: int = 30) -> List[Dict[str, Any]]:
        """Get metrics history for the last N minutes."""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)

        filtered_metrics = []
        for metrics in self.metrics_history:
            metrics_time = datetime.fromisoformat(metrics["timestamp"])
            if metrics_time >= cutoff_time:
                filtered_metrics.append(metrics)

        return filtered_metrics

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report."""
        current_metrics = self.get_current_metrics()

        # Calculate performance trends
        recent_metrics = self.get_metrics_history(minutes=10)

        trend_data = {
            "articles_per_second_trend": [],
            "success_rate_trend": [],
            "memory_usage_trend": [],
        }

        for metrics in recent_metrics:
            trend_data["articles_per_second_trend"].append(
                metrics["articles_per_second"]
            )
            trend_data["success_rate_trend"].append(metrics["success_rate"])
            trend_data["memory_usage_trend"].append(
                metrics["system"]["memory_mb"])

        # Performance insights
        insights = self._generate_insights(current_metrics, trend_data)

        return {
            "report_timestamp": datetime.now().isoformat(),
            "current_metrics": current_metrics,
            "trends": trend_data,
            "insights": insights,
            "recommendations": self._generate_recommendations(
                current_metrics, insights
            ),
        }

    def _generate_insights(
        self, metrics: Dict[str, Any], trends: Dict[str, List[float]]
    ) -> List[str]:
        """Generate performance insights."""
        insights = []

        # Throughput analysis
        if metrics["articles_per_second"] > 5:
            insights.append(
                " Excellent throughput: Scraper is performing at high speed"
            )
        elif metrics["articles_per_second"] > 2:
            insights.append("⚡ Good throughput: Scraper is performing well")
        else:
            insights.append(
                "🐌 Low throughput: Consider optimizing concurrent connections"
            )

        # Success rate analysis
        if metrics["success_rate"] > 95:
            insights.append(" Excellent success rate: Very reliable scraping")
        elif metrics["success_rate"] > 85:
            insights.append("👍 Good success rate: Mostly reliable scraping")
        else:
            insights.append(
                "⚠️ Low success rate: Check network conditions and rate limiting"
            )

        # Memory usage analysis
        avg_memory = metrics["system"]["avg_memory"]
        if avg_memory > 1000:
            insights.append(
                "🔥 High memory usage: Consider reducing concurrent connections"
            )
        elif avg_memory > 500:
            insights.append(
                " Moderate memory usage: Monitor for memory leaks")
        else:
            insights.append(
                "💚 Low memory usage: Efficient resource utilization")

        # CPU usage analysis
        avg_cpu = metrics["system"]["avg_cpu"]
        if avg_cpu > 80:
            insights.append(
                "🔥 High CPU usage: Consider reducing thread pool size")
        elif avg_cpu > 50:
            insights.append(" Moderate CPU usage: Good resource utilization")
        else:
            insights.append(
                "💚 Low CPU usage: Room for more concurrent processing")

        # Trend analysis
        if len(trends["articles_per_second_trend"]) > 5:
            recent_avg = sum(trends["articles_per_second_trend"][-5:]) / 5
            earlier_avg = sum(trends["articles_per_second_trend"][:5]) / 5

            if recent_avg > earlier_avg * 1.1:
                insights.append(
                    " Performance improving: Throughput trending upward")
            elif recent_avg < earlier_avg * 0.9:
                insights.append(
                    "📉 Performance declining: Throughput trending downward"
                )

        return insights

    def _generate_recommendations(
        self, metrics: Dict[str, Any], insights: List[str]
    ) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []

        # Based on success rate
        if metrics["success_rate"] < 90:
            recommendations.append(
                "🔧 Increase retry delays and reduce rate limits")
            recommendations.append(
                "🌐 Check network connectivity and target site availability"
            )

        # Based on throughput
        if metrics["articles_per_second"] < 2:
            recommendations.append(
                "⚡ Increase concurrent connections if system resources allow"
            )
            recommendations.append("🔄 Consider using more thread pool workers")

        # Based on memory usage
        if metrics["system"]["avg_memory"] > 800:
            recommendations.append(
                "💾 Reduce concurrent connections to lower memory usage"
            )
            recommendations.append(
                "🧹 Implement more aggressive garbage collection")

        # Based on source performance
        source_stats = metrics["sources"]
        problematic_sources = [
            source
            for source, stats in source_stats.items()
            if stats["success_rate"] < 80
        ]

        if problematic_sources:
            recommendations.append(
                f"Review configuration for problematic sources: {', '.join(problematic_sources)}"
            )

        # Based on concurrent connections
        if metrics["counters"]["concurrent_connections"] < 5:
            recommendations.append(
                " Consider increasing concurrent connections for better throughput"
            )

        return recommendations

    def print_live_dashboard(self):
        """Print live dashboard to console."""
        metrics = self.get_current_metrics()

        print("\n" + "=" * 80)
        print(" NEURONEWS ASYNC SCRAPER - LIVE PERFORMANCE DASHBOARD")
        print("=" * 80)

        # Key metrics
        print(f"⏱️  Uptime: {metrics['elapsed_time']:.1f}s")
        print(f"📰 Articles: {metrics['counters']['total_articles']}")
        print(f" Rate: {metrics['articles_per_second']:.2f} articles/sec")
        print(f" Success: {metrics['success_rate']:.1f}%")
        print(f"🔄 Requests: {metrics['counters']['total_requests']}")
        print(f"🌐 Concurrent: {metrics['counters']['concurrent_connections']}")
        print(f"🧵 Threads: {metrics['counters']['active_threads']}")

        # System metrics
        print("\n🖥️  System Resources:")
        print(f"   CPU: {metrics['system']['avg_cpu']:.1f}%")
        print(f"   Memory: {metrics['system']['avg_memory']:.1f} MB")

        # Source breakdown
        print("\n📊 Source Performance:")
        for source, stats in metrics["sources"].items():
            print(
                f"   {source}: {stats['articles']} articles, {stats['success_rate']:.1f}% success"
            )

        print("=" * 80)

    def save_metrics_to_file(self, filepath: str):
        """Save current metrics to JSON file."""
        metrics = self.get_current_metrics()

        with open(filepath, "w") as f:
            json.dump(metrics, f, indent=2)


    def export_metrics_history(self, filepath: str, hours: int = 24):
        """Export metrics history to JSON file."""
        history = self.get_metrics_history(minutes=hours * 60)

        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "period_hours": hours,
            "metrics_count": len(history),
            "metrics_history": history,
        }

        with open(filepath, "w") as f:
            json.dump(export_data, f, indent=2)


# Global dashboard instance
performance_dashboard = PerformanceDashboard()


def get_dashboard() -> PerformanceDashboard:
    """Get the global performance dashboard instance."""
    return performance_dashboard
