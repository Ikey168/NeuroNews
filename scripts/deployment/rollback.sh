#!/bin/bash

# Rollback Script for NeuroNews Services
# Handles automated rollbacks for Kubernetes deployments

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-neuronews}"
SERVICE="${SERVICE:-all}"
ROLLBACK_REVISION="${ROLLBACK_REVISION:-}"

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

# Help function
show_help() {
    cat << EOF
NeuroNews Rollback Script

Usage: $0 [OPTIONS]

Options:
    -h, --help              Show this help message
    -n, --namespace         Kubernetes namespace (default: neuronews)
    -s, --service          Service to rollback (api|dashboard|scraper|nlp-processor|all)
    -r, --revision         Specific revision to rollback to (optional)
    --list-revisions       List available revisions for service(s)
    --dry-run              Show what would be rolled back without executing
    --wait-timeout         Timeout for waiting operations (default: 600s)
    --auto-confirm         Skip confirmation prompts
    --health-check         Run health checks after rollback
    --emergency            Emergency rollback (skip safety checks)

Examples:
    $0 --service api
    $0 --service all --revision 3
    $0 --list-revisions --service dashboard
    $0 --emergency --service api --auto-confirm
EOF
}

# Parse command line arguments
LIST_REVISIONS=false
DRY_RUN=false
WAIT_TIMEOUT="600s"
AUTO_CONFIRM=false
HEALTH_CHECK=false
EMERGENCY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -s|--service)
            SERVICE="$2"
            shift 2
            ;;
        -r|--revision)
            ROLLBACK_REVISION="$2"
            shift 2
            ;;
        --list-revisions)
            LIST_REVISIONS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --wait-timeout)
            WAIT_TIMEOUT="$2"
            shift 2
            ;;
        --auto-confirm)
            AUTO_CONFIRM=true
            shift
            ;;
        --health-check)
            HEALTH_CHECK=true
            shift
            ;;
        --emergency)
            EMERGENCY=true
            AUTO_CONFIRM=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validation
validate_inputs() {
    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi

    # Validate service
    valid_services=("api" "dashboard" "scraper" "nlp-processor" "all")
    if [[ ! " ${valid_services[*]} " =~ " ${SERVICE} " ]]; then
        log_error "Invalid service. Must be one of: ${valid_services[*]}"
        exit 1
    fi

    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace '$NAMESPACE' does not exist"
        exit 1
    fi
}

# Get list of services to rollback
get_services() {
    if [ "$SERVICE" = "all" ]; then
        echo "api dashboard scraper nlp-processor"
    else
        echo "$SERVICE"
    fi
}

# Check if deployment exists
deployment_exists() {
    local service=$1
    kubectl get deployment "neuronews-$service" -n "$NAMESPACE" &> /dev/null
}

# Get deployment revision history
get_revision_history() {
    local service=$1
    
    if ! deployment_exists "$service"; then
        log_error "Deployment neuronews-$service not found in namespace $NAMESPACE"
        return 1
    fi
    
    kubectl rollout history deployment/"neuronews-$service" -n "$NAMESPACE"
}

# Get current revision
get_current_revision() {
    local service=$1
    kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
        -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/revision}' 2>/dev/null || echo "1"
}

# Get previous revision
get_previous_revision() {
    local service=$1
    local current_revision=$(get_current_revision "$service")
    local previous_revision=$((current_revision - 1))
    
    if [ $previous_revision -lt 1 ]; then
        echo "1"
    else
        echo "$previous_revision"
    fi
}

# Get revision details
get_revision_details() {
    local service=$1
    local revision=${2:-}
    
    if [ -n "$revision" ]; then
        kubectl rollout history deployment/"neuronews-$service" \
            --revision="$revision" -n "$NAMESPACE" 2>/dev/null
    else
        kubectl rollout history deployment/"neuronews-$service" -n "$NAMESPACE"
    fi
}

# Validate revision exists
validate_revision() {
    local service=$1
    local revision=$2
    
    local history
    history=$(kubectl rollout history deployment/"neuronews-$service" -n "$NAMESPACE" 2>/dev/null || echo "")
    
    if echo "$history" | grep -q "^$revision"; then
        return 0
    else
        return 1
    fi
}

# Pre-rollback safety checks
pre_rollback_checks() {
    local service=$1
    local target_revision=$2
    
    if [ "$EMERGENCY" = true ]; then
        log_warning "Emergency mode: Skipping safety checks"
        return 0
    fi
    
    log_info "Running pre-rollback safety checks for $service..."
    
    # Check if deployment exists
    if ! deployment_exists "$service"; then
        log_error "Deployment neuronews-$service not found"
        return 1
    fi
    
    # Check if target revision is valid
    if [ -n "$target_revision" ]; then
        if ! validate_revision "$service" "$target_revision"; then
            log_error "Revision $target_revision not found for $service"
            return 1
        fi
        
        local current_revision=$(get_current_revision "$service")
        if [ "$target_revision" = "$current_revision" ]; then
            log_warning "Target revision $target_revision is the same as current revision"
            return 1
        fi
    fi
    
    # Check current deployment health
    local ready_replicas=$(kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
        -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    local desired_replicas=$(kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
        -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    
    if [ "$ready_replicas" != "$desired_replicas" ]; then
        log_warning "Current deployment for $service is not fully healthy (${ready_replicas}/${desired_replicas} ready)"
        
        if [ "$AUTO_CONFIRM" = false ]; then
            read -p "Continue with rollback? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                return 1
            fi
        fi
    fi
    
    return 0
}

# Perform rollback
rollback_service() {
    local service=$1
    local target_revision=$2
    
    log_info "Rolling back service: $service"
    
    if [ -n "$target_revision" ]; then
        log_info "Target revision: $target_revision"
    else
        target_revision=$(get_previous_revision "$service")
        log_info "Rolling back to previous revision: $target_revision"
    fi
    
    # Show what will be rolled back
    local current_revision=$(get_current_revision "$service")
    local current_image=$(kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "unknown")
    
    log_info "Current revision: $current_revision"
    log_info "Current image: $current_image"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would rollback $service to revision $target_revision"
        return 0
    fi
    
    # Confirm rollback
    if [ "$AUTO_CONFIRM" = false ]; then
        echo
        log_warning "This will rollback $service from revision $current_revision to $target_revision"
        read -p "Are you sure you want to proceed? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Rollback cancelled"
            return 1
        fi
    fi
    
    # Perform the rollback
    log_info "Performing rollback..."
    
    if [ -n "$ROLLBACK_REVISION" ]; then
        kubectl rollout undo deployment/"neuronews-$service" \
            --to-revision="$target_revision" \
            --namespace="$NAMESPACE"
    else
        kubectl rollout undo deployment/"neuronews-$service" \
            --namespace="$NAMESPACE"
    fi
    
    # Add rollback annotations
    kubectl annotate deployment/"neuronews-$service" \
        neuronews.com/rollback-by="$(whoami)" \
        neuronews.com/rollback-at="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        neuronews.com/rollback-from-revision="$current_revision" \
        neuronews.com/rollback-to-revision="$target_revision" \
        neuronews.com/rollback-reason="${ROLLBACK_REASON:-Manual rollback}" \
        --namespace="$NAMESPACE" --overwrite
    
    # Wait for rollback to complete
    log_info "Waiting for rollback to complete..."
    if kubectl rollout status deployment/"neuronews-$service" \
        --namespace="$NAMESPACE" \
        --timeout="$WAIT_TIMEOUT"; then
        
        local new_image=$(kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
            -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "unknown")
        
        log_success "Rollback completed for $service"
        log_info "New image: $new_image"
        return 0
    else
        log_error "Rollback failed for $service"
        return 1
    fi
}

# Post-rollback health check
post_rollback_health_check() {
    local service=$1
    
    if [ "$HEALTH_CHECK" = false ]; then
        return 0
    fi
    
    log_info "Running post-rollback health checks for $service..."
    
    # Wait for pods to be ready
    log_info "Waiting for pods to be ready..."
    if kubectl wait --for=condition=ready pod \
        -l "app=neuronews-$service" \
        --namespace="$NAMESPACE" \
        --timeout="300s"; then
        log_success "Pods are ready for $service"
    else
        log_error "Pods failed to become ready for $service"
        return 1
    fi
    
    # Additional health checks can be added here
    return 0
}

# List revisions for service(s)
list_revisions() {
    local services
    read -ra services <<< "$(get_services)"
    
    for service in "${services[@]}"; do
        echo
        log_info "Revision history for $service:"
        echo "================================"
        
        if deployment_exists "$service"; then
            local current_revision=$(get_current_revision "$service")
            echo "Current revision: $current_revision"
            echo
            get_revision_history "$service"
        else
            log_error "Deployment neuronews-$service not found"
        fi
    done
}

# Generate rollback report
generate_rollback_report() {
    local services=("$@")
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local report_file="rollback-report-$(date +%Y%m%d-%H%M%S).json"
    
    # Collect rollback information
    local rollbacks_info=""
    for service in "${services[@]}"; do
        if deployment_exists "$service"; then
            local current_revision=$(get_current_revision "$service")
            local current_image=$(kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
                -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "unknown")
            local rollback_from=$(kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
                -o jsonpath='{.metadata.annotations.neuronews\.com/rollback-from-revision}' 2>/dev/null || echo "unknown")
            
            rollbacks_info+="{\"service\":\"$service\",\"current_revision\":\"$current_revision\",\"current_image\":\"$current_image\",\"rollback_from\":\"$rollback_from\"},"
        fi
    done
    rollbacks_info=${rollbacks_info%,}  # Remove trailing comma
    
    cat > "$report_file" << EOF
{
  "rollback_id": "${GITHUB_RUN_ID:-local-$(date +%s)}",
  "timestamp": "$timestamp",
  "namespace": "$NAMESPACE",
  "target_revision": "$ROLLBACK_REVISION",
  "emergency_mode": $EMERGENCY,
  "services": [$(printf '"%s",' "${services[@]}" | sed 's/,$//')],"
  "rollbacks": [$rollbacks_info],
  "initiated_by": "$(whoami)",
  "reason": "${ROLLBACK_REASON:-Manual rollback}"
}
EOF
    
    log_info "Rollback report generated: $report_file"
}

# Main function
main() {
    log_info "Starting rollback process..."
    log_info "Namespace: $NAMESPACE"
    log_info "Service(s): $SERVICE"
    
    if [ -n "$ROLLBACK_REVISION" ]; then
        log_info "Target revision: $ROLLBACK_REVISION"
    fi
    
    if [ "$EMERGENCY" = true ]; then
        log_warning "Emergency mode enabled"
    fi
    
    validate_inputs
    
    # Handle list revisions
    if [ "$LIST_REVISIONS" = true ]; then
        list_revisions
        exit 0
    fi
    
    local services
    read -ra services <<< "$(get_services)"
    
    local all_success=true
    local rolled_back_services=()
    
    # Pre-rollback checks
    for service in "${services[@]}"; do
        if ! pre_rollback_checks "$service" "$ROLLBACK_REVISION"; then
            log_error "Pre-rollback checks failed for $service"
            if [ "$EMERGENCY" = false ]; then
                exit 1
            fi
        fi
    done
    
    # Perform rollbacks
    for service in "${services[@]}"; do
        if rollback_service "$service" "$ROLLBACK_REVISION"; then
            rolled_back_services+=("$service")
            
            # Post-rollback health check
            if ! post_rollback_health_check "$service"; then
                log_warning "Post-rollback health check failed for $service"
                all_success=false
            fi
        else
            all_success=false
            log_error "Failed to rollback $service"
        fi
    done
    
    if [ ${#rolled_back_services[@]} -eq 0 ]; then
        log_error "No services were successfully rolled back"
        exit 1
    fi
    
    # Generate report
    if [ "$DRY_RUN" = false ]; then
        generate_rollback_report "${rolled_back_services[@]}"
    fi
    
    if [ "$all_success" = true ]; then
        log_success "Rollback completed successfully!"
        log_info "Rolled back services: ${rolled_back_services[*]}"
    else
        log_error "Some rollbacks failed or health checks failed. Check logs above."
        exit 1
    fi
}

# Run main function
main "$@"
