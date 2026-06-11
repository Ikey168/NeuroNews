"""
Prometheus Metrics for Data Contract Observability
Issue #371: Contract observability & alerting

This module provides Prometheus metrics collection for data contract validation,
including counters for failures, breaking changes, and success rates.
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

# Contract validation counters
contracts_validation_fail_total = Counter(
    'contracts_validation_fail_total',
    'Total number of contract validation failures',
    ['pipeline', 'source_id', 'schema_name', 'error_type']
)

contracts_validation_success_total = Counter(
    'contracts_validation_success_total',
    'Total number of successful contract validations',
    ['pipeline', 'source_id', 'schema_name']
)

contracts_breaking_change_total = Counter(
    'contracts_breaking_change_total',
    'Total number of breaking changes detected',
    ['pipeline', 'schema_name', 'change_type', 'detection_source']
)

# Contract validation latency
contracts_validation_latency_ms = Histogram(
    'contracts_validation_latency_milliseconds',
    'Time spent on contract validation in milliseconds',
    ['pipeline', 'source_id', 'schema_name'],
    buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
)

# DLQ (Dead Letter Queue) metrics
contracts_dlq_total = Counter(
    'contracts_dlq_total',
    'Total number of messages sent to dead letter queue due to validation failures',
    ['pipeline', 'source_id', 'schema_name', 'reason']
)

# Schema compatibility metrics
contracts_compatibility_check_total = Counter(
    'contracts_compatibility_check_total',
    'Total number of schema compatibility checks performed',
    ['schema_name', 'version_from', 'version_to', 'result']
)

# Info metrics - Static information
contracts_info = Info(
    'contracts_system_info',
    'Information about the data contracts system'
)

# =============================================================================
# Metrics Collection Class
# =============================================================================

class ContractMetricsCollector:
    """
    Centralized metrics collection for data contract operations.
    
    This class provides methods to record metrics for contract validation,
    breaking change detection, and schema compatibility checks.
    """
    
    def __init__(self):
        """Initialize the contract metrics collector."""
        self._local = threading.local()
        logger.info("Contract Metrics Collector initialized")
        
        # Set system info
        contracts_info.info({
            'version': '1.0.0',
            'component': 'data_contracts',
            'tracking': 'prometheus'
        })
    
    def record_validation_failure(self, pipeline: str, source_id: str, schema_name: str, error_type: str):
        """
        Record a contract validation failure.
        
        Args:
            pipeline: Data pipeline name (e.g., 'article-ingest', 'sentiment-processing')
            source_id: Source identifier (e.g., 'reuters', 'bbc')
            schema_name: Schema name (e.g., 'article-ingest-v1')
            error_type: Type of validation error (e.g., 'required_field_missing', 'type_mismatch')
        """
        contracts_validation_fail_total.labels(
            pipeline=pipeline,
            source_id=source_id,
            schema_name=schema_name,
            error_type=error_type
        ).inc()
        
        logger.warning(f"Contract validation failure: pipeline={pipeline}, source={source_id}, "
                      f"schema={schema_name}, error={error_type}")
    
    def record_validation_success(self, pipeline: str, source_id: str, schema_name: str):
        """
        Record a successful contract validation.
        
        Args:
            pipeline: Data pipeline name
            source_id: Source identifier
            schema_name: Schema name
        """
        contracts_validation_success_total.labels(
            pipeline=pipeline,
            source_id=source_id,
            schema_name=schema_name
        ).inc()
        
        logger.debug(f"Contract validation success: pipeline={pipeline}, source={source_id}, "
                    f"schema={schema_name}")
    
    def record_breaking_change(self, pipeline: str, schema_name: str, change_type: str, detection_source: str):
        """
        Record detection of a breaking change.
        
        Args:
            pipeline: Data pipeline name
            schema_name: Schema name where breaking change was detected
            change_type: Type of breaking change (e.g., 'field_removed', 'type_changed', 'enum_value_removed')
            detection_source: Where the change was detected (e.g., 'ci', 'compatibility_check', 'runtime')
        """
        contracts_breaking_change_total.labels(
            pipeline=pipeline,
            schema_name=schema_name,
            change_type=change_type,
            detection_source=detection_source
        ).inc()
        
        logger.error(f"Breaking change detected: pipeline={pipeline}, schema={schema_name}, "
                    f"type={change_type}, source={detection_source}")
    
    def record_validation_latency(self, latency_ms: float, pipeline: str, source_id: str, schema_name: str):
        """
        Record contract validation latency.
        
        Args:
            latency_ms: Validation time in milliseconds
            pipeline: Data pipeline name
            source_id: Source identifier
            schema_name: Schema name
        """
        contracts_validation_latency_ms.labels(
            pipeline=pipeline,
            source_id=source_id,
            schema_name=schema_name
        ).observe(latency_ms)
        
        logger.debug(f"Contract validation latency: {latency_ms}ms, pipeline={pipeline}, "
                    f"source={source_id}, schema={schema_name}")
    
    def record_dlq_message(self, pipeline: str, source_id: str, schema_name: str, reason: str):
        """
        Record a message sent to dead letter queue.
        
        Args:
            pipeline: Data pipeline name
            source_id: Source identifier
            schema_name: Schema name
            reason: Reason for DLQ (e.g., 'validation_failed', 'deserialization_error')
        """
        contracts_dlq_total.labels(
            pipeline=pipeline,
            source_id=source_id,
            schema_name=schema_name,
            reason=reason
        ).inc()
        
        logger.warning(f"Message sent to DLQ: pipeline={pipeline}, source={source_id}, "
                      f"schema={schema_name}, reason={reason}")
    
    def record_compatibility_check(self, schema_name: str, version_from: str, version_to: str, result: str):
        """
        Record a schema compatibility check.
        
        Args:
            schema_name: Schema name
            version_from: Source version
            version_to: Target version
            result: Check result ('compatible', 'breaking', 'error')
        """
        contracts_compatibility_check_total.labels(
            schema_name=schema_name,
            version_from=version_from,
            version_to=version_to,
            result=result
        ).inc()
        
        logger.info(f"Compatibility check: schema={schema_name}, {version_from}->{version_to}, "
                   f"result={result}")
    
    def get_failure_rate(self, pipeline: str, time_window_minutes: int = 15) -> float:
        """
        Calculate validation failure rate for a pipeline over time window.
        
        Args:
            pipeline: Data pipeline name
            time_window_minutes: Time window in minutes
            
        Returns:
            Failure rate as percentage (0.0 to 100.0)
        """
        # This would typically query Prometheus directly in a real implementation
        # For now, we'll return a placeholder that can be used in tests
        logger.debug(f"Calculating failure rate for pipeline={pipeline}, window={time_window_minutes}m")
        return 0.0
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get a summary of current metrics state.
        
        Returns:
            Dictionary with current metric values
        """
        # In a real implementation, this would query the current metric values
        # For demonstration purposes, we'll return a structure
        return {
            "validation_failures": "See Prometheus for current values",
            "validation_successes": "See Prometheus for current values", 
            "breaking_changes": "See Prometheus for current values",
            "dlq_messages": "See Prometheus for current values",
            "compatibility_checks": "See Prometheus for current values"
        }

# =============================================================================
# Decorators for Automatic Metrics Collection
# =============================================================================

def track_contract_validation(pipeline: str, source_id: str, schema_name: str):
    """
    Decorator to automatically track contract validation metrics.
    
    Args:
        pipeline: Data pipeline name
        source_id: Source identifier
        schema_name: Schema name
        
    Usage:
        @track_contract_validation("article-ingest", "reuters", "article-ingest-v1")
        def validate_article(data):
            # validation logic
            pass
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                
                # Record success
                contract_metrics.record_validation_success(pipeline, source_id, schema_name)
                
                # Record latency
                latency_ms = (time.time() - start_time) * 1000
                contract_metrics.record_validation_latency(latency_ms, pipeline, source_id, schema_name)
                
                return result
                
            except Exception as e:
                # Record failure
                error_type = type(e).__name__
                contract_metrics.record_validation_failure(pipeline, source_id, schema_name, error_type)
                
                # Record latency even for failures
                latency_ms = (time.time() - start_time) * 1000
                contract_metrics.record_validation_latency(latency_ms, pipeline, source_id, schema_name)
                
                raise
                
        return wrapper
    return decorator

# =============================================================================
# Global Instance
# =============================================================================

# Global metrics collector instance
contract_metrics = ContractMetricsCollector()

# =============================================================================
# Metrics Export Functions
# =============================================================================

def get_contract_metrics():
    """
    Get Prometheus metrics in text format.
    
    Returns:
        Prometheus metrics as text
    """
    return generate_latest(REGISTRY)

def get_content_type():
    """
    Get the content type for Prometheus metrics.
    
    Returns:
        Content type string
    """
    return CONTENT_TYPE_LATEST
