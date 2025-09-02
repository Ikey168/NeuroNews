#!/bin/bash
# OpenCost Installation Script
# Issue #402: Install OpenCost via Helm + expose Prometheus & API

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_section() {
    echo ""
    echo -e "${BLUE}===== $1 =====${NC}"
}

# Configuration
NAMESPACE="opencost"
RELEASE_NAME="opencost"
CHART_REPO="https://opencost.github.io/opencost-helm-chart"
VALUES_FILE="k8s/opencost/values.yaml"

print_section "OpenCost FinOps Installation"

# Step 1: Check prerequisites
print_info "Checking prerequisites..."

if ! command -v helm &> /dev/null; then
    print_error "Helm is not installed. Please install Helm first."
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed. Please install kubectl first."
    exit 1
fi

# Check if kubectl can connect to cluster
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    exit 1
fi

print_success "Prerequisites verified"

# Step 2: Add OpenCost Helm repository
print_info "Adding OpenCost Helm repository..."

if helm repo list | grep -q "opencost"; then
    print_info "OpenCost repo already exists, updating..."
    helm repo update opencost
else
    helm repo add opencost "$CHART_REPO"
    print_success "OpenCost Helm repository added"
fi

helm repo update

# Step 3: Create namespace
print_info "Creating namespace '$NAMESPACE'..."

if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    print_info "Namespace '$NAMESPACE' already exists"
else
    kubectl create namespace "$NAMESPACE"
    print_success "Namespace '$NAMESPACE' created"
fi

# Step 4: Install OpenCost
print_info "Installing OpenCost with Helm..."

if helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
    print_info "OpenCost release already exists, upgrading..."
    helm upgrade "$RELEASE_NAME" opencost/opencost \
        --namespace "$NAMESPACE" \
        --values "$VALUES_FILE" \
        --wait
else
    helm install "$RELEASE_NAME" opencost/opencost \
        --namespace "$NAMESPACE" \
        --create-namespace \
        --values "$VALUES_FILE" \
        --wait
fi

print_success "OpenCost installed successfully"

# Step 5: Verify installation
print_info "Verifying installation..."

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=opencost -n "$NAMESPACE" --timeout=300s

# Check pod status
PODS=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=opencost --no-headers | wc -l)
READY_PODS=$(kubectl get pods -n "$NAMESPACE" -l app.kubernetes.io/name=opencost --no-headers | grep "Running" | wc -l)

if [ "$PODS" -eq "$READY_PODS" ] && [ "$PODS" -gt 0 ]; then
    print_success "OpenCost pods are running ($READY_PODS/$PODS)"
else
    print_warning "Some OpenCost pods may not be ready ($READY_PODS/$PODS)"
fi

# Step 6: Check services
print_info "Checking services..."

kubectl get services -n "$NAMESPACE"

# Step 7: Test API endpoints
print_info "Testing OpenCost API endpoints..."

# Port forward for testing
kubectl port-forward -n "$NAMESPACE" svc/opencost 9003:9003 &
PORT_FORWARD_PID=$!

# Wait for port forward to establish
sleep 5

# Test allocation API
if curl -s http://localhost:9003/allocation > /dev/null; then
    print_success "Allocation API is accessible"
else
    print_warning "Allocation API test failed (may need time to collect data)"
fi

# Test assets API
if curl -s http://localhost:9003/assets > /dev/null; then
    print_success "Assets API is accessible"
else
    print_warning "Assets API test failed (may need time to collect data)"
fi

# Test metrics endpoint
if curl -s http://localhost:9003/metrics | grep -q "opencost"; then
    print_success "Metrics endpoint is working"
else
    print_warning "Metrics endpoint test failed"
fi

# Clean up port forward
kill $PORT_FORWARD_PID 2>/dev/null || true

# Step 8: Display access information
print_section "Installation Complete"

print_success "OpenCost has been installed successfully!"
echo ""
print_info "📊 Access Information:"
echo "   • Namespace: $NAMESPACE"
echo "   • Release: $RELEASE_NAME"
echo "   • API Service: opencost.$NAMESPACE:9003"
echo "   • UI Service: opencost-ui.$NAMESPACE:9090"
echo ""
print_info "🔧 Port Forward Commands:"
echo "   # API access:"
echo "   kubectl port-forward -n $NAMESPACE svc/opencost 9003:9003"
echo ""
echo "   # UI access:"
echo "   kubectl port-forward -n $NAMESPACE svc/opencost-ui 9090:9090"
echo ""
print_info "📈 API Endpoints:"
echo "   • Allocation: http://localhost:9003/allocation"
echo "   • Assets: http://localhost:9003/assets"
echo "   • Metrics: http://localhost:9003/metrics"
echo ""
print_info "📚 Documentation:"
echo "   • See docs/finops/opencost.md for usage examples"
echo ""
print_warning "⏰ Note: Cost data may take 10-15 minutes to appear after installation"
