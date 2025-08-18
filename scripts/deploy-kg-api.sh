#!/bin/bash
"""
Knowledge Graph API Kubernetes Deployment Script
Issue #75: Deploy Knowledge Graph API in Kubernetes

This script deploys the enhanced Knowledge Graph API with AWS Neptune backend,
Redis caching, optimization features, and comprehensive monitoring.
"""

set -euo pipefail

# Configuration
NAMESPACE="neuronews"
API_VERSION="v2.0.0"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"
SKIP_REDIS="${SKIP_REDIS:-false}"
SKIP_MONITORING="${SKIP_MONITORING:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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
        echo -e "${CYAN}[DEBUG]${NC} $1"
    fi
}

log_section() {
    echo
    echo -e "${CYAN}=== $1 ===${NC}"
    echo
}

# Function to check prerequisites
check_prerequisites() {
    log_section "Checking Prerequisites"
    
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
    if [[ ! -d "k8s/knowledge-graph-api" ]]; then
        log_error "Must be run from the project root directory"
        log_error "Expected directory: k8s/knowledge-graph-api"
        exit 1
    fi
    
    # Check cluster version
    K8S_VERSION=$(kubectl version --short --client | grep "Client Version" | cut -d' ' -f3)
    log_debug "Kubernetes client version: $K8S_VERSION"
    
    # Check available resources
    log_debug "Checking cluster resources..."
    kubectl top nodes --no-headers > /dev/null 2>&1 || log_warning "Metrics server not available"
    
    log_success "Prerequisites check passed"
}

# Function to validate configuration
validate_configuration() {
    log_section "Validating Configuration"
    
    # Check required environment variables
    local required_vars=(
        "NEPTUNE_ENDPOINT"
    )
    
    local missing_vars=()
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing_vars+=("$var")
        fi
    done
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        log_warning "Missing environment variables:"
        for var in "${missing_vars[@]}"; do
            log_warning "  - $var"
        done
        log_info "These can be set in the ConfigMap after deployment"
    fi
    
    # Validate Neptune endpoint format
    if [[ -n "${NEPTUNE_ENDPOINT:-}" ]]; then
        if [[ ! $NEPTUNE_ENDPOINT =~ ^wss?:// ]]; then
            log_warning "Neptune endpoint should start with ws:// or wss://"
        fi
        log_debug "Neptune endpoint: $NEPTUNE_ENDPOINT"
    fi
    
    log_success "Configuration validation completed"
}

# Function to create namespace
create_namespace() {
    log_section "Creating Namespace and RBAC"
    
    local manifest_file="k8s/knowledge-graph-api/namespace-rbac.yaml"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
    else
        log_info "Applying namespace and RBAC configuration..."
        if kubectl apply -f "$manifest_file"; then
            log_success "Namespace and RBAC applied successfully"
        else
            log_error "Failed to apply namespace and RBAC"
            exit 1
        fi
    fi
}

# Function to deploy configuration
deploy_configuration() {
    log_section "Deploying Configuration"
    
    local manifest_file="k8s/knowledge-graph-api/configmap.yaml"
    
    # Update configuration with environment variables if provided
    if [[ -n "${NEPTUNE_ENDPOINT:-}" && "$DRY_RUN" != "true" ]]; then
        log_info "Updating Neptune endpoint in configuration..."
        # Create a temporary file with updated configuration
        local temp_file=$(mktemp)
        sed "s|wss://neuronews-neptune-cluster.*amazonaws.com:8182/gremlin|$NEPTUNE_ENDPOINT|g" \
            "$manifest_file" > "$temp_file"
        manifest_file="$temp_file"
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
    else
        log_info "Applying configuration..."
        if kubectl apply -f "$manifest_file"; then
            log_success "Configuration applied successfully"
            
            # Verify ConfigMap
            if kubectl get configmap kg-api-config -n $NAMESPACE &> /dev/null; then
                log_debug "ConfigMap kg-api-config created successfully"
            fi
            
            if kubectl get secret kg-api-secrets -n $NAMESPACE &> /dev/null; then
                log_debug "Secret kg-api-secrets created successfully"
            fi
        else
            log_error "Failed to apply configuration"
            exit 1
        fi
    fi
    
    # Clean up temporary file
    if [[ -n "${temp_file:-}" && -f "$temp_file" ]]; then
        rm -f "$temp_file"
    fi
}

# Function to deploy Redis cache
deploy_redis() {
    if [[ "$SKIP_REDIS" == "true" ]]; then
        log_warning "Skipping Redis deployment (SKIP_REDIS=true)"
        return 0
    fi
    
    log_section "Deploying Redis Cache"
    
    local manifest_file="k8s/knowledge-graph-api/redis.yaml"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
    else
        log_info "Applying Redis cache configuration..."
        if kubectl apply -f "$manifest_file"; then
            log_success "Redis cache applied successfully"
            
            # Wait for Redis to be ready
            log_info "Waiting for Redis to be ready..."
            if kubectl wait --for=condition=Available deployment/kg-api-redis -n $NAMESPACE --timeout=300s; then
                log_success "Redis deployment is ready"
                
                # Verify Redis service
                if kubectl get service kg-api-redis-service -n $NAMESPACE &> /dev/null; then
                    log_debug "Redis service created successfully"
                fi
                
                # Test Redis connectivity
                log_info "Testing Redis connectivity..."
                if kubectl run redis-test --image=redis:7.0-alpine --rm -i --restart=Never -n $NAMESPACE \
                   -- redis-cli -h kg-api-redis-service ping 2>/dev/null | grep -q PONG; then
                    log_success "Redis connectivity test passed"
                else
                    log_warning "Redis connectivity test failed (may need more time)"
                fi
            else
                log_warning "Redis deployment did not become ready within 5 minutes"
            fi
        else
            log_error "Failed to apply Redis cache"
            exit 1
        fi
    fi
}

# Function to deploy the main API
deploy_api() {
    log_section "Deploying Knowledge Graph API"
    
    local manifest_file="k8s/knowledge-graph-api/deployment.yaml"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
    else
        log_info "Applying Knowledge Graph API deployment..."
        if kubectl apply -f "$manifest_file"; then
            log_success "API deployment applied successfully"
            
            # Wait for deployment to be ready
            log_info "Waiting for API deployment to be ready..."
            if kubectl wait --for=condition=Available deployment/knowledge-graph-api -n $NAMESPACE --timeout=600s; then
                log_success "API deployment is ready"
                
                # Verify service
                if kubectl get service knowledge-graph-api-service -n $NAMESPACE &> /dev/null; then
                    log_debug "API service created successfully"
                fi
                
                # Check pod status
                local pod_count=$(kubectl get pods -l app=knowledge-graph-api -n $NAMESPACE --no-headers | wc -l)
                local ready_pods=$(kubectl get pods -l app=knowledge-graph-api -n $NAMESPACE --no-headers | grep "Running" | wc -l)
                log_info "API pods: $ready_pods/$pod_count ready"
                
            else
                log_warning "API deployment did not become ready within 10 minutes"
                log_info "Checking pod status..."
                kubectl get pods -l app=knowledge-graph-api -n $NAMESPACE
            fi
        else
            log_error "Failed to apply API deployment"
            exit 1
        fi
    fi
}

# Function to deploy scaling and ingress
deploy_scaling_ingress() {
    log_section "Deploying Scaling and Ingress"
    
    local manifest_file="k8s/knowledge-graph-api/scaling-ingress.yaml"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
    else
        log_info "Applying scaling and ingress configuration..."
        if kubectl apply -f "$manifest_file"; then
            log_success "Scaling and ingress applied successfully"
            
            # Verify HPA
            if kubectl get hpa knowledge-graph-api-hpa -n $NAMESPACE &> /dev/null; then
                log_debug "HPA created successfully"
                
                # Check HPA status
                local hpa_status=$(kubectl get hpa knowledge-graph-api-hpa -n $NAMESPACE -o jsonpath='{.status.conditions[0].type}')
                if [[ "$hpa_status" == "ScalingActive" ]]; then
                    log_success "HPA is active"
                else
                    log_warning "HPA status: $hpa_status"
                fi
            fi
            
            # Verify PDB
            if kubectl get pdb knowledge-graph-api-pdb -n $NAMESPACE &> /dev/null; then
                log_debug "Pod Disruption Budget created successfully"
            fi
            
            # Verify Ingress
            if kubectl get ingress knowledge-graph-api-ingress -n $NAMESPACE &> /dev/null; then
                log_debug "Ingress created successfully"
                
                # Show ingress information
                log_info "Ingress endpoints:"
                kubectl get ingress knowledge-graph-api-ingress -n $NAMESPACE -o custom-columns=HOST:.spec.rules[*].host --no-headers | tr ' ' '\n' | sed 's/^/  - https:\/\//'
            fi
            
        else
            log_error "Failed to apply scaling and ingress"
            exit 1
        fi
    fi
}

# Function to deploy monitoring
deploy_monitoring() {
    if [[ "$SKIP_MONITORING" == "true" ]]; then
        log_warning "Skipping monitoring deployment (SKIP_MONITORING=true)"
        return 0
    fi
    
    log_section "Deploying Monitoring"
    
    # Check if Prometheus operator is available
    if ! kubectl get crd servicemonitors.monitoring.coreos.com &> /dev/null; then
        log_warning "Prometheus operator not found, skipping ServiceMonitor"
        log_info "Install Prometheus operator for full monitoring support"
        return 0
    fi
    
    local manifest_file="k8s/knowledge-graph-api/monitoring.yaml"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        kubectl apply -f "$manifest_file" --dry-run=client -o yaml > /dev/null
    else
        log_info "Applying monitoring configuration..."
        if kubectl apply -f "$manifest_file"; then
            log_success "Monitoring applied successfully"
            
            # Verify ServiceMonitors
            if kubectl get servicemonitor knowledge-graph-api-monitor -n $NAMESPACE &> /dev/null; then
                log_debug "API ServiceMonitor created successfully"
            fi
            
            if kubectl get servicemonitor kg-api-redis-monitor -n $NAMESPACE &> /dev/null; then
                log_debug "Redis ServiceMonitor created successfully"
            fi
            
            # Verify PrometheusRule
            if kubectl get prometheusrule knowledge-graph-api-alerts -n $NAMESPACE &> /dev/null; then
                log_debug "PrometheusRule created successfully"
            fi
            
            # Verify Grafana dashboard
            if kubectl get configmap kg-api-grafana-dashboard -n $NAMESPACE &> /dev/null; then
                log_debug "Grafana dashboard ConfigMap created successfully"
            fi
            
        else
            log_warning "Failed to apply monitoring (non-critical)"
        fi
    fi
}

# Function to run health checks
run_health_checks() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Skipping health checks"
        return 0
    fi
    
    log_section "Running Health Checks"
    
    # Check if pods are running
    log_info "Checking pod status..."
    local api_pods=$(kubectl get pods -l app=knowledge-graph-api -n $NAMESPACE --no-headers | grep "Running" | wc -l)
    local redis_pods=$(kubectl get pods -l app=kg-api-redis -n $NAMESPACE --no-headers | grep "Running" | wc -l)
    
    if [[ $api_pods -gt 0 ]]; then
        log_success "API pods running: $api_pods"
    else
        log_error "No API pods running"
        kubectl get pods -l app=knowledge-graph-api -n $NAMESPACE
    fi
    
    if [[ "$SKIP_REDIS" != "true" && $redis_pods -gt 0 ]]; then
        log_success "Redis pods running: $redis_pods"
    elif [[ "$SKIP_REDIS" != "true" ]]; then
        log_error "No Redis pods running"
        kubectl get pods -l app=kg-api-redis -n $NAMESPACE
    fi
    
    # Test API endpoint
    if [[ $api_pods -gt 0 ]]; then
        log_info "Testing API health endpoint..."
        
        # Port forward and test
        local port_forward_pid=""
        kubectl port-forward service/knowledge-graph-api-service 8080:80 -n $NAMESPACE &
        port_forward_pid=$!
        
        # Give port-forward time to establish
        sleep 5
        
        if curl -s -f http://localhost:8080/api/v2/graph/health > /dev/null 2>&1; then
            log_success "API health check passed"
        else
            log_warning "API health check failed (may need more time to initialize)"
        fi
        
        # Clean up port forward
        if [[ -n "$port_forward_pid" ]]; then
            kill $port_forward_pid 2>/dev/null || true
        fi
    fi
}

# Function to show deployment status
show_deployment_status() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Deployment status not available in dry run mode"
        return 0
    fi
    
    log_section "Deployment Status"
    
    echo
    echo "📊 Knowledge Graph API Deployment Summary"
    echo "----------------------------------------"
    
    # Namespace info
    echo "Namespace: $NAMESPACE"
    echo "API Version: $API_VERSION"
    echo
    
    # Deployments
    echo "🚀 Deployments:"
    kubectl get deployments -n $NAMESPACE -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,UP-TO-DATE:.status.updatedReplicas,AVAILABLE:.status.availableReplicas
    echo
    
    # Services
    echo "🌐 Services:"
    kubectl get services -n $NAMESPACE -o custom-columns=NAME:.metadata.name,TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip,PORTS:.spec.ports[*].port
    echo
    
    # Ingress
    echo "🔗 Ingress:"
    kubectl get ingress -n $NAMESPACE 2>/dev/null || echo "No ingress resources found"
    echo
    
    # HPA
    echo "📈 Horizontal Pod Autoscaler:"
    kubectl get hpa -n $NAMESPACE 2>/dev/null || echo "No HPA resources found"
    echo
    
    # Storage
    echo "💾 Storage:"
    kubectl get pvc -n $NAMESPACE 2>/dev/null || echo "No PVC resources found"
    echo
    
    # Recent events
    echo "📋 Recent Events:"
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10
    echo
}

# Function to show next steps
show_next_steps() {
    log_section "Next Steps"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "This was a dry run. To actually deploy, run without --dry-run flag"
        return 0
    fi
    
    echo "🎉 Knowledge Graph API deployment completed!"
    echo
    echo "📋 Next Steps:"
    echo
    echo "1. 🔍 Monitor deployment:"
    echo "   kubectl get all -n $NAMESPACE"
    echo "   kubectl logs -l app=knowledge-graph-api -n $NAMESPACE -f"
    echo
    echo "2. 🧪 Test API endpoints:"
    echo "   kubectl port-forward service/knowledge-graph-api-service 8080:80 -n $NAMESPACE"
    echo "   curl http://localhost:8080/api/v2/graph/health"
    echo "   curl http://localhost:8080/api/v2/graph/stats"
    echo
    echo "3. 📊 Access monitoring:"
    echo "   kubectl port-forward service/prometheus-server 9090:80 -n monitoring"
    echo "   kubectl port-forward service/grafana 3000:80 -n monitoring"
    echo
    echo "4. 🔧 Configure Neptune endpoint (if not set):"
    echo "   kubectl edit configmap kg-api-config -n $NAMESPACE"
    echo
    echo "5. 🚀 Scale if needed:"
    echo "   kubectl scale deployment knowledge-graph-api --replicas=5 -n $NAMESPACE"
    echo
    echo "6. 🔐 Set up SSL certificates:"
    echo "   kubectl apply -f cert-manager-issuer.yaml"
    echo
    echo "📖 Documentation: https://docs.neuronews.com/knowledge-graph-api"
    echo "🐛 Issues: https://github.com/neuronews/neuronews/issues"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy Knowledge Graph API to Kubernetes with enhanced caching and optimization

Options:
    --dry-run           Perform a dry run without actually applying changes
    --verbose           Enable verbose output
    --skip-redis        Skip Redis cache deployment
    --skip-monitoring   Skip monitoring components deployment
    --namespace NAME    Set target namespace (default: $NAMESPACE)
    --help              Show this help message

Environment Variables:
    DRY_RUN            Set to 'true' for dry run mode
    VERBOSE            Set to 'true' for verbose output
    SKIP_REDIS         Set to 'true' to skip Redis deployment
    SKIP_MONITORING    Set to 'true' to skip monitoring deployment
    NEPTUNE_ENDPOINT   AWS Neptune cluster endpoint

Examples:
    # Deploy with dry run
    $0 --dry-run
    
    # Deploy with verbose output
    $0 --verbose
    
    # Deploy without Redis (use external Redis)
    $0 --skip-redis
    
    # Deploy with custom Neptune endpoint
    NEPTUNE_ENDPOINT="wss://my-cluster.amazonaws.com:8182/gremlin" $0
    
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
        --verbose)
            VERBOSE="true"
            shift
            ;;
        --skip-redis)
            SKIP_REDIS="true"
            shift
            ;;
        --skip-monitoring)
            SKIP_MONITORING="true"
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
    echo
    echo -e "${CYAN}🚀 Knowledge Graph API Kubernetes Deployment${NC}"
    echo -e "${CYAN}=============================================${NC}"
    echo
    log_info "Starting Knowledge Graph API deployment"
    log_info "Target namespace: $NAMESPACE"
    log_info "API version: $API_VERSION"
    log_info "Dry run mode: $DRY_RUN"
    log_info "Verbose mode: $VERBOSE"
    log_info "Skip Redis: $SKIP_REDIS"
    log_info "Skip monitoring: $SKIP_MONITORING"
    
    # Execute deployment steps
    check_prerequisites
    validate_configuration
    create_namespace
    deploy_configuration
    deploy_redis
    deploy_api
    deploy_scaling_ingress
    deploy_monitoring
    run_health_checks
    show_deployment_status
    show_next_steps
    
    echo
    log_success "🎉 Knowledge Graph API deployment completed successfully!"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        echo
        log_info "🔍 Quick status check:"
        kubectl get pods -l app=knowledge-graph-api -n $NAMESPACE
    fi
}

# Run main function
main "$@"
