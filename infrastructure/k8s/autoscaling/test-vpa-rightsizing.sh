#!/bin/bash

# Test script for VPA Rightsizing Implementation
# Validates VPA installation, configuration, and monitoring

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Test configuration
TEST_DIR="$(mktemp -d)"
SCRIPT_DIR="$(dirname "$0")"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
NAMESPACE_DATA_PIPELINE="${NAMESPACE_DATA_PIPELINE:-data-pipeline}"

echo -e "${BLUE}🧪 Testing VPA Rightsizing Implementation${NC}"
echo "========================================"
echo ""

# Test 1: Validate VPA YAML configurations
test_vpa_configurations() {
    echo -e "${BLUE}Test 1: VPA Configuration Validation${NC}"
    echo "------------------------------------"
    
    local failed=0
    
    # Test VPA CRD file
    VPA_CRD_FILE="$REPO_ROOT/k8s/autoscaling/vpa-crd.yaml"
    if [[ ! -f "$VPA_CRD_FILE" ]]; then
        echo -e "${RED}❌ VPA CRD file not found: $VPA_CRD_FILE${NC}"
        ((failed++))
    else
        # Basic YAML syntax check
        if command -v yamllint &> /dev/null; then
            if yamllint "$VPA_CRD_FILE" &> /dev/null; then
                echo -e "${GREEN}✅ VPA CRD YAML syntax valid${NC}"
            else
                echo -e "${RED}❌ VPA CRD YAML syntax errors${NC}"
                ((failed++))
            fi
        else
            echo -e "${YELLOW}⚠️  yamllint not available, skipping syntax check${NC}"
        fi
        
        # Check required CRD kinds
        if grep -q "kind: CustomResourceDefinition" "$VPA_CRD_FILE"; then
            echo -e "${GREEN}✅ CustomResourceDefinition kind found${NC}"
        else
            echo -e "${RED}❌ CustomResourceDefinition kind missing${NC}"
            ((failed++))
        fi
        
        if grep -q "verticalpodautoscalers.autoscaling.k8s.io" "$VPA_CRD_FILE"; then
            echo -e "${GREEN}✅ VPA CRD name correctly defined${NC}"
        else
            echo -e "${RED}❌ VPA CRD name incorrect or missing${NC}"
            ((failed++))
        fi
    fi
    
    # Test VPA RBAC file
    VPA_RBAC_FILE="$REPO_ROOT/k8s/autoscaling/vpa-rbac.yaml"
    if [[ ! -f "$VPA_RBAC_FILE" ]]; then
        echo -e "${RED}❌ VPA RBAC file not found: $VPA_RBAC_FILE${NC}"
        ((failed++))
    else
        if grep -q "ClusterRole" "$VPA_RBAC_FILE" && grep -q "ClusterRoleBinding" "$VPA_RBAC_FILE"; then
            echo -e "${GREEN}✅ VPA RBAC configuration present${NC}"
        else
            echo -e "${RED}❌ VPA RBAC configuration incomplete${NC}"
            ((failed++))
        fi
    fi
    
    # Test VPA deployment file
    VPA_DEPLOYMENT_FILE="$REPO_ROOT/k8s/autoscaling/vpa-deployment.yaml"
    if [[ ! -f "$VPA_DEPLOYMENT_FILE" ]]; then
        echo -e "${RED}❌ VPA deployment file not found: $VPA_DEPLOYMENT_FILE${NC}"
        ((failed++))
    else
        if grep -q "vpa-recommender" "$VPA_DEPLOYMENT_FILE" && grep -q "vpa-updater" "$VPA_DEPLOYMENT_FILE"; then
            echo -e "${GREEN}✅ VPA components defined in deployment${NC}"
        else
            echo -e "${RED}❌ VPA components missing in deployment${NC}"
            ((failed++))
        fi
    fi
    
    echo ""
    return $failed
}

# Test 2: Validate pipeline VPA configurations
test_pipeline_vpa_configs() {
    echo -e "${BLUE}Test 2: Pipeline VPA Configuration Validation${NC}"
    echo "----------------------------------------------"
    
    local failed=0
    
    # Test ingestion pipeline VPAs
    INGESTION_VPA_FILE="$REPO_ROOT/k8s/autoscaling/vpa-ingestion-pipeline.yaml"
    if [[ ! -f "$INGESTION_VPA_FILE" ]]; then
        echo -e "${RED}❌ Ingestion VPA file not found: $INGESTION_VPA_FILE${NC}"
        ((failed++))
    else
        # Check for required VPA objects targeting ingest pipeline
        if grep -q "pipeline: ingest" "$INGESTION_VPA_FILE"; then
            echo -e "${GREEN}✅ Ingestion pipeline VPAs labeled correctly${NC}"
        else
            echo -e "${RED}❌ Ingestion pipeline labels missing${NC}"
            ((failed++))
        fi
        
        # Check updateMode is initially "Off"
        if grep -q 'updateMode: "Off"' "$INGESTION_VPA_FILE"; then
            echo -e "${GREEN}✅ VPAs configured for recommendations-only mode${NC}"
        else
            echo -e "${RED}❌ VPAs not in recommendations-only mode${NC}"
            ((failed++))
        fi
        
        # Check resource constraints
        if grep -q "minAllowed:" "$INGESTION_VPA_FILE" && grep -q "maxAllowed:" "$INGESTION_VPA_FILE"; then
            echo -e "${GREEN}✅ Resource constraints defined${NC}"
        else
            echo -e "${RED}❌ Resource constraints missing${NC}"
            ((failed++))
        fi
    fi
    
    # Test DBT pipeline VPAs
    DBT_VPA_FILE="$REPO_ROOT/k8s/autoscaling/vpa-dbt-pipeline.yaml"
    if [[ ! -f "$DBT_VPA_FILE" ]]; then
        echo -e "${RED}❌ DBT VPA file not found: $DBT_VPA_FILE${NC}"
        ((failed++))
    else
        if grep -q "pipeline: dbt" "$DBT_VPA_FILE"; then
            echo -e "${GREEN}✅ DBT pipeline VPAs labeled correctly${NC}"
        else
            echo -e "${RED}❌ DBT pipeline labels missing${NC}"
            ((failed++))
        fi
        
        # Check for CronJob and Deployment targets
        if grep -q "kind: CronJob" "$DBT_VPA_FILE" && grep -q "kind: Deployment" "$DBT_VPA_FILE"; then
            echo -e "${GREEN}✅ DBT VPAs target both CronJob and Deployment workloads${NC}"
        else
            echo -e "${RED}❌ DBT VPAs missing required target kinds${NC}"
            ((failed++))
        fi
    fi
    
    echo ""
    return $failed
}

# Test 3: Validate installation script functionality
test_installation_script() {
    echo -e "${BLUE}Test 3: Installation Script Validation${NC}"
    echo "--------------------------------------"
    
    local failed=0
    
    INSTALL_SCRIPT="$REPO_ROOT/k8s/autoscaling/install-vpa-rightsizing.sh"
    
    if [[ ! -f "$INSTALL_SCRIPT" ]]; then
        echo -e "${RED}❌ Installation script not found: $INSTALL_SCRIPT${NC}"
        ((failed++))
        return $failed
    fi
    
    if [[ ! -x "$INSTALL_SCRIPT" ]]; then
        echo -e "${RED}❌ Installation script not executable${NC}"
        ((failed++))
    else
        echo -e "${GREEN}✅ Installation script is executable${NC}"
    fi
    
    # Test help functionality
    if "$INSTALL_SCRIPT" --help &> /dev/null; then
        echo -e "${GREEN}✅ Installation script help works${NC}"
    else
        echo -e "${RED}❌ Installation script help failed${NC}"
        ((failed++))
    fi
    
    # Test dry run functionality
    cd "$REPO_ROOT"
    if DRY_RUN=true "$INSTALL_SCRIPT" 2>&1 | grep -q "DRY RUN"; then
        echo -e "${GREEN}✅ Dry run mode works${NC}"
    else
        echo -e "${RED}❌ Dry run mode failed${NC}"
        ((failed++))
    fi
    
    # Check phased approach support
    if grep -q "PHASE=" "$INSTALL_SCRIPT"; then
        echo -e "${GREEN}✅ Phased installation approach supported${NC}"
    else
        echo -e "${RED}❌ Phased installation approach missing${NC}"
        ((failed++))
    fi
    
    # Check prerequisite checking
    if grep -q "check_prerequisites" "$INSTALL_SCRIPT"; then
        echo -e "${GREEN}✅ Prerequisites checking implemented${NC}"
    else
        echo -e "${RED}❌ Prerequisites checking missing${NC}"
        ((failed++))
    fi
    
    echo ""
    return $failed
}

# Test 4: Validate monitoring rules
test_monitoring_rules() {
    echo -e "${BLUE}Test 4: VPA Monitoring Rules Validation${NC}"
    echo "---------------------------------------"
    
    local failed=0
    
    MONITORING_FILE="$REPO_ROOT/k8s/monitoring/prometheus-vpa-rules.yaml"
    
    if [[ ! -f "$MONITORING_FILE" ]]; then
        echo -e "${RED}❌ VPA monitoring rules file not found: $MONITORING_FILE${NC}"
        ((failed++))
        return $failed
    fi
    
    # Check for DoD-related metrics
    if grep -q "container_allocation" "$MONITORING_FILE"; then
        echo -e "${GREEN}✅ Container allocation metrics present${NC}"
    else
        echo -e "${RED}❌ Container allocation metrics missing${NC}"
        ((failed++))
    fi
    
    if grep -q "utilization.*improvement" "$MONITORING_FILE"; then
        echo -e "${GREEN}✅ Utilization improvement tracking present${NC}"
    else
        echo -e "${RED}❌ Utilization improvement tracking missing${NC}"
        ((failed++))
    fi
    
    # Check for VPA-specific alerts
    if grep -q "VPARecommendationMissing" "$MONITORING_FILE"; then
        echo -e "${GREEN}✅ VPA recommendation alerts present${NC}"
    else
        echo -e "${RED}❌ VPA recommendation alerts missing${NC}"
        ((failed++))
    fi
    
    if grep -q "VPAResourceAllocationReduced" "$MONITORING_FILE"; then
        echo -e "${GREEN}✅ Resource allocation reduction alerts present${NC}"
    else
        echo -e "${RED}❌ Resource allocation reduction alerts missing${NC}"
        ((failed++))
    fi
    
    # Check for pipeline coverage tracking
    if grep -q "pipeline_coverage" "$MONITORING_FILE"; then
        echo -e "${GREEN}✅ Pipeline coverage monitoring present${NC}"
    else
        echo -e "${RED}❌ Pipeline coverage monitoring missing${NC}"
        ((failed++))
    fi
    
    echo ""
    return $failed
}

# Test 5: Simulate VPA workflow
test_vpa_workflow_simulation() {
    echo -e "${BLUE}Test 5: VPA Workflow Simulation${NC}"
    echo "-------------------------------"
    
    local failed=0
    
    cd "$TEST_DIR"
    
    # Create mock kubectl that simulates VPA operations
    cat << 'EOF' > mock-kubectl.sh
#!/bin/bash
case "$*" in
    "cluster-info")
        echo "Kubernetes control plane is running at https://mock-cluster"
        ;;
    "get namespace vpa-system")
        exit 1  # Simulate namespace doesn't exist
        ;;
    "create namespace vpa-system")
        echo "namespace/vpa-system created"
        ;;
    "apply -f"*"vpa-crd.yaml")
        echo "customresourcedefinition.apiextensions.k8s.io/verticalpodautoscalers.autoscaling.k8s.io created"
        echo "customresourcedefinition.apiextensions.k8s.io/verticalpodautoscalercheckpoints.autoscaling.k8s.io created"
        ;;
    "wait --for condition=established"*)
        echo "condition met"
        ;;
    "apply -f"*"vpa-rbac.yaml")
        echo "clusterrole.rbac.authorization.k8s.io/vpa-actor created"
        echo "clusterrolebinding.rbac.authorization.k8s.io/vpa-actor created"
        ;;
    "get secret vpa-webhook-certs -n vpa-system")
        exit 1  # Simulate secret doesn't exist
        ;;
    "create secret generic vpa-webhook-certs"*)
        echo "secret/vpa-webhook-certs created"
        ;;
    "apply -f"*"vpa-deployment.yaml")
        echo "deployment.apps/vpa-recommender created"
        echo "deployment.apps/vpa-updater created"
        echo "deployment.apps/vpa-admission-controller created"
        ;;
    "wait --for=condition=available"*)
        echo "deployment.apps/vpa-recommender condition met"
        ;;
    "apply -f"*"vpa-ingestion-pipeline.yaml")
        echo "verticalpodautoscaler.autoscaling.k8s.io/neuronews-ingestion-vpa created"
        echo "verticalpodautoscaler.autoscaling.k8s.io/neuronews-consumer-vpa created"
        ;;
    "apply -f"*"vpa-dbt-pipeline.yaml")
        echo "verticalpodautoscaler.autoscaling.k8s.io/dbt-runner-vpa created"
        echo "verticalpodautoscaler.autoscaling.k8s.io/dbt-test-runner-vpa created"
        ;;
    "get pods -n vpa-system")
        echo "NAME                                     READY   STATUS    RESTARTS   AGE"
        echo "vpa-admission-controller-12345-abcde    1/1     Running   0          5m"
        echo "vpa-recommender-67890-fghij             1/1     Running   0          5m"
        echo "vpa-updater-54321-klmno                 1/1     Running   0          5m"
        ;;
    "get vpa -n data-pipeline -o wide")
        echo "NAME                        MODE   CPU    MEM    PROVIDED   AGE"
        echo "neuronews-ingestion-vpa     Off    100m   256Mi  True       2m"
        echo "dbt-runner-vpa              Off    200m   512Mi  True       2m"
        ;;
    "get deployment metrics-server -n kube-system")
        echo "NAME             READY   UP-TO-DATE   AVAILABLE   AGE"
        echo "metrics-server   1/1     1            1           30d"
        ;;
    "get service prometheus-server -n monitoring")
        echo "NAME                TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE"
        echo "prometheus-server   ClusterIP   10.96.123.456   <none>        80/TCP    15d"
        ;;
    *)
        echo "kubectl mock: $*"
        ;;
esac
EOF
    chmod +x mock-kubectl.sh
    
    # Test installation simulation
    export PATH="$TEST_DIR:$PATH"
    
    # Create minimal VPA files for testing
    mkdir -p k8s/autoscaling
    echo "apiVersion: v1" > k8s/autoscaling/vpa-crd.yaml
    echo "kind: ConfigMap" >> k8s/autoscaling/vpa-crd.yaml
    
    echo "apiVersion: v1" > k8s/autoscaling/vpa-rbac.yaml
    echo "kind: ConfigMap" >> k8s/autoscaling/vpa-rbac.yaml
    
    echo "apiVersion: v1" > k8s/autoscaling/vpa-deployment.yaml
    echo "kind: ConfigMap" >> k8s/autoscaling/vpa-deployment.yaml
    
    echo "apiVersion: v1" > k8s/autoscaling/vpa-ingestion-pipeline.yaml
    echo "kind: ConfigMap" >> k8s/autoscaling/vpa-ingestion-pipeline.yaml
    
    echo "apiVersion: v1" > k8s/autoscaling/vpa-dbt-pipeline.yaml
    echo "kind: ConfigMap" >> k8s/autoscaling/vpa-dbt-pipeline.yaml
    
    # Test dry run execution
    if DRY_RUN=true bash "$REPO_ROOT/k8s/autoscaling/install-vpa-rightsizing.sh" 2>&1 | grep -q "DRY RUN"; then
        echo -e "${GREEN}✅ VPA workflow simulation successful${NC}"
    else
        echo -e "${RED}❌ VPA workflow simulation failed${NC}"
        ((failed++))
    fi
    
    echo ""
    return $failed
}

# Test 6: Validate DoD requirements mapping
test_dod_requirements() {
    echo -e "${BLUE}Test 6: DoD Requirements Validation${NC}"
    echo "-----------------------------------"
    
    local failed=0
    
    # Check VPA CRDs installation capability
    if [[ -f "$REPO_ROOT/k8s/autoscaling/vpa-crd.yaml" ]] && [[ -f "$REPO_ROOT/k8s/autoscaling/install-vpa-rightsizing.sh" ]]; then
        echo -e "${GREEN}✅ VPA CRDs and controller installation supported${NC}"
    else
        echo -e "${RED}❌ VPA CRDs and controller installation missing${NC}"
        ((failed++))
    fi
    
    # Check updateMode "Off" initial configuration
    if grep -q 'updateMode: "Off"' "$REPO_ROOT/k8s/autoscaling/vpa-"*".yaml"; then
        echo -e "${GREEN}✅ Initial 'Off' mode configuration present${NC}"
    else
        echo -e "${RED}❌ Initial 'Off' mode configuration missing${NC}"
        ((failed++))
    fi
    
    # Check pipeline targeting (ingest, dbt)
    if grep -q "pipeline: ingest" "$REPO_ROOT/k8s/autoscaling/vpa-"*".yaml" && grep -q "pipeline: dbt" "$REPO_ROOT/k8s/autoscaling/vpa-"*".yaml"; then
        echo -e "${GREEN}✅ VPA objects target ingest and dbt pipelines${NC}"
    else
        echo -e "${RED}❌ VPA objects don't target required pipelines${NC}"
        ((failed++))
    fi
    
    # Check switch to "Auto" mode capability
    if grep -q "switch_to_auto_mode" "$REPO_ROOT/k8s/autoscaling/install-vpa-rightsizing.sh"; then
        echo -e "${GREEN}✅ Switch to 'Auto' mode functionality present${NC}"
    else
        echo -e "${RED}❌ Switch to 'Auto' mode functionality missing${NC}"
        ((failed++))
    fi
    
    # Check utilization improvement monitoring
    if grep -q "utilization.*improvement" "$REPO_ROOT/k8s/monitoring/prometheus-vpa-rules.yaml"; then
        echo -e "${GREEN}✅ CPU/memory utilization improvement monitoring present${NC}"
    else
        echo -e "${RED}❌ Utilization improvement monitoring missing${NC}"
        ((failed++))
    fi
    
    # Check container allocation monitoring
    if grep -q "container.*allocation" "$REPO_ROOT/k8s/monitoring/prometheus-vpa-rules.yaml"; then
        echo -e "${GREEN}✅ Container allocation monitoring present${NC}"
    else
        echo -e "${RED}❌ Container allocation monitoring missing${NC}"
        ((failed++))
    fi
    
    echo ""
    return $failed
}

# Test 7: Integration with existing FinOps stack
test_finops_integration() {
    echo -e "${BLUE}Test 7: FinOps Integration Validation${NC}"
    echo "------------------------------------"
    
    local failed=0
    
    # Check Prometheus integration
    if grep -q "prometheus-server" "$REPO_ROOT/k8s/autoscaling/vpa-deployment.yaml"; then
        echo -e "${GREEN}✅ Prometheus integration configured${NC}"
    else
        echo -e "${RED}❌ Prometheus integration missing${NC}"
        ((failed++))
    fi
    
    # Check cost impact tracking
    if grep -q "cost_impact" "$REPO_ROOT/k8s/monitoring/prometheus-vpa-rules.yaml"; then
        echo -e "${GREEN}✅ Cost impact tracking present${NC}"
    else
        echo -e "${RED}❌ Cost impact tracking missing${NC}"
        ((failed++))
    fi
    
    # Check OpenCost integration
    if grep -q "opencost" "$REPO_ROOT/k8s/monitoring/prometheus-vpa-rules.yaml"; then
        echo -e "${GREEN}✅ OpenCost integration present${NC}"
    else
        echo -e "${YELLOW}⚠️  OpenCost integration not explicitly configured${NC}"
    fi
    
    # Check alerting integration
    if grep -q "severity:" "$REPO_ROOT/k8s/monitoring/prometheus-vpa-rules.yaml"; then
        echo -e "${GREEN}✅ Alerting system integration present${NC}"
    else
        echo -e "${RED}❌ Alerting system integration missing${NC}"
        ((failed++))
    fi
    
    echo ""
    return $failed
}

# Run all tests
run_all_tests() {
    local total_failed=0
    
    test_vpa_configurations || ((total_failed += $?))
    test_pipeline_vpa_configs || ((total_failed += $?))
    test_installation_script || ((total_failed += $?))
    test_monitoring_rules || ((total_failed += $?))
    test_vpa_workflow_simulation || ((total_failed += $?))
    test_dod_requirements || ((total_failed += $?))
    test_finops_integration || ((total_failed += $?))
    
    echo -e "${BLUE}📋 Test Summary${NC}"
    echo "=================="
    
    if [[ $total_failed -eq 0 ]]; then
        echo -e "${GREEN}✅ All tests passed! VPA rightsizing implementation is ready.${NC}"
        echo ""
        echo -e "${BLUE}🚀 Next Steps:${NC}"
        echo "1. Deploy VPA in recommendations-only mode:"
        echo "   ./k8s/autoscaling/install-vpa-rightsizing.sh"
        echo ""
        echo "2. Monitor VPA recommendations for 1-2 weeks:"
        echo "   kubectl get vpa -n data-pipeline -o wide"
        echo "   kubectl describe vpa <vpa-name> -n data-pipeline"
        echo ""
        echo "3. Switch to Auto mode when ready:"
        echo "   PHASE=auto ./k8s/autoscaling/install-vpa-rightsizing.sh"
        echo ""
        echo "4. Monitor resource allocation improvements:"
        echo "   - FinOps Dashboard: http://grafana:3000/d/neuronews-finops/"
        echo "   - VPA Metrics: http://prometheus:9090/graph"
        echo ""
        return 0
    else
        echo -e "${RED}❌ $total_failed test(s) failed. Please fix the issues above.${NC}"
        return 1
    fi
}

# Cleanup function
cleanup() {
    if [[ -d "$TEST_DIR" ]]; then
        rm -rf "$TEST_DIR"
    fi
}
trap cleanup EXIT

# Run tests
run_all_tests
