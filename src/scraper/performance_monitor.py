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

        # Monitoring state
        self.monitoring = False
        self.monitor_thread = None

        self.logger = logging.getLogger(__name__)

    def start_monitoring(self):
        """Start performance monitoring."""
        if self.monitoring:
            return

        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        self.logger.info("📊 Performance monitoring started")

    def stop_monitoring(self):
        """Stop performance monitoring."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)

        self.logger.info("📊 Performance monitoring stopped")

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
            process = psutil.Process()

            # CPU and memory
            cpu_percent = process.cpu_percent()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # Network I/O
            net_io = psutil.net_io_counters()

            # Disk I/O
            disk_io = psutil.disk_io_counters()

            # Update metrics
            self.system_metrics["cpu_usage"].append(cpu_percent)
            self.system_metrics["memory_usage"].append(memory_mb)

            if net_io:
                self.system_metrics["network_io"].append(
                    {"bytes_sent": net_io.bytes_sent, "bytes_recv": net_io.bytes_recv}
                )

            if disk_io:
                self.system_metrics["disk_io"].append(
                    {
                        "read_bytes": disk_io.read_bytes,
                        "write_bytes": disk_io.write_bytes,
                    }
                )

        except Exception as e:
            self.logger.debug("System metrics collection error: {0}".format(e))

    def _update_metrics_history(self):
        """Update metrics history."""
        current_time = time.time()
        elapsed_time = current_time - self.start_time

        # Calculate rates
        articles_per_second = self.counters["total_articles"] / max(elapsed_time, 1)
        requests_per_second = self.counters["total_requests"] / max(elapsed_time, 1)
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
        self.source_metrics[source]["last_updated"] = datetime.now().isoformat()

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
            self.counters["successful_requests"] + self.counters["failed_requests"]
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
            trend_data["memory_usage_trend"].append(metrics["system"]["memory_mb"])

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
                "🚀 Excellent throughput: Scraper is performing at high speed"
            )
        elif metrics["articles_per_second"] > 2:
            insights.append("⚡ Good throughput: Scraper is performing well")
        else:
            insights.append(
                "🐌 Low throughput: Consider optimizing concurrent connections"
            )

        # Success rate analysis
        if metrics["success_rate"] > 95:
            insights.append("✅ Excellent success rate: Very reliable scraping")
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
            insights.append("📊 Moderate memory usage: Monitor for memory leaks")
        else:
            insights.append("💚 Low memory usage: Efficient resource utilization")

        # CPU usage analysis
        avg_cpu = metrics["system"]["avg_cpu"]
        if avg_cpu > 80:
            insights.append("🔥 High CPU usage: Consider reducing thread pool size")
        elif avg_cpu > 50:
            insights.append("📊 Moderate CPU usage: Good resource utilization")
        else:
            insights.append("💚 Low CPU usage: Room for more concurrent processing")

        # Trend analysis
        if len(trends["articles_per_second_trend"]) > 5:
            recent_avg = sum(trends["articles_per_second_trend"][-5:]) / 5
            earlier_avg = sum(trends["articles_per_second_trend"][:5]) / 5

            if recent_avg > earlier_avg * 1.1:
                insights.append("📈 Performance improving: Throughput trending upward")
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
            recommendations.append("🔧 Increase retry delays and reduce rate limits")
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
            recommendations.append("🧹 Implement more aggressive garbage collection")

        # Based on source performance
        source_stats = metrics["sources"]
        problematic_sources = [
            source
            for source, stats in source_stats.items()
            if stats["success_rate"] < 80
        ]

        if problematic_sources:
            recommendations.append(
                f"🎯 Review configuration for problematic sources: {
                    ', '.join(problematic_sources)}"
            )

        # Based on concurrent connections
        if metrics["counters"]["concurrent_connections"] < 5:
            recommendations.append(
                "🚀 Consider increasing concurrent connections for better throughput"
            )

        return recommendations

    def print_live_dashboard(self):
        """Print live dashboard to console."""
        metrics = self.get_current_metrics()

        print("\n" + "=" * 80)
        print("📊 NEURONEWS ASYNC SCRAPER - LIVE PERFORMANCE DASHBOARD")
        print("=" * 80)

        # Key metrics
        print(f"⏱️  Uptime: {metrics['elapsed_time']:.1f}s")
        print(f"📰 Articles: {metrics['counters']['total_articles']}")
        print(f"📈 Rate: {metrics['articles_per_second']:.2f} articles/sec")
        print(f"✅ Success: {metrics['success_rate']:.1f}%")
        print(f"🔄 Requests: {metrics['counters']['total_requests']}")
        print(f"🌐 Concurrent: {metrics['counters']['concurrent_connections']}")
        print(f"🧵 Threads: {metrics['counters']['active_threads']}")

        # System metrics
        print("\n🖥️  System Resources:")
        print(f"   CPU: {metrics['system']['avg_cpu']:.1f}%")
        print(f"   Memory: {metrics['system']['avg_memory']:.1f} MB")

        # Source breakdown
        print("\n📋 Source Performance:")
        for source, stats in metrics["sources"].items():
            print(
                f"   {source}: {
                    stats['articles']} articles, {
                    stats['success_rate']:.1f}% success"
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
