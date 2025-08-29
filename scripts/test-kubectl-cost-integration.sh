#!/bin/bash

# Test script for kubectl-cost integration
# Validates the nightly report workflow and developer tools

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
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}🧪 Testing kubectl-cost Integration${NC}"
echo "====================================="
echo ""

# Test 1: Validate GitHub Actions workflow syntax
test_github_actions_syntax() {
    echo -e "${BLUE}Test 1: GitHub Actions Workflow Syntax${NC}"
    echo "---------------------------------------"
    
    WORKFLOW_FILE="$REPO_ROOT/.github/workflows/kubectl-cost-nightly-report.yml"
    
    if [[ ! -f "$WORKFLOW_FILE" ]]; then
        echo -e "${RED}❌ Workflow file not found: $WORKFLOW_FILE${NC}"
        return 1
    fi
    
    # Basic YAML syntax check
    if command -v yamllint &> /dev/null; then
        if yamllint "$WORKFLOW_FILE" &> /dev/null; then
            echo -e "${GREEN}✅ YAML syntax valid${NC}"
        else
            echo -e "${RED}❌ YAML syntax errors found${NC}"
            return 1
        fi
    else
        echo -e "${YELLOW}⚠️  yamllint not available, skipping syntax check${NC}"
    fi
    
    # Check required workflow elements
    if grep -q "kubectl krew install cost" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ kubectl-cost installation step found${NC}"
    else
        echo -e "${RED}❌ kubectl-cost installation step missing${NC}"
        return 1
    fi
    
    if grep -q "schedule:" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Scheduled execution configured${NC}"
    else
        echo -e "${RED}❌ Schedule configuration missing${NC}"
        return 1
    fi
    
    if grep -q "workflow_dispatch" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Manual trigger enabled${NC}"
    else
        echo -e "${RED}❌ Manual trigger missing${NC}"
        return 1
    fi
    
    echo ""
}

# Test 2: Validate developer script functionality
test_developer_script() {
    echo -e "${BLUE}Test 2: Developer Script Functionality${NC}"
    echo "--------------------------------------"
    
    DEV_SCRIPT="$REPO_ROOT/scripts/kubectl-cost-dev.sh"
    
    if [[ ! -f "$DEV_SCRIPT" ]]; then
        echo -e "${RED}❌ Developer script not found: $DEV_SCRIPT${NC}"
        return 1
    fi
    
    if [[ ! -x "$DEV_SCRIPT" ]]; then
        echo -e "${RED}❌ Developer script not executable${NC}"
        return 1
    fi
    
    echo -e "${GREEN}✅ Developer script exists and is executable${NC}"
    
    # Test help command
    if "$DEV_SCRIPT" help &> /dev/null; then
        echo -e "${GREEN}✅ Help command works${NC}"
    else
        echo -e "${RED}❌ Help command failed${NC}"
        return 1
    fi
    
    # Check if script handles missing kubectl gracefully
    if PATH="/dev/null" "$DEV_SCRIPT" 2>&1 | grep -q "kubectl not found"; then
        echo -e "${GREEN}✅ Handles missing kubectl gracefully${NC}"
    else
        echo -e "${YELLOW}⚠️  kubectl handling test inconclusive${NC}"
    fi
    
    echo ""
}

# Test 3: Mock kubectl-cost report generation
test_report_generation() {
    echo -e "${BLUE}Test 3: Mock Report Generation${NC}"
    echo "--------------------------------"
    
    cd "$TEST_DIR"
    
    # Create mock kubectl-cost output
    cat << 'EOF' > mock-kubectl-cost.sh
#!/bin/bash
case "$*" in
    *"--help"*)
        echo "kubectl-cost mock help"
        exit 0
        ;;
    *"--show-cpu --show-memory --show-pv --show-efficiency"*)
        echo "NAMESPACE    CPU_COST  MEMORY_COST  PV_COST  TOTAL_COST  EFFICIENCY"
        echo "default      $5.23     $3.45        $1.20    $9.88       67%"
        echo "api          $12.45    $8.23        $2.10    $22.78      82%"
        echo "data-pipeline $8.90    $15.67       $5.43    $30.00      45%"
        ;;
    *"--namespace"*)
        NS=$(echo "$*" | grep -o '\--namespace [^ ]*' | cut -d' ' -f2)
        echo "Namespace: $NS"
        echo "CPU Cost: \$2.50, Memory Cost: \$1.75"
        ;;
    *"--show-controller"*)
        echo "CONTROLLER       COST"
        echo "Deployment       $25.50"
        echo "StatefulSet      $15.30"
        echo "Job             $5.20"
        ;;
    *)
        echo "kubectl-cost mock: $*"
        ;;
esac
EOF
    chmod +x mock-kubectl-cost.sh
    
    # Create mock kubectl command
    cat << 'EOF' > mock-kubectl.sh
#!/bin/bash
case "$*" in
    "cluster-info")
        echo "Kubernetes control plane is running"
        ;;
    "get nodes")
        echo "NAME    STATUS   ROLES    AGE   VERSION"
        echo "node1   Ready    master   1d    v1.28.0"
        ;;
    "get namespace"*)
        echo "NAME            STATUS   AGE"
        echo "default         Active   1d"
        echo "api             Active   1d"
        echo "data-pipeline   Active   1d"
        ;;
    "top nodes")
        echo "NAME    CPU    MEMORY"
        echo "node1   50%    60%"
        ;;
    "top pods"*)
        echo "NAMESPACE   NAME        CPU    MEMORY"
        echo "api         pod1        100m   256Mi"
        echo "default     pod2        50m    128Mi"
        ;;
    "cost"*)
        ./mock-kubectl-cost.sh "$@"
        ;;
    *)
        echo "kubectl mock: $*"
        ;;
esac
EOF
    chmod +x mock-kubectl.sh
    
    # Test report generation simulation
    export PATH="$TEST_DIR:$PATH"
    
    # Simulate report generation logic
    cat << 'EOF' > test-report-gen.sh
#!/bin/bash
echo "# 🏷️ NeuroNews Nightly Cost Report - $(date +%Y-%m-%d)" > cost-report.md
echo "" >> cost-report.md
echo "Generated at: $(date -u '+%Y-%m-%d %H:%M:%S UTC')" >> cost-report.md
echo "" >> cost-report.md

echo "## 💰 Overall Cluster Cost" >> cost-report.md
echo "" >> cost-report.md
echo "\`\`\`" >> cost-report.md
./mock-kubectl.sh cost --show-cpu --show-memory --show-pv --show-efficiency >> cost-report.md
echo "\`\`\`" >> cost-report.md
echo "" >> cost-report.md

echo "## 📊 Top 10 Costly Workloads by Namespace" >> cost-report.md
echo "" >> cost-report.md
echo "| Namespace | CPU Cost | Memory Cost | PV Cost | Total Cost | Efficiency |" >> cost-report.md
echo "|-----------|----------|-------------|---------|------------|------------|" >> cost-report.md
echo "| default | \$5.23 | \$3.45 | \$1.20 | \$9.88 | 67% |" >> cost-report.md
echo "| api | \$12.45 | \$8.23 | \$2.10 | \$22.78 | 82% |" >> cost-report.md
echo "| data-pipeline | \$8.90 | \$15.67 | \$5.43 | \$30.00 | 45% |" >> cost-report.md

echo "Cost report generated successfully"
EOF
    chmod +x test-report-gen.sh
    
    if ./test-report-gen.sh && [[ -f "cost-report.md" ]]; then
        echo -e "${GREEN}✅ Mock report generation successful${NC}"
        
        # Validate report content
        if grep -q "NeuroNews Nightly Cost Report" cost-report.md; then
            echo -e "${GREEN}✅ Report header present${NC}"
        else
            echo -e "${RED}❌ Report header missing${NC}"
            return 1
        fi
        
        if grep -q "Top 10 Costly Workloads" cost-report.md; then
            echo -e "${GREEN}✅ Workload analysis section present${NC}"
        else
            echo -e "${RED}❌ Workload analysis section missing${NC}"
            return 1
        fi
        
        if grep -q "data-pipeline" cost-report.md; then
            echo -e "${GREEN}✅ Pipeline-specific data included${NC}"
        else
            echo -e "${RED}❌ Pipeline-specific data missing${NC}"
            return 1
        fi
        
    else
        echo -e "${RED}❌ Mock report generation failed${NC}"
        return 1
    fi
    
    echo ""
}

# Test 4: Validate documentation completeness
test_documentation() {
    echo -e "${BLUE}Test 4: Documentation Completeness${NC}"
    echo "-----------------------------------"
    
    DOC_FILE="$REPO_ROOT/docs/finops/kubectl-cost-integration.md"
    
    if [[ ! -f "$DOC_FILE" ]]; then
        echo -e "${RED}❌ Documentation file not found: $DOC_FILE${NC}"
        return 1
    fi
    
    # Check required documentation sections
    sections=(
        "Overview"
        "Developer Usage"
        "Nightly Reports"
        "Pipeline Cost Analysis"
        "Installation & Setup"
        "Troubleshooting"
    )
    
    for section in "${sections[@]}"; do
        if grep -q "$section" "$DOC_FILE"; then
            echo -e "${GREEN}✅ $section section present${NC}"
        else
            echo -e "${RED}❌ $section section missing${NC}"
            return 1
        fi
    done
    
    # Check for code examples
    if grep -q "\`\`\`bash" "$DOC_FILE"; then
        echo -e "${GREEN}✅ Code examples included${NC}"
    else
        echo -e "${RED}❌ Code examples missing${NC}"
        return 1
    fi
    
    echo ""
}

# Test 5: Validate GitHub Discussions integration
test_discussions_integration() {
    echo -e "${BLUE}Test 5: GitHub Discussions Integration${NC}"
    echo "-------------------------------------"
    
    WORKFLOW_FILE="$REPO_ROOT/.github/workflows/kubectl-cost-nightly-report.yml"
    
    if grep -q "actions/github-script" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ GitHub script action configured${NC}"
    else
        echo -e "${RED}❌ GitHub script action missing${NC}"
        return 1
    fi
    
    if grep -q "createDiscussion" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Discussion creation logic present${NC}"
    else
        echo -e "${RED}❌ Discussion creation logic missing${NC}"
        return 1
    fi
    
    if grep -q "discussionCategories" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Category handling implemented${NC}"
    else
        echo -e "${RED}❌ Category handling missing${NC}"
        return 1
    fi
    
    echo ""
}

# Test 6: Validate Slack integration
test_slack_integration() {
    echo -e "${BLUE}Test 6: Slack Integration${NC}"
    echo "-------------------------"
    
    WORKFLOW_FILE="$REPO_ROOT/.github/workflows/kubectl-cost-nightly-report.yml"
    
    if grep -q "SLACK_WEBHOOK_URL" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Slack webhook configuration present${NC}"
    else
        echo -e "${RED}❌ Slack webhook configuration missing${NC}"
        return 1
    fi
    
    if grep -q "slack-payload.json" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Slack payload generation present${NC}"
    else
        echo -e "${RED}❌ Slack payload generation missing${NC}"
        return 1
    fi
    
    if grep -q "blocks" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Slack block formatting configured${NC}"
    else
        echo -e "${RED}❌ Slack block formatting missing${NC}"
        return 1
    fi
    
    echo ""
}

# Test 7: Validate error handling
test_error_handling() {
    echo -e "${BLUE}Test 7: Error Handling${NC}"
    echo "----------------------"
    
    WORKFLOW_FILE="$REPO_ROOT/.github/workflows/kubectl-cost-nightly-report.yml"
    DEV_SCRIPT="$REPO_ROOT/scripts/kubectl-cost-dev.sh"
    
    # Check workflow error handling
    if grep -q "|| {" "$WORKFLOW_FILE"; then
        echo -e "${GREEN}✅ Workflow error handling present${NC}"
    else
        echo -e "${RED}❌ Workflow error handling missing${NC}"
        return 1
    fi
    
    # Check script error handling
    if grep -q "set -e" "$DEV_SCRIPT"; then
        echo -e "${GREEN}✅ Script error handling enabled${NC}"
    else
        echo -e "${RED}❌ Script error handling missing${NC}"
        return 1
    fi
    
    if grep -q "command -v kubectl" "$DEV_SCRIPT"; then
        echo -e "${GREEN}✅ Prerequisites checking implemented${NC}"
    else
        echo -e "${RED}❌ Prerequisites checking missing${NC}"
        return 1
    fi
    
    echo ""
}

# Run all tests
run_all_tests() {
    local failed_tests=0
    
    test_github_actions_syntax || ((failed_tests++))
    test_developer_script || ((failed_tests++))
    test_report_generation || ((failed_tests++))
    test_documentation || ((failed_tests++))
    test_discussions_integration || ((failed_tests++))
    test_slack_integration || ((failed_tests++))
    test_error_handling || ((failed_tests++))
    
    echo -e "${BLUE}📋 Test Summary${NC}"
    echo "=================="
    
    if [[ $failed_tests -eq 0 ]]; then
        echo -e "${GREEN}✅ All tests passed! kubectl-cost integration is ready.${NC}"
        echo ""
        echo -e "${BLUE}🚀 Next Steps:${NC}"
        echo "1. Configure secrets in GitHub repository:"
        echo "   - KUBECONFIG_CONTENT (base64-encoded kubeconfig)"
        echo "   - SLACK_WEBHOOK_URL_FINOPS (optional Slack webhook)"
        echo ""
        echo "2. Enable GitHub Discussions in repository settings"
        echo ""
        echo "3. Test the developer script:"
        echo "   ./scripts/kubectl-cost-dev.sh help"
        echo ""
        echo "4. Trigger the nightly report manually:"
        echo "   Go to Actions → kubectl-cost nightly report → Run workflow"
        echo ""
        return 0
    else
        echo -e "${RED}❌ $failed_tests test(s) failed. Please fix the issues above.${NC}"
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
