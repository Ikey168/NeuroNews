#!/bin/bash

# Canary Deployment Script for NeuroNews
# This script manages canary deployments using Argo Rollouts

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-neuronews}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
TRAFFIC_PERCENTAGE="${TRAFFIC_PERCENTAGE:-10}"
SERVICE="${SERVICE:-all}"
REGISTRY="${REGISTRY:-ghcr.io/ikey168/neuronews}"

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
Canary Deployment Script

Usage: $0 [OPTIONS]

Options:
    -h, --help              Show this help message
    -n, --namespace         Kubernetes namespace (default: neuronews)
    -s, --service          Service to deploy (api|dashboard|scraper|nlp-processor|all)
    -t, --image-tag        Image tag to deploy (default: latest)
    -p, --traffic-percent  Initial traffic percentage (1-100, default: 10)
    -r, --registry         Container registry (default: ghcr.io/ikey168/neuronews)
    --dry-run              Show what would be deployed without executing
    --auto-promote         Automatically promote if canary succeeds
    --wait-timeout         Timeout for waiting operations (default: 600s)

Examples:
    $0 --service api --image-tag v1.2.3 --traffic-percent 25
    $0 --service all --image-tag main-abc123 --auto-promote
    $0 --dry-run --service dashboard
EOF
}

# Parse command line arguments
DRY_RUN=false
AUTO_PROMOTE=false
WAIT_TIMEOUT="600s"

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
        -t|--image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -p|--traffic-percent)
            TRAFFIC_PERCENTAGE="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --auto-promote)
            AUTO_PROMOTE=true
            shift
            ;;
        --wait-timeout)
            WAIT_TIMEOUT="$2"
            shift 2
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

    # Check if argo rollouts CLI is available
    if ! command -v kubectl-argo-rollouts &> /dev/null; then
        log_error "kubectl-argo-rollouts is not installed or not in PATH"
        exit 1
    fi

    # Validate traffic percentage
    if [[ ! "$TRAFFIC_PERCENTAGE" =~ ^[0-9]+$ ]] || [ "$TRAFFIC_PERCENTAGE" -lt 1 ] || [ "$TRAFFIC_PERCENTAGE" -gt 100 ]; then
        log_error "Traffic percentage must be a number between 1 and 100"
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

# Get list of services to deploy
get_services() {
    if [ "$SERVICE" = "all" ]; then
        echo "api dashboard scraper nlp-processor"
    else
        echo "$SERVICE"
    fi
}

# Check if rollout exists
rollout_exists() {
    local service=$1
    kubectl get rollout "neuronews-$service-rollout" -n "$NAMESPACE" &> /dev/null
}

# Deploy canary for a single service
deploy_service_canary() {
    local service=$1
    local image="$REGISTRY/$service:$IMAGE_TAG"
    
    log_info "Deploying canary for service: $service"
    log_info "Image: $image"
    log_info "Traffic percentage: $TRAFFIC_PERCENTAGE%"
    
    if ! rollout_exists "$service"; then
        log_warning "Rollout neuronews-$service-rollout not found in namespace $NAMESPACE"
        return 1
    fi
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would deploy: $image with $TRAFFIC_PERCENTAGE% traffic"
        return 0
    fi
    
    # Update rollout with new image
    log_info "Updating rollout image..."
    kubectl argo rollouts set image "neuronews-$service-rollout" \
        "neuronews-$service=$image" \
        --namespace="$NAMESPACE"
    
    # Set canary traffic weight
    log_info "Setting canary traffic weight to $TRAFFIC_PERCENTAGE%..."
    kubectl argo rollouts set canary-weight "neuronews-$service-rollout" "$TRAFFIC_PERCENTAGE" \
        --namespace="$NAMESPACE"
    
    # Wait for canary to be ready
    log_info "Waiting for canary to be ready..."
    if kubectl argo rollouts wait "neuronews-$service-rollout" \
        --for=health \
        --timeout="$WAIT_TIMEOUT" \
        --namespace="$NAMESPACE"; then
        log_success "Canary deployment ready for $service"
        return 0
    else
        log_error "Canary deployment failed for $service"
        return 1
    fi
}

# Monitor canary health
monitor_canary() {
    local service=$1
    local duration=${2:-300}  # 5 minutes default
    local interval=${3:-30}   # 30 seconds default
    
    log_info "Monitoring canary for $service (${duration}s)..."
    
    local start_time=$(date +%s)
    local success_count=0
    local total_checks=0
    
    while [ $(($(date +%s) - start_time)) -lt $duration ]; do
        total_checks=$((total_checks + 1))
        
        # Check rollout status
        if kubectl argo rollouts status "neuronews-$service-rollout" -n "$NAMESPACE" --timeout=10s &> /dev/null; then
            # Check if any canary pods are running
            local canary_pods=$(kubectl get pods -n "$NAMESPACE" \
                -l "app=neuronews-$service,rollouts-pod-template-hash" \
                --field-selector=status.phase=Running \
                --no-headers 2>/dev/null | wc -l)
            
            if [ "$canary_pods" -gt 0 ]; then
                success_count=$((success_count + 1))
                log_info "✅ Canary health check $total_checks passed ($canary_pods pods running)"
            else
                log_warning "⚠️ Canary health check $total_checks: no running pods"
            fi
        else
            log_warning "⚠️ Canary health check $total_checks: rollout not healthy"
        fi
        
        sleep $interval
    done
    
    local success_rate=$((success_count * 100 / total_checks))
    log_info "📊 Monitoring complete: $success_count/$total_checks checks passed ($success_rate%)"
    
    # Return success if >90% success rate
    if [ $success_rate -ge 90 ]; then
        log_success "Canary monitoring passed for $service"
        return 0
    else
        log_error "Canary monitoring failed for $service"
        return 1
    fi
}

# Promote canary to production
promote_canary() {
    local service=$1
    
    log_info "Promoting canary to production for $service..."
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would promote canary for $service"
        return 0
    fi
    
    kubectl argo rollouts promote "neuronews-$service-rollout" \
        --namespace="$NAMESPACE"
    
    # Wait for promotion to complete
    if kubectl argo rollouts wait "neuronews-$service-rollout" \
        --for=completion \
        --timeout="$WAIT_TIMEOUT" \
        --namespace="$NAMESPACE"; then
        log_success "Canary promoted successfully for $service"
        return 0
    else
        log_error "Canary promotion failed for $service"
        return 1
    fi
}

# Rollback canary
rollback_canary() {
    local service=$1
    
    log_warning "Rolling back canary for $service..."
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would rollback canary for $service"
        return 0
    fi
    
    kubectl argo rollouts abort "neuronews-$service-rollout" \
        --namespace="$NAMESPACE"
    
    kubectl argo rollouts undo "neuronews-$service-rollout" \
        --namespace="$NAMESPACE"
    
    log_warning "Canary rolled back for $service"
}

# Generate deployment report
generate_report() {
    local services=("$@")
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    cat > "canary-deployment-report-$(date +%Y%m%d-%H%M%S).json" << EOF
{
  "deployment_id": "${GITHUB_RUN_ID:-local-$(date +%s)}",
  "timestamp": "$timestamp",
  "namespace": "$NAMESPACE",
  "image_tag": "$IMAGE_TAG",
  "traffic_percentage": $TRAFFIC_PERCENTAGE,
  "auto_promote": $AUTO_PROMOTE,
  "services": [$(printf '"%s",' "${services[@]}" | sed 's/,$//')]
}
EOF
    
    log_info "Deployment report generated"
}

# Main deployment function
main() {
    log_info "Starting canary deployment..."
    log_info "Namespace: $NAMESPACE"
    log_info "Service(s): $SERVICE"
    log_info "Image tag: $IMAGE_TAG"
    log_info "Traffic percentage: $TRAFFIC_PERCENTAGE%"
    log_info "Auto promote: $AUTO_PROMOTE"
    log_info "Dry run: $DRY_RUN"
    
    validate_inputs
    
    local services
    read -ra services <<< "$(get_services)"
    
    local all_success=true
    local deployed_services=()
    
    # Deploy canaries
    for service in "${services[@]}"; do
        if deploy_service_canary "$service"; then
            deployed_services+=("$service")
        else
            all_success=false
            log_error "Failed to deploy canary for $service"
        fi
    done
    
    if [ ${#deployed_services[@]} -eq 0 ]; then
        log_error "No services were successfully deployed"
        exit 1
    fi
    
    # Monitor canaries if not dry run
    if [ "$DRY_RUN" = false ]; then
        log_info "Monitoring deployed canaries..."
        for service in "${deployed_services[@]}"; do
            if ! monitor_canary "$service"; then
                all_success=false
                rollback_canary "$service"
            fi
        done
    fi
    
    # Auto-promote if enabled and all succeeded
    if [ "$AUTO_PROMOTE" = true ] && [ "$all_success" = true ] && [ "$DRY_RUN" = false ]; then
        log_info "Auto-promoting successful canaries..."
        for service in "${deployed_services[@]}"; do
            promote_canary "$service"
        done
    fi
    
    # Generate report
    generate_report "${deployed_services[@]}"
    
    if [ "$all_success" = true ]; then
        log_success "Canary deployment completed successfully!"
        if [ "$AUTO_PROMOTE" = false ] && [ "$DRY_RUN" = false ]; then
            log_info "Manual promotion required. Run:"
            for service in "${deployed_services[@]}"; do
                echo "  kubectl argo rollouts promote neuronews-$service-rollout -n $NAMESPACE"
            done
        fi
    else
        log_error "Some canary deployments failed. Check logs above."
        exit 1
    fi
}

# Run main function
main "$@"
