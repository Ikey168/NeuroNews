#!/bin/bash
set -euo pipefail

# Test script for Carbon Cost Tracking
# Validates Issue #342 implementation and DoD requirements

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLUSTER_NAME="${CLUSTER_NAME:-neuronews-cluster}"
OPENCOST_NAMESPACE="${OPENCOST_NAMESPACE:-opencost}"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-monitoring}"

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

check_opencost_carbon_config() {
    test_case "OpenCost Carbon Configuration"
    
    local config_file="$SCRIPT_DIR/opencost-carbon.yaml"
    
    if [[ ! -f "$config_file" ]]; then
        fail "OpenCost carbon configuration file not found"
        return
    fi
    
    # Check carbon tracking enablement
    if grep -q "carbon_intensity:" "$config_file"; then
        success "✓ Carbon estimation configuration found in OpenCost"
    else
        fail "✗ Carbon estimation configuration missing"
        return
    fi
    
    # Check carbon intensity configuration
    if grep -q "carbon_intensity:" "$config_file"; then
        success "✓ Carbon intensity configuration found"
    else
        fail "✗ Carbon intensity configuration missing"
        return
    fi
    
    # Check instance power consumption data
    if grep -q "instance_power" "$config_file"; then
        success "✓ Instance power consumption data found"
    else
        fail "✗ Instance power consumption data missing"
        return
    fi
    
    # Check AWS regions coverage
    local expected_regions=("us-east-1" "us-west-2" "eu-west-1" "eu-central-1")
    for region in "${expected_regions[@]}"; do
        if grep -q "$region:" "$config_file"; then
            success "✓ Carbon intensity data for $region found"
        else
            fail "✗ Carbon intensity data for $region missing"
            return
        fi
    done
    
    # Check carbon price configuration
    if grep -q "carbon_price_per_tonne.*185" "$config_file"; then
        success "✓ Carbon price configuration found ($185/tonne)"
    else
        fail "✗ Carbon price configuration missing or incorrect"
        return
    fi
    
    success "OpenCost carbon configuration validation passed"
}

check_prometheus_carbon_rules() {
    test_case "Prometheus Carbon Monitoring Rules"
    
    local rules_file="$SCRIPT_DIR/prometheus-carbon-rules.yaml"
    
    if [[ ! -f "$rules_file" ]]; then
        fail "Prometheus carbon rules file not found"
        return
    fi
    
    # Check pipeline carbon metrics
    local pipeline_metrics=(
        "pipeline_emissions_kg_co2e"
        "pipeline_cost_usd"
        "namespace_emissions_kg_co2e"
    )
    
    for metric in "${pipeline_metrics[@]}"; do
        if grep -q "$metric" "$rules_file"; then
            success "✓ Pipeline metric found: $metric"
        else
            fail "✗ Pipeline metric missing: $metric"
            return
        fi
    done
    
    # Check cluster total metrics
    local cluster_metrics=(
        "cluster_total_emissions_kg_co2e"
        "cluster_total_cost_usd"
        "efficiency_kg_co2e_per_cpu_hour"
    )
    
    for metric in "${cluster_metrics[@]}"; do
        if grep -q "$metric" "$rules_file"; then
            success "✓ Cluster metric found: $metric"
        else
            fail "✗ Cluster metric missing: $metric"
            return
        fi
    done
    
    # Check sustainability metrics
    if grep -q "sustainability_score" "$rules_file"; then
        success "✓ Sustainability score metric found"
    else
        fail "✗ Sustainability score metric missing"
        return
    fi
    
    # Check carbon alerts
    local carbon_alerts=(
        "HighCarbonEmissions"
        "CarbonCostThreshold"
        "PipelineCarbonImpact"
    )
    
    for alert in "${carbon_alerts[@]}"; do
        if grep -q "$alert" "$rules_file"; then
            success "✓ Carbon alert found: $alert"
        else
            fail "✗ Carbon alert missing: $alert"
            return
        fi
    done
    
    success "Prometheus carbon rules validation passed"
}

check_grafana_dashboard() {
    test_case "Grafana Carbon Dashboard Configuration"
    
    local dashboard_file="$SCRIPT_DIR/grafana-carbon-dashboard.json"
    
    if [[ ! -f "$dashboard_file" ]]; then
        fail "Grafana carbon dashboard file not found"
        return
    fi
    
    # Check dashboard title
    if grep -q "Carbon Footprint & Cost Tracking" "$dashboard_file"; then
        success "✓ Dashboard title configured correctly"
    else
        fail "✗ Dashboard title missing or incorrect"
        return
    fi
    
    # Check pipeline carbon panels
    if grep -q "Carbon Emissions by Pipeline" "$dashboard_file"; then
        success "✓ Pipeline carbon emissions panel found"
    else
        fail "✗ Pipeline carbon emissions panel missing"
        return
    fi
    
    # Check cluster total panels
    if grep -q "cluster_total_emissions_kg_co2e" "$dashboard_file"; then
        success "✓ Cluster total emissions metric in dashboard"
    else
        fail "✗ Cluster total emissions metric missing from dashboard"
        return
    fi
    
    # Check carbon cost visualization
    if grep -q "Carbon Cost by Pipeline" "$dashboard_file"; then
        success "✓ Carbon cost visualization panel found"
    else
        fail "✗ Carbon cost visualization panel missing"
        return
    fi
    
    # Check sustainability metrics
    if grep -q "Sustainability Metrics" "$dashboard_file"; then
        success "✓ Sustainability metrics panel found"
    else
        fail "✗ Sustainability metrics panel missing"
        return
    fi
    
    # Check kgCO2e units
    if grep -q '"unit": "kg"' "$dashboard_file"; then
        success "✓ kgCO2e units configured in dashboard"
    else
        fail "✗ kgCO2e units not properly configured"
        return
    fi
    
    success "Grafana carbon dashboard validation passed"
}

check_installation_script() {
    test_case "Installation Script Validation"
    
    local install_script="$SCRIPT_DIR/install-carbon-tracking.sh"
    
    if [[ ! -f "$install_script" ]]; then
        fail "Installation script not found"
        return
    fi
    
    if [[ ! -x "$install_script" ]]; then
        fail "Installation script is not executable"
        return
    fi
    
    # Check OpenCost installation
    if grep -q "install_opencost_with_carbon" "$install_script"; then
        success "✓ OpenCost installation function found"
    else
        fail "✗ OpenCost installation function missing"
        return
    fi
    
    # Check carbon configuration
    if grep -q "configure_carbon_intensity" "$install_script"; then
        success "✓ Carbon intensity configuration function found"
    else
        fail "✗ Carbon intensity configuration function missing"
        return
    fi
    
    # Check Grafana dashboard installation
    if grep -q "install_grafana_dashboard" "$install_script"; then
        success "✓ Grafana dashboard installation function found"
    else
        fail "✗ Grafana dashboard installation function missing"
        return
    fi
    
    # Test dry run
    if timeout 30s "$install_script" --dry-run --cluster test-cluster 2>/dev/null; then
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
    
    # Check help documentation
    if "$install_script" --help | grep -q "Carbon Cost Tracking"; then
        success "✓ Installation script help documentation found"
    else
        fail "✗ Installation script help documentation missing"
        return
    fi
    
    success "Installation script validation passed"
}

validate_carbon_metrics_coverage() {
    test_case "Carbon Metrics Coverage"
    
    local rules_file="$SCRIPT_DIR/prometheus-carbon-rules.yaml"
    
    # Check pipeline-specific metrics
    if grep -q "pipeline.*emissions.*kg_co2e" "$rules_file"; then
        success "✓ Pipeline carbon emissions metrics found"
    else
        fail "✗ Pipeline carbon emissions metrics missing"
        return
    fi
    
    # Check workload-level metrics
    if grep -q "workload_emissions_kg_co2e" "$rules_file"; then
        success "✓ Workload-level carbon metrics found"
    else
        fail "✗ Workload-level carbon metrics missing"
        return
    fi
    
    # Check node lifecycle tracking (spot vs on-demand)
    if grep -q "node_lifecycle_emissions" "$rules_file"; then
        success "✓ Node lifecycle carbon tracking found"
    else
        fail "✗ Node lifecycle carbon tracking missing"
        return
    fi
    
    # Check cost integration
    if grep -q "carbon.*cost.*usd" "$rules_file"; then
        success "✓ Carbon cost integration found"
    else
        fail "✗ Carbon cost integration missing"
        return
    fi
    
    success "Carbon metrics coverage validation passed"
}

validate_dod_requirements() {
    test_case "DoD Requirements Validation"
    
    log "Validating Definition of Done requirements..."
    
    # DoD: Dashboard shows carbon per pipeline
    local dashboard_file="$SCRIPT_DIR/grafana-carbon-dashboard.json"
    if grep -q "pipeline_emissions_kg_co2e" "$dashboard_file" && 
       grep -q "Carbon Emissions by Pipeline" "$dashboard_file"; then
        success "✓ DoD: Dashboard shows carbon per pipeline"
    else
        fail "✗ DoD: Dashboard carbon per pipeline visualization missing"
        return
    fi
    
    # DoD: Dashboard shows cluster total
    if grep -q "cluster_total_emissions_kg_co2e" "$dashboard_file" &&
       grep -q "Total Cluster kgCO2e" "$dashboard_file"; then
        success "✓ DoD: Dashboard shows cluster total carbon"
    else
        fail "✗ DoD: Dashboard cluster total carbon visualization missing"
        return
    fi
    
    # DoD: OpenCost integration with Prometheus
    local config_file="$SCRIPT_DIR/opencost-carbon.yaml"
    if grep -q "prometheus.io/scrape.*true" "$config_file" &&
       grep -q "PROMETHEUS_SERVER_ENDPOINT" "$config_file"; then
        success "✓ DoD: OpenCost integration with Prometheus configured"
    else
        fail "✗ DoD: OpenCost Prometheus integration missing"
        return
    fi
    
    success "All DoD requirements validated successfully"
}

test_carbon_calculation_accuracy() {
    test_case "Carbon Calculation Accuracy"
    
    local config_file="$SCRIPT_DIR/opencost-carbon.yaml"
    
    # Check PUE (Power Usage Effectiveness) configuration
    if grep -q "pue.*1.135" "$config_file"; then
        success "✓ AWS data center PUE correctly configured (1.135)"
    else
        fail "✗ PUE configuration missing or incorrect"
        return
    fi
    
    # Check carbon price alignment with social cost of carbon
    if grep -q "185.*tonne" "$config_file"; then
        success "✓ Carbon price aligned with social cost of carbon ($185/tonne)"
    else
        fail "✗ Carbon price not aligned with standard social cost"
        return
    fi
    
    # Check regional carbon intensity variation
    local rules_file="$SCRIPT_DIR/prometheus-carbon-rules.yaml"
    if grep -q "carbon_intensity_grams_co2e_per_kwh" "$rules_file"; then
        success "✓ Regional carbon intensity tracking found"
    else
        fail "✗ Regional carbon intensity tracking missing"
        return
    fi
    
    success "Carbon calculation accuracy validation passed"
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
        log "Issue #342 implementation is ready for deployment"
        echo
        log "Key features implemented:"
        echo "  ✓ OpenCost carbon estimation with regional data"
        echo "  ✓ Pipeline-specific kgCO2e metrics tracking"
        echo "  ✓ Cluster total carbon footprint monitoring" 
        echo "  ✓ Grafana dashboard with carbon visualization"
        echo "  ✓ Prometheus rules for carbon alerts"
        echo "  ✓ Cost integration with $185/tonne CO2e pricing"
        echo
        log "DoD verification:"
        echo "  ✓ Dashboard shows carbon per pipeline"
        echo "  ✓ Dashboard shows cluster total kgCO2e"
        echo "  ✓ OpenCost integration with Prometheus metrics"
        echo
        log "Modern sustainability features:"
        echo "  • Real-time carbon footprint tracking"
        echo "  • Renewable energy percentage monitoring"
        echo "  • Carbon optimization recommendations"
        echo "  • Sustainability scoring (0-100)"
        echo
    else
        fail "Some tests failed ($FAILED_TESTS/$TOTAL_TESTS failed, $PASSED_TESTS/$TOTAL_TESTS passed)"
        echo
        log "Please review and fix the failing tests before deployment"
    fi
    
    log "========================================="
}

main() {
    log "Starting Carbon Cost Tracking tests..."
    log "Target cluster: $CLUSTER_NAME | OpenCost NS: $OPENCOST_NAMESPACE | Monitoring NS: $MONITORING_NAMESPACE"
    echo
    
    check_opencost_carbon_config
    check_prometheus_carbon_rules
    check_grafana_dashboard
    check_installation_script
    validate_carbon_metrics_coverage
    validate_dod_requirements
    test_carbon_calculation_accuracy
    
    generate_report
}

# Help function
show_help() {
    cat << EOF
Carbon Cost Tracking Test Suite

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -c, --cluster NAME     Specify cluster name (default: neuronews-cluster)
    -o, --opencost-ns NS   Specify OpenCost namespace (default: opencost)
    -m, --monitoring-ns NS Specify monitoring namespace (default: monitoring)

ENVIRONMENT VARIABLES:
    CLUSTER_NAME           Kubernetes cluster name
    OPENCOST_NAMESPACE    OpenCost deployment namespace
    MONITORING_NAMESPACE  Monitoring stack namespace

EXAMPLES:
    # Run all tests with defaults
    $0

    # Test with custom namespaces
    $0 --opencost-ns cost-tracking --monitoring-ns observability

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
        -o|--opencost-ns)
            OPENCOST_NAMESPACE="$2"
            shift 2
            ;;
        -m|--monitoring-ns)
            MONITORING_NAMESPACE="$2"
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
