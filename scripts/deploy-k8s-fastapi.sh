#!/bin/bash

# NeuroNews FastAPI Kubernetes Deployment Script
# Issue #72: Deploy API Server to Kubernetes

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="neuronews"
DEPLOYMENT_NAME="neuronews-fastapi"
SERVICE_NAME="neuronews-fastapi-service"
INGRESS_NAME="neuronews-fastapi-ingress"
HPA_NAME="neuronews-fastapi-hpa"

# Helper functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if kubectl can connect to cluster
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster. Please check your kubeconfig"
        exit 1
    fi
    
    log "kubectl is available and connected to cluster"
}

# Check if required tools are available
check_dependencies() {
    local deps=("kubectl" "helm" "docker")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            warn "$dep is not installed or not in PATH"
        else
            info "$dep is available"
        fi
    done
}

# Create namespace if it doesn't exist
create_namespace() {
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        info "Namespace $NAMESPACE already exists"
    else
        log "Creating namespace $NAMESPACE"
        kubectl apply -f k8s/fastapi/namespace.yaml
        log "Namespace $NAMESPACE created successfully"
    fi
}

# Deploy configurations and secrets
deploy_configs() {
    log "Deploying ConfigMaps and Secrets"
    kubectl apply -f k8s/fastapi/configmap.yaml
    log "ConfigMaps and Secrets deployed successfully"
}

# Deploy the FastAPI application
deploy_fastapi() {
    log "Deploying FastAPI application"
    
    # Apply deployment
    kubectl apply -f k8s/fastapi/deployment.yaml
    log "FastAPI deployment applied"
    
    # Apply service
    kubectl apply -f k8s/fastapi/service.yaml
    log "FastAPI service applied"
    
    # Apply policies
    kubectl apply -f k8s/fastapi/policies.yaml
    log "Policies applied"
    
    # Wait for deployment to be ready
    log "Waiting for deployment to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/$DEPLOYMENT_NAME -n $NAMESPACE
    log "FastAPI deployment is ready"
}

# Deploy HPA
deploy_hpa() {
    log "Deploying Horizontal Pod Autoscaler"
    
    # Check if metrics server is available
    if ! kubectl get apiservice v1beta1.metrics.k8s.io &> /dev/null; then
        warn "Metrics server not found. HPA may not work properly"
        warn "Please install metrics server: kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
    fi
    
    kubectl apply -f k8s/fastapi/hpa.yaml
    log "HPA deployed successfully"
}

# Deploy ingress
deploy_ingress() {
    log "Deploying Ingress Controller"
    
    # Check if ingress controller is installed
    if ! kubectl get pods -n ingress-nginx | grep -q "ingress-nginx-controller"; then
        warn "NGINX Ingress Controller not found"
        info "Installing NGINX Ingress Controller..."
        helm upgrade --install ingress-nginx ingress-nginx \
            --repo https://kubernetes.github.io/ingress-nginx \
            --namespace ingress-nginx --create-namespace
    fi
    
    kubectl apply -f k8s/fastapi/ingress.yaml
    log "Ingress deployed successfully"
}

# Deploy monitoring
deploy_monitoring() {
    log "Deploying monitoring configurations"
    kubectl apply -f k8s/fastapi/monitoring.yaml
    log "Monitoring configurations deployed successfully"
}

# Get deployment status
get_status() {
    info "=== Deployment Status ==="
    
    echo
    info "Namespace:"
    kubectl get namespace $NAMESPACE
    
    echo
    info "Pods:"
    kubectl get pods -n $NAMESPACE -l app=$DEPLOYMENT_NAME
    
    echo
    info "Services:"
    kubectl get services -n $NAMESPACE -l app=$DEPLOYMENT_NAME
    
    echo
    info "Ingress:"
    kubectl get ingress -n $NAMESPACE -l app=$DEPLOYMENT_NAME
    
    echo
    info "HPA:"
    kubectl get hpa -n $NAMESPACE -l app=$DEPLOYMENT_NAME
    
    echo
    info "Deployment:"
    kubectl get deployment -n $NAMESPACE $DEPLOYMENT_NAME
    
    echo
    info "Recent Events:"
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10
}

# Get service endpoints
get_endpoints() {
    info "=== Service Endpoints ==="
    
    # Get LoadBalancer IP
    LB_IP=$(kubectl get service $SERVICE_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "Pending")
    if [ "$LB_IP" != "Pending" ] && [ -n "$LB_IP" ]; then
        echo "LoadBalancer IP: http://$LB_IP"
    else
        warn "LoadBalancer IP is still pending or not available"
    fi
    
    # Get Ingress IP
    INGRESS_IP=$(kubectl get ingress $INGRESS_NAME -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "Pending")
    if [ "$INGRESS_IP" != "Pending" ] && [ -n "$INGRESS_IP" ]; then
        echo "Ingress IP: https://$INGRESS_IP"
    else
        warn "Ingress IP is still pending or not available"
    fi
    
    # Port forwarding option
    echo
    info "To access the API locally, run:"
    echo "kubectl port-forward service/$SERVICE_NAME -n $NAMESPACE 8000:80"
    echo "Then access: http://localhost:8000"
}

# Run health checks
health_check() {
    info "=== Health Checks ==="
    
    # Check if pods are ready
    READY_PODS=$(kubectl get pods -n $NAMESPACE -l app=$DEPLOYMENT_NAME --field-selector=status.phase=Running -o name | wc -l)
    TOTAL_PODS=$(kubectl get pods -n $NAMESPACE -l app=$DEPLOYMENT_NAME -o name | wc -l)
    
    echo "Ready Pods: $READY_PODS/$TOTAL_PODS"
    
    if [ "$READY_PODS" -eq "$TOTAL_PODS" ] && [ "$TOTAL_PODS" -gt 0 ]; then
        log "All pods are ready and running"
    else
        warn "Some pods are not ready. Check pod status above"
    fi
    
    # Test API endpoint (if accessible)
    if kubectl get service $SERVICE_NAME -n $NAMESPACE &> /dev/null; then
        info "Testing API health endpoint..."
        if kubectl run test-curl --image=curlimages/curl --rm -it --restart=Never -- \
           curl -f http://$SERVICE_NAME.$NAMESPACE.svc.cluster.local:8000/health &> /dev/null; then
            log "API health check passed"
        else
            warn "API health check failed or timed out"
        fi
    fi
}

# Scale deployment
scale_deployment() {
    local replicas=${1:-3}
    log "Scaling deployment to $replicas replicas"
    kubectl scale deployment $DEPLOYMENT_NAME -n $NAMESPACE --replicas=$replicas
    kubectl wait --for=condition=available --timeout=300s deployment/$DEPLOYMENT_NAME -n $NAMESPACE
    log "Deployment scaled successfully"
}

# Clean up deployment
cleanup() {
    warn "Cleaning up deployment..."
    
    kubectl delete -f k8s/fastapi/monitoring.yaml --ignore-not-found=true
    kubectl delete -f k8s/fastapi/ingress.yaml --ignore-not-found=true
    kubectl delete -f k8s/fastapi/hpa.yaml --ignore-not-found=true
    kubectl delete -f k8s/fastapi/service.yaml --ignore-not-found=true
    kubectl delete -f k8s/fastapi/deployment.yaml --ignore-not-found=true
    kubectl delete -f k8s/fastapi/policies.yaml --ignore-not-found=true
    kubectl delete -f k8s/fastapi/configmap.yaml --ignore-not-found=true
    
    warn "Cleanup completed"
}

# Show logs
show_logs() {
    local lines=${1:-100}
    info "Showing last $lines lines of logs from all pods:"
    kubectl logs -n $NAMESPACE -l app=$DEPLOYMENT_NAME --tail=$lines --follow=false
}

# Main function
main() {
    local action=${1:-deploy}
    
    case $action in
        "deploy")
            log "Starting NeuroNews FastAPI Kubernetes deployment"
            check_kubectl
            check_dependencies
            create_namespace
            deploy_configs
            deploy_fastapi
            deploy_hpa
            deploy_ingress
            deploy_monitoring
            get_status
            get_endpoints
            health_check
            log "Deployment completed successfully!"
            ;;
        "status")
            get_status
            get_endpoints
            health_check
            ;;
        "scale")
            scale_deployment $2
            ;;
        "logs")
            show_logs $2
            ;;
        "cleanup")
            cleanup
            ;;
        "help"|"--help"|"-h")
            echo "Usage: $0 {deploy|status|scale|logs|cleanup|help}"
            echo ""
            echo "Commands:"
            echo "  deploy    - Deploy the FastAPI application to Kubernetes"
            echo "  status    - Show deployment status and endpoints"
            echo "  scale N   - Scale deployment to N replicas"
            echo "  logs [N]  - Show last N lines of logs (default: 100)"
            echo "  cleanup   - Remove all deployed resources"
            echo "  help      - Show this help message"
            ;;
        *)
            error "Unknown action: $action"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
