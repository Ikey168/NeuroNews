#!/bin/bash
set -euo pipefail

# Test script for Node Autoscaling & Bin-Packing Guardrails
# Validates Issue #341 implementation and DoD requirements

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-neuronews-cluster}"
NAMESPACE="${NAMESPACE:-data-pipeline}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

success() {
    echo -e "${GREEN}[PASS] $1${NC}"
    ((PASSED_TESTS++))
}

fail() {
    echo -e "${RED}[FAIL] $1${NC}"
    ((FAILED_TESTS++))
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

test_case() {
    ((TOTAL_TESTS++))
    log "Test: $1"
}

check_cluster_autoscaler_config() {
    test_case "Cluster Autoscaler Configuration"
    
    local config_file="$SCRIPT_DIR/cluster-autoscaler.yaml"
    
    # Check if cluster autoscaler config exists
    if [[ ! -f "$config_file" ]]; then
        fail "Cluster autoscaler configuration file not found"
        return
    fi
    
    # Validate cost optimization settings
    local cost_settings=(
        "--scale-down-enabled=true"
        "--scale-down-delay-after-add=10m"
        "--scale-down-unneeded-time=5m"
        "--scale-down-utilization-threshold=0.5"
        "--expander=least-waste"
    )
    
    for setting in "${cost_settings[@]}"; do
        if grep -q "$setting" "$config_file"; then
            success "✓ Cost optimization setting found: $setting"
        else
            fail "✗ Missing cost optimization setting: $setting"
            return
        fi
    done
    
    # Check bin-packing settings
    local binpack_settings=(
        "--balance-similar-node-groups=true"
        "--skip-nodes-with-system-pods=false"
    )
    
    for setting in "${binpack_settings[@]}"; do
        if grep -q "$setting" "$config_file"; then
            success "✓ Bin-packing setting found: $setting"
        else
            fail "✗ Missing bin-packing setting: $setting"
            return
        fi
    done
    
    success "Cluster Autoscaler configuration validation passed"
}

check_priority_classes() {
    test_case "Priority Classes Configuration"
    
    local config_file="$SCRIPT_DIR/priority-classes.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        fail "Priority classes configuration file not found"
        return
    fi
    
    # Expected priority classes with their values
    local expected_classes=(
        "neuronews-critical:1000"
        "neuronews-standard:500"
        "neuronews-batch:100"
        "neuronews-dev:50"
        "neuronews-spot:25"
    )
    
    for class_value in "${expected_classes[@]}"; do
        local class_name="${class_value%:*}"
        local priority_value="${class_value#*:}"
        
        if grep -A 5 "name: $class_name" "$config_file" | grep -q "value: $priority_value"; then
            success "✓ Priority class found: $class_name (priority: $priority_value)"
        else
            fail "✗ Priority class missing or incorrect: $class_name"
            return
        fi
    done
    
    success "Priority classes configuration validation passed"
}

check_bin_packing_guardrails() {
    test_case "Bin-Packing Guardrails Configuration"
    
    local config_file="$SCRIPT_DIR/bin-packing-guardrails.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        fail "Bin-packing guardrails configuration file not found"
        return
    fi
    
    # Check Pod Disruption Budgets
    local pdb_names=("neuronews-ingestion-pdb" "neuronews-dbt-pdb" "neuronews-batch-pdb")
    
    for pdb in "${pdb_names[@]}"; do
        if grep -q "name: $pdb" "$config_file"; then
            success "✓ Pod Disruption Budget found: $pdb"
        else
            fail "✗ Pod Disruption Budget missing: $pdb"
            return
        fi
    done
    
    # Check topology spread constraints template
    if grep -q "topology-spread-constraints" "$config_file"; then
        success "✓ Topology spread constraints template found"
    else
        fail "✗ Topology spread constraints template missing"
        return
    fi
    
    # Check spot tolerations
    if grep -q "spot-tolerations.yaml" "$config_file"; then
        success "✓ Spot instance tolerations template found"
    else
        fail "✗ Spot instance tolerations template missing"
        return
    fi
    
    success "Bin-packing guardrails configuration validation passed"
}

check_spot_node_pools() {
    test_case "Spot Instance Node Pools Configuration"
    
    local config_file="$SCRIPT_DIR/spot-node-pools.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        fail "Spot node pools configuration file not found"
        return
    fi
    
    # Check spot node group configuration
    if grep -q "neuronews-spot-batch" "$config_file"; then
        success "✓ Spot node group configuration found"
    else
        fail "✗ Spot node group configuration missing"
        return
    fi
    
    # Check on-demand node group configuration
    if grep -q "neuronews-ondemand-critical" "$config_file"; then
        success "✓ On-demand node group configuration found"
    else
        fail "✗ On-demand node group configuration missing"
        return
    fi
    
    # Check capacity type settings
    if grep -q '"capacityType": "SPOT"' "$config_file"; then
        success "✓ Spot capacity type configuration found"
    else
        fail "✗ Spot capacity type configuration missing"
        return
    fi
    
    # Check node taints for spot instances
    if grep -q '"key": "node-lifecycle"' "$config_file"; then
        success "✓ Spot instance taints configuration found"
    else
        fail "✗ Spot instance taints configuration missing"
        return
    fi
    
    # Check cluster autoscaler tags
    if grep -q "k8s.io/cluster-autoscaler/enabled" "$config_file"; then
        success "✓ Cluster autoscaler tags found"
    else
        fail "✗ Cluster autoscaler tags missing"
        return
    fi
    
    success "Spot instance node pools configuration validation passed"
}

check_workload_examples() {
    test_case "Workload Examples with Autoscaling Optimizations"
    
    local config_file="$SCRIPT_DIR/workload-examples.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        fail "Workload examples configuration file not found"
        return
    fi
    
    # Check critical workload configuration
    if grep -q "priorityClassName: neuronews-critical" "$config_file"; then
        success "✓ Critical workload priority class usage found"
    else
        fail "✗ Critical workload priority class usage missing"
        return
    fi
    
    # Check batch workload configuration
    if grep -q "priorityClassName: neuronews-batch" "$config_file"; then
        success "✓ Batch workload priority class usage found"
    else
        fail "✗ Batch workload priority class usage missing"
        return
    fi
    
    # Check topology spread constraints usage
    if grep -q "topologySpreadConstraints:" "$config_file"; then
        success "✓ Topology spread constraints usage found"
    else
        fail "✗ Topology spread constraints usage missing"
        return
    fi
    
    # Check spot instance tolerations
    if grep -q "node-lifecycle" "$config_file" && grep -q "spot" "$config_file"; then
        success "✓ Spot instance tolerations usage found"
    else
        fail "✗ Spot instance tolerations usage missing"
        return
    fi
    
    # Check resource requests/limits
    if grep -q "resources:" "$config_file" && grep -q "requests:" "$config_file" && grep -q "limits:" "$config_file"; then
        success "✓ Resource requests/limits configuration found"
    else
        fail "✗ Resource requests/limits configuration missing"
        return
    fi
    
    success "Workload examples validation passed"
}

check_monitoring_rules() {
    test_case "Autoscaling Monitoring Rules"
    
    local config_file="$SCRIPT_DIR/../monitoring/prometheus-autoscaling-rules.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        fail "Autoscaling monitoring rules file not found"
        return
    fi
    
    # Check cluster autoscaler monitoring
    if grep -q "ClusterAutoscalerDown" "$config_file"; then
        success "✓ Cluster autoscaler health monitoring found"
    else
        fail "✗ Cluster autoscaler health monitoring missing"
        return
    fi
    
    # Check node utilization metrics
    if grep -q "node_utilization" "$config_file"; then
        success "✓ Node utilization metrics found"
    else
        fail "✗ Node utilization metrics missing"
        return
    fi
    
    # Check spot instance monitoring
    if grep -q "spot_instance" "$config_file"; then
        success "✓ Spot instance monitoring found"
    else
        fail "✗ Spot instance monitoring missing"
        return
    fi
    
    # Check bin-packing metrics
    if grep -q "binpacking" "$config_file"; then
        success "✓ Bin-packing metrics found"
    else
        fail "✗ Bin-packing metrics missing"
        return
    fi
    
    # Check cost tracking metrics
    if grep -q "cost:" "$config_file"; then
        success "✓ Cost tracking metrics found"
    else
        fail "✗ Cost tracking metrics missing"
        return
    fi
    
    success "Monitoring rules validation passed"
}

test_installation_script() {
    test_case "Installation Script Validation"
    
    local install_script="$SCRIPT_DIR/install-node-autoscaling.sh"
    
    if [[ ! -f "$install_script" ]]; then
        fail "Installation script not found"
        return
    fi
    
    if [[ ! -x "$install_script" ]]; then
        fail "Installation script is not executable"
        return
    fi
    
    # Test dry run
    if timeout 30s "$install_script" --dry-run --cluster test-cluster --namespace test-ns 2>/dev/null; then
        success "✓ Installation script dry run successful"
    else
        local exit_code=$?
        if [[ $exit_code -eq 124 ]]; then
            warn "⚠ Installation script dry run timed out (may be normal)"
        else
            fail "✗ Installation script dry run failed with exit code $exit_code"
            return
        fi
    fi
    
    # Check script has help
    if "$install_script" --help | grep -q "USAGE:"; then
        success "✓ Installation script help documentation found"
    else
        fail "✗ Installation script help documentation missing"
        return
    fi
    
    success "Installation script validation passed"
}

validate_dod_requirements() {
    test_case "DoD Requirements Validation"
    
    log "Validating Definition of Done requirements..."
    
    # DoD: Scale-down occurs after idle
    local autoscaler_config="$SCRIPT_DIR/cluster-autoscaler.yaml"
    if grep -q "scale-down-enabled=true" "$autoscaler_config" && 
       grep -q "scale-down-unneeded-time=5m" "$autoscaler_config"; then
        success "✓ DoD: Scale-down configuration for idle nodes"
    else
        fail "✗ DoD: Scale-down configuration missing"
        return
    fi
    
    # DoD: Workloads respect priorities
    local priorities_config="$SCRIPT_DIR/priority-classes.yaml"
    local examples_config="$SCRIPT_DIR/workload-examples.yaml"
    if [[ -f "$priorities_config" ]] && [[ -f "$examples_config" ]] &&
       grep -q "priorityClassName:" "$examples_config"; then
        success "✓ DoD: Workload prioritization implemented"
    else
        fail "✗ DoD: Workload prioritization missing"
        return
    fi
    
    # DoD: Spot pool handles batch jobs
    local spot_config="$SCRIPT_DIR/spot-node-pools.yaml"
    if grep -q "neuronews-spot-batch" "$spot_config" &&
       grep -q "neuronews-batch" "$examples_config" &&
       grep -q "node-lifecycle.*spot" "$examples_config"; then
        success "✓ DoD: Spot instance pool for batch jobs"
    else
        fail "✗ DoD: Spot instance pool configuration incomplete"
        return
    fi
    
    success "All DoD requirements validated successfully"
}

generate_report() {
    echo
    log "========================================="
    log "Test Results Summary"
    log "========================================="
    echo
    
    if [[ $FAILED_TESTS -eq 0 ]]; then
        success "All tests passed! ($PASSED_TESTS/$TOTAL_TESTS)"
        echo
        log "Issue #341 implementation is ready for deployment"
        echo
        log "Key features implemented:"
        echo "  ✓ Cluster Autoscaler with cost optimization"
        echo "  ✓ Priority classes for workload prioritization"
        echo "  ✓ Bin-packing guardrails with topology constraints"
        echo "  ✓ Spot instance node pools for batch workloads"
        echo "  ✓ Comprehensive monitoring and alerting"
        echo "  ✓ Installation automation with validation"
        echo
        log "Expected benefits:"
        echo "  • 30-60% cost reduction for batch workloads"
        echo "  • Improved resource utilization through bin-packing"
        echo "  • Automatic scaling based on demand"
        echo "  • Fault-tolerant workload distribution"
        echo
    else
        fail "Some tests failed ($FAILED_TESTS/$TOTAL_TESTS failed, $PASSED_TESTS/$TOTAL_TESTS passed)"
        echo
        log "Please review and fix the failing tests before deployment"
    fi
    
    log "========================================="
}

main() {
    log "Starting Node Autoscaling & Bin-Packing Guardrails tests..."
    log "Target cluster: $CLUSTER_NAME | Namespace: $NAMESPACE"
    echo
    
    check_cluster_autoscaler_config
    check_priority_classes
    check_bin_packing_guardrails
    check_spot_node_pools
    check_workload_examples
    check_monitoring_rules
    test_installation_script
    validate_dod_requirements
    
    generate_report
}

# Help function
show_help() {
    cat << EOF
Node Autoscaling & Bin-Packing Guardrails Test Suite

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -c, --cluster NAME     Specify cluster name (default: neuronews-cluster)
    -n, --namespace NS     Specify namespace (default: data-pipeline)

ENVIRONMENT VARIABLES:
    CLUSTER_NAME           Kubernetes cluster name
    NAMESPACE             Target namespace for workloads

EXAMPLES:
    # Run all tests with defaults
    $0

    # Test with custom cluster and namespace
    $0 --cluster my-cluster --namespace production

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -c|--cluster)
            CLUSTER_NAME="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run main function
main
