#!/bin/bash
# Canary deployment script for NeuroNews services
# Usage: ./canary-deployment.sh <namespace> <image-tag>

set -e

NAMESPACE=${1:-neuronews-prod}
IMAGE_TAG=${2:-latest}
SERVICE_NAME="neuronews-api"
CANARY_WEIGHT_STEPS=(10 25 50 100)
HEALTH_CHECK_TIMEOUT=120
ROLLBACK_ON_FAILURE=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    error "kubectl is not installed or not in PATH"
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
    error "Namespace $NAMESPACE does not exist"
    exit 1
fi

log "Starting canary deployment for $SERVICE_NAME in namespace $NAMESPACE"
log "Image tag: $IMAGE_TAG"

# Create canary deployment configuration
create_canary_deployment() {
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${SERVICE_NAME}-canary
  namespace: ${NAMESPACE}
  labels:
    app: ${SERVICE_NAME}
    version: canary
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${SERVICE_NAME}
      version: canary
  template:
    metadata:
      labels:
        app: ${SERVICE_NAME}
        version: canary
    spec:
      containers:
      - name: ${SERVICE_NAME}
        image: ghcr.io/ikey168/neuronews/api:${IMAGE_TAG}
        ports:
        - containerPort: 8000
        env:
        - name: VERSION
          value: "canary"
        - name: DEPLOYMENT_TYPE
          value: "canary"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 3
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: ${SERVICE_NAME}-canary
  namespace: ${NAMESPACE}
  labels:
    app: ${SERVICE_NAME}
    version: canary
spec:
  selector:
    app: ${SERVICE_NAME}
    version: canary
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
EOF
}

# Wait for deployment to be ready
wait_for_deployment() {
    local deployment_name=$1
    local timeout=$2
    
    log "Waiting for deployment $deployment_name to be ready..."
    
    if ! kubectl rollout status deployment/$deployment_name -n $NAMESPACE --timeout=${timeout}s; then
        error "Deployment $deployment_name failed to become ready within ${timeout}s"
        return 1
    fi
    
    log "Deployment $deployment_name is ready"
    return 0
}

# Health check function
check_health() {
    local service_name=$1
    local check_duration=$2
    
    log "Running health checks for $service_name (${check_duration}s)..."
    
    # Get service endpoint
    local service_ip=$(kubectl get svc $service_name -n $NAMESPACE -o jsonpath='{.spec.clusterIP}')
    local service_port=$(kubectl get svc $service_name -n $NAMESPACE -o jsonpath='{.spec.ports[0].port}')
    
    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        error "Could not get service endpoint for $service_name"
        return 1
    fi
    
    # Run health checks
    local start_time=$(date +%s)
    local end_time=$((start_time + check_duration))
    local success_count=0
    local total_count=0
    
    while [[ $(date +%s) -lt $end_time ]]; do
        total_count=$((total_count + 1))
        
        # Health check request
        if kubectl run health-check-pod --rm -i --restart=Never --image=curlimages/curl:latest \
           -- curl -f -s "http://$service_ip:$service_port/health" &> /dev/null; then
            success_count=$((success_count + 1))
        fi
        
        sleep 5
    done
    
    local success_rate=$((success_count * 100 / total_count))
    log "Health check results: $success_count/$total_count successful ($success_rate%)"
    
    if [[ $success_rate -lt 95 ]]; then
        error "Health check success rate ($success_rate%) is below threshold (95%)"
        return 1
    fi
    
    return 0
}

# Performance check function
check_performance() {
    local service_name=$1
    
    log "Running performance checks for $service_name..."
    
    # Simple performance check using kubectl exec
    local pod_name=$(kubectl get pods -n $NAMESPACE -l app=$SERVICE_NAME,version=canary -o jsonpath='{.items[0].metadata.name}')
    
    if [[ -z "$pod_name" ]]; then
        error "Could not find canary pod"
        return 1
    fi
    
    # Check memory and CPU usage
    local metrics=$(kubectl top pod $pod_name -n $NAMESPACE --no-headers 2>/dev/null || echo "0m 0Mi")
    log "Canary pod metrics: $metrics"
    
    # For now, just check if pod is running
    local pod_status=$(kubectl get pod $pod_name -n $NAMESPACE -o jsonpath='{.status.phase}')
    if [[ "$pod_status" != "Running" ]]; then
        error "Canary pod is not in Running state: $pod_status"
        return 1
    fi
    
    return 0
}

# Cleanup function
cleanup_canary() {
    log "Cleaning up canary deployment..."
    kubectl delete deployment ${SERVICE_NAME}-canary -n $NAMESPACE --ignore-not-found=true
    kubectl delete service ${SERVICE_NAME}-canary -n $NAMESPACE --ignore-not-found=true
}

# Rollback function
rollback() {
    error "Rolling back canary deployment..."
    cleanup_canary
    exit 1
}

# Main canary deployment process
main() {
    # Create canary deployment
    log "Creating canary deployment..."
    create_canary_deployment
    
    # Wait for canary to be ready
    if ! wait_for_deployment "${SERVICE_NAME}-canary" $HEALTH_CHECK_TIMEOUT; then
        if [[ "$ROLLBACK_ON_FAILURE" == "true" ]]; then
            rollback
        fi
        exit 1
    fi
    
    # Run initial health and performance checks
    if ! check_health "${SERVICE_NAME}-canary" 60; then
        if [[ "$ROLLBACK_ON_FAILURE" == "true" ]]; then
            rollback
        fi
        exit 1
    fi
    
    if ! check_performance "${SERVICE_NAME}-canary"; then
        if [[ "$ROLLBACK_ON_FAILURE" == "true" ]]; then
            rollback
        fi
        exit 1
    fi
    
    log "Canary deployment is healthy, proceeding with traffic shifting..."
    
    # Traffic shifting simulation (in real scenario, use Istio, ArgoCD Rollouts, or similar)
    for weight in "${CANARY_WEIGHT_STEPS[@]}"; do
        log "Shifting $weight% traffic to canary..."
        
        # In a real scenario, this would update traffic routing rules
        # For demonstration, we'll simulate the process
        
        # Update replica count based on traffic weight
        local canary_replicas=$(( (weight * 3) / 100 + 1 ))  # Scale based on percentage
        kubectl scale deployment ${SERVICE_NAME}-canary -n $NAMESPACE --replicas=$canary_replicas
        
        # Wait for scaling
        sleep 30
        
        # Run health checks
        if ! check_health "${SERVICE_NAME}-canary" 60; then
            error "Health checks failed at $weight% traffic"
            if [[ "$ROLLBACK_ON_FAILURE" == "true" ]]; then
                rollback
            fi
            exit 1
        fi
        
        # Run performance checks
        if ! check_performance "${SERVICE_NAME}-canary"; then
            error "Performance checks failed at $weight% traffic"
            if [[ "$ROLLBACK_ON_FAILURE" == "true" ]]; then
                rollback
            fi
            exit 1
        fi
        
        log "Traffic at $weight% is stable, waiting before next step..."
        
        # Wait between steps (shorter for demo)
        if [[ $weight -ne 100 ]]; then
            sleep 60
        fi
    done
    
    # If we reach here, canary is successful
    log "Canary deployment successful! Promoting to production..."
    
    # Update main deployment with new image
    kubectl set image deployment/$SERVICE_NAME $SERVICE_NAME=ghcr.io/ikey168/neuronews/api:$IMAGE_TAG -n $NAMESPACE
    
    # Wait for main deployment rollout
    if ! wait_for_deployment "$SERVICE_NAME" 300; then
        error "Failed to update main deployment"
        exit 1
    fi
    
    # Final health check on main deployment
    if ! check_health "$SERVICE_NAME" 120; then
        error "Main deployment health check failed"
        exit 1
    fi
    
    # Cleanup canary
    cleanup_canary
    
    log "✅ Canary deployment completed successfully!"
    log "Main deployment updated to image tag: $IMAGE_TAG"
}

# Trap errors and cleanup
trap cleanup_canary EXIT

# Run main function
main "$@"
