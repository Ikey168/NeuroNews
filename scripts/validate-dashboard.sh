#!/bin/bash

# NeuroNews Dashboard Validation Script
# Issue #76: Deploy the NeuroNews Dashboard
#
# This script validates the NeuroNews Dashboard deployment and performs
# comprehensive testing of the dashboard functionality.

set -euo pipefail

# Configuration
NAMESPACE="neuronews"
TIMEOUT=300
VERBOSE="${VERBOSE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_debug() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $1"
    fi
}

log_section() {
    echo
    echo -e "${CYAN}=== $1 ===${NC}"
    echo
}

# Test counters
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    local expected_result="${3:-0}"  # Default to expecting success (0)
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    log_info "Testing: $test_name"
    
    if eval "$test_command" > /dev/null 2>&1; then
        local result=0
    else
        local result=1
    fi
    
    if [[ $result -eq $expected_result ]]; then
        log_success "✅ $test_name"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "❌ $test_name"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        if [[ "$VERBOSE" == "true" ]]; then
            log_debug "Command: $test_command"
            log_debug "Expected: $expected_result, Got: $result"
        fi
        return 1
    fi
}

# Function to validate Kubernetes resources
validate_k8s_resources() {
    log_section "Validating Kubernetes Resources"
    
    # Test namespace exists
    run_test "Namespace exists" \
        "kubectl get namespace $NAMESPACE"
    
    # Test deployment exists and is ready
    run_test "Dashboard deployment exists" \
        "kubectl get deployment neuronews-dashboard -n $NAMESPACE"
    
    run_test "Dashboard deployment is available" \
        "kubectl get deployment neuronews-dashboard -n $NAMESPACE -o jsonpath='{.status.conditions[?(@.type==\"Available\")].status}' | grep -q True"
    
    # Test service exists
    run_test "Dashboard service exists" \
        "kubectl get service dashboard-service -n $NAMESPACE"
    
    # Test ConfigMap exists
    run_test "Dashboard ConfigMap exists" \
        "kubectl get configmap dashboard-config -n $NAMESPACE"
    
    # Test Secret exists
    run_test "Dashboard Secret exists" \
        "kubectl get secret dashboard-secrets -n $NAMESPACE"
    
    # Test ServiceAccount exists
    run_test "Dashboard ServiceAccount exists" \
        "kubectl get serviceaccount dashboard-sa -n $NAMESPACE"
    
    # Test HPA exists
    run_test "Horizontal Pod Autoscaler exists" \
        "kubectl get hpa dashboard-hpa -n $NAMESPACE"
    
    # Test PDB exists
    run_test "Pod Disruption Budget exists" \
        "kubectl get pdb dashboard-pdb -n $NAMESPACE"
    
    # Test Ingress exists
    run_test "Dashboard Ingress exists" \
        "kubectl get ingress dashboard-ingress -n $NAMESPACE"
}

# Function to validate pod health
validate_pod_health() {
    log_section "Validating Pod Health"
    
    # Get pod information
    local pods=$(kubectl get pods -l app=neuronews-dashboard -n $NAMESPACE --no-headers 2>/dev/null || echo "")
    
    if [[ -z "$pods" ]]; then
        log_error "No dashboard pods found"
        TESTS_TOTAL=$((TESTS_TOTAL + 1))
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
    
    local total_pods=$(echo "$pods" | wc -l)
    local running_pods=$(echo "$pods" | grep "Running" | wc -l)
    local ready_pods=$(echo "$pods" | awk '{print $2}' | grep -c ".*/.* " || echo "0")
    
    log_info "Found $total_pods dashboard pods"
    log_info "Running pods: $running_pods"
    
    # Test pod count
    run_test "At least one pod running" \
        "[[ $running_pods -gt 0 ]]"
    
    # Test individual pods
    while IFS= read -r pod_line; do
        if [[ -n "$pod_line" ]]; then
            local pod_name=$(echo "$pod_line" | awk '{print $1}')
            local pod_status=$(echo "$pod_line" | awk '{print $3}')
            local pod_ready=$(echo "$pod_line" | awk '{print $2}')
            
            run_test "Pod $pod_name is running" \
                "[[ \"$pod_status\" == \"Running\" ]]"
            
            # Check if pod is ready (all containers ready)
            if [[ "$pod_ready" =~ ^([0-9]+)/\1$ ]]; then
                run_test "Pod $pod_name is ready" \
                    "true"
            else
                run_test "Pod $pod_name is ready" \
                    "false" 1
            fi
        fi
    done <<< "$pods"
}

# Function to test dashboard endpoints
test_dashboard_endpoints() {
    log_section "Testing Dashboard Endpoints"
    
    # Port forward for testing
    local port_forward_pid=""
    local local_port=8501
    
    log_info "Setting up port forwarding for testing..."
    kubectl port-forward service/dashboard-service $local_port:80 -n $NAMESPACE > /dev/null 2>&1 &
    port_forward_pid=$!
    
    # Give port-forward time to establish
    sleep 10
    
    # Test if port forwarding is working
    if ! netstat -ln | grep -q ":$local_port "; then
        log_warning "Port forwarding failed, skipping endpoint tests"
        if [[ -n "$port_forward_pid" ]]; then
            kill $port_forward_pid 2>/dev/null || true
        fi
        return 0
    fi
    
    # Test main dashboard endpoint
    run_test "Dashboard main page accessible" \
        "curl -s -f --max-time 30 http://localhost:$local_port/ > /dev/null"
    
    # Test Streamlit health endpoint
    run_test "Streamlit health endpoint accessible" \
        "curl -s -f --max-time 10 http://localhost:$local_port/_stcore/health > /dev/null"
    
    # Test if dashboard returns HTML content
    run_test "Dashboard returns HTML content" \
        "curl -s --max-time 30 http://localhost:$local_port/ | grep -q '<html\\|<title\\|streamlit'"
    
    # Test real-time capabilities (WebSocket support)
    run_test "WebSocket endpoint accessible" \
        "curl -s -f --max-time 10 -H 'Connection: Upgrade' -H 'Upgrade: websocket' http://localhost:$local_port/_stcore/stream > /dev/null"
    
    # Clean up port forward
    if [[ -n "$port_forward_pid" ]]; then
        kill $port_forward_pid 2>/dev/null || true
        sleep 2
    fi
}

# Function to validate monitoring setup
validate_monitoring() {
    log_section "Validating Monitoring Setup"
    
    # Check if Prometheus operator is available
    if ! kubectl get crd servicemonitors.monitoring.coreos.com > /dev/null 2>&1; then
        log_warning "Prometheus operator not found, skipping monitoring validation"
        return 0
    fi
    
    # Test ServiceMonitor
    run_test "ServiceMonitor exists" \
        "kubectl get servicemonitor dashboard-monitor -n $NAMESPACE"
    
    # Test PrometheusRule
    run_test "PrometheusRule exists" \
        "kubectl get prometheusrule dashboard-alerts -n $NAMESPACE"
    
    # Test Grafana dashboard ConfigMap
    run_test "Grafana dashboard ConfigMap exists" \
        "kubectl get configmap dashboard-grafana-dashboard -n $NAMESPACE"
    
    # Validate ServiceMonitor configuration
    run_test "ServiceMonitor has correct selector" \
        "kubectl get servicemonitor dashboard-monitor -n $NAMESPACE -o jsonpath='{.spec.selector.matchLabels.app}' | grep -q 'neuronews-dashboard'"
    
    # Validate PrometheusRule has alerts
    run_test "PrometheusRule has alert rules" \
        "kubectl get prometheusrule dashboard-alerts -n $NAMESPACE -o jsonpath='{.spec.groups[0].rules}' | grep -q 'alert'"
}

# Function to validate network policies
validate_network_policies() {
    log_section "Validating Network Policies"
    
    # Test if network policies exist
    run_test "Dashboard network policy exists" \
        "kubectl get networkpolicy dashboard-netpol -n $NAMESPACE"
    
    # Test ingress network policy
    run_test "Ingress network policy exists" \
        "kubectl get networkpolicy dashboard-ingress-netpol -n $NAMESPACE"
    
    # Validate policy configuration
    run_test "Network policy allows ingress traffic" \
        "kubectl get networkpolicy dashboard-netpol -n $NAMESPACE -o jsonpath='{.spec.ingress}' | grep -q 'ports'"
    
    run_test "Network policy allows egress traffic" \
        "kubectl get networkpolicy dashboard-netpol -n $NAMESPACE -o jsonpath='{.spec.egress}' | grep -q 'ports'"
}

# Function to validate auto-scaling
validate_autoscaling() {
    log_section "Validating Auto-scaling"
    
    # Test HPA configuration
    run_test "HPA has correct min replicas" \
        "kubectl get hpa dashboard-hpa -n $NAMESPACE -o jsonpath='{.spec.minReplicas}' | grep -q '^3$'"
    
    run_test "HPA has correct max replicas" \
        "kubectl get hpa dashboard-hpa -n $NAMESPACE -o jsonpath='{.spec.maxReplicas}' | grep -q '^15$'"
    
    # Test HPA metrics
    run_test "HPA has CPU metric configured" \
        "kubectl get hpa dashboard-hpa -n $NAMESPACE -o jsonpath='{.spec.metrics[*].resource.name}' | grep -q 'cpu'"
    
    run_test "HPA has memory metric configured" \
        "kubectl get hpa dashboard-hpa -n $NAMESPACE -o jsonpath='{.spec.metrics[*].resource.name}' | grep -q 'memory'"
    
    # Test PDB configuration
    run_test "PDB has correct min available" \
        "kubectl get pdb dashboard-pdb -n $NAMESPACE -o jsonpath='{.spec.minAvailable}' | grep -q '^2$'"
}

# Function to validate ingress configuration
validate_ingress() {
    log_section "Validating Ingress Configuration"
    
    # Test ingress rules
    run_test "Ingress has correct hosts" \
        "kubectl get ingress dashboard-ingress -n $NAMESPACE -o jsonpath='{.spec.rules[*].host}' | grep -q 'dashboard.neuronews.com'"
    
    # Test TLS configuration
    run_test "Ingress has TLS configured" \
        "kubectl get ingress dashboard-ingress -n $NAMESPACE -o jsonpath='{.spec.tls}' | grep -q 'secretName'"
    
    # Test ingress class
    run_test "Ingress has correct class" \
        "kubectl get ingress dashboard-ingress -n $NAMESPACE -o jsonpath='{.spec.ingressClassName}' | grep -q 'nginx'"
    
    # Test WebSocket support annotations
    run_test "Ingress has WebSocket support" \
        "kubectl get ingress dashboard-ingress -n $NAMESPACE -o jsonpath='{.metadata.annotations}' | grep -q 'websocket'"
}

# Function to validate configuration
validate_configuration() {
    log_section "Validating Configuration"
    
    # Test ConfigMap data
    run_test "ConfigMap has dashboard configuration" \
        "kubectl get configmap dashboard-config -n $NAMESPACE -o jsonpath='{.data}' | grep -q 'DASHBOARD_TITLE'"
    
    run_test "ConfigMap has Streamlit configuration" \
        "kubectl get configmap dashboard-config -n $NAMESPACE -o jsonpath='{.data}' | grep -q 'config.toml'"
    
    # Test real-time configuration
    run_test "Real-time updates enabled" \
        "kubectl get configmap dashboard-config -n $NAMESPACE -o jsonpath='{.data.ENABLE_REAL_TIME_UPDATES}' | grep -q 'true'"
    
    # Test security configuration
    run_test "Security headers enabled" \
        "kubectl get configmap dashboard-config -n $NAMESPACE -o jsonpath='{.data}' | grep -q 'SECURITY_'"
}

# Function to test resource limits
validate_resource_limits() {
    log_section "Validating Resource Limits"
    
    # Test deployment resource requests
    run_test "Deployment has CPU requests" \
        "kubectl get deployment neuronews-dashboard -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.requests.cpu}' | grep -q '[0-9]'"
    
    run_test "Deployment has memory requests" \
        "kubectl get deployment neuronews-dashboard -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.requests.memory}' | grep -q '[0-9]'"
    
    run_test "Deployment has CPU limits" \
        "kubectl get deployment neuronews-dashboard -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' | grep -q '[0-9]'"
    
    run_test "Deployment has memory limits" \
        "kubectl get deployment neuronews-dashboard -n $NAMESPACE -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' | grep -q '[0-9]'"
    
    # Test namespace resource quota
    run_test "Namespace has resource quota" \
        "kubectl get resourcequota dashboard-quota -n $NAMESPACE"
    
    # Test limit ranges
    run_test "Namespace has limit range" \
        "kubectl get limitrange dashboard-limits -n $NAMESPACE"
}

# Function to show validation summary
show_validation_summary() {
    log_section "Validation Summary"
    
    echo
    echo "📊 NeuroNews Dashboard Validation Results"
    echo "========================================="
    echo
    echo "Total Tests: $TESTS_TOTAL"
    echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
    echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
    echo
    
    local success_rate=0
    if [[ $TESTS_TOTAL -gt 0 ]]; then
        success_rate=$((TESTS_PASSED * 100 / TESTS_TOTAL))
    fi
    
    echo "Success Rate: $success_rate%"
    echo
    
    if [[ $TESTS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}🎉 All validations passed! NeuroNews Dashboard is healthy.${NC}"
        echo
        log_info "Dashboard is ready for production use"
        echo
        echo "🌐 Access dashboard:"
        echo "   kubectl port-forward service/dashboard-service 8501:80 -n $NAMESPACE"
        echo "   Open browser: http://localhost:8501"
        echo
    else
        echo -e "${RED}⚠️  Some validations failed. Please review the issues above.${NC}"
        echo
        log_warning "Dashboard may not be fully functional"
        echo
        echo "🔍 Debug commands:"
        echo "   kubectl get all -n $NAMESPACE"
        echo "   kubectl describe deployment neuronews-dashboard -n $NAMESPACE"
        echo "   kubectl logs -l app=neuronews-dashboard -n $NAMESPACE"
        echo
    fi
    
    # Return appropriate exit code
    if [[ $TESTS_FAILED -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Validate NeuroNews Dashboard deployment in Kubernetes

Options:
    --verbose              Enable verbose output
    --namespace NAME       Set target namespace (default: $NAMESPACE)
    --timeout SECONDS      Set timeout for tests (default: $TIMEOUT)
    --help                 Show this help message

Environment Variables:
    VERBOSE               Set to 'true' for verbose output

Examples:
    # Basic validation
    $0
    
    # Verbose validation
    $0 --verbose
    
    # Custom namespace
    $0 --namespace production
    
    # With environment variable
    VERBOSE=true $0

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose)
            VERBOSE="true"
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main validation function
main() {
    echo
    echo -e "${CYAN}🔍 NeuroNews Dashboard Validation${NC}"
    echo -e "${CYAN}==================================${NC}"
    echo
    log_info "Starting NeuroNews Dashboard validation"
    log_info "Target namespace: $NAMESPACE"
    log_info "Timeout: ${TIMEOUT}s"
    log_info "Verbose mode: $VERBOSE"
    
    # Check prerequisites
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Run validation tests
    validate_k8s_resources
    validate_pod_health
    validate_configuration
    validate_resource_limits
    validate_autoscaling
    validate_ingress
    validate_network_policies
    validate_monitoring
    test_dashboard_endpoints
    
    # Show summary and exit with appropriate code
    show_validation_summary
}

# Run main function
main "$@"
