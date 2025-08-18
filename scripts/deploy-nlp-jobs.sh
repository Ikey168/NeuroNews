#!/bin/bash
"""
Kubernetes NLP Jobs Deployment Script
Issue #74: Deploy NLP & AI Processing as Kubernetes Jobs

This script deploys the complete NLP & AI processing infrastructure
including GPU acceleration, priority scheduling, and monitoring.
"""

set -euo pipefail

# Configuration
NAMESPACE="neuronews"
GPU_NAMESPACE="gpu-operator"
MONITORING_NAMESPACE="monitoring"
DRY_RUN="${DRY_RUN:-false}"
SKIP_GPU_CHECK="${SKIP_GPU_CHECK:-false}"
VERBOSE="${VERBOSE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
        echo -e "[DEBUG] $1"
    fi
}

# Function to check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
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
    
    # Check if we're in the right directory
    if [[ ! -d "k8s/nlp-jobs" ]]; then
        log_error "Must be run from the project root directory"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Function to check GPU availability
check_gpu_availability() {
    if [[ "$SKIP_GPU_CHECK" == "true" ]]; then
        log_warning "Skipping GPU availability check"
        return
    fi
    
    log_info "Checking GPU availability..."
    
    # Check for GPU nodes
    GPU_NODES=$(kubectl get nodes -l accelerator=nvidia-tesla-k80 --no-headers 2>/dev/null | wc -l || echo 0)
    if [[ $GPU_NODES -eq 0 ]]; then
        GPU_NODES=$(kubectl get nodes -l nvidia.com/gpu.present=true --no-headers 2>/dev/null | wc -l || echo 0)
    fi
    
    if [[ $GPU_NODES -eq 0 ]]; then
        log_warning "No GPU nodes found in cluster"
        log_warning "GPU features will not work properly"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelled"
            exit 0
        fi
    else
        log_success "Found $GPU_NODES GPU nodes"
    fi
    
    # Check for NVIDIA device plugin
    if ! kubectl get ds nvidia-device-plugin-daemonset -n $GPU_NAMESPACE &> /dev/null; then
        log_warning "NVIDIA device plugin not found"
        log_info "GPU support requires NVIDIA device plugin to be installed"
    else
        log_success "NVIDIA device plugin is available"
    fi
}

# Function to create namespace
create_namespace() {
    log_info "Creating namespace: $NAMESPACE"
    
    if kubectl get namespace $NAMESPACE &> /dev/null; then
        log_warning "Namespace $NAMESPACE already exists"
    else
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would create namespace: $NAMESPACE"
        else
            kubectl create namespace $NAMESPACE
            log_success "Created namespace: $NAMESPACE"
        fi
    fi
}

# Function to apply Kubernetes manifests
apply_manifest() {
    local manifest_file=$1
    local description=$2
    
    log_info "Applying $description..."
    log_debug "Manifest file: $manifest_file"
    
    if [[ ! -f "$manifest_file" ]]; then
        log_error "Manifest file not found: $manifest_file"
        return 1
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
        return $?
    else
        if kubectl apply -f "$manifest_file" -n $NAMESPACE; then
            log_success "Applied $description"
            return 0
        else
            log_error "Failed to apply $description"
            return 1
        fi
    fi
}

# Function to wait for resource readiness
wait_for_readiness() {
    local resource_type=$1
    local resource_name=$2
    local timeout=${3:-300}  # 5 minutes default
    
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Waiting for $resource_type/$resource_name to be ready..."
    
    if kubectl wait --for=condition=Ready $resource_type/$resource_name -n $NAMESPACE --timeout=${timeout}s; then
        log_success "$resource_type/$resource_name is ready"
        return 0
    else
        log_error "$resource_type/$resource_name failed to become ready within ${timeout}s"
        return 1
    fi
}

# Function to deploy priority classes
deploy_priority_classes() {
    log_info "Deploying priority classes..."
    
    if apply_manifest "k8s/nlp-jobs/priority-classes.yaml" "Priority Classes"; then
        # Priority classes are cluster-wide, no namespace needed
        if [[ "$DRY_RUN" != "true" ]]; then
            sleep 5  # Allow time for priority classes to be created
        fi
        return 0
    else
        return 1
    fi
}

# Function to deploy RBAC
deploy_rbac() {
    log_info "Deploying RBAC resources..."
    
    if apply_manifest "k8s/nlp-jobs/rbac.yaml" "RBAC Resources"; then
        return 0
    else
        return 1
    fi
}

# Function to deploy storage
deploy_storage() {
    log_info "Deploying storage resources..."
    
    if apply_manifest "k8s/nlp-jobs/storage.yaml" "Storage Resources"; then
        # Wait for PVCs to be bound
        if [[ "$DRY_RUN" != "true" ]]; then
            log_info "Waiting for PVCs to be bound..."
            sleep 10
            
            for pvc in nlp-models nlp-results nlp-cache; do
                if ! kubectl get pvc $pvc -n $NAMESPACE &> /dev/null; then
                    log_warning "PVC $pvc not found"
                    continue
                fi
                
                if ! kubectl wait --for=condition=Bound pvc/$pvc -n $NAMESPACE --timeout=60s; then
                    log_warning "PVC $pvc did not bind within 60s"
                fi
            done
        fi
        return 0
    else
        return 1
    fi
}

# Function to deploy ConfigMap
deploy_configmap() {
    log_info "Deploying ConfigMap..."
    
    if apply_manifest "k8s/nlp-jobs/configmap.yaml" "NLP ConfigMap"; then
        return 0
    else
        return 1
    fi
}

# Function to deploy network policies
deploy_policies() {
    log_info "Deploying security policies..."
    
    if apply_manifest "k8s/nlp-jobs/policies.yaml" "Security Policies"; then
        return 0
    else
        return 1
    fi
}

# Function to deploy monitoring
deploy_monitoring() {
    log_info "Deploying monitoring resources..."
    
    # Check if Prometheus operator is available
    if ! kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        log_warning "Prometheus operator not found, skipping ServiceMonitor"
        log_warning "Install Prometheus operator for full monitoring support"
        return 0
    fi
    
    if apply_manifest "k8s/nlp-jobs/monitoring.yaml" "Monitoring Resources"; then
        return 0
    else
        return 1
    fi
}

# Function to deploy NLP jobs
deploy_nlp_jobs() {
    log_info "Deploying NLP processing jobs..."
    
    if apply_manifest "k8s/nlp-jobs/sentiment-analysis-job.yaml" "NLP Processing Jobs"; then
        return 0
    else
        return 1
    fi
}

# Function to validate deployment
validate_deployment() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Skipping deployment validation"
        return 0
    fi
    
    log_info "Validating deployment..."
    
    # Check priority classes
    log_debug "Checking priority classes..."
    for pc in nlp-critical nlp-high nlp-medium nlp-low nlp-maintenance; do
        if kubectl get priorityclass $pc &> /dev/null; then
            log_debug "✓ Priority class $pc exists"
        else
            log_warning "✗ Priority class $pc not found"
        fi
    done
    
    # Check namespace resources
    log_debug "Checking namespace resources..."
    if kubectl get ns $NAMESPACE &> /dev/null; then
        log_debug "✓ Namespace $NAMESPACE exists"
    else
        log_error "✗ Namespace $NAMESPACE not found"
        return 1
    fi
    
    # Check service account
    if kubectl get sa nlp-processor -n $NAMESPACE &> /dev/null; then
        log_debug "✓ ServiceAccount nlp-processor exists"
    else
        log_warning "✗ ServiceAccount nlp-processor not found"
    fi
    
    # Check ConfigMap
    if kubectl get cm nlp-config -n $NAMESPACE &> /dev/null; then
        log_debug "✓ ConfigMap nlp-config exists"
    else
        log_warning "✗ ConfigMap nlp-config not found"
    fi
    
    # Check PVCs
    for pvc in nlp-models nlp-results nlp-cache; do
        if kubectl get pvc $pvc -n $NAMESPACE &> /dev/null; then
            STATUS=$(kubectl get pvc $pvc -n $NAMESPACE -o jsonpath='{.status.phase}')
            if [[ "$STATUS" == "Bound" ]]; then
                log_debug "✓ PVC $pvc is bound"
            else
                log_warning "✗ PVC $pvc is $STATUS"
            fi
        else
            log_warning "✗ PVC $pvc not found"
        fi
    done
    
    log_success "Deployment validation completed"
}

# Function to show deployment status
show_deployment_status() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi
    
    log_info "Deployment Status Summary:"
    
    echo
    echo "Namespace: $NAMESPACE"
    kubectl get all -n $NAMESPACE
    
    echo
    echo "Storage:"
    kubectl get pvc -n $NAMESPACE
    
    echo
    echo "ConfigMaps:"
    kubectl get cm -n $NAMESPACE
    
    echo
    echo "Priority Classes:"
    kubectl get priorityclass | grep nlp- || echo "No NLP priority classes found"
    
    echo
    echo "Recent Events:"
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy NLP & AI Processing Jobs to Kubernetes

Options:
    --dry-run           Perform a dry run without actually applying changes
    --skip-gpu-check    Skip GPU availability checks
    --verbose           Enable verbose output
    --namespace NAME    Set target namespace (default: $NAMESPACE)
    --help              Show this help message

Environment Variables:
    DRY_RUN            Set to 'true' for dry run mode
    SKIP_GPU_CHECK     Set to 'true' to skip GPU checks
    VERBOSE            Set to 'true' for verbose output

Examples:
    # Deploy with dry run
    $0 --dry-run
    
    # Deploy with verbose output
    $0 --verbose
    
    # Deploy to custom namespace
    $0 --namespace my-nlp
    
    # Deploy with environment variables
    DRY_RUN=true VERBOSE=true $0

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="true"
            shift
            ;;
        --skip-gpu-check)
            SKIP_GPU_CHECK="true"
            shift
            ;;
        --verbose)
            VERBOSE="true"
            shift
            ;;
        --namespace)
            NAMESPACE="$2"
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

# Main deployment function
main() {
    log_info "Starting NLP Jobs deployment to Kubernetes"
    log_info "Target namespace: $NAMESPACE"
    log_info "Dry run mode: $DRY_RUN"
    log_info "Skip GPU check: $SKIP_GPU_CHECK"
    log_info "Verbose mode: $VERBOSE"
    
    echo
    
    # Check prerequisites
    check_prerequisites
    
    # Check GPU availability
    check_gpu_availability
    
    # Create namespace
    create_namespace
    
    # Deploy components in order
    deploy_priority_classes || { log_error "Failed to deploy priority classes"; exit 1; }
    deploy_rbac || { log_error "Failed to deploy RBAC"; exit 1; }
    deploy_storage || { log_error "Failed to deploy storage"; exit 1; }
    deploy_configmap || { log_error "Failed to deploy ConfigMap"; exit 1; }
    deploy_policies || { log_error "Failed to deploy policies"; exit 1; }
    deploy_monitoring || { log_warning "Failed to deploy monitoring (non-critical)"; }
    deploy_nlp_jobs || { log_error "Failed to deploy NLP jobs"; exit 1; }
    
    # Validate deployment
    validate_deployment
    
    # Show status
    show_deployment_status
    
    echo
    log_success "NLP Jobs deployment completed successfully!"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        echo
        log_info "Next steps:"
        echo "1. Monitor job execution: kubectl get jobs -n $NAMESPACE -w"
        echo "2. Check job logs: kubectl logs -l app=nlp-processor -n $NAMESPACE"
        echo "3. View job status: kubectl describe jobs -n $NAMESPACE"
        echo "4. Scale resources if needed: kubectl patch job <job-name> -n $NAMESPACE -p '{\"spec\":{\"parallelism\":N}}'"
        echo "5. Monitor GPU usage: kubectl top nodes"
    fi
}

# Run main function
main "$@"
