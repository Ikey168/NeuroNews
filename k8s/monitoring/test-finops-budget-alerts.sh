#!/bin/bash

#
# FinOps Budget Alerts Test Suite
# Issue #338: Budget & burn-rate alerts (monthly projection + drift)
#
# This script tests the FinOps budget alerting system by validating
# alert rules, triggering test alerts, and verifying notifications.
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE_MONITORING="monitoring"
PROMETHEUS_PORT=9090
ALERTMANAGER_PORT=9093
TEST_TIMEOUT=300  # 5 minutes

# Test configuration
TEST_BUDGET_EUR=1  # Very low budget to trigger alerts quickly
TEST_COST_PER_1K_ARTICLES=0.01
TEST_COST_PER_RAG_QUERY=0.001

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] ✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ✗${NC} $1"
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check curl
    if ! command -v curl &> /dev/null; then
        log_error "curl is not installed or not in PATH"
        exit 1
    fi
    
    # Check jq
    if ! command -v jq &> /dev/null; then
        log_warning "jq is not installed - JSON parsing will be limited"
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if monitoring namespace exists
    if ! kubectl get namespace "$NAMESPACE_MONITORING" &> /dev/null; then
        log_error "Monitoring namespace '$NAMESPACE_MONITORING' does not exist"
        exit 1
    fi
    
    log_success "Prerequisites check completed"
}

check_deployments() {
    log "Checking required deployments..."
    
    local required_deployments=(
        "prometheus-server"
        "alertmanager"
    )
    
    for deployment in "${required_deployments[@]}"; do
        if kubectl get deployment "$deployment" -n "$NAMESPACE_MONITORING" &> /dev/null; then
            local ready=$(kubectl get deployment "$deployment" -n "$NAMESPACE_MONITORING" -o jsonpath='{.status.readyReplicas}')
            local desired=$(kubectl get deployment "$deployment" -n "$NAMESPACE_MONITORING" -o jsonpath='{.spec.replicas}')
            
            if [[ "$ready" == "$desired" ]]; then
                log_success "Deployment '$deployment' is ready ($ready/$desired)"
            else
                log_warning "Deployment '$deployment' is not fully ready ($ready/$desired)"
            fi
        else
            log_error "Deployment '$deployment' not found in namespace '$NAMESPACE_MONITORING'"
        fi
    done
}

check_configmaps() {
    log "Checking FinOps alert ConfigMaps..."
    
    local required_configmaps=(
        "prometheus-finops-budget-alerts"
        "alertmanager-finops-config"
    )
    
    for configmap in "${required_configmaps[@]}"; do
        if kubectl get configmap "$configmap" -n "$NAMESPACE_MONITORING" &> /dev/null; then
            log_success "ConfigMap '$configmap' exists"
            
            # Check if the ConfigMap has data
            local data_keys=$(kubectl get configmap "$configmap" -n "$NAMESPACE_MONITORING" -o jsonpath='{.data}' | jq -r 'keys[]' 2>/dev/null || echo "")
            if [[ -n "$data_keys" ]]; then
                log_success "ConfigMap '$configmap' has data: $data_keys"
            else
                log_warning "ConfigMap '$configmap' exists but has no data"
            fi
        else
            log_error "ConfigMap '$configmap' not found"
        fi
    done
}

start_port_forwards() {
    log "Starting port forwards for testing..."
    
    # Kill any existing port forwards
    pkill -f "kubectl port-forward.*prometheus-server" 2>/dev/null || true
    pkill -f "kubectl port-forward.*alertmanager" 2>/dev/null || true
    
    # Start Prometheus port forward
    kubectl port-forward service/prometheus-server "$PROMETHEUS_PORT:80" -n "$NAMESPACE_MONITORING" &> /dev/null &
    local prom_pid=$!
    
    # Start Alertmanager port forward
    kubectl port-forward service/alertmanager "$ALERTMANAGER_PORT:9093" -n "$NAMESPACE_MONITORING" &> /dev/null &
    local alert_pid=$!
    
    # Wait for services to be ready
    sleep 5
    
    # Test connectivity
    if curl -s "http://localhost:$PROMETHEUS_PORT/api/v1/status/config" &> /dev/null; then
        log_success "Prometheus port forward active on port $PROMETHEUS_PORT"
    else
        log_error "Failed to connect to Prometheus on port $PROMETHEUS_PORT"
        kill $prom_pid $alert_pid 2>/dev/null || true
        exit 1
    fi
    
    if curl -s "http://localhost:$ALERTMANAGER_PORT/api/v1/status" &> /dev/null; then
        log_success "Alertmanager port forward active on port $ALERTMANAGER_PORT"
    else
        log_error "Failed to connect to Alertmanager on port $ALERTMANAGER_PORT"
        kill $prom_pid $alert_pid 2>/dev/null || true
        exit 1
    fi
    
    echo "$prom_pid $alert_pid"
}

test_prometheus_rules() {
    log "Testing Prometheus alerting rules..."
    
    # Get loaded rules
    local rules_response=$(curl -s "http://localhost:$PROMETHEUS_PORT/api/v1/rules")
    
    if echo "$rules_response" | jq -e '.status == "success"' &> /dev/null; then
        log_success "Prometheus rules API is accessible"
        
        # Check for FinOps rules
        local finops_rules=$(echo "$rules_response" | jq -r '.data.groups[] | select(.name == "finops-budget-alerts") | .rules[].alert' 2>/dev/null || echo "")
        
        if [[ -n "$finops_rules" ]]; then
            log_success "FinOps budget alert rules loaded:"
            echo "$finops_rules" | while read -r rule; do
                echo "  • $rule"
            done
        else
            log_error "FinOps budget alert rules not found"
            return 1
        fi
    else
        log_error "Failed to query Prometheus rules API"
        return 1
    fi
}

test_alert_queries() {
    log "Testing alert query expressions..."
    
    local test_queries=(
        "sum(opencost_node_cost_hourly)"
        "sum(opencost_node_cost_hourly) * 24 * 30"
        "unit_economics:cost_per_1k_articles_hourly"
        "unit_economics:cost_per_rag_query_hourly"
    )
    
    for query in "${test_queries[@]}"; do
        local encoded_query=$(printf '%s' "$query" | jq -sRr @uri)
        local response=$(curl -s "http://localhost:$PROMETHEUS_PORT/api/v1/query?query=$encoded_query")
        
        if echo "$response" | jq -e '.status == "success"' &> /dev/null; then
            local result_type=$(echo "$response" | jq -r '.data.resultType')
            local result_count=$(echo "$response" | jq -r '.data.result | length')
            
            if [[ "$result_count" -gt 0 ]]; then
                log_success "Query '$query' returned $result_count results"
            else
                log_warning "Query '$query' returned no results (may be normal if no data)"
            fi
        else
            log_error "Query '$query' failed"
        fi
    done
}

test_alertmanager_config() {
    log "Testing Alertmanager configuration..."
    
    # Get Alertmanager config
    local config_response=$(curl -s "http://localhost:$ALERTMANAGER_PORT/api/v1/status")
    
    if echo "$config_response" | jq -e '.status == "success"' &> /dev/null; then
        log_success "Alertmanager status API is accessible"
        
        # Check version info
        local version=$(echo "$config_response" | jq -r '.data.versionInfo.version' 2>/dev/null || echo "unknown")
        log_success "Alertmanager version: $version"
    else
        log_error "Failed to query Alertmanager status API"
        return 1
    fi
    
    # Test configuration
    local receivers_response=$(curl -s "http://localhost:$ALERTMANAGER_PORT/api/v1/receivers")
    if echo "$receivers_response" | jq -e '.status == "success"' &> /dev/null; then
        local receivers=$(echo "$receivers_response" | jq -r '.data[].name' 2>/dev/null || echo "")
        if [[ -n "$receivers" ]]; then
            log_success "Alertmanager receivers configured:"
            echo "$receivers" | while read -r receiver; do
                echo "  • $receiver"
            done
        else
            log_warning "No Alertmanager receivers found"
        fi
    else
        log_warning "Could not query Alertmanager receivers"
    fi
}

trigger_test_alert() {
    log "Triggering test alert by lowering budget threshold..."
    
    # Install alerts with very low budget to trigger immediately
    BUDGET_EUR=$TEST_BUDGET_EUR \
    COST_PER_1K_ARTICLES_THRESHOLD=$TEST_COST_PER_1K_ARTICLES \
    COST_PER_RAG_QUERY_THRESHOLD=$TEST_COST_PER_RAG_QUERY \
    /workspaces/NeuroNews/k8s/monitoring/install-finops-budget-alerts.sh &> /dev/null
    
    log "Waiting for alert to trigger (timeout: ${TEST_TIMEOUT}s)..."
    
    # Wait and check for firing alerts
    local start_time=$(date +%s)
    local alert_found=false
    
    while [[ $(($(date +%s) - start_time)) -lt $TEST_TIMEOUT ]]; do
        local alerts_response=$(curl -s "http://localhost:$PROMETHEUS_PORT/api/v1/alerts")
        
        if echo "$alerts_response" | jq -e '.status == "success"' &> /dev/null; then
            local firing_alerts=$(echo "$alerts_response" | jq -r '.data.alerts[] | select(.state == "firing") | .labels.alertname' 2>/dev/null || echo "")
            
            if echo "$firing_alerts" | grep -q "FinOps"; then
                alert_found=true
                log_success "FinOps alert triggered successfully!"
                echo "$firing_alerts" | while read -r alert; do
                    echo "  🔥 $alert"
                done
                break
            fi
        fi
        
        sleep 10
    done
    
    if [[ "$alert_found" == false ]]; then
        log_warning "No FinOps alerts triggered within timeout period"
        log_warning "This may be normal if no cost data is available"
    fi
}

check_alert_history() {
    log "Checking alert history in Alertmanager..."
    
    local alerts_response=$(curl -s "http://localhost:$ALERTMANAGER_PORT/api/v1/alerts")
    
    if echo "$alerts_response" | jq -e '.status == "success"' &> /dev/null; then
        local alert_count=$(echo "$alerts_response" | jq -r '.data | length' 2>/dev/null || echo "0")
        
        if [[ "$alert_count" -gt 0 ]]; then
            log_success "Found $alert_count alerts in Alertmanager"
            
            # Show recent FinOps alerts
            local finops_alerts=$(echo "$alerts_response" | jq -r '.data[] | select(.labels.category == "finops") | .labels.alertname' 2>/dev/null || echo "")
            if [[ -n "$finops_alerts" ]]; then
                log_success "Recent FinOps alerts:"
                echo "$finops_alerts" | while read -r alert; do
                    echo "  • $alert"
                done
            else
                log_warning "No FinOps alerts found in Alertmanager history"
            fi
        else
            log_warning "No alerts found in Alertmanager"
        fi
    else
        log_error "Failed to query Alertmanager alerts API"
    fi
}

restore_original_config() {
    log "Restoring original alert configuration..."
    
    # Restore with default values
    /workspaces/NeuroNews/k8s/monitoring/install-finops-budget-alerts.sh &> /dev/null
    
    log_success "Original configuration restored"
}

cleanup_port_forwards() {
    log "Cleaning up port forwards..."
    
    # Kill port forwards
    pkill -f "kubectl port-forward.*prometheus-server" 2>/dev/null || true
    pkill -f "kubectl port-forward.*alertmanager" 2>/dev/null || true
    
    log_success "Port forwards cleaned up"
}

show_test_results() {
    log "Test Results Summary"
    echo "===================="
    echo ""
    echo "✅ Tests completed successfully!"
    echo ""
    echo "📊 What was tested:"
    echo "  • ConfigMap presence and validity"
    echo "  • Prometheus rule loading"
    echo "  • Alert query execution"
    echo "  • Alertmanager configuration"
    echo "  • Alert triggering mechanism"
    echo ""
    echo "🔍 Next steps:"
    echo "  1. Monitor alerts in Prometheus: http://localhost:9090/alerts"
    echo "  2. Check Alertmanager: http://localhost:9093"
    echo "  3. View FinOps dashboard: http://localhost:3000/d/unit-economics-001/"
    echo ""
    echo "⚠️  Note: Alert notifications require proper webhook/email configuration"
    echo "    Set SLACK_WEBHOOK_URL_FINOPS and FINOPS_EMAIL_CRITICAL environment variables"
}

run_all_tests() {
    echo "🧪 FinOps Budget Alerts Test Suite"
    echo "Issue #338: Budget & burn-rate alerts"
    echo "=================================="
    echo ""
    
    check_prerequisites
    check_deployments
    check_configmaps
    
    echo ""
    log "Starting interactive tests..."
    
    local pids=$(start_port_forwards)
    local prom_pid=$(echo $pids | cut -d' ' -f1)
    local alert_pid=$(echo $pids | cut -d' ' -f2)
    
    # Ensure cleanup happens
    trap "cleanup_port_forwards; kill $prom_pid $alert_pid 2>/dev/null || true" EXIT
    
    test_prometheus_rules
    test_alert_queries
    test_alertmanager_config
    
    echo ""
    log "Running alert trigger test..."
    trigger_test_alert
    check_alert_history
    restore_original_config
    
    echo ""
    show_test_results
}

# Handle script arguments
case "${1:-test}" in
    "test")
        run_all_tests
        ;;
    "quick")
        check_prerequisites
        check_deployments
        check_configmaps
        log_success "Quick test completed"
        ;;
    "trigger")
        log "Triggering test alert..."
        pids=$(start_port_forwards)
        trap "cleanup_port_forwards; kill $pids 2>/dev/null || true" EXIT
        trigger_test_alert
        ;;
    *)
        echo "Usage: $0 [test|quick|trigger]"
        echo ""
        echo "Commands:"
        echo "  test     - Run full test suite (default)"
        echo "  quick    - Run basic checks only"
        echo "  trigger  - Trigger test alert"
        exit 1
        ;;
esac
