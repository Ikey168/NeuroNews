#!/bin/bash

"""
Unit Economics Monitoring Test Suite
Issue #337: Unit economics: "€ per 1k articles" & "€ per RAG query"

This script provides comprehensive testing for the unit economics monitoring system,
verifying dashboard functionality, metrics availability, and cost calculations.
"""

set -euo pipefail

# Configuration
NAMESPACE_MONITORING="monitoring"
NAMESPACE_OPENCOST="opencost"
PROMETHEUS_PORT="9090"
GRAFANA_PORT="3000"
OPENCOST_PORT="9003"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] ✅ $1${NC}"
    ((TESTS_PASSED++))
}

fail() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ❌ $1${NC}"
    ((TESTS_FAILED++))
}

warning() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠️  $1${NC}"
}

run_test() {
    ((TESTS_RUN++))
    local test_name="$1"
    local test_command="$2"
    
    log "Running test: $test_name"
    
    if eval "$test_command"; then
        success "$test_name"
        return 0
    else
        fail "$test_name"
        return 1
    fi
}

test_prerequisites() {
    log "Testing prerequisites..."
    
    run_test "kubectl available" "command -v kubectl >/dev/null 2>&1"
    run_test "kubectl cluster connectivity" "kubectl cluster-info >/dev/null 2>&1"
    run_test "monitoring namespace exists" "kubectl get namespace ${NAMESPACE_MONITORING} >/dev/null 2>&1"
    
    # Optional services
    if kubectl get deployment prometheus-server -n "${NAMESPACE_MONITORING}" >/dev/null 2>&1; then
        success "Prometheus deployment found"
    else
        warning "Prometheus deployment not found"
    fi
    
    if kubectl get deployment grafana -n "${NAMESPACE_MONITORING}" >/dev/null 2>&1; then
        success "Grafana deployment found"
    else
        warning "Grafana deployment not found"
    fi
    
    if kubectl get namespace "${NAMESPACE_OPENCOST}" >/dev/null 2>&1; then
        if kubectl get deployment opencost -n "${NAMESPACE_OPENCOST}" >/dev/null 2>&1; then
            success "OpenCost deployment found"
        else
            warning "OpenCost namespace exists but deployment not found"
        fi
    else
        warning "OpenCost namespace not found"
    fi
}

test_configmaps() {
    log "Testing ConfigMaps installation..."
    
    run_test "Prometheus rules ConfigMap exists" \
        "kubectl get configmap prometheus-unit-economics-rules -n ${NAMESPACE_MONITORING} >/dev/null 2>&1"
    
    run_test "Grafana dashboard ConfigMap exists" \
        "kubectl get configmap unit-economics-dashboard -n ${NAMESPACE_MONITORING} >/dev/null 2>&1"
    
    run_test "Dashboard ConfigMap has correct label" \
        "kubectl get configmap unit-economics-dashboard -n ${NAMESPACE_MONITORING} -o jsonpath='{.metadata.labels.grafana_dashboard}' | grep -q '1'"
}

test_prometheus_rules() {
    log "Testing Prometheus recording rules..."
    
    # Check if rules are present in ConfigMap
    run_test "Unit economics rules in ConfigMap" \
        "kubectl get configmap prometheus-unit-economics-rules -n ${NAMESPACE_MONITORING} -o yaml | grep -q 'unit-economics'"
    
    run_test "Cost recording rules present" \
        "kubectl get configmap prometheus-unit-economics-rules -n ${NAMESPACE_MONITORING} -o yaml | grep -q 'cost:cluster_hourly:sum'"
    
    run_test "Business metrics rules present" \
        "kubectl get configmap prometheus-unit-economics-rules -n ${NAMESPACE_MONITORING} -o yaml | grep -q 'articles:rate_1h'"
    
    run_test "Unit economics calculation rules present" \
        "kubectl get configmap prometheus-unit-economics-rules -n ${NAMESPACE_MONITORING} -o yaml | grep -q 'unit_economics:cost_per_1k_articles_hourly'"
}

test_grafana_dashboard() {
    log "Testing Grafana dashboard configuration..."
    
    run_test "Dashboard JSON in ConfigMap" \
        "kubectl get configmap unit-economics-dashboard -n ${NAMESPACE_MONITORING} -o jsonpath='{.data.unit-economics\.json}' | jq . >/dev/null 2>&1"
    
    run_test "Dashboard has correct title" \
        "kubectl get configmap unit-economics-dashboard -n ${NAMESPACE_MONITORING} -o jsonpath='{.data.unit-economics\.json}' | jq -r '.title' | grep -q 'Unit Economics'"
    
    run_test "Dashboard has unit economics panels" \
        "kubectl get configmap unit-economics-dashboard -n ${NAMESPACE_MONITORING} -o jsonpath='{.data.unit-economics\.json}' | jq -r '.panels[].title' | grep -q 'per 1000 Articles'"
    
    run_test "Dashboard has RAG query panels" \
        "kubectl get configmap unit-economics-dashboard -n ${NAMESPACE_MONITORING} -o jsonpath='{.data.unit-economics\.json}' | jq -r '.panels[].title' | grep -q 'per RAG Query'"
}

start_port_forwards() {
    log "Starting port forwards for testing..."
    
    # Prometheus port forward
    if kubectl get deployment prometheus-server -n "${NAMESPACE_MONITORING}" >/dev/null 2>&1; then
        kubectl port-forward svc/prometheus-server "${PROMETHEUS_PORT}:80" -n "${NAMESPACE_MONITORING}" >/dev/null 2>&1 &
        PROMETHEUS_PF_PID=$!
        sleep 3
        log "Prometheus port forward started (PID: $PROMETHEUS_PF_PID)"
    fi
    
    # Grafana port forward
    if kubectl get deployment grafana -n "${NAMESPACE_MONITORING}" >/dev/null 2>&1; then
        kubectl port-forward svc/grafana "${GRAFANA_PORT}:80" -n "${NAMESPACE_MONITORING}" >/dev/null 2>&1 &
        GRAFANA_PF_PID=$!
        sleep 3
        log "Grafana port forward started (PID: $GRAFANA_PF_PID)"
    fi
    
    # OpenCost port forward
    if kubectl get deployment opencost -n "${NAMESPACE_OPENCOST}" >/dev/null 2>&1; then
        kubectl port-forward svc/opencost "${OPENCOST_PORT}:9003" -n "${NAMESPACE_OPENCOST}" >/dev/null 2>&1 &
        OPENCOST_PF_PID=$!
        sleep 3
        log "OpenCost port forward started (PID: $OPENCOST_PF_PID)"
    fi
}

test_service_connectivity() {
    log "Testing service connectivity..."
    
    if [[ -n "${PROMETHEUS_PF_PID:-}" ]]; then
        run_test "Prometheus API accessible" \
            "curl -s --max-time 5 http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=up | jq -r '.status' | grep -q success"
    else
        warning "Prometheus port forward not available, skipping connectivity test"
    fi
    
    if [[ -n "${GRAFANA_PF_PID:-}" ]]; then
        run_test "Grafana API accessible" \
            "curl -s --max-time 5 http://localhost:${GRAFANA_PORT}/api/health | jq -r '.status' | grep -q ok"
    else
        warning "Grafana port forward not available, skipping connectivity test"
    fi
    
    if [[ -n "${OPENCOST_PF_PID:-}" ]]; then
        run_test "OpenCost metrics accessible" \
            "curl -s --max-time 5 http://localhost:${OPENCOST_PORT}/metrics | grep -q opencost_"
    else
        warning "OpenCost port forward not available, skipping connectivity test"
    fi
}

test_prometheus_metrics() {
    log "Testing Prometheus metrics availability..."
    
    if [[ -z "${PROMETHEUS_PF_PID:-}" ]]; then
        warning "Prometheus not available, skipping metrics tests"
        return
    fi
    
    # Test basic cluster metrics
    run_test "Kubernetes metrics available" \
        "curl -s 'http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=up' | jq -r '.status' | grep -q success"
    
    # Test if business counter metrics are available (may not have data yet)
    local articles_query="neuro_articles_ingested_total"
    local rag_query="neuro_rag_queries_total"
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${articles_query}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Articles ingested metrics found"
    else
        warning "Articles ingested metrics not found (may not have data yet)"
    fi
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${rag_query}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "RAG queries metrics found"
    else
        warning "RAG queries metrics not found (may not have data yet)"
    fi
    
    # Test recording rules (may not be active yet)
    local cost_rule="cost:cluster_hourly:sum"
    local articles_rule="articles:rate_1h"
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${cost_rule}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Cost recording rule working"
    else
        warning "Cost recording rule not active (OpenCost may not be available)"
    fi
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${articles_rule}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Articles rate recording rule working"
    else
        warning "Articles rate recording rule not active (may not have data yet)"
    fi
}

test_unit_economics_calculations() {
    log "Testing unit economics calculations..."
    
    if [[ -z "${PROMETHEUS_PF_PID:-}" ]]; then
        warning "Prometheus not available, skipping calculation tests"
        return
    fi
    
    # Test unit economics recording rules
    local cost_per_articles="unit_economics:cost_per_1k_articles_hourly"
    local cost_per_rag="unit_economics:cost_per_rag_query_hourly"
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${cost_per_articles}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Cost per 1k articles calculation working"
        
        # Get the actual value
        local articles_cost=$(curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${cost_per_articles}" | jq -r '.data.result[0].value[1]')
        log "Current cost per 1k articles: €${articles_cost}"
    else
        warning "Cost per 1k articles calculation not active (requires both cost and articles data)"
    fi
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${cost_per_rag}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Cost per RAG query calculation working"
        
        # Get the actual value  
        local rag_cost=$(curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${cost_per_rag}" | jq -r '.data.result[0].value[1]')
        log "Current cost per RAG query: €${rag_cost}"
    else
        warning "Cost per RAG query calculation not active (requires both cost and query data)"
    fi
    
    # Test efficiency metrics
    local articles_per_euro="efficiency:articles_per_euro_hourly"
    local queries_per_euro="efficiency:queries_per_euro_hourly"
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${articles_per_euro}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Articles per euro calculation working"
    else
        warning "Articles per euro calculation not active"
    fi
    
    if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${queries_per_euro}" | jq -r '.data.result | length' | grep -q "^[1-9]"; then
        success "Queries per euro calculation working"
    else
        warning "Queries per euro calculation not active"
    fi
}

test_dashboard_queries() {
    log "Testing dashboard query validity..."
    
    if [[ -z "${PROMETHEUS_PF_PID:-}" ]]; then
        warning "Prometheus not available, skipping dashboard query tests"
        return
    fi
    
    # Extract queries from dashboard and test them
    local dashboard_json=$(kubectl get configmap unit-economics-dashboard -n "${NAMESPACE_MONITORING}" -o jsonpath='{.data.unit-economics\.json}')
    
    # Test each query from the dashboard
    local queries=(
        "unit_economics:cost_per_1k_articles_hourly"
        "unit_economics:cost_per_1k_articles_daily"
        "unit_economics:cost_per_rag_query_hourly"
        "unit_economics:cost_per_rag_query_daily"
        "efficiency:articles_per_euro_hourly"
        "efficiency:queries_per_euro_hourly"
        "articles:rate_1h"
        "ragq:rate_1h"
        "cost:cluster_hourly:sum"
    )
    
    for query in "${queries[@]}"; do
        if curl -s "http://localhost:${PROMETHEUS_PORT}/api/v1/query?query=${query}" | jq -r '.status' | grep -q "success"; then
            success "Dashboard query valid: $query"
        else
            fail "Dashboard query invalid: $query"
        fi
    done
}

cleanup_port_forwards() {
    log "Cleaning up port forwards..."
    
    if [[ -n "${PROMETHEUS_PF_PID:-}" ]]; then
        kill "${PROMETHEUS_PF_PID}" 2>/dev/null || true
        log "Stopped Prometheus port forward"
    fi
    
    if [[ -n "${GRAFANA_PF_PID:-}" ]]; then
        kill "${GRAFANA_PF_PID}" 2>/dev/null || true
        log "Stopped Grafana port forward"
    fi
    
    if [[ -n "${OPENCOST_PF_PID:-}" ]]; then
        kill "${OPENCOST_PF_PID}" 2>/dev/null || true
        log "Stopped OpenCost port forward"
    fi
}

show_test_summary() {
    echo ""
    echo "=========================================="
    echo "📊 Unit Economics Monitoring Test Summary"
    echo "=========================================="
    echo "Total tests run: ${TESTS_RUN}"
    echo -e "Tests passed: ${GREEN}${TESTS_PASSED}${NC}"
    echo -e "Tests failed: ${RED}${TESTS_FAILED}${NC}"
    
    local pass_rate=$((TESTS_PASSED * 100 / TESTS_RUN))
    echo "Pass rate: ${pass_rate}%"
    
    if [[ ${TESTS_FAILED} -eq 0 ]]; then
        echo -e "${GREEN}🎉 All tests passed!${NC}"
        return 0
    else
        echo -e "${RED}❌ Some tests failed${NC}"
        return 1
    fi
}

show_access_info() {
    echo ""
    echo "🚀 Access Information:"
    echo "======================"
    
    if [[ -n "${GRAFANA_PF_PID:-}" ]]; then
        echo "📊 Grafana Dashboard: http://localhost:${GRAFANA_PORT}"
        echo "   Look for 'Unit Economics - Cost per Outcome' dashboard"
    fi
    
    if [[ -n "${PROMETHEUS_PF_PID:-}" ]]; then
        echo "🔍 Prometheus: http://localhost:${PROMETHEUS_PORT}"
        echo "   Try queries: unit_economics:cost_per_1k_articles_hourly"
    fi
    
    if [[ -n "${OPENCOST_PF_PID:-}" ]]; then
        echo "💰 OpenCost: http://localhost:${OPENCOST_PORT}"
    fi
    
    echo ""
    echo "Press Ctrl+C to stop port forwards and exit..."
}

main() {
    echo "🧪 Unit Economics Monitoring Test Suite"
    echo "========================================"
    
    # Trap to cleanup on exit
    trap cleanup_port_forwards EXIT
    
    test_prerequisites
    test_configmaps
    test_prometheus_rules
    test_grafana_dashboard
    
    start_port_forwards
    
    test_service_connectivity
    test_prometheus_metrics
    test_unit_economics_calculations
    test_dashboard_queries
    
    if show_test_summary; then
        show_access_info
        
        # Keep port forwards running for manual testing
        read -p "Press Enter to exit and cleanup port forwards..."
    else
        error "Test suite failed. Check the errors above."
        exit 1
    fi
}

# Run main function
main "$@"
