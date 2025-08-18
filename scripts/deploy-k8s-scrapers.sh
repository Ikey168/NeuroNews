#!/bin/bash

# NeuroNews Scrapers Kubernetes Deployment Script
# Issue #73: Deploy Scrapers as Kubernetes CronJobs

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="neuronews"
CRONJOB_PREFIX="neuronews"
DEPLOYMENT_NAME="scrapers"

# Helper functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO:${NC} $1"
}

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if kubectl can connect to cluster
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster. Please check your kubeconfig"
        exit 1
    fi
    
    log "kubectl is available and connected to cluster"
}

# Check if required tools are available
check_dependencies() {
    local deps=("kubectl" "jq")
    for dep in "${deps[@]}"; do
        if ! command -v "$dep" &> /dev/null; then
            warn "$dep is not installed or not in PATH"
        else
            info "$dep is available"
        fi
    done
}

# Create namespace if it doesn't exist
create_namespace() {
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        info "Namespace $NAMESPACE already exists"
    else
        log "Creating namespace $NAMESPACE"
        kubectl create namespace "$NAMESPACE"
        kubectl label namespace "$NAMESPACE" name="$NAMESPACE"
        log "Namespace $NAMESPACE created successfully"
    fi
}

# Deploy RBAC
deploy_rbac() {
    log "Deploying RBAC for scrapers"
    kubectl apply -f k8s/scrapers/rbac.yaml
    log "RBAC deployed successfully"
}

# Deploy configurations
deploy_configs() {
    log "Deploying ConfigMaps and Secrets"
    kubectl apply -f k8s/scrapers/configmap.yaml
    kubectl apply -f k8s/scrapers/policies.yaml
    log "Configurations deployed successfully"
}

# Deploy CronJobs
deploy_cronjobs() {
    log "Deploying Scraper CronJobs"
    kubectl apply -f k8s/scrapers/cronjobs.yaml
    log "CronJobs deployed successfully"
}

# Deploy monitoring
deploy_monitoring() {
    log "Deploying monitoring configurations"
    kubectl apply -f k8s/scrapers/monitoring.yaml
    log "Monitoring configurations deployed successfully"
}

# Get deployment status
get_status() {
    info "=== Scrapers Deployment Status ==="
    
    echo
    info "Namespace:"
    kubectl get namespace $NAMESPACE
    
    echo
    info "CronJobs:"
    kubectl get cronjobs -n $NAMESPACE -l app=neuronews-scrapers
    
    echo
    info "Active Jobs:"
    kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers
    
    echo
    info "Running Pods:"
    kubectl get pods -n $NAMESPACE -l app=neuronews-scrapers
    
    echo
    info "ConfigMaps:"
    kubectl get configmaps -n $NAMESPACE -l app=neuronews-scrapers
    
    echo
    info "Secrets:"
    kubectl get secrets -n $NAMESPACE -l app=neuronews-scrapers
    
    echo
    info "Recent Events:"
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' | tail -10
}

# Get CronJob schedules
get_schedules() {
    info "=== Scraper Schedules ==="
    
    local cronjobs=$(kubectl get cronjobs -n $NAMESPACE -l app=neuroneus-scrapers -o json)
    
    echo "$cronjobs" | jq -r '.items[] | "CronJob: \(.metadata.name), Schedule: \(.spec.schedule), Next Run: \(.status.lastScheduleTime // "Never")"'
    
    echo
    info "Current Time: $(date)"
}

# Get job history
get_job_history() {
    info "=== Job Execution History ==="
    
    echo "Recent Successful Jobs:"
    kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers --field-selector=status.successful=1 --sort-by='.status.completionTime' | tail -5
    
    echo
    echo "Recent Failed Jobs:"
    kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers --field-selector=status.failed=1 --sort-by='.status.completionTime' | tail -5
    
    echo
    echo "Currently Running Jobs:"
    kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers --field-selector=status.active=1
}

# Trigger manual job
trigger_job() {
    local scraper_type=${1:-news}
    local job_name="${CRONJOB_PREFIX}-${scraper_type}-scraper-manual-$(date +%s)"
    
    log "Triggering manual job for $scraper_type scraper: $job_name"
    
    # Get CronJob spec and create manual job
    kubectl get cronjob "${CRONJOB_PREFIX}-${scraper_type}-scraper" -n $NAMESPACE -o json | \
        jq ".spec.jobTemplate.spec.template.metadata.name = \"$job_name\"" | \
        jq ".spec.jobTemplate" | \
        jq "del(.spec.template.metadata.name)" | \
        kubectl create -f - -n $NAMESPACE
    
    log "Manual job $job_name created successfully"
    
    # Wait for job to start
    log "Waiting for job to start..."
    kubectl wait --for=condition=Ready pod -l job-name=$job_name -n $NAMESPACE --timeout=60s || true
    
    # Show job status
    kubectl get job $job_name -n $NAMESPACE
}

# Scale CronJobs (suspend/resume)
scale_cronjobs() {
    local action=${1:-suspend}
    local suspend_value="true"
    
    if [ "$action" = "resume" ]; then
        suspend_value="false"
    fi
    
    log "${action^}ing all scraper CronJobs"
    
    kubectl patch cronjobs -n $NAMESPACE -l app=neuronews-scrapers -p "{\"spec\":{\"suspend\":$suspend_value}}"
    
    log "All scraper CronJobs ${action}d successfully"
}

# Show logs from scraper jobs
show_logs() {
    local scraper_type=${1:-}
    local lines=${2:-100}
    
    if [ -n "$scraper_type" ]; then
        info "Showing logs from $scraper_type scraper (last $lines lines):"
        kubectl logs -n $NAMESPACE -l component=${scraper_type}-scraper --tail=$lines
    else
        info "Showing logs from all scrapers (last $lines lines):"
        kubectl logs -n $NAMESPACE -l app=neuronews-scrapers --tail=$lines
    fi
}

# Monitor job execution
monitor_jobs() {
    info "Monitoring scraper job execution (Press Ctrl+C to stop)"
    
    while true; do
        clear
        echo "=== NeuroNews Scrapers Monitor ==="
        echo "Time: $(date)"
        echo
        
        echo "Active Jobs:"
        kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers --field-selector=status.active=1 --no-headers 2>/dev/null || echo "No active jobs"
        echo
        
        echo "Recently Completed Jobs:"
        kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers --sort-by='.status.completionTime' --no-headers | tail -3 2>/dev/null || echo "No completed jobs"
        echo
        
        echo "Resource Usage:"
        kubectl top pods -n $NAMESPACE -l app=neuronews-scrapers --no-headers 2>/dev/null || echo "Metrics not available"
        echo
        
        sleep 30
    done
}

# Clean up failed jobs
cleanup_failed_jobs() {
    log "Cleaning up failed jobs"
    
    # Delete failed jobs older than 24 hours
    local failed_jobs=$(kubectl get jobs -n $NAMESPACE -l app=neuronews-scrapers --field-selector=status.failed=1 -o json | \
        jq -r '.items[] | select((.status.completionTime // .metadata.creationTimestamp) < (now - 86400 | strftime("%Y-%m-%dT%H:%M:%SZ"))) | .metadata.name')
    
    if [ -n "$failed_jobs" ]; then
        echo "$failed_jobs" | xargs -I {} kubectl delete job {} -n $NAMESPACE
        log "Cleaned up $(echo "$failed_jobs" | wc -l) failed jobs"
    else
        info "No old failed jobs to clean up"
    fi
}

# Cleanup all resources
cleanup() {
    warn "Cleaning up scraper deployment..."
    
    # Suspend all CronJobs first
    kubectl patch cronjobs -n $NAMESPACE -l app=neuronews-scrapers -p '{"spec":{"suspend":true}}' || true
    
    # Delete all jobs
    kubectl delete jobs -n $NAMESPACE -l app=neuronews-scrapers --ignore-not-found=true
    
    # Delete CronJobs
    kubectl delete -f k8s/scrapers/cronjobs.yaml --ignore-not-found=true
    
    # Delete monitoring
    kubectl delete -f k8s/scrapers/monitoring.yaml --ignore-not-found=true
    
    # Delete policies
    kubectl delete -f k8s/scrapers/policies.yaml --ignore-not-found=true
    
    # Delete configs
    kubectl delete -f k8s/scrapers/configmap.yaml --ignore-not-found=true
    
    # Delete RBAC
    kubectl delete -f k8s/scrapers/rbac.yaml --ignore-not-found=true
    
    warn "Cleanup completed"
}

# Validate deployment
validate_deployment() {
    info "=== Validating Scraper Deployment ==="
    
    local errors=0
    
    # Check namespace
    if kubectl get namespace $NAMESPACE &> /dev/null; then
        log "✅ Namespace exists"
    else
        error "❌ Namespace missing"
        ((errors++))
    fi
    
    # Check CronJobs
    local cronjob_count=$(kubectl get cronjobs -n $NAMESPACE -l app=neuronews-scrapers --no-headers 2>/dev/null | wc -l)
    if [ "$cronjob_count" -gt 0 ]; then
        log "✅ $cronjob_count CronJobs deployed"
    else
        error "❌ No CronJobs found"
        ((errors++))
    fi
    
    # Check ConfigMaps
    if kubectl get configmap neuronews-scraper-config -n $NAMESPACE &> /dev/null; then
        log "✅ ConfigMap exists"
    else
        error "❌ ConfigMap missing"
        ((errors++))
    fi
    
    # Check ServiceAccount
    if kubectl get serviceaccount neuronews-scrapers -n $NAMESPACE &> /dev/null; then
        log "✅ ServiceAccount exists"
    else
        error "❌ ServiceAccount missing"
        ((errors++))
    fi
    
    # Check RBAC
    if kubectl get role neuronews-scrapers-role -n $NAMESPACE &> /dev/null; then
        log "✅ RBAC configured"
    else
        error "❌ RBAC missing"
        ((errors++))
    fi
    
    if [ $errors -eq 0 ]; then
        log "✅ All validation checks passed!"
        return 0
    else
        error "❌ $errors validation errors found"
        return 1
    fi
}

# Main function
main() {
    local action=${1:-deploy}
    
    case $action in
        "deploy")
            log "Starting NeuroNews Scrapers Kubernetes deployment"
            check_kubectl
            check_dependencies
            create_namespace
            deploy_rbac
            deploy_configs
            deploy_cronjobs
            deploy_monitoring
            get_status
            validate_deployment
            log "Deployment completed successfully!"
            ;;
        "status")
            get_status
            get_schedules
            get_job_history
            ;;
        "trigger")
            trigger_job $2
            ;;
        "suspend")
            scale_cronjobs suspend
            ;;
        "resume")
            scale_cronjobs resume
            ;;
        "logs")
            show_logs $2 $3
            ;;
        "monitor")
            monitor_jobs
            ;;
        "cleanup-failed")
            cleanup_failed_jobs
            ;;
        "cleanup")
            cleanup
            ;;
        "validate")
            validate_deployment
            ;;
        "help"|"--help"|"-h")
            echo "Usage: $0 {deploy|status|trigger|suspend|resume|logs|monitor|cleanup-failed|cleanup|validate|help}"
            echo ""
            echo "Commands:"
            echo "  deploy        - Deploy all scraper CronJobs to Kubernetes"
            echo "  status        - Show deployment status and schedules"
            echo "  trigger TYPE  - Manually trigger scraper job (news|tech|ai)"
            echo "  suspend       - Suspend all scraper CronJobs"
            echo "  resume        - Resume all scraper CronJobs"
            echo "  logs [TYPE] [N] - Show logs from scrapers (optional type and line count)"
            echo "  monitor       - Real-time monitoring of job execution"
            echo "  cleanup-failed - Clean up old failed jobs"
            echo "  cleanup       - Remove all deployed resources"
            echo "  validate      - Validate deployment configuration"
            echo "  help          - Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 deploy"
            echo "  $0 trigger news"
            echo "  $0 logs tech 200"
            echo "  $0 status"
            ;;
        *)
            error "Unknown action: $action"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
