#!/bin/bash

# NeuroNews Grafana FinOps Dashboards Installation
# This script installs OpenCost overview and NeuroNews FinOps dashboards in Grafana

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE_MONITORING="monitoring"
NAMESPACE_OPENCOST="opencost"

# Logging functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
    fi
    
    # Check if monitoring namespace exists
    if ! kubectl get namespace $NAMESPACE_MONITORING &> /dev/null; then
        error "Monitoring namespace '$NAMESPACE_MONITORING' does not exist"
    fi
    
    # Check if Grafana is running
    if ! kubectl get deployment grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        warn "Grafana deployment not found in $NAMESPACE_MONITORING namespace"
        info "Make sure Grafana is installed before deploying dashboards"
    fi
    
    # Check if OpenCost is available
    if ! kubectl get deployment opencost -n $NAMESPACE_OPENCOST &> /dev/null; then
        warn "OpenCost deployment not found in $NAMESPACE_OPENCOST namespace"
        info "OpenCost integration will be limited without OpenCost installed"
    fi
    
    log "Prerequisites check completed"
}

# Create ConfigMaps for dashboards
create_dashboard_configmaps() {
    log "Creating dashboard ConfigMaps..."
    
    # Create ConfigMap with dashboard JSON files
    kubectl create configmap grafana-dashboards-finops \
        --from-file="$SCRIPT_DIR/dashboards/" \
        --namespace=$NAMESPACE_MONITORING \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Add labels to the ConfigMap
    kubectl label configmap grafana-dashboards-finops \
        -n $NAMESPACE_MONITORING \
        app=grafana \
        component=dashboards \
        category=finops \
        --overwrite
    
    log "Dashboard ConfigMaps created successfully"
}

# Create provisioning ConfigMaps
create_provisioning_configmaps() {
    log "Creating provisioning ConfigMaps..."
    
    # Create dashboard provisioning ConfigMap
    kubectl create configmap grafana-dashboard-provisioning \
        --from-file="$SCRIPT_DIR/provisioning/dashboards/" \
        --namespace=$NAMESPACE_MONITORING \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Create datasource provisioning ConfigMap
    kubectl create configmap grafana-datasources-opencost \
        --from-file="$SCRIPT_DIR/provisioning/datasources/" \
        --namespace=$NAMESPACE_MONITORING \
        --dry-run=client -o yaml | kubectl apply -f -
    
    # Add labels
    kubectl label configmap grafana-dashboard-provisioning \
        -n $NAMESPACE_MONITORING \
        app=grafana \
        component=provisioning \
        --overwrite
    
    kubectl label configmap grafana-datasources-opencost \
        -n $NAMESPACE_MONITORING \
        app=grafana \
        component=datasources \
        --overwrite
    
    log "Provisioning ConfigMaps created successfully"
}

# Patch Grafana deployment to mount new ConfigMaps
patch_grafana_deployment() {
    log "Patching Grafana deployment to mount dashboards..."
    
    # Check if Grafana deployment exists
    if ! kubectl get deployment grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        warn "Grafana deployment not found, skipping deployment patch"
        info "You'll need to manually mount the ConfigMaps in your Grafana deployment"
        return 0
    fi
    
    # Create patch for mounting dashboard ConfigMaps
    cat > /tmp/grafana-patch.yaml << EOF
spec:
  template:
    spec:
      containers:
      - name: grafana
        volumeMounts:
        - name: dashboards-finops
          mountPath: /var/lib/grafana/dashboards/finops
          readOnly: true
        - name: dashboards-opencost
          mountPath: /var/lib/grafana/dashboards/opencost
          readOnly: true
        - name: provisioning-dashboards
          mountPath: /etc/grafana/provisioning/dashboards/finops.yaml
          subPath: finops.yaml
          readOnly: true
        - name: provisioning-datasources
          mountPath: /etc/grafana/provisioning/datasources/opencost.yaml
          subPath: prometheus.yaml
          readOnly: true
      volumes:
      - name: dashboards-finops
        configMap:
          name: grafana-dashboards-finops
      - name: dashboards-opencost
        configMap:
          name: grafana-dashboards-finops
      - name: provisioning-dashboards
        configMap:
          name: grafana-dashboard-provisioning
      - name: provisioning-datasources
        configMap:
          name: grafana-datasources-opencost
EOF
    
    # Apply the patch
    kubectl patch deployment grafana -n $NAMESPACE_MONITORING --patch-file /tmp/grafana-patch.yaml
    
    # Wait for rollout to complete
    kubectl rollout status deployment/grafana -n $NAMESPACE_MONITORING --timeout=300s
    
    # Clean up temp file
    rm -f /tmp/grafana-patch.yaml
    
    log "Grafana deployment patched successfully"
}

# Restart Grafana to reload configurations
restart_grafana() {
    log "Restarting Grafana to reload configurations..."
    
    if kubectl get deployment grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        kubectl rollout restart deployment/grafana -n $NAMESPACE_MONITORING
        kubectl rollout status deployment/grafana -n $NAMESPACE_MONITORING --timeout=300s
        log "Grafana restarted successfully"
    else
        warn "Grafana deployment not found, skipping restart"
    fi
}

# Validate dashboard installation
validate_installation() {
    log "Validating dashboard installation..."
    
    # Check ConfigMaps
    local configmaps=("grafana-dashboards-finops" "grafana-dashboard-provisioning" "grafana-datasources-opencost")
    
    for cm in "${configmaps[@]}"; do
        if kubectl get configmap $cm -n $NAMESPACE_MONITORING &> /dev/null; then
            info "✓ ConfigMap $cm exists"
        else
            error "✗ ConfigMap $cm is missing"
        fi
    done
    
    # Check if Grafana is running
    if kubectl get deployment grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        local ready_replicas=$(kubectl get deployment grafana -n $NAMESPACE_MONITORING -o jsonpath='{.status.readyReplicas}')
        local desired_replicas=$(kubectl get deployment grafana -n $NAMESPACE_MONITORING -o jsonpath='{.spec.replicas}')
        
        if [[ "$ready_replicas" == "$desired_replicas" && "$ready_replicas" -gt 0 ]]; then
            info "✓ Grafana is running ($ready_replicas/$desired_replicas replicas ready)"
        else
            warn "⚠ Grafana may not be fully ready ($ready_replicas/$desired_replicas replicas ready)"
        fi
    fi
    
    # Get Grafana service info
    if kubectl get service grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        local service_type=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.spec.type}')
        local service_port=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.spec.ports[0].port}')
        
        info "Grafana service: $service_type on port $service_port"
        
        if [[ "$service_type" == "NodePort" ]]; then
            local node_port=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.spec.ports[0].nodePort}')
            info "NodePort: $node_port"
        elif [[ "$service_type" == "LoadBalancer" ]]; then
            local external_ip=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
            if [[ -n "$external_ip" ]]; then
                info "External IP: $external_ip"
            fi
        fi
    fi
    
    log "Validation completed"
}

# Show access instructions
show_access_instructions() {
    log "Dashboard access instructions:"
    
    echo
    echo "=========================================="
    echo "Grafana FinOps Dashboards Installation Complete!"
    echo "=========================================="
    echo
    echo "📊 Available Dashboards:"
    echo "  • OpenCost Overview (folder: OpenCost)"
    echo "  • NeuroNews FinOps (folder: FinOps)"
    echo
    echo "🔗 Access Grafana:"
    
    if kubectl get service grafana -n $NAMESPACE_MONITORING &> /dev/null; then
        local service_type=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.spec.type}')
        
        case $service_type in
            "ClusterIP")
                echo "  • Port forward: kubectl port-forward svc/grafana -n $NAMESPACE_MONITORING 3000:80"
                echo "  • Then visit: http://localhost:3000"
                ;;
            "NodePort")
                local node_port=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.spec.ports[0].nodePort}')
                echo "  • NodePort: http://<node-ip>:$node_port"
                ;;
            "LoadBalancer")
                local external_ip=$(kubectl get service grafana -n $NAMESPACE_MONITORING -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
                if [[ -n "$external_ip" ]]; then
                    echo "  • LoadBalancer: http://$external_ip"
                else
                    echo "  • LoadBalancer: Waiting for external IP..."
                fi
                ;;
        esac
    fi
    
    echo
    echo "📈 Dashboard Features:"
    echo "  • Monthly cluster cost tracking"
    echo "  • Cost allocation by pipeline (ingest, transform, api, rag, monitoring, infra)"
    echo "  • Cost allocation by team"
    echo "  • Cost allocation by environment (dev, staging, prod)"
    echo "  • Cost allocation by cost center"
    echo "  • Load balancer and storage cost breakdown"
    echo "  • Resource efficiency metrics"
    echo
    echo "🔧 Prerequisites for full functionality:"
    echo "  • OpenCost installed and running"
    echo "  • Prometheus collecting OpenCost metrics"
    echo "  • Workloads labeled with FinOps labels (app, component, pipeline, team, env, cost_center)"
    echo
    echo "💡 Next steps:"
    echo "  • Ensure FinOps labeling is applied to workloads"
    echo "  • Configure OpenCost data sources if needed"
    echo "  • Set up alerting for cost thresholds"
    echo
}

# Manual installation instructions
show_manual_instructions() {
    echo
    echo "=========================================="
    echo "Manual Installation Instructions"
    echo "=========================================="
    echo
    echo "If automatic installation failed, you can manually:"
    echo
    echo "1. Apply ConfigMaps:"
    echo "   kubectl apply -f $SCRIPT_DIR/k8s-manifests.yaml"
    echo
    echo "2. Mount ConfigMaps in Grafana deployment:"
    echo "   - Add volumes for dashboard ConfigMaps"
    echo "   - Add volumeMounts to Grafana container"
    echo "   - Mount provisioning files"
    echo
    echo "3. Restart Grafana:"
    echo "   kubectl rollout restart deployment/grafana -n $NAMESPACE_MONITORING"
    echo
    echo "4. Import dashboards manually via Grafana UI if needed"
    echo
}

# Main installation function
main() {
    log "Starting NeuroNews Grafana FinOps Dashboards installation..."
    
    # Parse command line arguments
    local action="${1:-install}"
    
    case $action in
        "install")
            check_prerequisites
            create_dashboard_configmaps
            create_provisioning_configmaps
            
            # Try to patch Grafana deployment
            if patch_grafana_deployment; then
                restart_grafana
            else
                warn "Could not automatically patch Grafana deployment"
                show_manual_instructions
            fi
            
            validate_installation
            show_access_instructions
            
            log "Grafana FinOps dashboards installation completed!"
            ;;
        
        "validate")
            validate_installation
            ;;
        
        "uninstall")
            log "Uninstalling Grafana FinOps dashboards..."
            kubectl delete configmap grafana-dashboards-finops -n $NAMESPACE_MONITORING --ignore-not-found=true
            kubectl delete configmap grafana-dashboard-provisioning -n $NAMESPACE_MONITORING --ignore-not-found=true
            kubectl delete configmap grafana-datasources-opencost -n $NAMESPACE_MONITORING --ignore-not-found=true
            log "Dashboards uninstalled (Grafana deployment not modified)"
            ;;
        
        "manual")
            show_manual_instructions
            ;;
        
        *)
            echo "Usage: $0 [install|validate|uninstall|manual]"
            echo
            echo "  install   - Install FinOps dashboards in Grafana (default)"
            echo "  validate  - Validate installation"
            echo "  uninstall - Remove dashboard ConfigMaps"
            echo "  manual    - Show manual installation instructions"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
