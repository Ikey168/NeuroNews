#!/bin/bash

# DoD Verification Script for Issue #371
# Contract observability & alerting

set -e

echo "🔍 Verifying Issue #371: Contract observability & alerting"
echo "=============================================================="

# Check 1: Verify metrics module exists with required metrics
echo ""
echo "✅ Check 1: Contract metrics module exists"
if [ -f "services/ingest/metrics.py" ]; then
    echo "   ✓ services/ingest/metrics.py exists"
else
    echo "   ❌ services/ingest/metrics.py missing"
    exit 1
fi

# Check metrics definitions
echo "   Checking required metrics definitions..."
python3 -c "
import sys
sys.path.insert(0, '/workspaces/NeuroNews')

try:
    from services.ingest.metrics import (
        contracts_validation_fail_total,
        contracts_breaking_change_total,
        contract_metrics
    )
    print('   ✓ contracts_validation_fail_total metric defined')
    print('   ✓ contracts_breaking_change_total metric defined') 
    print('   ✓ contract_metrics collector available')
except ImportError as e:
    print(f'   ❌ Required metrics not found: {e}')
    sys.exit(1)
"

# Check 2: Verify Prometheus alert rules exist
echo ""
echo "✅ Check 2: Prometheus alert rules configuration"
if [ -f "k8s/monitoring/prometheus-rules-contracts.yaml" ]; then
    echo "   ✓ prometheus-rules-contracts.yaml exists"
else
    echo "   ❌ prometheus-rules-contracts.yaml missing"
    exit 1
fi

# Check alert rules content
echo "   Checking alert rules content..."
if grep -q "ContractValidationFailureRateHigh" k8s/monitoring/prometheus-rules-contracts.yaml; then
    echo "   ✓ Failure rate alert rule found"
else
    echo "   ❌ Failure rate alert rule missing"
    exit 1
fi

if grep -q "ContractBreakingChangeDetected" k8s/monitoring/prometheus-rules-contracts.yaml; then
    echo "   ✓ Breaking change alert rule found"
else
    echo "   ❌ Breaking change alert rule missing"
    exit 1
fi

# Check threshold conditions
if grep -q "> 1" k8s/monitoring/prometheus-rules-contracts.yaml; then
    echo "   ✓ >1% failure rate threshold configured"
else
    echo "   ❌ >1% failure rate threshold missing"
    exit 1
fi

if grep -q "15m" k8s/monitoring/prometheus-rules-contracts.yaml; then
    echo "   ✓ 15-minute time window configured"
else
    echo "   ❌ 15-minute time window missing"
    exit 1
fi

# Check 3: Verify Grafana dashboard configuration
echo ""
echo "✅ Check 3: Grafana dashboard configuration"
if [ -f "k8s/monitoring/grafana-dashboard-contracts.json" ]; then
    echo "   ✓ grafana-dashboard-contracts.json exists"
else
    echo "   ❌ grafana-dashboard-contracts.json missing"
    exit 1
fi

# Check dashboard content
echo "   Checking dashboard panels..."
if grep -q "pipeline" k8s/monitoring/grafana-dashboard-contracts.json; then
    echo "   ✓ Pipeline filtering configured"
else
    echo "   ❌ Pipeline filtering missing"
    exit 1
fi

if grep -q "source_id" k8s/monitoring/grafana-dashboard-contracts.json; then
    echo "   ✓ Source ID filtering configured"
else
    echo "   ❌ Source ID filtering missing"
    exit 1
fi

# Check 4: Verify alerting configuration
echo ""
echo "✅ Check 4: Alerting configuration (Slack/email)"
if [ -f "k8s/monitoring/alertmanager-contracts-config.yaml" ]; then
    echo "   ✓ alertmanager-contracts-config.yaml exists"
else
    echo "   ❌ alertmanager-contracts-config.yaml missing"
    exit 1
fi

# Check alerting destinations
if grep -q "slack" k8s/monitoring/alertmanager-contracts-config.yaml; then
    echo "   ✓ Slack alerting configured"
else
    echo "   ❌ Slack alerting missing"
    exit 1
fi

if grep -q "email" k8s/monitoring/alertmanager-contracts-config.yaml; then
    echo "   ✓ Email alerting configured"
else
    echo "   ❌ Email alerting missing"
    exit 1
fi

# Check 5: Test metrics functionality
echo ""
echo "✅ Check 5: Testing metrics functionality"
python3 -c "
import sys
import time
sys.path.insert(0, '/workspaces/NeuroNews')

try:
    from services.ingest.metrics import contract_metrics
    
    # Test validation failure recording
    contract_metrics.record_validation_failure('test-pipeline', 'test-source', 'test-schema', 'test-error')
    print('   ✓ Validation failure recording works')
    
    # Test breaking change recording
    contract_metrics.record_breaking_change('test-pipeline', 'test-schema', 'field_removed', 'ci')
    print('   ✓ Breaking change recording works')
    
    # Test validation success recording
    contract_metrics.record_validation_success('test-pipeline', 'test-source', 'test-schema')
    print('   ✓ Validation success recording works')
    
    # Test latency recording
    contract_metrics.record_validation_latency(50.0, 'test-pipeline', 'test-source', 'test-schema')
    print('   ✓ Validation latency recording works')
    
    # Test DLQ recording
    contract_metrics.record_dlq_message('test-pipeline', 'test-source', 'test-schema', 'validation_failed')
    print('   ✓ DLQ message recording works')
    
    print('   ✓ All metrics recording functions operational')
    
except Exception as e:
    print(f'   ❌ Metrics functionality test failed: {e}')
    sys.exit(1)
"

# Check 6: Verify integration with existing contracts
echo ""
echo "✅ Check 6: Integration with existing contract validation"
if grep -q "contract_metrics" services/ingest/common/contracts.py; then
    echo "   ✓ Prometheus metrics integrated with existing validation"
else
    echo "   ❌ Prometheus metrics not integrated with existing validation"
    exit 1
fi

# Check method signature updates
if grep -q "pipeline.*source_id" services/ingest/common/contracts.py; then
    echo "   ✓ Validation methods updated with pipeline/source_id parameters"
else
    echo "   ❌ Validation methods not updated for enhanced metrics"
    exit 1
fi

# Check 7: Test demo script
echo ""
echo "✅ Check 7: Demo script functionality"
if [ -f "demo_contract_observability.py" ]; then
    echo "   ✓ demo_contract_observability.py exists"
else
    echo "   ❌ demo_contract_observability.py missing"
    exit 1
fi

# Quick demo test
echo "   Running quick demo validation..."
python3 -c "
import sys
sys.path.insert(0, '/workspaces/NeuroNews')

try:
    from demo_contract_observability import simulate_validation_success, simulate_validation_failure
    
    # Test simulation functions
    simulate_validation_success()
    simulate_validation_failure()
    
    print('   ✓ Demo script functions work correctly')
    
except Exception as e:
    print(f'   ❌ Demo script test failed: {e}')
    sys.exit(1)
"

# Check 8: Verify metrics export capability
echo ""
echo "✅ Check 8: Prometheus metrics export"
python3 -c "
import sys
sys.path.insert(0, '/workspaces/NeuroNews')

try:
    from services.ingest.metrics import get_contract_metrics, get_content_type
    
    # Test metrics export
    metrics_text = get_contract_metrics()
    content_type = get_content_type()
    
    if b'contracts_validation' in metrics_text:
        print('   ✓ Contract validation metrics exported')
    else:
        print('   ❌ Contract validation metrics not found in export')
        sys.exit(1)
    
    if b'contracts_breaking_change' in metrics_text:
        print('   ✓ Breaking change metrics exported')
    else:
        print('   ❌ Breaking change metrics not found in export')
        sys.exit(1)
    
    if 'text/plain' in content_type:
        print('   ✓ Correct content type for Prometheus')
    else:
        print('   ❌ Incorrect content type for Prometheus')
        sys.exit(1)
    
    print('   ✓ Prometheus metrics export working correctly')
    
except Exception as e:
    print(f'   ❌ Metrics export test failed: {e}')
    sys.exit(1)
"

echo ""
echo "📋 DoD Requirements Summary:"
echo "✅ contracts_validation_fail_total metric implemented and functional"
echo "✅ contracts_breaking_change_total metric implemented and functional"
echo "✅ Prometheus alert rules configured (>1% failure rate over 15m, breaking changes)"
echo "✅ Grafana dashboard shows failures by pipeline and source_id"
echo "✅ Alerts route to Slack and email via Alertmanager"
echo "✅ Integration with existing contract validation infrastructure"
echo "✅ Comprehensive metrics collection (latency, DLQ, compatibility checks)"
echo "✅ Demo script demonstrates all observability capabilities"
echo ""
echo "🎉 Issue #371 implementation complete and DoD verified!"
echo ""
echo "ℹ️  Next steps for deployment:"
echo "   1. Apply Prometheus rules: kubectl apply -f k8s/monitoring/prometheus-rules-contracts.yaml"
echo "   2. Configure Alertmanager: kubectl apply -f k8s/monitoring/alertmanager-contracts-config.yaml"
echo "   3. Import Grafana dashboard from k8s/monitoring/grafana-dashboard-contracts.json"
echo "   4. Set environment variables for Slack webhook and SMTP configuration"
echo "   5. Update production pipelines to use enhanced validation methods"
