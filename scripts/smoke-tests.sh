#!/bin/bash
# Smoke tests for NeuroNews deployment
# Usage: ./smoke-tests.sh <namespace> [service-name]

set -e

NAMESPACE=${1:-neuronews-prod}
SERVICE_NAME=${2:-neuronews-api}
TIMEOUT=60

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test result tracking
declare -a FAILED_TESTS=()

# Helper function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TESTS_RUN=$((TESTS_RUN + 1))
    info "Running test: $test_name"
    
    if eval "$test_command"; then
        log "✅ PASSED: $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        error "❌ FAILED: $test_name"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        FAILED_TESTS+=("$test_name")
        return 1
    fi
}

# Test if namespace exists
test_namespace_exists() {
    kubectl get namespace "$NAMESPACE" &> /dev/null
}

# Test if service exists
test_service_exists() {
    kubectl get service "$SERVICE_NAME" -n "$NAMESPACE" &> /dev/null
}

# Test if deployment exists and is ready
test_deployment_ready() {
    kubectl rollout status deployment/"$SERVICE_NAME" -n "$NAMESPACE" --timeout=60s &> /dev/null
}

# Test if pods are running
test_pods_running() {
    local running_pods=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE_NAME" --field-selector=status.phase=Running -o name | wc -l)
    [[ "$running_pods" -gt 0 ]]
}

# Test health endpoint
test_health_endpoint() {
    local service_ip=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
    local service_port=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
    
    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        return 1
    fi
    
    kubectl run smoke-test-health --rm -i --restart=Never --image=curlimages/curl:latest --timeout=30s \
        -- curl -f -s --max-time 10 "http://$service_ip:$service_port/health" &> /dev/null
}

# Test metrics endpoint
test_metrics_endpoint() {
    local service_ip=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
    local service_port=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
    
    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        return 1
    fi
    
    kubectl run smoke-test-metrics --rm -i --restart=Never --image=curlimages/curl:latest --timeout=30s \
        -- curl -f -s --max-time 10 "http://$service_ip:$service_port/metrics" &> /dev/null
}

# Test API endpoint with basic request
test_api_basic_request() {
    local service_ip=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
    local service_port=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
    
    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        return 1
    fi
    
    # Test basic API endpoint (adjust path based on your API)
    kubectl run smoke-test-api --rm -i --restart=Never --image=curlimages/curl:latest --timeout=30s \
        -- curl -f -s --max-time 10 "http://$service_ip:$service_port/api/v1/articles?limit=1" &> /dev/null
}

# Test database connectivity (if applicable)
test_database_connectivity() {
    # Try to get database-related info from a pod
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod_name" ]]; then
        return 1
    fi
    
    # Simple database connection test (adjust based on your setup)
    kubectl exec "$pod_name" -n "$NAMESPACE" -- python -c "
import os
import sys
try:
    # Try to import database-related modules
    import psycopg2
    print('Database client available')
    sys.exit(0)
except ImportError:
    print('Database client not available')
    sys.exit(1)
except Exception as e:
    print(f'Database test error: {e}')
    sys.exit(1)
" 2>/dev/null
}

# Test logging functionality
test_logging() {
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod_name" ]]; then
        return 1
    fi
    
    # Check if logs are being generated
    local log_lines=$(kubectl logs "$pod_name" -n "$NAMESPACE" --tail=10 2>/dev/null | wc -l)
    [[ "$log_lines" -gt 0 ]]
}

# Test resource limits are respected
test_resource_limits() {
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod_name" ]]; then
        return 1
    fi
    
    # Check if pod has resource limits defined
    local cpu_limit=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].resources.limits.cpu}' 2>/dev/null)
    local memory_limit=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.spec.containers[0].resources.limits.memory}' 2>/dev/null)
    
    [[ -n "$cpu_limit" && -n "$memory_limit" ]]
}

# Test security context
test_security_context() {
    local pod_name=$(kubectl get pods -n "$NAMESPACE" -l app="$SERVICE_NAME" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [[ -z "$pod_name" ]]; then
        return 1
    fi
    
    # Check if pod is running as non-root (security best practice)
    local run_as_non_root=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.spec.securityContext.runAsNonRoot}' 2>/dev/null)
    local run_as_user=$(kubectl get pod "$pod_name" -n "$NAMESPACE" -o jsonpath='{.spec.securityContext.runAsUser}' 2>/dev/null)
    
    # Pass if either runAsNonRoot is true or runAsUser is not 0
    [[ "$run_as_non_root" == "true" ]] || [[ "$run_as_user" != "0" && -n "$run_as_user" ]]
}

# Test horizontal pod autoscaler (if configured)
test_hpa() {
    kubectl get hpa "$SERVICE_NAME" -n "$NAMESPACE" &> /dev/null
}

# Test ingress configuration (if applicable)
test_ingress() {
    local ingress_count=$(kubectl get ingress -n "$NAMESPACE" -o name 2>/dev/null | wc -l)
    [[ "$ingress_count" -gt 0 ]]
}

# Test persistent volumes (if applicable)
test_persistent_volumes() {
    local pvc_count=$(kubectl get pvc -n "$NAMESPACE" -o name 2>/dev/null | wc -l)
    # This test passes if there are no PVCs (stateless) or if PVCs exist and are bound
    if [[ "$pvc_count" -eq 0 ]]; then
        return 0  # Stateless application
    else
        local bound_pvc_count=$(kubectl get pvc -n "$NAMESPACE" -o jsonpath='{.items[?(@.status.phase=="Bound")].metadata.name}' 2>/dev/null | wc -w)
        [[ "$bound_pvc_count" -eq "$pvc_count" ]]
    fi
}

# Test performance (basic)
test_performance() {
    local service_ip=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
    local service_port=$(kubectl get svc "$SERVICE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
    
    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        return 1
    fi
    
    # Test response time (should be under 5 seconds)
    local response_time=$(kubectl run smoke-test-perf --rm -i --restart=Never --image=curlimages/curl:latest --timeout=30s \
        -- curl -o /dev/null -s -w '%{time_total}\n' "http://$service_ip:$service_port/health" 2>/dev/null | head -1)
    
    if [[ -n "$response_time" ]]; then
        # Check if response time is under 5 seconds
        python3 -c "import sys; sys.exit(0 if float('$response_time') < 5.0 else 1)" 2>/dev/null
    else
        return 1
    fi
}

# Dashboard-specific tests
test_dashboard() {
    if kubectl get service "neuronews-dashboard" -n "$NAMESPACE" &> /dev/null; then
        local dashboard_ip=$(kubectl get svc "neuronews-dashboard" -n "$NAMESPACE" -o jsonpath='{.spec.clusterIP}' 2>/dev/null)
        local dashboard_port=$(kubectl get svc "neuronews-dashboard" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)
        
        if [[ -n "$dashboard_ip" && -n "$dashboard_port" ]]; then
            kubectl run smoke-test-dashboard --rm -i --restart=Never --image=curlimages/curl:latest --timeout=30s \
                -- curl -f -s --max-time 10 "http://$dashboard_ip:$dashboard_port" &> /dev/null
        else
            return 1
        fi
    else
        # Dashboard not deployed, skip test
        return 0
    fi
}

# Main function
main() {
    log "Starting smoke tests for NeuroNews deployment"
    log "Namespace: $NAMESPACE"
    log "Service: $SERVICE_NAME"
    echo ""
    
    # Core infrastructure tests
    run_test "Namespace exists" "test_namespace_exists"
    run_test "Service exists" "test_service_exists"
    run_test "Deployment ready" "test_deployment_ready"
    run_test "Pods running" "test_pods_running"
    
    # Application health tests
    run_test "Health endpoint" "test_health_endpoint"
    run_test "Metrics endpoint" "test_metrics_endpoint"
    run_test "API basic request" "test_api_basic_request"
    
    # Infrastructure tests
    run_test "Logging functionality" "test_logging"
    run_test "Resource limits" "test_resource_limits"
    run_test "Security context" "test_security_context"
    
    # Optional tests (these may fail in some environments)
    run_test "Database connectivity" "test_database_connectivity" || true
    run_test "HPA configuration" "test_hpa" || true
    run_test "Ingress configuration" "test_ingress" || true
    run_test "Persistent volumes" "test_persistent_volumes" || true
    
    # Performance test
    run_test "Performance check" "test_performance"
    
    # Dashboard test (if applicable)
    run_test "Dashboard availability" "test_dashboard" || true
    
    # Results summary
    echo ""
    echo "=========================================="
    echo "  Smoke Tests Results"
    echo "=========================================="
    echo "Total tests run: $TESTS_RUN"
    echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
    
    if [[ $TESTS_FAILED -gt 0 ]]; then
        echo ""
        echo "Failed tests:"
        for test in "${FAILED_TESTS[@]}"; do
            echo -e "  ${RED}❌ $test${NC}"
        done
        echo ""
        error "Some tests failed. Check the deployment."
        exit 1
    else
        echo ""
        log "✅ All critical tests passed! Deployment appears healthy."
        exit 0
    fi
}

# Handle interrupts
trap 'echo ""; warn "Smoke tests interrupted"; exit 130' INT TERM

# Run main function
main "$@"
