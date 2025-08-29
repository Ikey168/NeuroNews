#!/bin/bash

# VPA Installation and Configuration Script for NeuroNews
# Implements phased approach: Off mode → Auto mode for ingestion & dbt pipelines

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
VPA_VERSION="${VPA_VERSION:-1.0.0}"
DRY_RUN="${DRY_RUN:-false}"
PHASE="${PHASE:-install}"  # install, recommendations, auto
NAMESPACE_DATA_PIPELINE="${NAMESPACE_DATA_PIPELINE:-data-pipeline}"

# Functions
print_header() {
    echo -e "${BLUE}===================================================${NC}"
    echo -e "${BLUE}🔧 NeuroNews VPA Rightsizing Installation${NC}"
    echo -e "${BLUE}===================================================${NC}"
    echo ""
}

print_section() {
    echo -e "${GREEN}📊 $1${NC}"
    echo "-------------------------------------------"
}

check_prerequisites() {
    print_section "Checking Prerequisites"
    
    # Check kubectl
    if ! command -v kubectl &> /dev/null; then
        echo -e "${RED}❌ kubectl not found. Please install kubectl first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ kubectl found${NC}"
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        echo -e "${RED}❌ Cannot connect to Kubernetes cluster. Check your kubeconfig.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Cluster connectivity confirmed${NC}"
    
    # Check if metrics-server is running
    if ! kubectl get deployment metrics-server -n kube-system &> /dev/null; then
        echo -e "${RED}❌ metrics-server not found. VPA requires metrics-server for recommendations.${NC}"
        echo "Install metrics-server first: kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml"
        exit 1
    fi
    echo -e "${GREEN}✅ metrics-server found${NC}"
    
    # Check if Prometheus is available (recommended for better metrics)
    if kubectl get service prometheus-server -n monitoring &> /dev/null; then
        echo -e "${GREEN}✅ Prometheus server found - will use for enhanced metrics${NC}"
        PROMETHEUS_AVAILABLE=true
    else
        echo -e "${YELLOW}⚠️  Prometheus not found - will use basic metrics-server${NC}"
        PROMETHEUS_AVAILABLE=false
    fi
    
    echo ""
}

create_namespace() {
    print_section "Creating VPA System Namespace"
    
    if kubectl get namespace vpa-system &> /dev/null; then
        echo -e "${YELLOW}⚠️  vpa-system namespace already exists${NC}"
    else
        if [[ "$DRY_RUN" == "true" ]]; then
            echo -e "${BLUE}[DRY RUN] Would create vpa-system namespace${NC}"
        else
            kubectl create namespace vpa-system
            echo -e "${GREEN}✅ vpa-system namespace created${NC}"
        fi
    fi
    
    # Ensure data-pipeline namespace exists
    if ! kubectl get namespace "$NAMESPACE_DATA_PIPELINE" &> /dev/null; then
        echo -e "${YELLOW}⚠️  Creating $NAMESPACE_DATA_PIPELINE namespace for VPA targets${NC}"
        if [[ "$DRY_RUN" == "true" ]]; then
            echo -e "${BLUE}[DRY RUN] Would create $NAMESPACE_DATA_PIPELINE namespace${NC}"
        else
            kubectl create namespace "$NAMESPACE_DATA_PIPELINE"
            echo -e "${GREEN}✅ $NAMESPACE_DATA_PIPELINE namespace created${NC}"
        fi
    fi
    
    echo ""
}

install_vpa_crds() {
    print_section "Installing VPA Custom Resource Definitions"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${BLUE}[DRY RUN] Would install VPA CRDs${NC}"
        kubectl apply --dry-run=client -f k8s/autoscaling/vpa-crd.yaml
    else
        kubectl apply -f k8s/autoscaling/vpa-crd.yaml
        echo -e "${GREEN}✅ VPA CRDs installed${NC}"
        
        # Wait for CRDs to be established
        echo "Waiting for CRDs to be established..."
        kubectl wait --for condition=established --timeout=60s crd/verticalpodautoscalers.autoscaling.k8s.io
        kubectl wait --for condition=established --timeout=60s crd/verticalpodautoscalercheckpoints.autoscaling.k8s.io
        echo -e "${GREEN}✅ VPA CRDs established${NC}"
    fi
    
    echo ""
}

install_vpa_rbac() {
    print_section "Installing VPA RBAC Configuration"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${BLUE}[DRY RUN] Would install VPA RBAC${NC}"
        kubectl apply --dry-run=client -f k8s/autoscaling/vpa-rbac.yaml
    else
        kubectl apply -f k8s/autoscaling/vpa-rbac.yaml
        echo -e "${GREEN}✅ VPA RBAC configuration installed${NC}"
    fi
    
    echo ""
}

generate_webhook_certs() {
    print_section "Generating Webhook Certificates"
    
    if kubectl get secret vpa-webhook-certs -n vpa-system &> /dev/null; then
        echo -e "${YELLOW}⚠️  VPA webhook certificates already exist${NC}"
        return
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${BLUE}[DRY RUN] Would generate webhook certificates${NC}"
        return
    fi
    
    # Create temporary directory for certificate generation
    CERT_DIR=$(mktemp -d)
    cd "$CERT_DIR"
    
    # Generate CA private key
    openssl genrsa -out ca.key 2048
    
    # Generate CA certificate
    openssl req -new -x509 -days 365 -key ca.key -subj "/C=US/ST=CA/L=San Francisco/O=NeuroNews/CN=VPA CA" -out ca.crt
    
    # Generate server private key
    openssl genrsa -out server.key 2048
    
    # Create certificate signing request config
    cat > csr.conf <<EOF
[req]
default_bits = 2048
prompt = no
distinguished_name = dn
req_extensions = v3_req
[dn]
C=US
ST=CA
L=San Francisco
O=NeuroNews
CN=vpa-webhook.vpa-system.svc
[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names
[alt_names]
DNS.1 = vpa-webhook
DNS.2 = vpa-webhook.vpa-system
DNS.3 = vpa-webhook.vpa-system.svc
DNS.4 = vpa-webhook.vpa-system.svc.cluster.local
EOF
    
    # Generate certificate signing request
    openssl req -new -key server.key -out server.csr -config csr.conf
    
    # Generate server certificate
    openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt -days 365 -extensions v3_req -extfile csr.conf
    
    # Create Kubernetes secret
    kubectl create secret generic vpa-webhook-certs \
        --from-file=caCert.pem=ca.crt \
        --from-file=serverCert.pem=server.crt \
        --from-file=serverKey.pem=server.key \
        -n vpa-system
    
    # Cleanup
    cd - > /dev/null
    rm -rf "$CERT_DIR"
    
    echo -e "${GREEN}✅ VPA webhook certificates generated and stored${NC}"
    echo ""
}

install_vpa_components() {
    print_section "Installing VPA Components"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${BLUE}[DRY RUN] Would install VPA deployments${NC}"
        kubectl apply --dry-run=client -f k8s/autoscaling/vpa-deployment.yaml
    else
        kubectl apply -f k8s/autoscaling/vpa-deployment.yaml
        echo -e "${GREEN}✅ VPA components installed${NC}"
        
        # Wait for deployments to be ready
        echo "Waiting for VPA components to be ready..."
        kubectl wait --for=condition=available --timeout=300s deployment/vpa-recommender -n vpa-system
        kubectl wait --for=condition=available --timeout=300s deployment/vpa-updater -n vpa-system
        kubectl wait --for=condition=available --timeout=300s deployment/vpa-admission-controller -n vpa-system
        
        echo -e "${GREEN}✅ All VPA components are ready${NC}"
    fi
    
    echo ""
}

install_pipeline_vpas() {
    print_section "Installing VPA Objects for Pipelines"
    
    case "$PHASE" in
        "install"|"recommendations")
            echo -e "${BLUE}Installing VPA objects in 'Off' mode (recommendations-only)${NC}"
            if [[ "$DRY_RUN" == "true" ]]; then
                echo -e "${BLUE}[DRY RUN] Would install pipeline VPAs in Off mode${NC}"
                kubectl apply --dry-run=client -f k8s/autoscaling/vpa-ingestion-pipeline.yaml
                kubectl apply --dry-run=client -f k8s/autoscaling/vpa-dbt-pipeline.yaml
            else
                kubectl apply -f k8s/autoscaling/vpa-ingestion-pipeline.yaml
                kubectl apply -f k8s/autoscaling/vpa-dbt-pipeline.yaml
                echo -e "${GREEN}✅ Pipeline VPAs installed in recommendations-only mode${NC}"
                echo -e "${YELLOW}📝 Note: VPAs are in 'Off' mode. Monitor recommendations for 1-2 weeks before switching to 'Auto'${NC}"
            fi
            ;;
        "auto")
            echo -e "${BLUE}Switching VPA objects to 'Auto' mode for automatic resource updates${NC}"
            if [[ "$DRY_RUN" == "true" ]]; then
                echo -e "${BLUE}[DRY RUN] Would switch VPAs to Auto mode${NC}"
            else
                switch_to_auto_mode
            fi
            ;;
    esac
    
    echo ""
}

switch_to_auto_mode() {
    print_section "Switching VPAs to Auto Mode"
    
    # Get all VPAs in data-pipeline namespace
    VPA_NAMES=$(kubectl get vpa -n "$NAMESPACE_DATA_PIPELINE" -o jsonpath='{.items[*].metadata.name}')
    
    if [[ -z "$VPA_NAMES" ]]; then
        echo -e "${RED}❌ No VPA objects found in $NAMESPACE_DATA_PIPELINE namespace${NC}"
        return 1
    fi
    
    for vpa_name in $VPA_NAMES; do
        echo -e "${BLUE}Switching $vpa_name to Auto mode...${NC}"
        
        # Patch the VPA to change updateMode from "Off" to "Auto"
        kubectl patch vpa "$vpa_name" -n "$NAMESPACE_DATA_PIPELINE" --type='merge' -p='{"spec":{"updatePolicy":{"updateMode":"Auto"}}}'
        
        echo -e "${GREEN}✅ $vpa_name switched to Auto mode${NC}"
    done
    
    echo -e "${YELLOW}⚠️  VPAs are now in Auto mode. They will automatically update pod resources based on recommendations.${NC}"
    echo -e "${YELLOW}⚠️  Monitor resource allocation changes and application performance closely.${NC}"
}

verify_installation() {
    print_section "Verifying VPA Installation"
    
    # Check VPA components
    echo "VPA Components Status:"
    kubectl get pods -n vpa-system
    echo ""
    
    # Check VPA objects
    echo "VPA Objects Status:"
    kubectl get vpa -n "$NAMESPACE_DATA_PIPELINE" -o wide 2>/dev/null || {
        echo -e "${YELLOW}No VPA objects found in $NAMESPACE_DATA_PIPELINE namespace${NC}"
    }
    echo ""
    
    # Check for recommendations (if VPAs exist)
    if kubectl get vpa -n "$NAMESPACE_DATA_PIPELINE" &> /dev/null; then
        echo "Sample VPA Recommendations:"
        VPA_NAME=$(kubectl get vpa -n "$NAMESPACE_DATA_PIPELINE" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
        if [[ -n "$VPA_NAME" ]]; then
            kubectl describe vpa "$VPA_NAME" -n "$NAMESPACE_DATA_PIPELINE" | grep -A 20 "Container Recommendations:" || {
                echo -e "${YELLOW}No recommendations available yet. Wait a few minutes for VPA to collect metrics.${NC}"
            }
        fi
    fi
    
    echo ""
}

show_next_steps() {
    print_section "Next Steps"
    
    case "$PHASE" in
        "install"|"recommendations")
            cat << EOF
🎯 VPA Installation Complete - Recommendations Phase

1. Monitor VPA recommendations for 1-2 weeks:
   kubectl get vpa -n $NAMESPACE_DATA_PIPELINE -o wide
   kubectl describe vpa <vpa-name> -n $NAMESPACE_DATA_PIPELINE

2. Check resource utilization trends:
   kubectl top pods -n $NAMESPACE_DATA_PIPELINE --sort-by=memory
   kubectl top pods -n $NAMESPACE_DATA_PIPELINE --sort-by=cpu

3. Review recommendations in monitoring dashboards:
   - FinOps Dashboard: http://grafana:3000/d/neuronews-finops/
   - VPA Metrics: http://prometheus:9090/graph

4. When ready, switch to Auto mode:
   PHASE=auto ./install-vpa-rightsizing.sh

🔍 Key Metrics to Monitor:
- container_memory_allocation_bytes (should decrease)
- container_cpu_allocation_millicores (should optimize)
- VPA recommendation vs actual usage gap
- Application performance and stability

📋 VPA Objects Created:
$(kubectl get vpa -n $NAMESPACE_DATA_PIPELINE --no-headers 2>/dev/null | awk '{print "- " $1}' || echo "- None found")

EOF
            ;;
        "auto")
            cat << EOF
🎯 VPA Auto Mode Enabled

✅ VPAs are now automatically updating pod resources based on recommendations.

🔍 Monitor Closely:
1. Resource allocation changes:
   kubectl get pods -n $NAMESPACE_DATA_PIPELINE -o custom-columns="NAME:.metadata.name,CPU-REQ:.spec.containers[0].resources.requests.cpu,MEM-REQ:.spec.containers[0].resources.requests.memory"

2. Application performance:
   - Monitor application logs for errors
   - Check response times and throughput
   - Watch for pod restarts: kubectl get pods -n $NAMESPACE_DATA_PIPELINE -w

3. Cost optimization metrics:
   - FinOps Dashboard: http://grafana:3000/d/neuronews-finops/
   - Unit Economics: Cost per article/query trends

🚨 Rollback if Needed:
If issues occur, quickly switch back to Off mode:
kubectl patch vpa <vpa-name> -n $NAMESPACE_DATA_PIPELINE --type='merge' -p='{"spec":{"updatePolicy":{"updateMode":"Off"}}}'

EOF
            ;;
    esac
}

# Main execution
main() {
    print_header
    
    echo -e "${BLUE}Phase: $PHASE${NC}"
    echo -e "${BLUE}Target Namespace: $NAMESPACE_DATA_PIPELINE${NC}"
    echo -e "${BLUE}Dry Run: $DRY_RUN${NC}"
    echo ""
    
    check_prerequisites
    
    case "$PHASE" in
        "install"|"recommendations")
            create_namespace
            install_vpa_crds
            install_vpa_rbac
            generate_webhook_certs
            install_vpa_components
            install_pipeline_vpas
            ;;
        "auto")
            install_pipeline_vpas
            ;;
        *)
            echo -e "${RED}❌ Invalid phase: $PHASE. Use 'install', 'recommendations', or 'auto'${NC}"
            exit 1
            ;;
    esac
    
    verify_installation
    show_next_steps
}

# Script usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

OPTIONS:
    PHASE=<phase>                   Phase to execute: install, recommendations, auto (default: install)
    DRY_RUN=true                    Show what would be done without executing
    NAMESPACE_DATA_PIPELINE=<ns>    Target namespace for pipeline VPAs (default: data-pipeline)
    VPA_VERSION=<version>           VPA version to install (default: 1.0.0)

Examples:
    # Initial installation (recommendations-only mode)
    ./install-vpa-rightsizing.sh

    # Dry run to see what would be installed
    DRY_RUN=true ./install-vpa-rightsizing.sh

    # Switch to auto mode after 1-2 weeks of monitoring
    PHASE=auto ./install-vpa-rightsizing.sh

    # Install in different namespace
    NAMESPACE_DATA_PIPELINE=my-pipeline ./install-vpa-rightsizing.sh

EOF
}

# Handle script arguments
if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    show_usage
    exit 0
fi

# Run main function
main "$@"
