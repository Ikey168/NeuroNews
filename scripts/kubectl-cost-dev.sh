#!/bin/bash

# kubectl-cost Developer Helper Script
# Provides quick cost insights for NeuroNews developers

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}===================================================${NC}"
    echo -e "${BLUE}🏷️  NeuroNews kubectl-cost Developer Tool${NC}"
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
    
    # Check kubectl-cost plugin
    if ! kubectl cost --help &> /dev/null; then
        echo -e "${YELLOW}⚠️  kubectl-cost plugin not found. Installing via krew...${NC}"
        install_kubectl_cost
    else
        echo -e "${GREEN}✅ kubectl-cost plugin found${NC}"
    fi
    
    echo ""
}

install_kubectl_cost() {
    echo -e "${BLUE}Installing kubectl-cost plugin...${NC}"
    
    # Check if krew is installed
    if ! command -v kubectl-krew &> /dev/null; then
        echo -e "${YELLOW}Installing krew plugin manager...${NC}"
        (
            set -x; cd "$(mktemp -d)" &&
            OS="$(uname | tr '[:upper:]' '[:lower:]')" &&
            ARCH="$(uname -m | sed -e 's/x86_64/amd64/' -e 's/\(arm\)\(64\)\?.*/\1\2/' -e 's/aarch64$/arm64/')" &&
            KREW="krew-${OS}_${ARCH}" &&
            curl -fsSLO "https://github.com/kubernetes-sigs/krew/releases/latest/download/${KREW}.tar.gz" &&
            tar zxvf "${KREW}.tar.gz" &&
            ./"${KREW}" install krew
        )
        export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"
        echo 'export PATH="${KREW_ROOT:-$HOME/.krew}/bin:$PATH"' >> ~/.bashrc
    fi
    
    # Install kubectl-cost
    kubectl krew update
    kubectl krew install cost
    echo -e "${GREEN}✅ kubectl-cost plugin installed${NC}"
}

show_quick_overview() {
    print_section "Quick Cost Overview"
    
    echo -e "${BLUE}Overall cluster cost:${NC}"
    kubectl cost --show-cpu --show-memory --show-pv --show-efficiency 2>/dev/null || {
        echo -e "${YELLOW}⚠️  Cost data not available yet. OpenCost may still be initializing.${NC}"
        echo "Try again in a few minutes, or check if OpenCost is deployed:"
        echo "kubectl get pods -n opencost"
    }
    echo ""
}

show_pipeline_costs() {
    print_section "NeuroNews Pipeline Costs"
    
    # Check common NeuroNews namespaces
    namespaces=("data-pipeline" "ingestion" "api" "embedding" "vector-search" "monitoring" "default")
    
    for ns in "${namespaces[@]}"; do
        if kubectl get namespace "$ns" &> /dev/null; then
            echo -e "${BLUE}💰 $ns namespace:${NC}"
            kubectl cost --namespace "$ns" --show-cpu --show-memory 2>/dev/null || {
                echo -e "${YELLOW}  No cost data available for $ns${NC}"
            }
            echo ""
        fi
    done
}

show_workload_costs() {
    print_section "Top Costly Workloads"
    
    echo -e "${BLUE}Cost by controller type:${NC}"
    kubectl cost --show-controller 2>/dev/null || {
        echo -e "${YELLOW}⚠️  Controller cost data not available${NC}"
    }
    echo ""
    
    echo -e "${BLUE}Resource utilization:${NC}"
    echo "Top memory consumers:"
    kubectl top pods --all-namespaces --sort-by=memory | head -10 2>/dev/null || {
        echo -e "${YELLOW}  Pod metrics not available${NC}"
    }
    echo ""
}

show_optimization_tips() {
    print_section "Cost Optimization Tips"
    
    cat << EOF
💡 Quick wins for cost reduction:

🔧 Resource Right-sizing:
   • Review pods with low efficiency scores (<50%)
   • Check resource requests vs actual usage
   • kubectl top pods --all-namespaces --sort-by=memory

⏰ Temporal Optimization:
   • Scale down dev/test environments after hours
   • Use scheduled scaling for predictable workloads
   • Consider spot instances for batch jobs

📊 Monitoring:
   • Set up budget alerts (see prometheus alerts)
   • Review weekly cost trends
   • Monitor unit economics (cost per article/query)

🔗 Resources:
   • FinOps Dashboard: http://grafana:3000/d/neuronews-finops/
   • Budget Alerts: http://prometheus:9090/alerts
   • Runbook: docs/runbooks/finops-budget-alerts.md

EOF
}

generate_pr_screenshot() {
    print_section "PR Screenshot Helper"
    
    echo -e "${BLUE}Generating cost summary for PR descriptions...${NC}"
    
    {
        echo "## 💰 Cost Impact Analysis"
        echo ""
        echo "### Before/After Comparison"
        echo "\`\`\`"
        echo "Generated at: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
        echo ""
        kubectl cost --show-cpu --show-memory --show-pv 2>/dev/null || echo "Cost data not available"
        echo "\`\`\`"
        echo ""
        echo "### Top Resource Consumers"
        echo "\`\`\`"
        kubectl top pods --all-namespaces --sort-by=memory | head -5 2>/dev/null || echo "Pod metrics not available"
        echo "\`\`\`"
        echo ""
        echo "**💡 Cost Optimization Notes:**"
        echo "- [ ] Reviewed resource requests vs actual usage"
        echo "- [ ] Confirmed no significant cost increase"
        echo "- [ ] Updated monitoring dashboards if needed"
        echo ""
    } > pr-cost-summary.md
    
    echo -e "${GREEN}✅ Cost summary saved to pr-cost-summary.md${NC}"
    echo "Copy this content to your PR description for cost transparency!"
    echo ""
}

show_help() {
    cat << EOF
🏷️ NeuroNews kubectl-cost Developer Tool

Usage: $0 [command]

Commands:
  overview    Show quick cost overview (default)
  pipelines   Show costs by NeuroNews pipeline components
  workloads   Show top costly workloads and resource usage
  optimize    Show cost optimization recommendations
  pr          Generate cost summary for PR descriptions
  install     Install kubectl-cost plugin
  help        Show this help message

Examples:
  $0                    # Quick overview
  $0 pipelines         # Pipeline-specific costs
  $0 pr               # Generate PR cost summary
  
Environment Variables:
  KUBECONFIG          Path to kubernetes config file
  KUBECTL_COST_FORMAT Output format (json, table, csv)

For more detailed reports, check the nightly cost reports in:
- GitHub Discussions (search for "Nightly Cost Report")
- Slack #finops-team channel
- FinOps Dashboard: http://grafana:3000/d/neuronews-finops/

EOF
}

# Main script logic
main() {
    case "${1:-overview}" in
        "overview")
            print_header
            check_prerequisites
            show_quick_overview
            ;;
        "pipelines")
            print_header
            check_prerequisites
            show_pipeline_costs
            ;;
        "workloads")
            print_header
            check_prerequisites
            show_workload_costs
            ;;
        "optimize")
            print_header
            show_optimization_tips
            ;;
        "pr")
            print_header
            check_prerequisites
            generate_pr_screenshot
            ;;
        "install")
            print_header
            install_kubectl_cost
            ;;
        "help"|"-h"|"--help")
            show_help
            ;;
        *)
            echo -e "${RED}Unknown command: $1${NC}"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Trap to cleanup on exit
cleanup() {
    if [[ -f "pr-cost-summary.md" ]]; then
        echo -e "${BLUE}💾 PR cost summary available at: pr-cost-summary.md${NC}"
    fi
}
trap cleanup EXIT

# Run main function
main "$@"
