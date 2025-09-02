#!/bin/bash

"""
Unit Economics Monitoring Installation Script
Issue #337: Unit economics: "€ per 1k articles" & "€ per RAG query"

This script installs the complete unit economics monitoring system including:
- Prometheus recording rules for cost and business metrics
- Grafana dashboard for unit economics visualization
- Service instrumentation for metrics collection
"""

set -euo pipefail

# Configuration
NAMESPACE_MONITORING="monitoring"
NAMESPACE_OPENCOST="opencost"
GRAFANA_DASHBOARD_CONFIG_NAME="unit-economics-dashboard"
PROMETHEUS_RULES_CONFIG_NAME="prometheus-unit-economics-rules"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] ✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] ⚠️  $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ❌ $1${NC}"
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    # Check monitoring namespace
    if ! kubectl get namespace "${NAMESPACE_MONITORING}" &> /dev/null; then
        warning "Monitoring namespace '${NAMESPACE_MONITORING}' does not exist. Creating it..."
        kubectl create namespace "${NAMESPACE_MONITORING}"
    fi
    
    # Check if Prometheus is running
    if ! kubectl get deployment prometheus-server -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        warning "Prometheus deployment not found in ${NAMESPACE_MONITORING} namespace"
        warning "Unit economics recording rules may not work without Prometheus"
    fi
    
    # Check if Grafana is running
    if ! kubectl get deployment grafana -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        warning "Grafana deployment not found in ${NAMESPACE_MONITORING} namespace"
        warning "Unit economics dashboard may not be accessible without Grafana"
    fi
    
    # Check if OpenCost is running
    if ! kubectl get namespace "${NAMESPACE_OPENCOST}" &> /dev/null; then
        warning "OpenCost namespace '${NAMESPACE_OPENCOST}' does not exist"
        warning "Cost metrics may not be available without OpenCost"
    elif ! kubectl get deployment opencost -n "${NAMESPACE_OPENCOST}" &> /dev/null; then
        warning "OpenCost deployment not found in ${NAMESPACE_OPENCOST} namespace"
        warning "Cost metrics may not be available without OpenCost"
    fi
    
    success "Prerequisites check completed"
}

install_prometheus_rules() {
    log "Installing Prometheus recording rules for unit economics..."
    
    local rules_file="${SCRIPT_DIR}/../k8s/monitoring/prometheus-unit-economics-rules.yaml"
    
    if [[ ! -f "${rules_file}" ]]; then
        error "Prometheus rules file not found: ${rules_file}"
        exit 1
    fi
    
    # Apply the recording rules ConfigMap
    kubectl apply -f "${rules_file}"
    
    # Check if Prometheus deployment exists and patch it to include the new rules
    if kubectl get deployment prometheus-server -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        log "Patching Prometheus deployment to include unit economics rules..."
        
        # Add the ConfigMap as a volume if not already present
        kubectl patch deployment prometheus-server -n "${NAMESPACE_MONITORING}" --type='json' -p='[
            {
                "op": "add",
                "path": "/spec/template/spec/volumes/-",
                "value": {
                    "name": "unit-economics-rules",
                    "configMap": {
                        "name": "prometheus-unit-economics-rules"
                    }
                }
            }
        ]' || true
        
        # Add the volume mount if not already present
        kubectl patch deployment prometheus-server -n "${NAMESPACE_MONITORING}" --type='json' -p='[
            {
                "op": "add", 
                "path": "/spec/template/spec/containers/0/volumeMounts/-",
                "value": {
                    "name": "unit-economics-rules",
                    "mountPath": "/etc/prometheus/rules/unit-economics",
                    "readOnly": true
                }
            }
        ]' || true
        
        success "Prometheus recording rules installed and deployment updated"
    else
        warning "Prometheus deployment not found. Rules ConfigMap created but not mounted."
    fi
}

install_grafana_dashboard() {
    log "Installing Grafana dashboard for unit economics..."
    
    local dashboard_file="${SCRIPT_DIR}/dashboards/unit-economics.json"
    
    if [[ ! -f "${dashboard_file}" ]]; then
        error "Grafana dashboard file not found: ${dashboard_file}"
        exit 1
    fi
    
    # Create ConfigMap for the dashboard
    kubectl create configmap "${GRAFANA_DASHBOARD_CONFIG_NAME}" \
        --from-file="unit-economics.json=${dashboard_file}" \
        --namespace="${NAMESPACE_MONITORING}" \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Add labels for Grafana auto-discovery
    kubectl label configmap "${GRAFANA_DASHBOARD_CONFIG_NAME}" \
        --namespace="${NAMESPACE_MONITORING}" \
        grafana_dashboard=1 \
        --overwrite
    
    # If Grafana deployment exists, restart it to pick up new dashboard
    if kubectl get deployment grafana -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        log "Restarting Grafana to load new dashboard..."
        kubectl rollout restart deployment/grafana -n "${NAMESPACE_MONITORING}"
        kubectl rollout status deployment/grafana -n "${NAMESPACE_MONITORING}" --timeout=300s
    fi
    
    success "Grafana dashboard installed"
}

verify_installation() {
    log "Verifying unit economics monitoring installation..."
    
    # Check if ConfigMaps exist
    if kubectl get configmap "${PROMETHEUS_RULES_CONFIG_NAME}" -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        success "Prometheus recording rules ConfigMap found"
    else
        error "Prometheus recording rules ConfigMap not found"
        return 1
    fi
    
    if kubectl get configmap "${GRAFANA_DASHBOARD_CONFIG_NAME}" -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        success "Grafana dashboard ConfigMap found"
    else
        error "Grafana dashboard ConfigMap not found"
        return 1
    fi
    
    # Check if services are running
    local prometheus_ready=false
    local grafana_ready=false
    
    if kubectl get deployment prometheus-server -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        if kubectl get pods -n "${NAMESPACE_MONITORING}" -l app=prometheus -o jsonpath='{.items[0].status.phase}' 2>/dev/null | grep -q "Running"; then
            prometheus_ready=true
            success "Prometheus is running"
        fi
    fi
    
    if kubectl get deployment grafana -n "${NAMESPACE_MONITORING}" &> /dev/null; then
        if kubectl get pods -n "${NAMESPACE_MONITORING}" -l app.kubernetes.io/name=grafana -o jsonpath='{.items[0].status.phase}' 2>/dev/null | grep -q "Running"; then
            grafana_ready=true
            success "Grafana is running"
        fi
    fi
    
    if [[ "${prometheus_ready}" == true && "${grafana_ready}" == true ]]; then
        success "All monitoring services are running"
        return 0
    else
        warning "Some monitoring services are not running"
        return 1
    fi
}

show_access_information() {
    log "Unit economics monitoring access information:"
    
    echo ""
    echo "📊 Grafana Dashboard Access:"
    echo "  1. Port forward Grafana:"
    echo "     kubectl port-forward svc/grafana 3000:80 -n ${NAMESPACE_MONITORING}"
    echo "  2. Open browser: http://localhost:3000"
    echo "  3. Find 'Unit Economics - Cost per Outcome' dashboard"
    echo ""
    
    echo "🔍 Prometheus Metrics:"
    echo "  1. Port forward Prometheus:"
    echo "     kubectl port-forward svc/prometheus-server 9090:80 -n ${NAMESPACE_MONITORING}"
    echo "  2. Open browser: http://localhost:9090"
    echo "  3. Query unit economics metrics:"
    echo "     - unit_economics:cost_per_1k_articles_hourly"
    echo "     - unit_economics:cost_per_rag_query_hourly"
    echo "     - articles:rate_1h"
    echo "     - ragq:rate_1h"
    echo ""
    
    echo "📈 Key Metrics:"
    echo "  • € per 1000 articles - Cost efficiency of content processing"
    echo "  • € per RAG query - Cost efficiency of AI inference"
    echo "  • Articles per € - Processing efficiency"
    echo "  • RAG queries per € - Query efficiency"
    echo ""
    
    echo "⚡ Business Counters:"
    echo "  • neuro_articles_ingested_total - Track in ingestion services"
    echo "  • neuro_rag_queries_total - Track in API endpoints"
    echo ""
}

main() {
    echo "🚀 Installing Unit Economics Monitoring System"
    echo "=============================================="
    
    check_prerequisites
    install_prometheus_rules
    install_grafana_dashboard
    
    if verify_installation; then
        success "Unit economics monitoring installation completed successfully!"
        show_access_information
    else
        error "Installation completed with warnings. Please check the issues above."
        exit 1
    fi
}

# Run main function
main "$@"
