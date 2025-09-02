#!/bin/bash

# NeuroNews FinOps Labeling System Test Suite
# Tests policy enforcement, label validation, and compliance reporting

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
TEST_NAMESPACE="finops-test"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] INFO: $1${NC}"
}

success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓ $1${NC}"
}

fail() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ✗ $1${NC}"
}

# Test counter
TEST_COUNT=0
PASS_COUNT=0
FAIL_COUNT=0

run_test() {
    local test_name="$1"
    local test_function="$2"
    
    ((TEST_COUNT++))
    info "Running test $TEST_COUNT: $test_name"
    
    if $test_function; then
        success "$test_name"
        ((PASS_COUNT++))
    else
        fail "$test_name"
        ((FAIL_COUNT++))
    fi
    
    echo
}

# Setup test environment
setup_test_environment() {
    log "Setting up test environment..."
    
    # Create test namespace
    kubectl create namespace $TEST_NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
    
    # Wait a moment for namespace to be ready
    sleep 2
    
    log "Test environment ready"
}

# Cleanup test environment
cleanup_test_environment() {
    log "Cleaning up test environment..."
    
    # Delete test namespace and all resources
    kubectl delete namespace $TEST_NAMESPACE --ignore-not-found=true
    
    # Remove temporary test files
    rm -f /tmp/test-*.yaml
    
    log "Test environment cleaned up"
}

# Test 1: Valid deployment with all required labels should succeed
test_valid_deployment() {
    cat > /tmp/test-valid-deployment.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-valid
  namespace: $TEST_NAMESPACE
  labels:
    app: test-app
    component: backend
    pipeline: api
    team: test-team
    env: test
    cost_center: test-center
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
        component: backend
        pipeline: api
        team: test-team
        env: test
        cost_center: test-center
    spec:
      containers:
      - name: test
        image: nginx:alpine
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
EOF

    # Apply and check if it succeeds
    if kubectl apply -f /tmp/test-valid-deployment.yaml &>/dev/null; then
        # Verify deployment was created
        kubectl get deployment test-valid -n $TEST_NAMESPACE &>/dev/null
    else
        return 1
    fi
}

# Test 2: Deployment missing required labels should fail in enforce mode
test_missing_labels_deployment() {
    cat > /tmp/test-missing-labels.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-missing-labels
  namespace: $TEST_NAMESPACE
  labels:
    app: test-app
    # Missing: component, pipeline, team, env, cost_center
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
    spec:
      containers:
      - name: test
        image: nginx:alpine
EOF

    # Check if policies are in enforce mode
    local validation_action=$(kubectl get clusterpolicy require-finops-labels -o jsonpath='{.spec.validationFailureAction}' 2>/dev/null || echo "unknown")
    
    if [[ "$validation_action" == "enforce" ]]; then
        # Should fail in enforce mode
        if kubectl apply -f /tmp/test-missing-labels.yaml &>/dev/null; then
            return 1  # Test fails if deployment succeeds
        else
            return 0  # Test passes if deployment is blocked
        fi
    else
        # In audit mode, deployment succeeds but generates violation event
        if kubectl apply -f /tmp/test-missing-labels.yaml &>/dev/null; then
            # Check for policy violation event
            sleep 2
            kubectl get events -n $TEST_NAMESPACE --field-selector reason=PolicyViolation 2>/dev/null | grep -q "require-finops-labels"
        else
            return 1
        fi
    fi
}

# Test 3: Invalid pipeline value should fail
test_invalid_pipeline_value() {
    cat > /tmp/test-invalid-pipeline.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-invalid-pipeline
  namespace: $TEST_NAMESPACE
  labels:
    app: test-app
    component: backend
    pipeline: invalid-pipeline
    team: test-team
    env: test
    cost_center: test-center
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
        component: backend
        pipeline: invalid-pipeline
        team: test-team
        env: test
        cost_center: test-center
    spec:
      containers:
      - name: test
        image: nginx:alpine
EOF

    # Should fail due to invalid pipeline value
    if kubectl apply -f /tmp/test-invalid-pipeline.yaml &>/dev/null; then
        return 1  # Test fails if deployment succeeds
    else
        return 0  # Test passes if deployment is blocked
    fi
}

# Test 4: Invalid env value should fail
test_invalid_env_value() {
    cat > /tmp/test-invalid-env.yaml << EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-invalid-env
  namespace: $TEST_NAMESPACE
  labels:
    app: test-app
    component: backend
    pipeline: api
    team: test-team
    env: invalid-env
    cost_center: test-center
spec:
  replicas: 1
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
        component: backend
        pipeline: api
        team: test-team
        env: invalid-env
        cost_center: test-center
    spec:
      containers:
      - name: test
        image: nginx:alpine
EOF

    # Should fail due to invalid env value
    if kubectl apply -f /tmp/test-invalid-env.yaml &>/dev/null; then
        return 1  # Test fails if deployment succeeds
    else
        return 0  # Test passes if deployment is blocked
    fi
}

# Test 5: StatefulSet with valid labels should succeed
test_valid_statefulset() {
    cat > /tmp/test-valid-statefulset.yaml << EOF
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: test-valid-sts
  namespace: $TEST_NAMESPACE
  labels:
    app: test-database
    component: database
    pipeline: ingest
    team: data-engineering
    env: test
    cost_center: data-platform
spec:
  serviceName: test-database
  replicas: 1
  selector:
    matchLabels:
      app: test-database
  template:
    metadata:
      labels:
        app: test-database
        component: database
        pipeline: ingest
        team: data-engineering
        env: test
        cost_center: data-platform
    spec:
      containers:
      - name: database
        image: postgres:13-alpine
        env:
        - name: POSTGRES_DB
          value: testdb
        - name: POSTGRES_PASSWORD
          value: testpass
EOF

    if kubectl apply -f /tmp/test-valid-statefulset.yaml &>/dev/null; then
        kubectl get statefulset test-valid-sts -n $TEST_NAMESPACE &>/dev/null
    else
        return 1
    fi
}

# Test 6: Job with valid labels should succeed
test_valid_job() {
    cat > /tmp/test-valid-job.yaml << EOF
apiVersion: batch/v1
kind: Job
metadata:
  name: test-valid-job
  namespace: $TEST_NAMESPACE
  labels:
    app: test-etl
    component: etl-job
    pipeline: transform
    team: data-engineering
    env: test
    cost_center: data-platform
spec:
  template:
    metadata:
      labels:
        app: test-etl
        component: etl-job
        pipeline: transform
        team: data-engineering
        env: test
        cost_center: data-platform
    spec:
      restartPolicy: Never
      containers:
      - name: etl
        image: busybox
        command: ["echo", "ETL job completed"]
EOF

    if kubectl apply -f /tmp/test-valid-job.yaml &>/dev/null; then
        kubectl get job test-valid-job -n $TEST_NAMESPACE &>/dev/null
    else
        return 1
    fi
}

# Test 7: Check Kyverno policies are installed
test_kyverno_policies_installed() {
    local policies=("require-finops-labels" "validate-finops-label-values" "generate-missing-finops-labels")
    
    for policy in "${policies[@]}"; do
        if ! kubectl get clusterpolicy $policy &>/dev/null; then
            return 1
        fi
    done
    
    return 0
}

# Test 8: Check labeling schema ConfigMap exists
test_labeling_schema_exists() {
    kubectl get configmap finops-labeling-schema -n kube-system &>/dev/null
}

# Test 9: Validate policy readiness
test_policy_readiness() {
    local policies=("require-finops-labels" "validate-finops-label-values" "generate-missing-finops-labels")
    
    for policy in "${policies[@]}"; do
        local ready=$(kubectl get clusterpolicy $policy -o jsonpath='{.status.ready}' 2>/dev/null || echo "false")
        if [[ "$ready" != "true" ]]; then
            return 1
        fi
    done
    
    return 0
}

# Test 10: Generate and validate compliance report
test_compliance_report() {
    # Create a temporary script to generate report
    cat > /tmp/test-compliance-report.sh << 'EOF'
#!/bin/bash
echo "Compliance Report Test"
echo "====================="

# Check deployments in test namespace
kubectl get deployments -n finops-test -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.app}{"\t"}{.metadata.labels.pipeline}{"\t"}{.metadata.labels.team}{"\n"}{end}' 2>/dev/null || echo "No deployments"

echo
echo "Policy Status:"
kubectl get clusterpolicy -o custom-columns="NAME:.metadata.name,READY:.status.ready" 2>/dev/null || echo "No policies"
EOF

    chmod +x /tmp/test-compliance-report.sh
    
    # Run report and check it produces output
    local output=$(/tmp/test-compliance-report.sh 2>/dev/null)
    if [[ -n "$output" && "$output" =~ "Compliance Report Test" ]]; then
        return 0
    else
        return 1
    fi
}

# Performance test: Check policy enforcement doesn't significantly slow deployments
test_performance() {
    local start_time=$(date +%s)
    
    # Deploy a simple workload and measure time
    kubectl apply -f /tmp/test-valid-deployment.yaml &>/dev/null
    kubectl wait --for=condition=Available deployment/test-valid -n $TEST_NAMESPACE --timeout=60s &>/dev/null
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Should complete within reasonable time (60 seconds)
    if [[ $duration -lt 60 ]]; then
        return 0
    else
        warn "Deployment took ${duration}s, might be performance issue"
        return 1
    fi
}

# Main test runner
main() {
    log "Starting NeuroNews FinOps Labeling System Test Suite"
    echo
    
    # Setup
    setup_test_environment
    
    # Run tests
    run_test "Kyverno policies installed" test_kyverno_policies_installed
    run_test "Labeling schema ConfigMap exists" test_labeling_schema_exists
    run_test "Policy readiness" test_policy_readiness
    run_test "Valid deployment with all labels" test_valid_deployment
    run_test "Valid StatefulSet with labels" test_valid_statefulset
    run_test "Valid Job with labels" test_valid_job
    run_test "Missing labels deployment handling" test_missing_labels_deployment
    run_test "Invalid pipeline value rejection" test_invalid_pipeline_value
    run_test "Invalid env value rejection" test_invalid_env_value
    run_test "Compliance report generation" test_compliance_report
    run_test "Performance within limits" test_performance
    
    # Cleanup
    cleanup_test_environment
    
    # Summary
    echo "=================================="
    log "Test Summary"
    echo "=================================="
    info "Total tests: $TEST_COUNT"
    success "Passed: $PASS_COUNT"
    if [[ $FAIL_COUNT -gt 0 ]]; then
        fail "Failed: $FAIL_COUNT"
    else
        info "Failed: $FAIL_COUNT"
    fi
    echo
    
    if [[ $FAIL_COUNT -eq 0 ]]; then
        success "All tests passed! FinOps labeling system is working correctly."
        exit 0
    else
        error "Some tests failed. Please review the output above."
        exit 1
    fi
}

# Handle command line arguments
case "${1:-test}" in
    "test")
        main
        ;;
    "setup")
        setup_test_environment
        ;;
    "cleanup")
        cleanup_test_environment
        ;;
    *)
        echo "Usage: $0 [test|setup|cleanup]"
        echo
        echo "  test    - Run complete test suite (default)"
        echo "  setup   - Setup test environment only"
        echo "  cleanup - Cleanup test environment only"
        exit 1
        ;;
esac
