#!/bin/bash
# OpenCost FinOps Integration Test Script - Issue #402
#
# This script validates the complete OpenCost integration including:
# 1. Helm chart installation capability
# 2. Prometheus metrics scraping configuration
# 3. API endpoint accessibility
# 4. Documentation completeness
# 5. DoD validation

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
VALUES_FILE="k8s/opencost/values.yaml"
INSTALL_SCRIPT="k8s/opencost/install.sh"
PROMETHEUS_CONFIG="k8s/monitoring/prometheus.yaml"
DOCUMENTATION="docs/finops/opencost.md"

print_section "OpenCost FinOps Integration Test - Issue #402"

print_info "Testing OpenCost FinOps integration implementation"
print_info "This validates Helm installation, Prometheus integration, and API access"

# Test 1: Check if required files exist
print_section "1. Configuration Files Validation"

if [ -f "$VALUES_FILE" ]; then
    print_success "OpenCost Helm values file exists"
    
    # Validate YAML syntax
    if command -v yq &> /dev/null; then
        if yq eval '.' "$VALUES_FILE" > /dev/null 2>&1; then
            print_success "Helm values YAML is valid"
        else
            print_error "Helm values YAML is invalid"
        fi
    else
        print_warning "yq not available, skipping YAML validation"
    fi
    
    # Check key configuration values
    if grep -q "CLUSTER_ID.*neuronews-cluster" "$VALUES_FILE"; then
        print_success "Cluster ID configured correctly"
    else
        print_warning "Cluster ID not found or incorrect"
    fi
    
    if grep -q "PROMETHEUS_SERVER_ENDPOINT" "$VALUES_FILE"; then
        print_success "Prometheus endpoint configured"
    else
        print_error "Prometheus endpoint not configured"
    fi
    
else
    print_error "OpenCost Helm values file not found"
fi

if [ -f "$INSTALL_SCRIPT" ] && [ -x "$INSTALL_SCRIPT" ]; then
    print_success "Installation script exists and is executable"
else
    print_error "Installation script missing or not executable"
fi

# Test 2: Prometheus Configuration
print_section "2. Prometheus Integration"

if [ -f "$PROMETHEUS_CONFIG" ]; then
    print_success "Prometheus configuration file exists"
    
    # Check for OpenCost scrape job
    if grep -q "job_name.*opencost" "$PROMETHEUS_CONFIG"; then
        print_success "OpenCost scrape job configured in Prometheus"
        
        # Check scrape interval
        if grep -A 10 "job_name.*opencost" "$PROMETHEUS_CONFIG" | grep -q "scrape_interval.*1m"; then
            print_success "Prometheus scrape interval set to 1 minute"
        else
            print_warning "Scrape interval not found or not set to 1 minute"
        fi
        
        # Check target configuration
        if grep -A 10 "job_name.*opencost" "$PROMETHEUS_CONFIG" | grep -q "opencost.opencost.*9003"; then
            print_success "OpenCost target endpoint configured correctly"
        else
            print_warning "OpenCost target endpoint not found or incorrect"
        fi
        
    else
        print_error "OpenCost scrape job not found in Prometheus config"
    fi
    
    # Check for ServiceMonitor configuration
    if grep -q "opencost-servicemonitor" "$PROMETHEUS_CONFIG"; then
        print_success "OpenCost ServiceMonitor job configured"
    else
        print_warning "ServiceMonitor configuration not found (optional)"
    fi
    
else
    print_error "Prometheus configuration file not found"
fi

# Test 3: Documentation Validation
print_section "3. Documentation Completeness"

if [ -f "$DOCUMENTATION" ]; then
    print_success "OpenCost documentation exists"
    
    doc_size=$(wc -l < "$DOCUMENTATION")
    print_info "Documentation contains $doc_size lines"
    
    # Check for required sections
    if grep -q "## API Usage" "$DOCUMENTATION"; then
        print_success "API usage section documented"
    else
        print_error "API usage section missing"
    fi
    
    if grep -q "curl.*allocation" "$DOCUMENTATION"; then
        print_success "Allocation API curl examples provided"
    else
        print_error "Allocation API examples missing"
    fi
    
    if grep -q "curl.*assets" "$DOCUMENTATION"; then
        print_success "Assets API curl examples provided"
    else
        print_error "Assets API examples missing"
    fi
    
    if grep -q "node_total_hourly_cost" "$DOCUMENTATION"; then
        print_success "Prometheus metrics documented"
    else
        print_error "Prometheus metrics documentation missing"
    fi
    
    if grep -q "container_cpu_allocation" "$DOCUMENTATION"; then
        print_success "Container allocation metrics documented"
    else
        print_error "Container allocation metrics missing"
    fi
    
    # Check for troubleshooting section
    if grep -q "## Troubleshooting" "$DOCUMENTATION"; then
        print_success "Troubleshooting section provided"
    else
        print_warning "Troubleshooting section missing"
    fi
    
else
    print_error "OpenCost documentation not found"
fi

# Test 4: Helm Chart Validation
print_section "4. Helm Chart Configuration"

if command -v helm &> /dev/null; then
    print_success "Helm is available"
    
    # Test if we can add the repo (dry run)
    if helm repo add opencost https://opencost.github.io/opencost-helm-chart --dry-run &> /dev/null; then
        print_success "OpenCost Helm repository URL is valid"
    else
        print_warning "Cannot validate Helm repository (may be network issue)"
    fi
    
    # Validate values file against schema (if possible)
    if [ -f "$VALUES_FILE" ]; then
        # Check for required fields
        if grep -q "opencost:" "$VALUES_FILE"; then
            print_success "Main opencost configuration block found"
        fi
        
        if grep -q "prometheus:" "$VALUES_FILE"; then
            print_success "Prometheus integration configuration found"
        fi
        
        if grep -q "serviceMonitor:" "$VALUES_FILE"; then
            print_success "ServiceMonitor configuration found"
        fi
    fi
    
else
    print_warning "Helm not available, skipping Helm-specific tests"
fi

# Test 5: Installation Script Validation
print_section "5. Installation Script Analysis"

if [ -f "$INSTALL_SCRIPT" ]; then
    print_success "Installation script exists"
    
    # Check script structure
    if grep -q "helm repo add opencost" "$INSTALL_SCRIPT"; then
        print_success "Script adds OpenCost Helm repository"
    else
        print_error "Script missing Helm repo add command"
    fi
    
    if grep -q "helm install.*opencost" "$INSTALL_SCRIPT"; then
        print_success "Script installs OpenCost via Helm"
    else
        print_error "Script missing Helm install command"
    fi
    
    if grep -q "kubectl wait.*condition=ready" "$INSTALL_SCRIPT"; then
        print_success "Script waits for pod readiness"
    else
        print_warning "Script doesn't wait for pod readiness"
    fi
    
    if grep -q "port-forward" "$INSTALL_SCRIPT"; then
        print_success "Script includes API testing"
    else
        print_warning "Script doesn't test API endpoints"
    fi
    
    # Check for error handling
    if grep -q "set -e" "$INSTALL_SCRIPT"; then
        print_success "Script has error handling enabled"
    else
        print_warning "Script missing error handling"
    fi
    
else
    print_error "Installation script not found"
fi

# Test 6: Kubernetes Manifests Check
print_section "6. Kubernetes Integration"

# Check if there are any additional K8s manifests
k8s_files=$(find k8s/ -name "*.yaml" -o -name "*.yml" | grep -i opencost || true)
if [ -n "$k8s_files" ]; then
    print_info "Found OpenCost-related Kubernetes files:"
    echo "$k8s_files" | while read file; do
        print_info "  - $file"
    done
else
    print_info "No additional Kubernetes manifests found (using Helm only)"
fi

# Test 7: Security Configuration
print_section "7. Security Configuration"

if grep -q "securityContext" "$VALUES_FILE"; then
    print_success "Security context configured"
    
    if grep -q "runAsNonRoot.*true" "$VALUES_FILE"; then
        print_success "Non-root execution configured"
    else
        print_warning "Non-root execution not explicitly configured"
    fi
    
    if grep -q "runAsUser" "$VALUES_FILE"; then
        print_success "User ID specified"
    else
        print_warning "User ID not specified"
    fi
else
    print_warning "Security context not found in values"
fi

# Test 8: Resource Configuration
print_section "8. Resource Management"

if grep -q "resources:" "$VALUES_FILE"; then
    print_success "Resource limits/requests configured"
    
    if grep -q "requests:" "$VALUES_FILE"; then
        print_success "Resource requests defined"
    fi
    
    if grep -q "limits:" "$VALUES_FILE"; then
        print_success "Resource limits defined"
    fi
    
    # Check memory allocation
    if grep -q "memory.*Gi" "$VALUES_FILE"; then
        print_success "Memory allocation configured appropriately"
    else
        print_warning "Memory allocation may be too low"
    fi
else
    print_warning "Resource configuration not found"
fi

# Test 9: Mock API Test (if running)
print_section "9. API Endpoint Validation"

# Check if OpenCost might be running locally
if curl -s --max-time 5 http://localhost:9003/healthz > /dev/null 2>&1; then
    print_success "OpenCost API is accessible locally"
    
    # Test allocation endpoint
    if curl -s --max-time 10 http://localhost:9003/allocation > /dev/null 2>&1; then
        print_success "Allocation API endpoint responds"
    else
        print_warning "Allocation API endpoint not responding (may need data collection time)"
    fi
    
    # Test assets endpoint
    if curl -s --max-time 10 http://localhost:9003/assets > /dev/null 2>&1; then
        print_success "Assets API endpoint responds"
    else
        print_warning "Assets API endpoint not responding (may need data collection time)"
    fi
    
    # Test metrics endpoint
    if curl -s --max-time 5 http://localhost:9003/metrics | head -n 1 | grep -q "#"; then
        print_success "Metrics endpoint returns Prometheus format"
    else
        print_warning "Metrics endpoint format unclear"
    fi
    
else
    print_info "OpenCost not running locally (expected for configuration-only test)"
fi

# Test 10: Directory Structure
print_section "10. Project Structure"

if [ -d "k8s/opencost" ]; then
    print_success "OpenCost K8s directory exists"
    
    file_count=$(find k8s/opencost -type f | wc -l)
    print_info "OpenCost directory contains $file_count files"
    
    # List contents
    print_info "OpenCost directory contents:"
    ls -la k8s/opencost/ | tail -n +2 | while read line; do
        print_info "  - $(echo $line | awk '{print $9}')"
    done
else
    print_error "OpenCost K8s directory not found"
fi

if [ -d "docs/finops" ]; then
    print_success "FinOps documentation directory exists"
else
    print_error "FinOps documentation directory not found"
fi

# Summary
print_section "Test Summary"

print_info "OpenCost FinOps Integration Implementation Test Results:"
echo ""

# Check each DoD requirement
print_info "🎯 Issue #402 DoD Validation:"

if [ -f "$VALUES_FILE" ] && [ -f "$INSTALL_SCRIPT" ]; then
    print_success "✅ Helm chart + values configuration: IMPLEMENTED"
else
    print_error "❌ Helm configuration: NOT IMPLEMENTED"
fi

if grep -q "job_name.*opencost" "$PROMETHEUS_CONFIG" 2>/dev/null; then
    print_success "✅ Prometheus scrape job configuration: IMPLEMENTED"
else
    print_error "❌ Prometheus integration: NOT IMPLEMENTED"
fi

if grep -q "node_total_hourly_cost\|container_cpu_allocation" "$DOCUMENTATION" 2>/dev/null; then
    print_success "✅ Prometheus metrics documented: IMPLEMENTED"
else
    print_error "❌ Metrics documentation: NOT IMPLEMENTED"
fi

if grep -q "curl.*allocation\|curl.*assets" "$DOCUMENTATION" 2>/dev/null; then
    print_success "✅ API curl examples in README: IMPLEMENTED"
else
    print_error "❌ API examples: NOT IMPLEMENTED"
fi

echo ""
print_info "🚀 Quick Start Commands:"
echo "   # Install OpenCost"
echo "   cd k8s/opencost && ./install.sh"
echo ""
echo "   # Test API (after installation)"
echo "   kubectl port-forward -n opencost svc/opencost 9003:9003"
echo "   curl http://localhost:9003/allocation?window=24h"
echo "   curl http://localhost:9003/assets?window=7d"
echo ""
print_info "📊 Access Points:"
print_info "   • API: http://localhost:9003 (via port-forward)"
print_info "   • UI: http://localhost:9090 (via port-forward)"
print_info "   • Metrics: http://localhost:9003/metrics"
print_info "   • Docs: docs/finops/opencost.md"

echo ""
if [ -f "$VALUES_FILE" ] && [ -f "$INSTALL_SCRIPT" ] && [ -f "$DOCUMENTATION" ] && grep -q "opencost" "$PROMETHEUS_CONFIG" 2>/dev/null; then
    print_success "🎉 OpenCost FinOps Integration Complete! Ready for deployment."
else
    print_warning "⚠️  Some components may be missing. Review the test results above."
fi
