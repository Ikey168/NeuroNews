"""
Performance monitoring and optimization for web scraping.
"""

import time
import logging
import asyncio
from typing import Dict, List, Optional, Any
from functools import wraps
import boto3
from datetime import datetime
import threading
import psutil
import resource

logger = logging.getLogger(__name__)

class ScraperMetrics:
    """Track and report scraper performance metrics."""
    
    def __init__(self, namespace: str = "Production/Scraper"):
        """
        Initialize metrics tracking.
        
        Args:
            namespace: CloudWatch namespace
        """
        self.namespace = namespace
        self.cloudwatch = boto3.client('cloudwatch')
        self.metrics: Dict[str, List[float]] = {
            'RequestLatency': [],
            'ParsingTime': [],
            'ProcessingTime': [],
            'MemoryUsage': [],
            'CPUUsage': [],
        }
        self.start_time = time.time()
        
        # Start background monitoring
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_resources)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def _monitor_resources(self):
        """Background thread to monitor system resources."""
        while self.monitoring:
            # Memory usage
            memory_percent = psutil.Process().memory_percent()
            self.metrics['MemoryUsage'].append(memory_percent)
            
            # CPU usage
            cpu_percent = psutil.Process().cpu_percent()
            self.metrics['CPUUsage'].append(cpu_percent)
            
            time.sleep(5)  # Sample every 5 seconds

    def record_metric(self, name: str, value: float):
        """
        Record a metric value.
        
        Args:
            name: Metric name
            value: Metric value
        """
        if name in self.metrics:
            self.metrics[name].append(value)

    def publish_metrics(self):
        """Publish metrics to CloudWatch."""
        try:
            metric_data = []
            
            for metric_name, values in self.metrics.items():
                if values:
                    metric_data.append({
                        'MetricName': metric_name,
                        'Value': sum(values) / len(values),  # Average
                        'Unit': 'Milliseconds' if 'Time' in metric_name else 'Percent',
                        'Dimensions': [
                            {'Name': 'Environment', 'Value': 'Production'}
                        ]
                    })
                    
                    if metric_name in ['RequestLatency', 'ProcessingTime']:
                        # Also publish p90 and p99 for latency metrics
                        values.sort()
                        p90_idx = int(len(values) * 0.9)
                        p99_idx = int(len(values) * 0.99)
                        
                        metric_data.extend([
                            {
                                'MetricName': f"{metric_name}P90",
                                'Value': values[p90_idx],
                                'Unit': 'Milliseconds',
                                'Dimensions': [
                                    {'Name': 'Environment', 'Value': 'Production'}
                                ]
                            },
                            {
                                'MetricName': f"{metric_name}P99",
                                'Value': values[p99_idx],
                                'Unit': 'Milliseconds',
                                'Dimensions': [
                                    {'Name': 'Environment', 'Value': 'Production'}
                                ]
                            }
                        ])
            
            if metric_data:
                self.cloudwatch.put_metric_data(
                    Namespace=self.namespace,
                    MetricData=metric_data
                )
                
        except Exception as e:
            logger.error(f"Failed to publish metrics: {e}")

    def stop(self):
        """Stop monitoring and publish final metrics."""
        self.monitoring = False
        self.monitor_thread.join()
        self.publish_metrics()

def measure_time(metric_name: str):
    """
    Decorator to measure execution time of a function.
    
    Args:
        metric_name: Name of the metric to record
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            metrics = getattr(args[0], 'metrics', None)
            if not metrics:
                return await func(*args, **kwargs)
                
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start) * 1000  # Convert to ms
                metrics.record_metric(metric_name, duration)
                return result
            except Exception:
                duration = (time.time() - start) * 1000
                metrics.record_metric(f"{metric_name}Error", duration)
                raise
                
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            metrics = getattr(args[0], 'metrics', None)
            if not metrics:
                return func(*args, **kwargs)
                
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start) * 1000
                metrics.record_metric(metric_name, duration)
                return result
            except Exception:
                duration = (time.time() - start) * 1000
                metrics.record_metric(f"{metric_name}Error", duration)
                raise
                
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

def optimize_memory():
    """Optimize memory usage for scraping."""
    # Set memory limits
    max_memory = 1024 * 1024 * 1024  # 1GB
    resource.setrlimit(resource.RLIMIT_AS, (max_memory, max_memory))
    
    # Garbage collection settings
    import gc
    gc.enable()
    gc.set_threshold(700, 10, 5)

def optimize_network():
    """Optimize network settings for scraping."""
    import socket
    import platform
    
    # Increase socket timeouts
    socket.setdefaulttimeout(30)
    
    if platform.system() == 'Linux':
        # Set TCP keepalive
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 60)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 10)
        sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 5)

class PerformanceOptimizer:
    """Apply performance optimizations to scraper."""
    
    def __init__(self):
        """Initialize optimizer."""
        self.metrics = ScraperMetrics()
        optimize_memory()
        optimize_network()
        
    async def __aenter__(self):
        """Enter context with optimizations."""
        return self.metrics
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up and publish metrics."""
        self.metrics.stop()