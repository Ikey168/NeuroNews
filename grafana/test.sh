#!/bin/bash

# NeuroNews Grafana FinOps Dashboards Test Suite
# Tests dashboard installation, queries, and data availability

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
NAMESPACE_MONITORING="monitoring"
NAMESPACE_OPENCOST="opencost"

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

# Test 1: Check prerequisites
test_prerequisites() {
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        return 1
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        return 1
    fi
    
    # Check monitoring namespace
    if ! kubectl get namespace $NAMESPACE_MONITORING &> /dev/null; then
        return 1
    fi
    
    return 0
}

# Test 2: Check Grafana deployment
test_grafana_deployment() {
    if kubectl get deployment grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        local ready_replicas=$(kubectl get deployment grafana -n $NAMESPACE_MONITORING -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$ready_replicas" -gt 0 ]]; then
            return 0
        fi
    fi
    return 1
}

# Test 3: Check OpenCost deployment
test_opencost_deployment() {
    if kubectl get deployment opencost -n $NAMESPACE_OPENCOST &> /dev/null; then
        local ready_replicas=$(kubectl get deployment opencost -n $NAMESPACE_OPENCOST -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
        if [[ "$ready_replicas" -gt 0 ]]; then
            return 0
        fi
    fi
    return 1
}

# Test 4: Check dashboard ConfigMaps exist
test_dashboard_configmaps() {
    local configmaps=("grafana-dashboards-finops" "grafana-dashboard-provisioning" "grafana-datasources-opencost")
    
    for cm in "${configmaps[@]}"; do
        if ! kubectl get configmap $cm -n $NAMESPACE_MONITORING &> /dev/null; then
            return 1
        fi
    done
    
    return 0
}

# Test 5: Validate dashboard JSON structure
test_dashboard_json_structure() {
    # Check if dashboard files exist and are valid JSON
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    for dashboard in "$script_dir/dashboards"/*.json; do
        if [[ -f "$dashboard" ]]; then
            if ! python3 -m json.tool "$dashboard" > /dev/null 2>&1; then
                return 1
            fi
        else
            return 1
        fi
    done
    
    return 0
}

# Test 6: Check Prometheus connectivity
test_prometheus_connectivity() {
    # Try to connect to Prometheus service
    if kubectl get service prometheus-server -n $NAMESPACE_MONITORING &> /dev/null; then
        # Port forward and test connectivity
        local port_forward_pid
        kubectl port-forward svc/prometheus-server -n $NAMESPACE_MONITORING 9090:80 &> /dev/null &
        port_forward_pid=$!
        
        sleep 3
        
        # Test if we can reach Prometheus
        if curl -s --max-time 5 http://localhost:9090/api/v1/query?query=up &> /dev/null; then
            kill $port_forward_pid 2>/dev/null || true
            return 0
        fi
        
        kill $port_forward_pid 2>/dev/null || true
    fi
    
    return 1
}

# Test 7: Test OpenCost metrics availability
test_opencost_metrics() {
    if ! kubectl get service opencost -n $NAMESPACE_OPENCOST &> /dev/null; then
        return 1
    fi
    
    # Port forward and test OpenCost metrics endpoint
    local port_forward_pid
    kubectl port-forward svc/opencost -n $NAMESPACE_OPENCOST 9003:9003 &> /dev/null &
    port_forward_pid=$!
    
    sleep 3
    
    # Test if we can reach OpenCost metrics
    if curl -s --max-time 5 http://localhost:9003/metrics | grep -q "opencost_"; then
        kill $port_forward_pid 2>/dev/null || true
        return 0
    fi
    
    kill $port_forward_pid 2>/dev/null || true
    return 1
}

# Test 8: Test key PromQL queries
test_promql_queries() {
    if ! kubectl get service prometheus-server -n $NAMESPACE_MONITORING &> /dev/null; then
        return 1
    fi
    
    # Port forward to Prometheus
    local port_forward_pid
    kubectl port-forward svc/prometheus-server -n $NAMESPACE_MONITORING 9090:80 &> /dev/null &
    port_forward_pid=$!
    
    sleep 3
    
    # Test key queries used in dashboards
    local queries=(
        "up"
        "kube_node_info"
        "kube_pod_info"
    )
    
    local query_success=true
    
    for query in "${queries[@]}"; do
        if ! curl -s --max-time 5 "http://localhost:9090/api/v1/query?query=${query}" | grep -q '"status":"success"'; then
            query_success=false
            break
        fi
    done
    
    kill $port_forward_pid 2>/dev/null || true
    
    if $query_success; then
        return 0
    else
        return 1
    fi
}

# Test 9: Check FinOps labels on workloads
test_finops_labels() {
    # Check if any workloads have FinOps labels
    local labels_found=false
    
    # Check deployments for FinOps labels
    if kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.labels.pipeline}{.metadata.labels.team}{.metadata.labels.env}{"\n"}{end}' 2>/dev/null | grep -q .; then
        labels_found=true
    fi
    
    # Check pods for FinOps labels
    if kubectl get pods --all-namespaces -o jsonpath='{range .items[*]}{.metadata.labels.pipeline}{.metadata.labels.team}{.metadata.labels.env}{"\n"}{end}' 2>/dev/null | grep -q .; then
        labels_found=true
    fi
    
    if $labels_found; then
        return 0
    else
        warn "No FinOps labels found on workloads. Dashboards may show empty data."
        return 1
    fi
}

# Test 10: Test Grafana API access
test_grafana_api() {
    if ! kubectl get service grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        return 1
    fi
    
    # Port forward and test Grafana API
    local port_forward_pid
    kubectl port-forward svc/grafana -n $NAMESPACE_MONITORING 3000:80 &> /dev/null &
    port_forward_pid=$!
    
    sleep 3
    
    # Test if we can reach Grafana health endpoint
    if curl -s --max-time 5 http://localhost:3000/api/health | grep -q '"database":"ok"'; then
        kill $port_forward_pid 2>/dev/null || true
        return 0
    fi
    
    kill $port_forward_pid 2>/dev/null || true
    return 1
}

# Performance test: Check dashboard load time
test_dashboard_performance() {
    # This is a placeholder for more sophisticated performance testing
    # In a real environment, you might test dashboard rendering time
    
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Count panels in dashboards (more panels = potentially slower load)
    local total_panels=0
    
    for dashboard in "$script_dir/dashboards"/*.json; do
        if [[ -f "$dashboard" ]]; then
            local panel_count=$(python3 -c "
import json
with open('$dashboard') as f:
    data = json.load(f)
    print(len(data.get('panels', [])))
" 2>/dev/null || echo "0")
            
            total_panels=$((total_panels + panel_count))
        fi
    done
    
    # Reasonable threshold: less than 50 total panels
    if [[ $total_panels -lt 50 ]]; then
        info "Total dashboard panels: $total_panels"
        return 0
    else
        warn "High panel count ($total_panels) may impact dashboard performance"
        return 1
    fi
}

# Generate dashboard usage report
generate_usage_report() {
    log "Generating dashboard usage report..."
    
    local report_file="/tmp/grafana-dashboard-report-$(date +%Y%m%d-%H%M%S).txt"
    
    {
        echo "NeuroNews Grafana FinOps Dashboards Report"
        echo "Generated: $(date)"
        echo "=========================================="
        echo
        
        echo "Dashboard Files:"
        echo "=================="
        local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
        for dashboard in "$script_dir/dashboards"/*.json; do
            if [[ -f "$dashboard" ]]; then
                local filename=$(basename "$dashboard")
                local title=$(python3 -c "
import json
with open('$dashboard') as f:
    data = json.load(f)
    print(data.get('title', 'Unknown'))
" 2>/dev/null || echo "Unknown")
                
                local panels=$(python3 -c "
import json
with open('$dashboard') as f:
    data = json.load(f)
    print(len(data.get('panels', [])))
" 2>/dev/null || echo "0")
                
                echo "• $filename: '$title' ($panels panels)"
            fi
        done
        
        echo
        echo "Kubernetes Resources:"
        echo "===================="
        kubectl get configmap grafana-dashboards-finops -n $NAMESPACE_MONITORING -o yaml 2>/dev/null | head -10 || echo "ConfigMap not found"
        
        echo
        echo "Service Status:"
        echo "==============="
        kubectl get deployments -n $NAMESPACE_MONITORING 2>/dev/null | grep -E "(grafana|prometheus)" || echo "No monitoring deployments found"
        kubectl get deployments -n $NAMESPACE_OPENCOST 2>/dev/null | grep opencost || echo "OpenCost not found"
        
        echo
        echo "FinOps Label Coverage:"
        echo "====================="
        echo "Deployments with pipeline labels:"
        kubectl get deployments --all-namespaces -o jsonpath='{range .items[*]}{.metadata.namespace}{"\t"}{.metadata.name}{"\t"}{.metadata.labels.pipeline}{"\n"}{end}' 2>/dev/null | grep -v "^.*\t$" | head -10 || echo "No labeled deployments found"
        
    } > "$report_file"
    
    info "Dashboard report generated: $report_file"
    cat "$report_file"
}

# Cleanup function
cleanup() {
    # Kill any remaining port-forward processes
    pkill -f "kubectl port-forward" 2>/dev/null || true
}

# Main test runner
main() {
    log "Starting NeuroNews Grafana FinOps Dashboards Test Suite"
    echo
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    # Run tests
    run_test "Prerequisites check" test_prerequisites
    run_test "Grafana deployment status" test_grafana_deployment
    run_test "OpenCost deployment status" test_opencost_deployment
    run_test "Dashboard ConfigMaps exist" test_dashboard_configmaps
    run_test "Dashboard JSON structure valid" test_dashboard_json_structure
    run_test "Prometheus connectivity" test_prometheus_connectivity
    run_test "OpenCost metrics available" test_opencost_metrics
    run_test "PromQL queries functional" test_promql_queries
    run_test "FinOps labels present" test_finops_labels
    run_test "Grafana API accessible" test_grafana_api
    run_test "Dashboard performance acceptable" test_dashboard_performance
    
    # Generate report
    generate_usage_report
    
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
        success "All tests passed! Grafana FinOps dashboards are ready to use."
        echo
        info "Access dashboards at:"
        info "• OpenCost Overview (folder: OpenCost)"
        info "• NeuroNews FinOps (folder: FinOps)"
        exit 0
    else
        error "Some tests failed. Review the output above and check prerequisites."
        echo
        info "Common fixes:"
        info "• Install/configure OpenCost for cost metrics"
        info "• Apply FinOps labels to workloads"
        info "• Ensure Prometheus is scraping metrics"
        info "• Run ./install.sh to deploy dashboards"
        exit 1
    fi
}

# Handle command line arguments
case "${1:-test}" in
    "test")
        main
        ;;
    "report")
        generate_usage_report
        ;;
    *)
        echo "Usage: $0 [test|report]"
        echo
        echo "  test   - Run complete test suite (default)"
        echo "  report - Generate usage report only"
        exit 1
        ;;
esac
