#!/usr/bin/env python3
"""
Demo script for contract observability and alerting - Issue #371

This script demonstrates the contract metrics collection, Prometheus integration,
and alerting capabilities for data contract validation failures and breaking changes.
"""

import time
import logging
import random
from typing import Dict, Any
import json
import sys
import os

# Add the project root to the path
sys.path.insert(0, '/workspaces/NeuroNews')

from services.ingest.metrics import (
    contract_metrics,
    ContractMetricsCollector,
    track_contract_validation
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def simulate_validation_success():
    """Simulate successful contract validations."""
    pipelines = ['article-ingest', 'sentiment-processing', 'nlp-pipeline']
    sources = ['reuters', 'bbc', 'cnn', 'ap', 'bloomberg']
    schemas = ['article-ingest-v1', 'sentiment-analysis-v2', 'nlp-entities-v1']
    
    pipeline = random.choice(pipelines)
    source = random.choice(sources)
    schema = random.choice(schemas)
    
    logger.info(f"✅ Successful validation: {pipeline}/{source}/{schema}")
    contract_metrics.record_validation_success(pipeline, source, schema)
    
    # Record latency (successful validations are typically faster)
    latency = random.uniform(5, 50)  # 5-50ms
    contract_metrics.record_validation_latency(latency, pipeline, source, schema)

def simulate_validation_failure():
    """Simulate contract validation failures."""
    pipelines = ['article-ingest', 'sentiment-processing', 'nlp-pipeline']
    sources = ['reuters', 'bbc', 'cnn', 'ap', 'bloomberg']
    schemas = ['article-ingest-v1', 'sentiment-analysis-v2', 'nlp-entities-v1']
    error_types = [
        'required_field_missing',
        'type_mismatch',
        'invalid_enum_value',
        'field_length_exceeded',
        'invalid_format',
        'constraint_violation'
    ]
    
    pipeline = random.choice(pipelines)
    source = random.choice(sources)
    schema = random.choice(schemas)
    error_type = random.choice(error_types)
    
    logger.warning(f"❌ Validation failure: {pipeline}/{source}/{schema} - {error_type}")
    contract_metrics.record_validation_failure(pipeline, source, schema, error_type)
    
    # Record latency (failures might take longer due to validation logic)
    latency = random.uniform(10, 100)  # 10-100ms
    contract_metrics.record_validation_latency(latency, pipeline, source, schema)
    
    # Sometimes send to DLQ
    if random.random() < 0.3:  # 30% chance
        reason = random.choice(['validation_failed', 'deserialization_error', 'retry_exhausted'])
        contract_metrics.record_dlq_message(pipeline, source, schema, reason)
        logger.warning(f"📨 Message sent to DLQ: {reason}")

def simulate_breaking_change():
    """Simulate breaking change detection."""
    pipelines = ['article-ingest', 'sentiment-processing', 'nlp-pipeline']
    schemas = ['article-ingest-v1', 'sentiment-analysis-v2', 'nlp-entities-v1']
    change_types = [
        'field_removed',
        'type_changed',
        'enum_value_removed',
        'required_field_added',
        'constraint_tightened'
    ]
    detection_sources = ['ci', 'compatibility_check', 'runtime']
    
    pipeline = random.choice(pipelines)
    schema = random.choice(schemas)
    change_type = random.choice(change_types)
    detection_source = random.choice(detection_sources)
    
    logger.error(f"🚨 Breaking change detected: {pipeline}/{schema} - {change_type} ({detection_source})")
    contract_metrics.record_breaking_change(pipeline, schema, change_type, detection_source)

def simulate_compatibility_check():
    """Simulate schema compatibility checks."""
    schemas = ['article-ingest-v1', 'sentiment-analysis-v2', 'nlp-entities-v1']
    versions = ['v1', 'v2', 'v3']
    results = ['compatible', 'breaking', 'error']
    
    schema = random.choice(schemas)
    version_from = random.choice(versions)
    version_to = random.choice([v for v in versions if v != version_from])
    result = random.choice(results)
    
    logger.info(f"🔍 Compatibility check: {schema} {version_from}->{version_to} = {result}")
    contract_metrics.record_compatibility_check(schema, version_from, version_to, result)

@track_contract_validation("article-ingest", "reuters", "article-ingest-v1")
def validate_article_with_decorator(data: Dict[str, Any]):
    """Example function using the validation decorator."""
    # Simulate validation logic
    time.sleep(random.uniform(0.01, 0.05))  # 10-50ms
    
    if random.random() < 0.1:  # 10% failure rate
        raise ValueError("Validation failed")
    
    return {"status": "valid", "data": data}

def demonstrate_high_failure_rate():
    """Simulate conditions that would trigger alerts."""
    logger.info("🚨 Demonstrating HIGH FAILURE RATE scenario...")
    
    # Generate many failures to trigger >1% failure rate alert
    for i in range(20):
        simulate_validation_failure()
        time.sleep(0.1)
    
    # Generate some successes to provide baseline
    for i in range(5):
        simulate_validation_success()
        time.sleep(0.1)
    
    logger.warning("High failure rate simulation complete - should trigger alerts")

def demonstrate_breaking_changes():
    """Simulate breaking changes that would trigger immediate alerts."""
    logger.info("🚨 Demonstrating BREAKING CHANGES scenario...")
    
    # Simulate breaking changes from different sources
    scenarios = [
        ("article-ingest", "article-ingest-v2", "field_removed", "ci"),
        ("sentiment-processing", "sentiment-analysis-v3", "type_changed", "runtime"),
        ("nlp-pipeline", "nlp-entities-v2", "enum_value_removed", "compatibility_check")
    ]
    
    for pipeline, schema, change_type, source in scenarios:
        contract_metrics.record_breaking_change(pipeline, schema, change_type, source)
        logger.error(f"Breaking change: {schema} - {change_type} detected in {source}")
        time.sleep(1)
    
    logger.warning("Breaking changes simulation complete - should trigger critical alerts")

def run_normal_operations(duration_seconds: int = 60):
    """Run normal operations simulation."""
    logger.info(f"🔄 Running normal operations for {duration_seconds} seconds...")
    
    start_time = time.time()
    while time.time() - start_time < duration_seconds:
        # 90% success rate under normal conditions
        if random.random() < 0.9:
            simulate_validation_success()
        else:
            simulate_validation_failure()
        
        # Occasional compatibility checks
        if random.random() < 0.1:
            simulate_compatibility_check()
        
        # Very rare breaking changes under normal conditions
        if random.random() < 0.01:
            simulate_breaking_change()
        
        time.sleep(random.uniform(0.5, 2.0))
    
    logger.info("Normal operations simulation complete")

def test_decorator_functionality():
    """Test the validation decorator."""
    logger.info("🧪 Testing validation decorator...")
    
    test_data = {
        "article_id": "test-123",
        "title": "Test Article",
        "body": "This is a test article",
        "source": "test-source"
    }
    
    # Test successful validation
    try:
        result = validate_article_with_decorator(test_data)
        logger.info(f"✅ Decorator test success: {result}")
    except Exception as e:
        logger.error(f"❌ Decorator test failure: {e}")
    
    # Generate multiple tests to get some failures
    for i in range(10):
        try:
            validate_article_with_decorator({"test_id": i})
        except Exception:
            pass  # Expected failures
        time.sleep(0.1)

def display_prometheus_metrics():
    """Display current Prometheus metrics."""
    logger.info("📊 Current metrics summary:")
    
    try:
        from services.ingest.metrics import get_contract_metrics
        metrics_text = get_contract_metrics()
        
        # Parse and display key metrics
        lines = metrics_text.decode('utf-8').split('\n')
        for line in lines:
            if line.startswith('contracts_validation_') or line.startswith('contracts_breaking_change_'):
                if not line.startswith('#'):
                    logger.info(f"  {line}")
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")

def main():
    """Main demo function."""
    print("=" * 60)
    print("🔍 DATA CONTRACT OBSERVABILITY & ALERTING DEMO")
    print("Issue #371: Contract observability & alerting")
    print("=" * 60)
    
    try:
        # Test 1: Normal operations
        print("\n1. Normal Operations (30 seconds)")
        run_normal_operations(30)
        
        # Test 2: Decorator functionality
        print("\n2. Testing Validation Decorator")
        test_decorator_functionality()
        
        # Test 3: High failure rate scenario
        print("\n3. High Failure Rate Scenario")
        demonstrate_high_failure_rate()
        
        # Test 4: Breaking changes scenario
        print("\n4. Breaking Changes Scenario")
        demonstrate_breaking_changes()
        
        # Display current metrics
        print("\n5. Current Metrics State")
        display_prometheus_metrics()
        
        print("\n" + "=" * 60)
        print("✅ Demo completed successfully!")
        print("\nKey capabilities demonstrated:")
        print("  ✓ Contract validation metrics collection")
        print("  ✓ Breaking change detection and alerting") 
        print("  ✓ Failure rate monitoring")
        print("  ✓ DLQ message tracking")
        print("  ✓ Validation latency measurement")
        print("  ✓ Schema compatibility checks")
        print("  ✓ Prometheus metrics export")
        print("\nAlert conditions tested:")
        print("  ⚠️  Validation failure rate >1% over 15m")
        print("  🚨 Any breaking change detected")
        print("  📨 High DLQ message rate")
        print("\nNext steps:")
        print("  1. Deploy Prometheus rules to cluster")
        print("  2. Configure Alertmanager with Slack/email")
        print("  3. Import Grafana dashboard")
        print("  4. Set up monitoring for production pipelines")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
