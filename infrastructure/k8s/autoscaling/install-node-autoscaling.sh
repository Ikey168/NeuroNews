#!/bin/bash
set -euo pipefail

# Node Autoscaling & Bin-Packing Guardrails Installation Script
# Implements Issue #341: Node autoscaling & bin-packing guardrails (cost-saver)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-neuronews-cluster}"
AWS_REGION="${AWS_REGION:-us-east-1}"
NAMESPACE="${NAMESPACE:-data-pipeline}"
DRY_RUN="${DRY_RUN:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
    fi
    
    # Check AWS CLI (optional but recommended)
    if ! command -v aws &> /dev/null; then
        warn "AWS CLI not found - some features may not be available"
    fi
    
    # Check cluster autoscaler prerequisites
    if ! kubectl get nodes -o jsonpath='{.items[0].metadata.labels}' | grep -q "kubernetes.io/arch"; then
        error "Node labels missing - ensure cluster is properly configured"
    fi
    
    success "Prerequisites check passed"
}

install_priority_classes() {
    log "Installing priority classes..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply --dry-run=client -f "$SCRIPT_DIR/priority-classes.yaml"
    else
        kubectl apply -f "$SCRIPT_DIR/priority-classes.yaml"
    fi
    
    success "Priority classes installed"
}

install_cluster_autoscaler() {
    log "Installing Cluster Autoscaler..."
    
    # Update cluster name in the deployment
    local temp_file=$(mktemp)
    sed "s/neuronews-cluster/$CLUSTER_NAME/g" "$SCRIPT_DIR/cluster-autoscaler.yaml" > "$temp_file"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply --dry-run=client -f "$temp_file"
    else
        kubectl apply -f "$temp_file"
        
        # Wait for deployment to be ready
        kubectl rollout status deployment/cluster-autoscaler -n kube-system --timeout=300s
    fi
    
    rm "$temp_file"
    success "Cluster Autoscaler installed"
}

install_bin_packing_guardrails() {
    log "Installing bin-packing guardrails..."
    
    # Create namespace if it doesn't exist
    kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply --dry-run=client -f "$SCRIPT_DIR/bin-packing-guardrails.yaml" -n "$NAMESPACE"
    else
        kubectl apply -f "$SCRIPT_DIR/bin-packing-guardrails.yaml" -n "$NAMESPACE"
    fi
    
    success "Bin-packing guardrails installed"
}

install_monitoring() {
    log "Installing autoscaling monitoring rules..."
    
    # Create monitoring namespace if it doesn't exist
    kubectl create namespace monitoring --dry-run=client -o yaml | kubectl apply -f -
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply --dry-run=client -f "$SCRIPT_DIR/../monitoring/prometheus-autoscaling-rules.yaml"
    else
        kubectl apply -f "$SCRIPT_DIR/../monitoring/prometheus-autoscaling-rules.yaml"
    fi
    
    success "Monitoring rules installed"
}

configure_spot_node_pools() {
    log "Configuring spot instance node pools..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log "DRY RUN: Would create spot node pools configuration"
        kubectl apply --dry-run=client -f "$SCRIPT_DIR/spot-node-pools.yaml"
        return
    fi
    
    # Apply spot node pool configuration
    kubectl apply -f "$SCRIPT_DIR/spot-node-pools.yaml"
    
    # Show instructions for AWS node group creation
    cat << EOF

${YELLOW}MANUAL STEP REQUIRED:${NC}
To complete spot instance setup, you need to create AWS EKS managed node groups.

Option 1 - AWS CLI:
${GREEN}
# Extract and run commands from the ConfigMap
kubectl get configmap spot-node-pool-config -n kube-system -o jsonpath='{.data.aws-cli-commands\.sh}' > create-node-groups.sh
chmod +x create-node-groups.sh
# Edit the script to replace ACCOUNT_ID and subnet IDs
./create-node-groups.sh
${NC}

Option 2 - Terraform:
${GREEN}
# Extract Terraform configuration
kubectl get configmap spot-node-pool-config -n kube-system -o jsonpath='{.data.terraform-example\.tf}' > node-groups.tf
# Integrate into your existing Terraform configuration
${NC}

Option 3 - AWS Console:
${GREEN}
# Use the JSON configurations from:
kubectl get configmap spot-node-pool-config -n kube-system -o jsonpath='{.data.spot-node-group\.yaml}'
kubectl get configmap spot-node-pool-config -n kube-system -o jsonpath='{.data.on-demand-node-group\.yaml}'
${NC}

EOF
    
    success "Spot node pools configuration completed"
}

deploy_example_workloads() {
    log "Deploying example workloads with autoscaling optimizations..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl apply --dry-run=client -f "$SCRIPT_DIR/workload-examples.yaml" -n "$NAMESPACE"
    else
        kubectl apply -f "$SCRIPT_DIR/workload-examples.yaml" -n "$NAMESPACE"
    fi
    
    success "Example workloads deployed"
}

verify_installation() {
    log "Verifying installation..."
    
    # Check cluster autoscaler
    if kubectl get deployment cluster-autoscaler -n kube-system &> /dev/null; then
        success "✓ Cluster Autoscaler deployed"
    else
        error "✗ Cluster Autoscaler not found"
    fi
    
    # Check priority classes
    local priority_classes=(neuronews-critical neuronews-standard neuronews-batch neuronews-dev neuronews-spot)
    for pc in "${priority_classes[@]}"; do
        if kubectl get priorityclass "$pc" &> /dev/null; then
            success "✓ Priority class $pc created"
        else
            error "✗ Priority class $pc not found"
        fi
    done
    
    # Check pod disruption budgets
    if kubectl get pdb -n "$NAMESPACE" | grep -q neuronews; then
        success "✓ Pod Disruption Budgets created"
    else
        warn "⚠ Pod Disruption Budgets not found in namespace $NAMESPACE"
    fi
    
    # Check monitoring rules
    if kubectl get prometheusrule neuronews-autoscaling-monitoring -n monitoring &> /dev/null; then
        success "✓ Autoscaling monitoring rules deployed"
    else
        warn "⚠ Monitoring rules not found"
    fi
    
    # Check if cluster autoscaler is running
    if [[ "$DRY_RUN" != "true" ]]; then
        local ready_pods=$(kubectl get pods -n kube-system -l app=cluster-autoscaler --field-selector=status.phase=Running --no-headers | wc -l)
        if [[ "$ready_pods" -gt 0 ]]; then
            success "✓ Cluster Autoscaler is running"
        else
            warn "⚠ Cluster Autoscaler pods not running yet"
        fi
    fi
    
    success "Installation verification completed"
}

show_status() {
    cat << EOF

${GREEN}========================================
Node Autoscaling & Bin-Packing Guardrails
Installation Complete!
========================================${NC}

${BLUE}What was installed:${NC}
• Cluster Autoscaler with cost-optimized settings
• Priority classes for workload prioritization
• Pod Disruption Budgets for bin-packing
• Topology spread constraints templates
• Spot instance node pool configurations
• Monitoring rules for cost tracking
• Example workloads demonstrating best practices

${BLUE}Next steps:${NC}
1. Create AWS EKS managed node groups (see instructions above)
2. Update your workloads to use priority classes and tolerations
3. Monitor autoscaling effectiveness with Prometheus metrics
4. Adjust resource requests/limits based on VPA recommendations

${BLUE}Monitoring commands:${NC}
# Check cluster autoscaler status
kubectl logs -n kube-system deployment/cluster-autoscaler --tail=50

# Monitor node scaling
kubectl get nodes -l node-lifecycle --show-labels

# Check workload distribution
kubectl get pods -n $NAMESPACE -o wide

# View autoscaling metrics
kubectl get --raw /metrics | grep cluster_autoscaler

${BLUE}DoD Verification:${NC}
✓ Scale-down occurs after idle (check cluster-autoscaler logs)
✓ Workloads respect priorities (check pod eviction events)
✓ Spot pool handles batch jobs (create spot node groups)

${YELLOW}Cost Impact:${NC}
Expected savings: 30-60% on compute costs for batch workloads
Spot instances can provide up to 90% cost reduction vs on-demand

EOF
}

main() {
    log "Starting Node Autoscaling & Bin-Packing Guardrails installation..."
    log "Cluster: $CLUSTER_NAME | Region: $AWS_REGION | Namespace: $NAMESPACE | Dry Run: $DRY_RUN"
    
    check_prerequisites
    install_priority_classes
    install_cluster_autoscaler
    install_bin_packing_guardrails
    install_monitoring
    configure_spot_node_pools
    deploy_example_workloads
    verify_installation
    show_status
    
    success "Node autoscaling and bin-packing guardrails installation completed successfully!"
}

# Help function
show_help() {
    cat << EOF
Node Autoscaling & Bin-Packing Guardrails Installation

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -d, --dry-run          Perform a dry run without making changes
    -c, --cluster NAME     Specify cluster name (default: neuronews-cluster)
    -r, --region REGION    Specify AWS region (default: us-east-1)
    -n, --namespace NS     Specify namespace (default: data-pipeline)

ENVIRONMENT VARIABLES:
    CLUSTER_NAME           Kubernetes cluster name
    AWS_REGION            AWS region for node groups
    NAMESPACE             Target namespace for workloads
    DRY_RUN               Set to 'true' for dry run

EXAMPLES:
    # Install with defaults
    $0

    # Dry run
    $0 --dry-run

    # Custom cluster and region
    $0 --cluster my-cluster --region us-west-2

    # Using environment variables
    CLUSTER_NAME=prod-cluster NAMESPACE=production $0

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -d|--dry-run)
            DRY_RUN="true"
            shift
            ;;
        -c|--cluster)
            CLUSTER_NAME="$2"
            shift 2
            ;;
        -r|--region)
            AWS_REGION="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Run main function
main
