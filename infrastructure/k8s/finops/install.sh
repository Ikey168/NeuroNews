#!/bin/bash

# NeuroNews FinOps Labeling Governance Installation
# This script installs Kyverno policies and applies labeling overlays

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE_KYVERNO="kyverno"
NAMESPACE_NEURONEWS="neuronews"
NAMESPACE_MONITORING="monitoring"
NAMESPACE_DATA_PROCESSING="data-processing"
NAMESPACE_OPENCOST="opencost"

# Logging function
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
    
    # Check if kustomize is available
    if ! command -v kustomize &> /dev/null; then
        error "kustomize is not installed or not in PATH"
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
    fi
    
    log "Prerequisites check passed"
}

# Install Kyverno if not present
install_kyverno() {
    log "Checking Kyverno installation..."
    
    if kubectl get namespace $NAMESPACE_KYVERNO &> /dev/null; then
        info "Kyverno namespace already exists, checking deployment..."
        
        if kubectl get deployment kyverno-admission-controller -n $NAMESPACE_KYVERNO &> /dev/null; then
            info "Kyverno is already installed"
            return 0
        fi
    fi
    
    log "Installing Kyverno..."
    
    # Install Kyverno using Helm or kubectl
    kubectl create namespace $NAMESPACE_KYVERNO --dry-run=client -o yaml | kubectl apply -f -
    
    # Install latest Kyverno
    kubectl apply -f https://github.com/kyverno/kyverno/releases/latest/download/install.yaml
    
    # Wait for Kyverno to be ready
    log "Waiting for Kyverno to be ready..."
    kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=kyverno -n $NAMESPACE_KYVERNO --timeout=300s
    
    log "Kyverno installation completed"
}

# Create namespaces if they don't exist
create_namespaces() {
    log "Creating required namespaces..."
    
    local namespaces=($NAMESPACE_NEURONEWS $NAMESPACE_MONITORING $NAMESPACE_DATA_PROCESSING $NAMESPACE_OPENCOST)
    
    for ns in "${namespaces[@]}"; do
        if ! kubectl get namespace $ns &> /dev/null; then
            log "Creating namespace: $ns"
            kubectl create namespace $ns
        else
            info "Namespace $ns already exists"
        fi
    done
}

# Apply labeling schema ConfigMap
apply_labeling_schema() {
    log "Applying FinOps labeling schema..."
    
    kubectl apply -f "$SCRIPT_DIR/labeling-schema.yaml"
    
    log "Labeling schema applied successfully"
}

# Apply Kyverno policies
apply_kyverno_policies() {
    log "Applying Kyverno policies for FinOps governance..."
    
    # Apply policies in warn mode first for gradual rollout
    sed 's/validationFailureAction: enforce/validationFailureAction: audit/' "$SCRIPT_DIR/kyverno-policies.yaml" | kubectl apply -f -
    
    log "Kyverno policies applied in audit mode"
    info "Policies will be switched to enforce mode after validation period"
}

# Apply Kustomize overlays to patch existing workloads
apply_labeling_patches() {
    log "Applying labeling patches to existing workloads..."
    
    if [ -f "$SCRIPT_DIR/kustomization.yaml" ]; then
        # Build and apply the kustomization
        log "Building Kustomize overlay..."
        kustomize build "$SCRIPT_DIR" > "/tmp/finops-labeling-overlay.yaml"
        
        # Show what will be applied (for safety)
        info "Generated labeling overlay contains $(grep -c '^---' /tmp/finops-labeling-overlay.yaml) resources"
        
        # Apply with dry-run first
        log "Performing dry-run validation..."
        kubectl apply --dry-run=client -f "/tmp/finops-labeling-overlay.yaml"
        
        # Apply for real if dry-run succeeds
        log "Applying labeling patches..."
        kubectl apply -f "/tmp/finops-labeling-overlay.yaml"
        
        # Clean up
        rm -f "/tmp/finops-labeling-overlay.yaml"
        
        log "Labeling patches applied successfully"
    else
        warn "No kustomization.yaml found, skipping patch application"
    fi
}

# Validate policy installation
validate_installation() {
    log "Validating FinOps governance installation..."
    
    # Check Kyverno policies
    local policies=("require-finops-labels" "validate-finops-label-values" "generate-missing-finops-labels")
    
    for policy in "${policies[@]}"; do
        if kubectl get clusterpolicy $policy &> /dev/null; then
            info "✓ Policy $policy is installed"
        else
            error "✗ Policy $policy is missing"
        fi
    done
    
    # Check labeling schema ConfigMap
    if kubectl get configmap finops-labeling-schema -n kube-system &> /dev/null; then
        info "✓ Labeling schema ConfigMap is installed"
    else
        error "✗ Labeling schema ConfigMap is missing"
    fi
    
    log "Installation validation completed successfully"
}

# Generate compliance report
generate_compliance_report() {
    log "Generating initial compliance report..."
    
    local report_file="/tmp/finops-labeling-compliance-$(date +%Y%m%d-%H%M%S).txt"
    
    {
        echo "NeuroNews FinOps Labeling Compliance Report"
        echo "Generated: $(date)"
        echo "========================================"
        echo
        
        echo "Required Labels: app, component, pipeline, team, env, cost_center"
        echo
        
        # Check workloads in each namespace
        local namespaces=($NAMESPACE_NEURONEWS $NAMESPACE_MONITORING $NAMESPACE_DATA_PROCESSING $NAMESPACE_OPENCOST)
        
        for ns in "${namespaces[@]}"; do
            echo "Namespace: $ns"
            echo "===================="
            
            # Check Deployments
            echo "Deployments:"
            kubectl get deployments -n $ns -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.app}{"\t"}{.metadata.labels.component}{"\t"}{.metadata.labels.pipeline}{"\t"}{.metadata.labels.team}{"\t"}{.metadata.labels.env}{"\t"}{.metadata.labels.cost_center}{"\n"}{end}' 2>/dev/null | column -t || echo "No deployments found"
            
            # Check StatefulSets
            echo "StatefulSets:"
            kubectl get statefulsets -n $ns -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.metadata.labels.app}{"\t"}{.metadata.labels.component}{"\t"}{.metadata.labels.pipeline}{"\t"}{.metadata.labels.team}{"\t"}{.metadata.labels.env}{"\t"}{.metadata.labels.cost_center}{"\n"}{end}' 2>/dev/null | column -t || echo "No statefulsets found"
            
            echo
        done
        
        echo "Kyverno Policy Status:"
        echo "====================="
        kubectl get clusterpolicy -o custom-columns="NAME:.metadata.name,READY:.status.ready,MESSAGE:.status.conditions[0].message" 2>/dev/null || echo "No policies found"
        
    } > "$report_file"
    
    info "Compliance report generated: $report_file"
    cat "$report_file"
}

# Enable enforcement mode (run after validation period)
enable_enforcement() {
    log "Enabling enforcement mode for Kyverno policies..."
    
    read -p "Are you sure you want to enable enforcement mode? This will block non-compliant resources. (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        info "Enforcement mode not enabled"
        return 0
    fi
    
    # Switch policies to enforce mode
    kubectl patch clusterpolicy require-finops-labels --type='merge' -p='{"spec":{"validationFailureAction":"enforce"}}'
    kubectl patch clusterpolicy validate-finops-label-values --type='merge' -p='{"spec":{"validationFailureAction":"enforce"}}'
    
    log "Enforcement mode enabled"
    warn "Monitor cluster for any blocked deployments"
}

# Cleanup function
cleanup() {
    log "Cleaning up temporary files..."
    rm -f "/tmp/finops-labeling-overlay.yaml"
    rm -f "/tmp/finops-labeling-compliance-"*.txt
}

# Main installation function
main() {
    log "Starting NeuroNews FinOps Labeling Governance installation..."
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    # Parse command line arguments
    local action="${1:-install}"
    
    case $action in
        "install")
            check_prerequisites
            install_kyverno
            create_namespaces
            apply_labeling_schema
            apply_kyverno_policies
            apply_labeling_patches
            validate_installation
            generate_compliance_report
            
            log "FinOps labeling governance installation completed successfully!"
            info "Policies are in audit mode for validation. Run '$0 enforce' to enable enforcement after review."
            ;;
        
        "enforce")
            enable_enforcement
            ;;
        
        "validate")
            validate_installation
            generate_compliance_report
            ;;
        
        "report")
            generate_compliance_report
            ;;
        
        *)
            echo "Usage: $0 [install|enforce|validate|report]"
            echo
            echo "  install  - Install FinOps labeling governance (default)"
            echo "  enforce  - Enable enforcement mode for policies"
            echo "  validate - Validate installation and generate report"
            echo "  report   - Generate compliance report only"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
