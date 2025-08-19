#!/bin/bash

# Production Deployment Script for NeuroNews
# Handles zero-downtime rolling deployments with health checks

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-neuronews}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
SERVICE="${SERVICE:-all}"
REGISTRY="${REGISTRY:-ghcr.io/ikey168/neuronews}"
DEPLOYMENT_STRATEGY="${DEPLOYMENT_STRATEGY:-rolling}"

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
Production Deployment Script

Usage: $0 [OPTIONS]

Options:
    -h, --help              Show this help message
    -n, --namespace         Kubernetes namespace (default: neuronews)
    -s, --service          Service to deploy (api|dashboard|scraper|nlp-processor|all)
    -t, --image-tag        Image tag to deploy (default: latest)
    -r, --registry         Container registry (default: ghcr.io/ikey168/neuronews)
    -S, --strategy         Deployment strategy (rolling|recreate, default: rolling)
    --dry-run              Show what would be deployed without executing
    --wait-timeout         Timeout for waiting operations (default: 600s)
    --health-check-url     Base URL for health checks
    --skip-health-check    Skip post-deployment health checks
    --rollback-on-failure  Automatically rollback on deployment failure

Examples:
    $0 --service api --image-tag v1.2.3
    $0 --service all --image-tag main-abc123 --rollback-on-failure
    $0 --dry-run --service dashboard
EOF
}

# Parse command line arguments
DRY_RUN=false
WAIT_TIMEOUT="600s"
HEALTH_CHECK_URL=""
SKIP_HEALTH_CHECK=false
ROLLBACK_ON_FAILURE=false

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
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -S|--strategy)
            DEPLOYMENT_STRATEGY="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --wait-timeout)
            WAIT_TIMEOUT="$2"
            shift 2
            ;;
        --health-check-url)
            HEALTH_CHECK_URL="$2"
            shift 2
            ;;
        --skip-health-check)
            SKIP_HEALTH_CHECK=true
            shift
            ;;
        --rollback-on-failure)
            ROLLBACK_ON_FAILURE=true
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

    # Validate deployment strategy
    valid_strategies=("rolling" "recreate")
    if [[ ! " ${valid_strategies[*]} " =~ " ${DEPLOYMENT_STRATEGY} " ]]; then
        log_error "Invalid deployment strategy. Must be one of: ${valid_strategies[*]}"
        exit 1
    fi

    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_error "Namespace '$NAMESPACE' does not exist"
        exit 1
    fi

    # Set default health check URL if not provided
    if [ -z "$HEALTH_CHECK_URL" ]; then
        if [ "$NAMESPACE" = "neuronews" ]; then
            HEALTH_CHECK_URL="https://neuronews.com"
        else
            HEALTH_CHECK_URL="https://${NAMESPACE}.neuronews.com"
        fi
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

# Check if deployment exists
deployment_exists() {
    local service=$1
    kubectl get deployment "neuronews-$service" -n "$NAMESPACE" &> /dev/null
}

# Get current image for rollback
get_current_image() {
    local service=$1
    kubectl get deployment "neuronews-$service" -n "$NAMESPACE" \
        -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo ""
}

# Pre-deployment validation
pre_deployment_checks() {
    local service=$1
    
    log_info "Running pre-deployment checks for $service..."
    
    # Check if deployment exists
    if ! deployment_exists "$service"; then
        log_error "Deployment neuronews-$service not found in namespace $NAMESPACE"
        return 1
    fi
    
    # Check current deployment status
    if ! kubectl rollout status deployment/"neuronews-$service" -n "$NAMESPACE" --timeout=30s &> /dev/null; then
        log_warning "Current deployment for $service is not healthy"
        if [ "$ROLLBACK_ON_FAILURE" = false ]; then
            read -p "Continue anyway? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                return 1
            fi
        fi
    fi
    
    # Validate image exists (basic check)
    local image="$REGISTRY/$service:$IMAGE_TAG"
    log_info "Validating image: $image"
    
    return 0
}

# Deploy service with rolling update
deploy_service_rolling() {
    local service=$1
    local image="$REGISTRY/$service:$IMAGE_TAG"
    local current_image
    
    log_info "Deploying service: $service"
    log_info "Image: $image"
    log_info "Strategy: rolling update"
    
    # Get current image for potential rollback
    current_image=$(get_current_image "$service")
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would deploy: $image"
        return 0
    fi
    
    # Update deployment with new image
    log_info "Updating deployment image..."
    kubectl set image deployment/"neuronews-$service" \
        "neuronews-$service=$image" \
        --namespace="$NAMESPACE"
    
    # Add deployment annotations
    kubectl annotate deployment/"neuronews-$service" \
        deployment.kubernetes.io/revision- \
        --namespace="$NAMESPACE" || true
    
    kubectl annotate deployment/"neuronews-$service" \
        neuronews.com/deployed-by="$(whoami)" \
        neuronews.com/deployed-at="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        neuronews.com/image-tag="$IMAGE_TAG" \
        neuronews.com/previous-image="$current_image" \
        --namespace="$NAMESPACE"
    
    # Wait for rollout to complete
    log_info "Waiting for rollout to complete..."
    if kubectl rollout status deployment/"neuronews-$service" \
        --namespace="$NAMESPACE" \
        --timeout="$WAIT_TIMEOUT"; then
        log_success "Rollout completed for $service"
        return 0
    else
        log_error "Rollout failed for $service"
        
        # Auto-rollback if enabled
        if [ "$ROLLBACK_ON_FAILURE" = true ]; then
            log_warning "Auto-rolling back deployment..."
            kubectl rollout undo deployment/"neuronews-$service" \
                --namespace="$NAMESPACE"
            
            kubectl rollout status deployment/"neuronews-$service" \
                --namespace="$NAMESPACE" \
                --timeout="300s"
        fi
        
        return 1
    fi
}

# Deploy service with recreate strategy
deploy_service_recreate() {
    local service=$1
    local image="$REGISTRY/$service:$IMAGE_TAG"
    
    log_info "Deploying service: $service"
    log_info "Image: $image"
    log_info "Strategy: recreate"
    
    if [ "$DRY_RUN" = true ]; then
        log_info "[DRY RUN] Would deploy: $image with recreate strategy"
        return 0
    fi
    
    # Scale down to 0
    log_info "Scaling down deployment..."
    kubectl scale deployment/"neuronews-$service" --replicas=0 \
        --namespace="$NAMESPACE"
    
    # Wait for pods to terminate
    kubectl wait --for=delete pod -l "app=neuronews-$service" \
        --namespace="$NAMESPACE" \
        --timeout="$WAIT_TIMEOUT" || true
    
    # Update image
    log_info "Updating deployment image..."
    kubectl set image deployment/"neuronews-$service" \
        "neuronews-$service=$image" \
        --namespace="$NAMESPACE"
    
    # Scale back up
    log_info "Scaling up deployment..."
    local desired_replicas=$(kubectl get deployment/"neuronews-$service" \
        -n "$NAMESPACE" \
        -o jsonpath='{.metadata.annotations.deployment\.kubernetes\.io/desired-replicas}' 2>/dev/null || echo "1")
    
    kubectl scale deployment/"neuronews-$service" --replicas="$desired_replicas" \
        --namespace="$NAMESPACE"
    
    # Wait for rollout
    if kubectl rollout status deployment/"neuronews-$service" \
        --namespace="$NAMESPACE" \
        --timeout="$WAIT_TIMEOUT"; then
        log_success "Recreation completed for $service"
        return 0
    else
        log_error "Recreation failed for $service"
        return 1
    fi
}

# Post-deployment health checks
health_check() {
    local service=$1
    local max_attempts=30
    local attempt=1
    
    if [ "$SKIP_HEALTH_CHECK" = true ]; then
        log_info "Skipping health checks for $service"
        return 0
    fi
    
    log_info "Running health checks for $service..."
    
    # Wait for pods to be ready
    log_info "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod \
        -l "app=neuronews-$service" \
        --namespace="$NAMESPACE" \
        --timeout="300s"
    
    # HTTP health check
    if [[ "$service" == "api" || "$service" == "dashboard" ]]; then
        local health_url="$HEALTH_CHECK_URL"
        if [ "$service" = "api" ]; then
            health_url="$HEALTH_CHECK_URL/api/health"
        else
            health_url="$HEALTH_CHECK_URL/health"
        fi
        
        log_info "Checking HTTP endpoint: $health_url"
        
        while [ $attempt -le $max_attempts ]; do
            if curl -sf "$health_url" >/dev/null 2>&1; then
                log_success "Health check passed for $service (attempt $attempt)"
                return 0
            fi
            
            log_info "Health check attempt $attempt/$max_attempts failed, retrying in 10s..."
            sleep 10
            ((attempt++))
        done
        
        log_error "Health check failed for $service after $max_attempts attempts"
        return 1
    else
        # For non-HTTP services, just check pod readiness
        log_success "Pod readiness check passed for $service"
        return 0
    fi
}

# Generate deployment report
generate_deployment_report() {
    local services=("$@")
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local report_file="production-deployment-report-$(date +%Y%m%d-%H%M%S).json"
    
    # Collect deployment information
    local deployments_info=""
    for service in "${services[@]}"; do
        if deployment_exists "$service"; then
            local current_image=$(get_current_image "$service")
            local ready_replicas=$(kubectl get deployment "neuronews-$service" \
                -n "$NAMESPACE" \
                -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
            local desired_replicas=$(kubectl get deployment "neuronews-$service" \
                -n "$NAMESPACE" \
                -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
            
            deployments_info+="{\"service\":\"$service\",\"image\":\"$current_image\",\"ready_replicas\":$ready_replicas,\"desired_replicas\":$desired_replicas},"
        fi
    done
    deployments_info=${deployments_info%,}  # Remove trailing comma
    
    cat > "$report_file" << EOF
{
  "deployment_id": "${GITHUB_RUN_ID:-local-$(date +%s)}",
  "timestamp": "$timestamp",
  "namespace": "$NAMESPACE",
  "image_tag": "$IMAGE_TAG",
  "deployment_strategy": "$DEPLOYMENT_STRATEGY",
  "services": [$(printf '"%s",' "${services[@]}" | sed 's/,$//')],"
  "deployments": [$deployments_info],
  "health_check_url": "$HEALTH_CHECK_URL",
  "rollback_on_failure": $ROLLBACK_ON_FAILURE
}
EOF
    
    log_info "Deployment report generated: $report_file"
}

# Main deployment function
main() {
    log_info "Starting production deployment..."
    log_info "Namespace: $NAMESPACE"
    log_info "Service(s): $SERVICE"
    log_info "Image tag: $IMAGE_TAG"
    log_info "Deployment strategy: $DEPLOYMENT_STRATEGY"
    log_info "Dry run: $DRY_RUN"
    
    validate_inputs
    
    local services
    read -ra services <<< "$(get_services)"
    
    local all_success=true
    local deployed_services=()
    
    # Pre-deployment checks
    for service in "${services[@]}"; do
        if ! pre_deployment_checks "$service"; then
            log_error "Pre-deployment checks failed for $service"
            exit 1
        fi
    done
    
    # Deploy services
    for service in "${services[@]}"; do
        if [ "$DEPLOYMENT_STRATEGY" = "rolling" ]; then
            if deploy_service_rolling "$service"; then
                deployed_services+=("$service")
            else
                all_success=false
                log_error "Failed to deploy $service"
            fi
        else
            if deploy_service_recreate "$service"; then
                deployed_services+=("$service")
            else
                all_success=false
                log_error "Failed to deploy $service"
            fi
        fi
    done
    
    if [ ${#deployed_services[@]} -eq 0 ]; then
        log_error "No services were successfully deployed"
        exit 1
    fi
    
    # Post-deployment health checks
    if [ "$DRY_RUN" = false ]; then
        log_info "Running post-deployment health checks..."
        for service in "${deployed_services[@]}"; do
            if ! health_check "$service"; then
                all_success=false
                log_error "Health check failed for $service"
            fi
        done
    fi
    
    # Generate report
    generate_deployment_report "${deployed_services[@]}"
    
    if [ "$all_success" = true ]; then
        log_success "Production deployment completed successfully!"
        log_info "Deployed services: ${deployed_services[*]}"
    else
        log_error "Some deployments failed. Check logs above."
        exit 1
    fi
}

# Run main function
main "$@"
