"""
Prometheus Metrics for RAG Observability
Issue #236: Observability: Prometheus counters + logs

This module provides Prometheus metrics collection for the RAG system,
including counters, histograms, and labels for comprehensive monitoring.
"""

import time
import logging
from typing import Optional, Dict, Any
from prometheus_client import Counter, Histogram, Info, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.registry import REGISTRY
from functools import wraps
import threading

# Configure logging
logger = logging.getLogger(__name__)

# =============================================================================
# Prometheus Metrics Definitions
# =============================================================================

# Counters - Track cumulative values
queries_total = Counter(
    'rag_queries_total',
    'Total number of RAG queries processed',
    ['provider', 'lang', 'has_rerank', 'status']
)

answers_total = Counter(
    'rag_answers_total', 
    'Total number of RAG answers generated',
    ['provider', 'lang', 'has_rerank']
)

errors_total = Counter(
    'rag_errors_total',
    'Total number of RAG processing errors',
    ['provider', 'error_type', 'component']
)

# Histograms - Track distributions of values
retrieval_latency_ms = Histogram(
    'rag_retrieval_latency_milliseconds',
    'Time spent on document retrieval in milliseconds',
    ['provider', 'k_used'],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
)

answer_latency_ms = Histogram(
    'rag_answer_latency_milliseconds',
    'Time spent on answer generation in milliseconds',
    ['provider', 'lang'],
    buckets=[100, 250, 500, 1000, 2000, 5000, 10000, 20000, 30000, 60000]
)

k_used = Histogram(
    'rag_k_documents_used',
    'Number of documents used for answer generation',
    ['provider', 'query_type'],
    buckets=[1, 3, 5, 10, 15, 20, 25, 30, 50, 100]
)

# Info metrics - Static information
rag_info = Info(
    'rag_system_info',
    'Information about the RAG system'
)

# =============================================================================
# Metrics Collection Class
# =============================================================================

class RAGMetricsCollector:
    """
    Centralized metrics collection for RAG system operations.
    
    This class provides methods to record metrics for different RAG operations
    with appropriate labels and timing information.
    """
    
    def __init__(self):
        """Initialize the metrics collector."""
        self._local = threading.local()
        logger.info("RAG Metrics Collector initialized")
        
        # Set system info
        rag_info.info({
            'version': '1.0.0',
            'component': 'rag_system',
            'tracking': 'prometheus'
        })
    
    def record_query(self, provider: str, lang: str = "en", has_rerank: bool = False, status: str = "success"):
        """
        Record a RAG query.
        
        Args:
            provider: Answer provider (openai, anthropic, local, etc.)
            lang: Language code (en, es, fr, etc.)
            has_rerank: Whether reranking was used
            status: Query status (success, error, timeout)
        """
        queries_total.labels(
            provider=provider,
            lang=lang,
            has_rerank=str(has_rerank).lower(),
            status=status
        ).inc()
        
        logger.debug(f"Recorded query: provider={provider}, lang={lang}, rerank={has_rerank}, status={status}")
    
    def record_answer(self, provider: str, lang: str = "en", has_rerank: bool = False):
        """
        Record a successful answer generation.
        
        Args:
            provider: Answer provider used
            lang: Language code
            has_rerank: Whether reranking was used
        """
        answers_total.labels(
            provider=provider,
            lang=lang,
            has_rerank=str(has_rerank).lower()
        ).inc()
        
        logger.debug(f"Recorded answer: provider={provider}, lang={lang}, rerank={has_rerank}")
    
    def record_error(self, provider: str, error_type: str, component: str):
        """
        Record an error in RAG processing.
        
        Args:
            provider: Provider where error occurred
            error_type: Type of error (retrieval_error, llm_error, timeout, etc.)
            component: Component where error occurred (retrieval, rerank, answer, etc.)
        """
        errors_total.labels(
            provider=provider,
            error_type=error_type,
            component=component
        ).inc()
        
        logger.debug(f"Recorded error: provider={provider}, type={error_type}, component={component}")
    
    def record_retrieval_latency(self, latency_ms: float, provider: str, k_used: int):
        """
        Record document retrieval latency.
        
        Args:
            latency_ms: Retrieval time in milliseconds
            provider: Provider used for retrieval
            k_used: Number of documents retrieved
        """
        retrieval_latency_ms.labels(
            provider=provider,
            k_used=str(k_used)
        ).observe(latency_ms)
        
        logger.debug(f"Recorded retrieval latency: {latency_ms}ms, provider={provider}, k={k_used}")
    
    def record_answer_latency(self, latency_ms: float, provider: str, lang: str = "en"):
        """
        Record answer generation latency.
        
        Args:
            latency_ms: Answer generation time in milliseconds
            provider: LLM provider used
            lang: Language code
        """
        answer_latency_ms.labels(
            provider=provider,
            lang=lang
        ).observe(latency_ms)
        
        logger.debug(f"Recorded answer latency: {latency_ms}ms, provider={provider}, lang={lang}")
    
    def record_k_documents(self, k: int, provider: str, query_type: str = "general"):
        """
        Record number of documents used for answer generation.
        
        Args:
            k: Number of documents used
            provider: Provider used
            query_type: Type of query (general, factual, complex, etc.)
        """
        k_used.labels(
            provider=provider,
            query_type=query_type
        ).observe(k)
        
        logger.debug(f"Recorded k documents: {k}, provider={provider}, type={query_type}")

# =============================================================================
# Decorators for Automatic Metrics Collection
# =============================================================================

def track_rag_operation(operation: str, provider: str = "unknown"):
    """
    Decorator to automatically track RAG operations with timing.
    
    Args:
        operation: Operation name (retrieval, answer, rerank)
        provider: Provider name
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # Calculate latency
                latency_ms = (time.time() - start_time) * 1000
                
                # Record based on operation type
                if operation == "retrieval":
                    # Extract k from result or kwargs
                    k = len(result) if hasattr(result, '__len__') else kwargs.get('k', 10)
                    metrics_collector.record_retrieval_latency(latency_ms, provider, k)
                elif operation == "answer":
                    lang = kwargs.get('lang', 'en')
                    metrics_collector.record_answer_latency(latency_ms, provider, lang)
                
                return result
                
            except Exception as e:
                # Record error
                error_type = type(e).__name__.lower()
                metrics_collector.record_error(provider, error_type, operation)
                raise
        
        return wrapper
    return decorator

def track_query_metrics(provider: str, lang: str = "en", has_rerank: bool = False):
    """
    Decorator to track full query metrics.
    
    Args:
        provider: Answer provider
        lang: Language code
        has_rerank: Whether reranking is used
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                
                # Record successful query and answer
                metrics_collector.record_query(provider, lang, has_rerank, "success")
                metrics_collector.record_answer(provider, lang, has_rerank)
                
                return result
                
            except Exception as e:
                # Record failed query
                metrics_collector.record_query(provider, lang, has_rerank, "error")
                error_type = type(e).__name__.lower()
                metrics_collector.record_error(provider, error_type, "query")
                raise
        
        return wrapper
    return decorator

# =============================================================================
# Global Metrics Collector Instance
# =============================================================================

# Global instance for use throughout the application
metrics_collector = RAGMetricsCollector()

# =============================================================================
# Metrics Export Functions
# =============================================================================

def get_metrics() -> str:
    """
    Get all metrics in Prometheus format.
    
    Returns:
        str: Metrics in Prometheus exposition format
    """
    return generate_latest(REGISTRY)

def get_metrics_content_type() -> str:
    """
    Get the content type for Prometheus metrics.
    
    Returns:
        str: Content type string
    """
    return CONTENT_TYPE_LATEST

# =============================================================================
# Utility Functions
# =============================================================================

def reset_metrics():
    """Reset all metrics (useful for testing)."""
    logger.warning("Resetting all metrics - this should only be used for testing")
    
    # Clear counters and histograms
    queries_total.clear()
    answers_total.clear()
    errors_total.clear()
    retrieval_latency_ms.clear()
    answer_latency_ms.clear()
    k_used.clear()

def get_metrics_summary() -> Dict[str, Any]:
    """
    Get a summary of current metrics for debugging.
    
    Returns:
        Dict containing metrics summary
    """
    return {
        "queries_total": queries_total._value._value,
        "answers_total": answers_total._value._value,
        "errors_total": errors_total._value._value,
        "collectors": [
            "retrieval_latency_ms",
            "answer_latency_ms", 
            "k_used"
        ]
    }

# =============================================================================
# Demo and Testing Functions
# =============================================================================

def demo_metrics():
    """Demonstrate metrics collection with sample data."""
    logger.info("Starting RAG metrics demo")
    
    # Simulate some queries
    providers = ["openai", "anthropic", "local"]
    languages = ["en", "es", "fr"]
    
    for i in range(10):
        provider = providers[i % len(providers)]
        lang = languages[i % len(languages)]
        has_rerank = i % 3 == 0
        
        # Record query
        metrics_collector.record_query(provider, lang, has_rerank)
        
        # Record retrieval latency
        metrics_collector.record_retrieval_latency(
            latency_ms=50 + (i * 10),
            provider=provider,
            k_used=10 + (i % 5)
        )
        
        # Record answer latency
        metrics_collector.record_answer_latency(
            latency_ms=1000 + (i * 100),
            provider=provider,
            lang=lang
        )
        
        # Record successful answer
        metrics_collector.record_answer(provider, lang, has_rerank)
        
        # Record some errors occasionally
        if i % 4 == 0:
            metrics_collector.record_error(provider, "timeout", "retrieval")
    
    logger.info("RAG metrics demo completed")
    return get_metrics_summary()

if __name__ == "__main__":
    # Demo the metrics system
    print("RAG Metrics System Demo")
    print("=" * 50)
    
    demo_metrics()
    summary = get_metrics_summary()
    print(f"Metrics Summary: {summary}")
    
    print("\\nPrometheus Metrics Output:")
    print(get_metrics().decode('utf-8'))
