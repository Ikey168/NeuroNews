"""
Unit Economics Monitoring for NeuroNews
Issue #337: Unit economics: "€ per 1k articles" & "€ per RAG query"

This module provides Prometheus metrics for tracking business unit economics,
including articles ingested and RAG queries processed. These metrics enable
cost-per-outcome analysis essential for FinOps monitoring.
"""

import logging
import threading
from typing import Optional
from prometheus_client import Counter, start_http_server, CollectorRegistry, REGISTRY

# Configure logging
logger = logging.getLogger(__name__)

# =============================================================================
# Business Counter Metrics
# =============================================================================

# Articles ingested counter
neuro_articles_ingested_total = Counter(
    'neuro_articles_ingested_total',
    'Total number of articles ingested by NeuroNews',
    ['pipeline', 'source', 'status'],
    registry=REGISTRY
)

# RAG queries counter  
neuro_rag_queries_total = Counter(
    'neuro_rag_queries_total', 
    'Total number of RAG queries processed',
    ['endpoint', 'provider', 'status'],
    registry=REGISTRY
)

# Additional business metrics for comprehensive unit economics
neuro_pipeline_operations_total = Counter(
    'neuro_pipeline_operations_total',
    'Total pipeline operations by type',
    ['operation_type', 'pipeline', 'status'],
    registry=REGISTRY
)

# =============================================================================
# Unit Economics Metrics Collection Class
# =============================================================================

class UnitEconomicsCollector:
    """
    Centralized collector for unit economics metrics.
    
    This class provides methods to increment business counters and track
    key performance indicators for cost-per-outcome analysis.
    """
    
    def __init__(self, enable_http_server: bool = True, port: int = 8000):
        """
        Initialize unit economics collector.
        
        Args:
            enable_http_server: Whether to start HTTP metrics server
            port: Port for metrics server
        """
        self.port = port
        self.server_started = False
        self._lock = threading.Lock()
        
        if enable_http_server:
            self.start_metrics_server()
        
        logger.info("Unit economics collector initialized")
    
    def start_metrics_server(self) -> None:
        """Start Prometheus metrics HTTP server."""
        with self._lock:
            if not self.server_started:
                try:
                    start_http_server(self.port)
                    self.server_started = True
                    logger.info(f"Unit economics metrics server started on port {self.port}")
                except Exception as e:
                    logger.error(f"Failed to start metrics server: {e}")
    
    def increment_articles_ingested(
        self, 
        pipeline: str = "ingest",
        source: str = "unknown", 
        status: str = "success",
        count: int = 1
    ) -> None:
        """
        Increment articles ingested counter.
        
        Args:
            pipeline: Processing pipeline (ingest, transform, etc.)
            source: Article source (rss, api, scraper, etc.)
            status: Processing status (success, failed, duplicate)
            count: Number of articles to increment by
        """
        try:
            neuro_articles_ingested_total.labels(
                pipeline=pipeline,
                source=source, 
                status=status
            ).inc(count)
            
            logger.debug(
                f"Incremented articles counter: pipeline={pipeline}, "
                f"source={source}, status={status}, count={count}"
            )
        except Exception as e:
            logger.error(f"Failed to increment articles counter: {e}")
    
    def increment_rag_queries(
        self,
        endpoint: str = "/ask",
        provider: str = "openai",
        status: str = "success", 
        count: int = 1
    ) -> None:
        """
        Increment RAG queries counter.
        
        Args:
            endpoint: API endpoint (/ask, /search, etc.)
            provider: Answer provider (openai, anthropic, etc.)
            status: Query status (success, failed, timeout)
            count: Number of queries to increment by
        """
        try:
            neuro_rag_queries_total.labels(
                endpoint=endpoint,
                provider=provider,
                status=status
            ).inc(count)
            
            logger.debug(
                f"Incremented RAG queries counter: endpoint={endpoint}, "
                f"provider={provider}, status={status}, count={count}"
            )
        except Exception as e:
            logger.error(f"Failed to increment RAG queries counter: {e}")
    
    def increment_pipeline_operation(
        self,
        operation_type: str,
        pipeline: str,
        status: str = "success",
        count: int = 1
    ) -> None:
        """
        Increment pipeline operations counter.
        
        Args:
            operation_type: Type of operation (ingest, transform, index, etc.)
            pipeline: Pipeline name (data, rag, api, etc.)
            status: Operation status (success, failed, retried)
            count: Number of operations to increment by
        """
        try:
            neuro_pipeline_operations_total.labels(
                operation_type=operation_type,
                pipeline=pipeline,
                status=status
            ).inc(count)
            
            logger.debug(
                f"Incremented pipeline operations counter: operation={operation_type}, "
                f"pipeline={pipeline}, status={status}, count={count}"
            )
        except Exception as e:
            logger.error(f"Failed to increment pipeline operations counter: {e}")

# =============================================================================
# Global Collector Instance
# =============================================================================

# Global instance for easy access throughout the application
_unit_economics_collector: Optional[UnitEconomicsCollector] = None
_collector_lock = threading.Lock()

def get_unit_economics_collector(
    enable_http_server: bool = True,
    port: int = 8000
) -> UnitEconomicsCollector:
    """
    Get or create global unit economics collector instance.
    
    Args:
        enable_http_server: Whether to start HTTP metrics server
        port: Port for metrics server
        
    Returns:
        UnitEconomicsCollector instance
    """
    global _unit_economics_collector
    
    with _collector_lock:
        if _unit_economics_collector is None:
            _unit_economics_collector = UnitEconomicsCollector(
                enable_http_server=enable_http_server,
                port=port
            )
        return _unit_economics_collector

# =============================================================================
# Convenience Functions
# =============================================================================

def increment_articles_ingested(
    pipeline: str = "ingest",
    source: str = "unknown",
    status: str = "success", 
    count: int = 1
) -> None:
    """Convenience function to increment articles ingested counter."""
    collector = get_unit_economics_collector()
    collector.increment_articles_ingested(pipeline, source, status, count)

def increment_rag_queries(
    endpoint: str = "/ask",
    provider: str = "openai",
    status: str = "success",
    count: int = 1
) -> None:
    """Convenience function to increment RAG queries counter."""
    collector = get_unit_economics_collector()
    collector.increment_rag_queries(endpoint, provider, status, count)

def increment_pipeline_operation(
    operation_type: str,
    pipeline: str,
    status: str = "success",
    count: int = 1
) -> None:
    """Convenience function to increment pipeline operations counter."""
    collector = get_unit_economics_collector()
    collector.increment_pipeline_operation(operation_type, pipeline, status, count)

# =============================================================================
# Decorator for Automatic Metrics Collection
# =============================================================================

def track_articles_ingested(
    pipeline: str = "ingest",
    source: str = "unknown"
):
    """
    Decorator to automatically track articles ingested.
    
    Usage:
        @track_articles_ingested(pipeline="batch", source="rss")
        def process_articles(articles):
            # Process articles
            return processed_count
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                # If function returns a count, use it; otherwise increment by 1
                count = result if isinstance(result, int) else 1
                increment_articles_ingested(pipeline, source, "success", count)
                return result
            except Exception as e:
                increment_articles_ingested(pipeline, source, "failed", 1)
                raise
        return wrapper
    return decorator

def track_rag_queries(
    endpoint: str = "/ask",
    provider: str = "openai"
):
    """
    Decorator to automatically track RAG queries.
    
    Usage:
        @track_rag_queries(endpoint="/ask", provider="openai")
        def handle_query(question):
            # Process query
            return answer
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                increment_rag_queries(endpoint, provider, "success", 1)
                return result
            except Exception as e:
                increment_rag_queries(endpoint, provider, "failed", 1) 
                raise
        return wrapper
    return decorator
