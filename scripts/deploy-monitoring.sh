#!/bin/bash

# NeuroNews Monitoring & Logging Deployment Script
# Issue #77: Implement Kubernetes Monitoring & Logging
#
# This script deploys Prometheus, Grafana, AlertManager, and CloudWatch logging
# for comprehensive monitoring and alerting of the NeuroNews platform.

set -euo pipefail

# Configuration
NAMESPACE="monitoring"
MONITORING_VERSION="v1.0.0"
DRY_RUN="${DRY_RUN:-false}"
VERBOSE="${VERBOSE:-false}"
SKIP_CLOUDWATCH="${SKIP_CLOUDWATCH:-false}"
AWS_REGION="${AWS_REGION:-us-east-1}"
CLUSTER_NAME="${CLUSTER_NAME:-neuronews}"

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

# Function to validate YAML file
validate_yaml() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        log_error "File not found: $file"
        return 1
    fi
    
    # Basic YAML validation using python
    if command -v python3 &> /dev/null; then
        python3 -c "
import yaml
import sys
try:
    with open('$file', 'r') as f:
        list(yaml.safe_load_all(f))
    print('Valid YAML')
except Exception as e:
    print(f'Invalid YAML: {e}')
    sys.exit(1)
        " > /dev/null
        return $?
    else
        log_debug "Python3 not available, skipping YAML validation"
        return 0
    fi
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
        log_warning "Cannot connect to Kubernetes cluster"
        log_info "This appears to be a development environment"
        log_info "The script will validate manifests but cannot deploy to a cluster"
        
        if [[ "$DRY_RUN" != "true" ]]; then
            log_warning "Switching to dry-run mode due to missing cluster connection"
            DRY_RUN="true"
        fi
    fi
    
    # Check if we're in the right directory
    if [[ ! -d "k8s/monitoring" ]]; then
        log_error "Must be run from the project root directory"
        log_error "Expected directory: k8s/monitoring"
        exit 1
    fi
    
    # Check cluster version if connected
    if kubectl cluster-info &> /dev/null; then
        K8S_VERSION=$(kubectl version --short --client 2>/dev/null | grep "Client Version" | cut -d' ' -f3 || echo "unknown")
        log_debug "Kubernetes client version: $K8S_VERSION"
        
        # Check if Prometheus operator is available
        if kubectl get crd prometheuses.monitoring.coreos.com &> /dev/null; then
            log_debug "Prometheus operator detected"
        else
            log_warning "Prometheus operator not found - ServiceMonitors may not work"
        fi
    fi
    
    log_success "Prerequisites check completed"
}

# Function to validate configuration
validate_configuration() {
    log_section "Validating Configuration"
    
    # Check AWS configuration for CloudWatch
    if [[ "$SKIP_CLOUDWATCH" != "true" ]]; then
        log_info "CloudWatch logging enabled - validating AWS configuration"
        log_debug "AWS Region: $AWS_REGION"
        log_debug "Cluster Name: $CLUSTER_NAME"
        
        # Check if AWS CLI is available (optional)
        if command -v aws &> /dev/null; then
            if aws sts get-caller-identity &> /dev/null; then
                log_debug "AWS credentials are configured"
            else
                log_warning "AWS credentials not configured - ensure IRSA or node IAM roles are set up"
            fi
        else
            log_debug "AWS CLI not available, assuming IRSA or node IAM roles"
        fi
    else
        log_info "CloudWatch logging disabled"
    fi
    
    log_success "Configuration validation completed"
}

# Function to apply or validate manifest
apply_manifest() {
    local manifest_file="$1"
    local description="$2"
    
    log_info "Processing $description..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would apply: $manifest_file"
        
        # Validate YAML syntax
        if validate_yaml "$manifest_file"; then
            log_debug "[DRY RUN] YAML validation passed for $manifest_file"
        else
            log_error "[DRY RUN] YAML validation failed for $manifest_file"
            return 1
        fi
        
        # If cluster is available, do client-side dry run
        if kubectl cluster-info &> /dev/null; then
            if kubectl apply -f "$manifest_file" --dry-run=client > /dev/null 2>&1; then
                log_debug "[DRY RUN] Kubernetes validation passed for $manifest_file"
            else
                log_warning "[DRY RUN] Kubernetes validation failed for $manifest_file"
            fi
        fi
    else
        log_info "Applying $description..."
        if kubectl apply -f "$manifest_file"; then
            log_success "$description applied successfully"
        else
            log_error "Failed to apply $description"
            exit 1
        fi
    fi
}

# Function to create namespace and RBAC
create_namespace_rbac() {
    log_section "Creating Monitoring Namespace and RBAC"
    apply_manifest "k8s/monitoring/namespace-rbac.yaml" "monitoring namespace and RBAC"
}

# Function to deploy exporters
deploy_exporters() {
    log_section "Deploying Node Exporter and kube-state-metrics"
    apply_manifest "k8s/monitoring/exporters.yaml" "monitoring exporters"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Waiting for exporters to be ready..."
        
        # Wait for Node Exporter DaemonSet
        if kubectl rollout status daemonset/node-exporter -n $NAMESPACE --timeout=300s; then
            log_success "Node Exporter DaemonSet is ready"
        else
            log_warning "Node Exporter DaemonSet not ready within 5 minutes"
        fi
        
        # Wait for kube-state-metrics deployment
        if kubectl wait --for=condition=Available deployment/kube-state-metrics -n $NAMESPACE --timeout=300s; then
            log_success "kube-state-metrics deployment is ready"
        else
            log_warning "kube-state-metrics deployment not ready within 5 minutes"
        fi
    fi
}

# Function to deploy Prometheus
deploy_prometheus() {
    log_section "Deploying Prometheus"
    apply_manifest "k8s/monitoring/prometheus.yaml" "Prometheus server"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Waiting for Prometheus to be ready..."
        
        if kubectl wait --for=condition=Available deployment/prometheus -n $NAMESPACE --timeout=600s; then
            log_success "Prometheus deployment is ready"
            
            # Check if PVC is bound
            if kubectl get pvc prometheus-storage -n $NAMESPACE -o jsonpath='{.status.phase}' | grep -q "Bound"; then
                log_debug "Prometheus storage PVC is bound"
            else
                log_warning "Prometheus storage PVC is not bound"
            fi
        else
            log_warning "Prometheus deployment not ready within 10 minutes"
            log_info "Checking pod status..."
            kubectl get pods -l app.kubernetes.io/name=prometheus -n $NAMESPACE
        fi
    fi
}

# Function to deploy AlertManager
deploy_alertmanager() {
    log_section "Deploying AlertManager"
    apply_manifest "k8s/monitoring/alertmanager.yaml" "AlertManager"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Waiting for AlertManager to be ready..."
        
        if kubectl wait --for=condition=Available deployment/alertmanager -n $NAMESPACE --timeout=300s; then
            log_success "AlertManager deployment is ready"
        else
            log_warning "AlertManager deployment not ready within 5 minutes"
        fi
    fi
}

# Function to deploy Grafana
deploy_grafana() {
    log_section "Deploying Grafana"
    apply_manifest "k8s/monitoring/grafana.yaml" "Grafana dashboard"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Waiting for Grafana to be ready..."
        
        if kubectl wait --for=condition=Available deployment/grafana -n $NAMESPACE --timeout=300s; then
            log_success "Grafana deployment is ready"
            
            # Show Grafana access information
            log_info "Grafana access information:"
            echo "  Username: admin"
            echo "  Password: neuronews123"
            
            # Check for LoadBalancer IP
            local external_ip=$(kubectl get service grafana -n $NAMESPACE -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "")
            if [[ -n "$external_ip" ]]; then
                echo "  External URL: http://$external_ip:3000"
            else
                echo "  Port-forward: kubectl port-forward service/grafana 3000:3000 -n $NAMESPACE"
            fi
        else
            log_warning "Grafana deployment not ready within 5 minutes"
        fi
    fi
}

# Function to deploy CloudWatch logging
deploy_cloudwatch_logging() {
    if [[ "$SKIP_CLOUDWATCH" == "true" ]]; then
        log_warning "Skipping CloudWatch logging deployment (SKIP_CLOUDWATCH=true)"
        return 0
    fi
    
    log_section "Deploying CloudWatch Logging"
    
    # Update CloudWatch configuration with region and cluster name
    local cloudwatch_file="k8s/monitoring/cloudwatch-logging.yaml"
    local temp_file=$(mktemp)
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Updating CloudWatch configuration..."
        sed -e "s/us-east-1/$AWS_REGION/g" \
            -e "s/neuronews/$CLUSTER_NAME/g" \
            "$cloudwatch_file" > "$temp_file"
        cloudwatch_file="$temp_file"
    fi
    
    apply_manifest "$cloudwatch_file" "CloudWatch logging with Fluent Bit"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        log_info "Waiting for Fluent Bit to be ready..."
        
        if kubectl rollout status daemonset/fluent-bit -n $NAMESPACE --timeout=300s; then
            log_success "Fluent Bit DaemonSet is ready"
            
            # Show CloudWatch log groups
            log_info "CloudWatch log groups that will be created:"
            echo "  - /aws/kubernetes/$CLUSTER_NAME/application"
            echo "  - /aws/kubernetes/$CLUSTER_NAME/scrapers"
            echo "  - /aws/kubernetes/$CLUSTER_NAME/nlp"
        else
            log_warning "Fluent Bit DaemonSet not ready within 5 minutes"
        fi
    fi
    
    # Clean up temporary file
    if [[ -n "${temp_file:-}" && -f "$temp_file" ]]; then
        rm -f "$temp_file"
    fi
}

# Function to deploy ingress and service monitors
deploy_ingress_servicemonitors() {
    log_section "Deploying Ingress and ServiceMonitors"
    apply_manifest "k8s/monitoring/ingress-servicemonitors.yaml" "monitoring ingress and ServiceMonitors"
    
    if [[ "$DRY_RUN" != "true" ]]; then
        # Check if ingress was created
        if kubectl get ingress monitoring-ingress -n $NAMESPACE &> /dev/null; then
            log_success "Monitoring ingress created"
            
            log_info "External monitoring endpoints (when DNS is configured):"
            echo "  - https://grafana.neuronews.com"
            echo "  - https://prometheus.neuronews.com"
            echo "  - https://alertmanager.neuronews.com"
        fi
        
        # Check ServiceMonitors
        if kubectl get servicemonitor -n $NAMESPACE &> /dev/null; then
            local sm_count=$(kubectl get servicemonitor -n $NAMESPACE --no-headers | wc -l)
            log_debug "Created $sm_count ServiceMonitors"
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
    
    # Check Prometheus
    log_info "Checking Prometheus health..."
    if kubectl get pods -l app.kubernetes.io/name=prometheus -n $NAMESPACE --no-headers | grep -q "Running"; then
        log_success "Prometheus is running"
    else
        log_warning "Prometheus is not running properly"
    fi
    
    # Check Grafana
    log_info "Checking Grafana health..."
    if kubectl get pods -l app.kubernetes.io/name=grafana -n $NAMESPACE --no-headers | grep -q "Running"; then
        log_success "Grafana is running"
    else
        log_warning "Grafana is not running properly"
    fi
    
    # Check AlertManager
    log_info "Checking AlertManager health..."
    if kubectl get pods -l app.kubernetes.io/name=alertmanager -n $NAMESPACE --no-headers | grep -q "Running"; then
        log_success "AlertManager is running"
    else
        log_warning "AlertManager is not running properly"
    fi
    
    # Check exporters
    log_info "Checking monitoring exporters..."
    local node_exporter_pods=$(kubectl get pods -l app.kubernetes.io/name=node-exporter -n $NAMESPACE --no-headers | grep "Running" | wc -l)
    log_info "Node Exporter pods running: $node_exporter_pods"
    
    if kubectl get pods -l app.kubernetes.io/name=kube-state-metrics -n $NAMESPACE --no-headers | grep -q "Running"; then
        log_success "kube-state-metrics is running"
    else
        log_warning "kube-state-metrics is not running properly"
    fi
    
    # Check Fluent Bit if not skipped
    if [[ "$SKIP_CLOUDWATCH" != "true" ]]; then
        log_info "Checking Fluent Bit health..."
        local fluent_bit_pods=$(kubectl get pods -l app.kubernetes.io/name=fluent-bit -n $NAMESPACE --no-headers | grep "Running" | wc -l)
        log_info "Fluent Bit pods running: $fluent_bit_pods"
    fi
}

# Function to show deployment status
show_deployment_status() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Deployment status not available in dry run mode"
        return 0
    fi
    
    log_section "Monitoring Deployment Status"
    
    echo
    echo "📊 NeuroNews Monitoring & Logging Summary"
    echo "========================================="
    
    # Namespace info
    echo "Namespace: $NAMESPACE"
    echo "Monitoring Version: $MONITORING_VERSION"
    echo "AWS Region: $AWS_REGION"
    echo "Cluster Name: $CLUSTER_NAME"
    echo "CloudWatch Logging: $([ "$SKIP_CLOUDWATCH" == "true" ] && echo "Disabled" || echo "Enabled")"
    echo
    
    # Deployments
    echo "🚀 Deployments:"
    kubectl get deployments -n $NAMESPACE -o custom-columns=NAME:.metadata.name,READY:.status.readyReplicas,UP-TO-DATE:.status.updatedReplicas,AVAILABLE:.status.availableReplicas
    echo
    
    # DaemonSets
    echo "🔧 DaemonSets:"
    kubectl get daemonsets -n $NAMESPACE -o custom-columns=NAME:.metadata.name,DESIRED:.status.desiredNumberScheduled,CURRENT:.status.currentNumberScheduled,READY:.status.numberReady
    echo
    
    # Services
    echo "🌐 Services:"
    kubectl get services -n $NAMESPACE -o custom-columns=NAME:.metadata.name,TYPE:.spec.type,CLUSTER-IP:.spec.clusterIP,EXTERNAL-IP:.status.loadBalancer.ingress[0].ip,PORTS:.spec.ports[*].port
    echo
    
    # PVCs
    echo "💾 Persistent Volume Claims:"
    kubectl get pvc -n $NAMESPACE -o custom-columns=NAME:.metadata.name,STATUS:.status.phase,VOLUME:.spec.volumeName,CAPACITY:.status.capacity.storage
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
        log_info "All manifest files have been validated successfully!"
        echo
        echo "🚀 To deploy to a Kubernetes cluster:"
        echo "   1. Connect to your Kubernetes cluster"
        echo "   2. Run: ./scripts/deploy-monitoring.sh"
        echo "   3. Configure DNS for external access (optional)"
        return 0
    fi
    
    echo "🎉 NeuroNews Monitoring & Logging deployment completed!"
    echo
    echo "📋 Next Steps:"
    echo
    echo "1. 🔍 Access Grafana dashboard:"
    echo "   kubectl port-forward service/grafana 3000:3000 -n $NAMESPACE"
    echo "   Open browser: http://localhost:3000"
    echo "   Username: admin, Password: neuronews123"
    echo
    echo "2. 📊 Access Prometheus:"
    echo "   kubectl port-forward service/prometheus 9090:9090 -n $NAMESPACE"
    echo "   Open browser: http://localhost:9090"
    echo
    echo "3. 🚨 Access AlertManager:"
    echo "   kubectl port-forward service/alertmanager 9093:9093 -n $NAMESPACE"
    echo "   Open browser: http://localhost:9093"
    echo
    echo "4. 🌐 External access (configure DNS):"
    echo "   https://grafana.neuronews.com"
    echo "   https://prometheus.neuronews.com"
    echo "   https://alertmanager.neuroneus.com"
    echo
    echo "5. ☁️ CloudWatch logs (if enabled):"
    echo "   AWS Console > CloudWatch > Logs"
    echo "   Log Groups: /aws/kubernetes/$CLUSTER_NAME/*"
    echo
    echo "6. 📧 Configure AlertManager notifications:"
    echo "   kubectl edit configmap alertmanager-config -n $NAMESPACE"
    echo "   Update SMTP and Slack webhook configurations"
    echo
    echo "7. 🔐 Set up SSL certificates (if using external domains):"
    echo "   kubectl apply -f cert-manager-issuer.yaml"
    echo
    echo "📖 Documentation: https://docs.neuronews.com/monitoring"
    echo "🐛 Issues: https://github.com/neuronews/neuronews/issues"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Deploy NeuroNews Monitoring & Logging infrastructure with Prometheus, Grafana, AlertManager, and CloudWatch

Options:
    --dry-run              Perform a dry run without actually applying changes
    --verbose              Enable verbose output
    --skip-cloudwatch      Skip CloudWatch logging deployment
    --aws-region REGION    Set AWS region (default: us-east-1)
    --cluster-name NAME    Set cluster name (default: neuronews)
    --help                 Show this help message

Environment Variables:
    DRY_RUN               Set to 'true' for dry run mode
    VERBOSE               Set to 'true' for verbose output
    SKIP_CLOUDWATCH       Set to 'true' to skip CloudWatch deployment
    AWS_REGION           AWS region for CloudWatch logs
    CLUSTER_NAME         Kubernetes cluster name

Examples:
    # Deploy with dry run
    $0 --dry-run
    
    # Deploy with verbose output
    $0 --verbose
    
    # Deploy without CloudWatch logging
    $0 --skip-cloudwatch
    
    # Deploy with custom AWS region
    $0 --aws-region eu-west-1 --cluster-name neuronews-prod
    
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
        --skip-cloudwatch)
            SKIP_CLOUDWATCH="true"
            shift
            ;;
        --aws-region)
            AWS_REGION="$2"
            shift 2
            ;;
        --cluster-name)
            CLUSTER_NAME="$2"
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
    echo -e "${CYAN}📊 NeuroNews Monitoring & Logging Deployment${NC}"
    echo -e "${CYAN}==============================================${NC}"
    echo
    log_info "Starting NeuroNews Monitoring & Logging deployment"
    log_info "Target namespace: $NAMESPACE"
    log_info "Monitoring version: $MONITORING_VERSION"
    log_info "Dry run mode: $DRY_RUN"
    log_info "Verbose mode: $VERBOSE"
    log_info "Skip CloudWatch: $SKIP_CLOUDWATCH"
    log_info "AWS Region: $AWS_REGION"
    log_info "Cluster Name: $CLUSTER_NAME"
    
    # Execute deployment steps
    check_prerequisites
    validate_configuration
    create_namespace_rbac
    deploy_exporters
    deploy_prometheus
    deploy_alertmanager
    deploy_grafana
    deploy_cloudwatch_logging
    deploy_ingress_servicemonitors
    run_health_checks
    show_deployment_status
    show_next_steps
    
    echo
    if [[ "$DRY_RUN" == "true" ]]; then
        log_success "🎉 NeuroNews Monitoring & Logging dry-run validation completed successfully!"
        log_info "All Kubernetes manifests are valid and ready for deployment"
    else
        log_success "🎉 NeuroNews Monitoring & Logging deployment completed successfully!"
        
        echo
        log_info "🔍 Quick status check:"
        kubectl get pods -n $NAMESPACE
    fi
}

# Run main function
main "$@"
