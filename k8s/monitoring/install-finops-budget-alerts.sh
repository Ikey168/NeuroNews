#!/bin/bash

#
# FinOps Budget Alerts Installation Script
# Issue #338: Budget & burn-rate alerts (monthly projection + drift)
#
# This script installs Prometheus alerting rules and Alertmanager configuration
# for FinOps budget monitoring and cost drift detection.
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
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$SCRIPT_DIR/../k8s/monitoring"

# Default budget values (can be overridden via environment variables)
BUDGET_EUR="${BUDGET_EUR:-5000}"
COST_PER_1K_ARTICLES_THRESHOLD="${COST_PER_1K_ARTICLES_THRESHOLD:-2.0}"
COST_PER_RAG_QUERY_THRESHOLD="${COST_PER_RAG_QUERY_THRESHOLD:-0.05}"

# Notification settings
SLACK_WEBHOOK_URL_FINOPS="${SLACK_WEBHOOK_URL_FINOPS:-}"
FINOPS_EMAIL_CRITICAL="${FINOPS_EMAIL_CRITICAL:-platform-team@neuronews.io}"

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
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check if monitoring namespace exists
    if ! kubectl get namespace "$NAMESPACE_MONITORING" &> /dev/null; then
        log_error "Monitoring namespace '$NAMESPACE_MONITORING' does not exist"
        log "Please create the monitoring namespace first:"
        log "kubectl create namespace $NAMESPACE_MONITORING"
        exit 1
    fi
    
    # Check if Prometheus is running
    if ! kubectl get deployment prometheus-server -n "$NAMESPACE_MONITORING" &> /dev/null; then
        log_warning "Prometheus server deployment not found in namespace '$NAMESPACE_MONITORING'"
        log_warning "Alerts will not work without Prometheus"
    fi
    
    # Check if Alertmanager is running
    if ! kubectl get deployment alertmanager -n "$NAMESPACE_MONITORING" &> /dev/null; then
        log_warning "Alertmanager deployment not found in namespace '$NAMESPACE_MONITORING'"
        log_warning "Alert notifications will not work without Alertmanager"
    fi
    
    # Check if OpenCost is available
    if ! kubectl get deployment opencost -n opencost &> /dev/null 2>&1; then
        log_warning "OpenCost deployment not found"
        log_warning "Cost-based alerts require OpenCost to be installed"
        log_warning "See: https://opencost.io/docs/install"
    fi
    
    log_success "Prerequisites check completed"
}

show_configuration() {
    log "FinOps Budget Alerts Configuration:"
    echo "  📊 Monthly Budget: €$BUDGET_EUR"
    echo "  📰 Cost per 1k Articles Threshold: €$COST_PER_1K_ARTICLES_THRESHOLD"
    echo "  🤖 Cost per RAG Query Threshold: €$COST_PER_RAG_QUERY_THRESHOLD"
    echo "  📧 Critical Alerts Email: $FINOPS_EMAIL_CRITICAL"
    echo "  🔔 Slack Webhook: ${SLACK_WEBHOOK_URL_FINOPS:-'Not configured'}"
    echo "  🎯 Target Namespace: $NAMESPACE_MONITORING"
    echo ""
}

substitute_variables() {
    local file="$1"
    local temp_file=$(mktemp)
    
    # Substitute environment variables in the file
    envsubst < "$file" > "$temp_file"
    
    # Replace template variables with actual values
    sed -i "s/\${BUDGET_EUR:5000}/$BUDGET_EUR/g" "$temp_file"
    sed -i "s/\${COST_PER_1K_ARTICLES_THRESHOLD:2.0}/$COST_PER_1K_ARTICLES_THRESHOLD/g" "$temp_file"
    sed -i "s/\${COST_PER_RAG_QUERY_THRESHOLD:0.05}/$COST_PER_RAG_QUERY_THRESHOLD/g" "$temp_file"
    sed -i "s/\${FINOPS_EMAIL_CRITICAL:platform-team@neuronews.io}/$FINOPS_EMAIL_CRITICAL/g" "$temp_file"
    
    echo "$temp_file"
}

install_alerting_rules() {
    log "Installing Prometheus alerting rules..."
    
    local rules_file="$K8S_DIR/prometheus-finops-budget-alerts.yaml"
    if [[ ! -f "$rules_file" ]]; then
        log_error "Alerting rules file not found: $rules_file"
        exit 1
    fi
    
    # Substitute variables and apply
    local temp_file=$(substitute_variables "$rules_file")
    
    if kubectl apply -f "$temp_file" -n "$NAMESPACE_MONITORING"; then
        log_success "Prometheus alerting rules installed successfully"
    else
        log_error "Failed to install Prometheus alerting rules"
        rm -f "$temp_file"
        exit 1
    fi
    
    rm -f "$temp_file"
    
    # Verify the ConfigMap was created
    if kubectl get configmap prometheus-finops-budget-alerts -n "$NAMESPACE_MONITORING" &> /dev/null; then
        log_success "Alerting rules ConfigMap created successfully"
    else
        log_error "Failed to create alerting rules ConfigMap"
        exit 1
    fi
}

install_alertmanager_config() {
    log "Installing Alertmanager configuration..."
    
    local config_file="$K8S_DIR/alertmanager-finops-config.yaml"
    if [[ ! -f "$config_file" ]]; then
        log_error "Alertmanager config file not found: $config_file"
        exit 1
    fi
    
    # Check if Slack webhook is configured
    if [[ -z "$SLACK_WEBHOOK_URL_FINOPS" ]]; then
        log_warning "SLACK_WEBHOOK_URL_FINOPS not set - Slack notifications will not work"
        log_warning "Set this environment variable to enable Slack alerts"
    fi
    
    # Substitute variables and apply
    local temp_file=$(substitute_variables "$config_file")
    
    if kubectl apply -f "$temp_file" -n "$NAMESPACE_MONITORING"; then
        log_success "Alertmanager configuration installed successfully"
    else
        log_error "Failed to install Alertmanager configuration"
        rm -f "$temp_file"
        exit 1
    fi
    
    rm -f "$temp_file"
    
    # Verify the ConfigMap was created
    if kubectl get configmap alertmanager-finops-config -n "$NAMESPACE_MONITORING" &> /dev/null; then
        log_success "Alertmanager config ConfigMap created successfully"
    else
        log_error "Failed to create Alertmanager config ConfigMap"
        exit 1
    fi
}

restart_prometheus() {
    log "Restarting Prometheus to pick up new alerting rules..."
    
    if kubectl get deployment prometheus-server -n "$NAMESPACE_MONITORING" &> /dev/null; then
        kubectl rollout restart deployment/prometheus-server -n "$NAMESPACE_MONITORING"
        
        # Wait for rollout to complete
        if kubectl rollout status deployment/prometheus-server -n "$NAMESPACE_MONITORING" --timeout=300s; then
            log_success "Prometheus restarted successfully"
        else
            log_error "Prometheus restart failed or timed out"
            exit 1
        fi
    else
        log_warning "Prometheus server deployment not found - skipping restart"
    fi
}

restart_alertmanager() {
    log "Restarting Alertmanager to pick up new configuration..."
    
    if kubectl get deployment alertmanager -n "$NAMESPACE_MONITORING" &> /dev/null; then
        kubectl rollout restart deployment/alertmanager -n "$NAMESPACE_MONITORING"
        
        # Wait for rollout to complete
        if kubectl rollout status deployment/alertmanager -n "$NAMESPACE_MONITORING" --timeout=300s; then
            log_success "Alertmanager restarted successfully"
        else
            log_error "Alertmanager restart failed or timed out"
            exit 1
        fi
    else
        log_warning "Alertmanager deployment not found - skipping restart"
    fi
}

verify_installation() {
    log "Verifying installation..."
    
    # Check if ConfigMaps exist
    local configs=(
        "prometheus-finops-budget-alerts"
        "alertmanager-finops-config"
    )
    
    for config in "${configs[@]}"; do
        if kubectl get configmap "$config" -n "$NAMESPACE_MONITORING" &> /dev/null; then
            log_success "ConfigMap '$config' exists"
        else
            log_error "ConfigMap '$config' not found"
        fi
    done
    
    # Check Prometheus targets (if accessible)
    log "Checking Prometheus targets..."
    if command -v curl &> /dev/null && kubectl get service prometheus-server -n "$NAMESPACE_MONITORING" &> /dev/null; then
        local prometheus_port=$(kubectl get service prometheus-server -n "$NAMESPACE_MONITORING" -o jsonpath='{.spec.ports[0].port}')
        if kubectl port-forward service/prometheus-server "$prometheus_port:$prometheus_port" -n "$NAMESPACE_MONITORING" &> /dev/null & then
            local pf_pid=$!
            sleep 3
            
            if curl -s "http://localhost:$prometheus_port/api/v1/targets" &> /dev/null; then
                log_success "Prometheus is accessible"
            else
                log_warning "Prometheus is not accessible via port-forward"
            fi
            
            kill $pf_pid 2>/dev/null || true
        fi
    fi
    
    log_success "Installation verification completed"
}

show_next_steps() {
    log "Installation completed successfully! 🎉"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. 📊 Verify alerts in Prometheus:"
    echo "   kubectl port-forward service/prometheus-server 9090:80 -n $NAMESPACE_MONITORING"
    echo "   Open: http://localhost:9090/alerts"
    echo ""
    echo "2. 🔔 Check Alertmanager:"
    echo "   kubectl port-forward service/alertmanager 9093:9093 -n $NAMESPACE_MONITORING"
    echo "   Open: http://localhost:9093"
    echo ""
    echo "3. 🧪 Test budget alert (temporarily lower budget):"
    echo "   BUDGET_EUR=1 $0"
    echo "   (Wait 30-60 minutes for alert to fire)"
    echo ""
    echo "4. 📈 View FinOps dashboards:"
    echo "   kubectl port-forward service/grafana 3000:80 -n $NAMESPACE_MONITORING"
    echo "   Open: http://localhost:3000/d/unit-economics-001/unit-economics-cost-per-outcome"
    echo ""
    echo "5. ⚙️ Configure notification channels:"
    echo "   Set SLACK_WEBHOOK_URL_FINOPS for Slack notifications"
    echo "   Update FINOPS_EMAIL_CRITICAL for email alerts"
    echo ""
    echo "📋 Current thresholds:"
    echo "   • Monthly Budget: €$BUDGET_EUR"
    echo "   • Cost per 1k Articles: €$COST_PER_1K_ARTICLES_THRESHOLD"
    echo "   • Cost per RAG Query: €$COST_PER_RAG_QUERY_THRESHOLD"
    echo ""
    echo "💡 To update thresholds, set environment variables and re-run this script."
}

main() {
    echo "🚨 FinOps Budget Alerts Installation"
    echo "Issue #338: Budget & burn-rate alerts (monthly projection + drift)"
    echo "=================================="
    echo ""
    
    show_configuration
    check_prerequisites
    
    echo ""
    log "Starting installation..."
    
    install_alerting_rules
    install_alertmanager_config
    restart_prometheus
    restart_alertmanager
    verify_installation
    
    echo ""
    show_next_steps
}

# Handle script arguments
case "${1:-install}" in
    "install")
        main
        ;;
    "uninstall")
        log "Uninstalling FinOps budget alerts..."
        kubectl delete configmap prometheus-finops-budget-alerts -n "$NAMESPACE_MONITORING" --ignore-not-found
        kubectl delete configmap alertmanager-finops-config -n "$NAMESPACE_MONITORING" --ignore-not-found
        log_success "Uninstallation completed"
        ;;
    "verify")
        check_prerequisites
        verify_installation
        ;;
    *)
        echo "Usage: $0 [install|uninstall|verify]"
        echo ""
        echo "Environment variables:"
        echo "  BUDGET_EUR=5000                              # Monthly budget in EUR"
        echo "  COST_PER_1K_ARTICLES_THRESHOLD=2.0          # Cost per 1k articles threshold"
        echo "  COST_PER_RAG_QUERY_THRESHOLD=0.05           # Cost per RAG query threshold"
        echo "  SLACK_WEBHOOK_URL_FINOPS=<webhook_url>      # Slack webhook for notifications"
        echo "  FINOPS_EMAIL_CRITICAL=platform@company.com  # Email for critical alerts"
        exit 1
        ;;
esac
