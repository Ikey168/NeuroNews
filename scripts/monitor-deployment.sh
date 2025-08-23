#!/bin/bash
# Deployment monitoring script for NeuroNews
# Usage: ./monitor-deployment.sh <namespace> [duration_minutes]

set -e

NAMESPACE=${1:-neuronews-prod}
DURATION_MINUTES=${2:-10}
SERVICE_NAME="neuronews-api"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Check prerequisites
check_prerequisites() {
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        error "Namespace $NAMESPACE does not exist"
        exit 1
    fi
}

# Get deployment status
get_deployment_status() {
    local deployment_name=$1
    
    if ! kubectl get deployment $deployment_name -n $NAMESPACE &> /dev/null; then
        echo "NOT_FOUND"
        return
    fi
    
    local ready_replicas=$(kubectl get deployment $deployment_name -n $NAMESPACE -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    local desired_replicas=$(kubectl get deployment $deployment_name -n $NAMESPACE -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    
    if [[ "$ready_replicas" == "$desired_replicas" ]] && [[ "$ready_replicas" -gt 0 ]]; then
        echo "HEALTHY"
    elif [[ "$ready_replicas" -gt 0 ]]; then
        echo "DEGRADED"
    else
        echo "FAILED"
    fi
}

# Get pod status
get_pod_status() {
    local app_label=$1
    
    local pods=$(kubectl get pods -n $NAMESPACE -l app=$app_label -o jsonpath='{.items[*].status.phase}' 2>/dev/null || echo "")
    
    if [[ -z "$pods" ]]; then
        echo "NO_PODS"
        return
    fi
    
    local running_count=0
    local total_count=0
    
    for pod_phase in $pods; do
        total_count=$((total_count + 1))
        if [[ "$pod_phase" == "Running" ]]; then
            running_count=$((running_count + 1))
        fi
    done
    
    echo "RUNNING:$running_count/$total_count"
}

# Check service health
check_service_health() {
    local service_name=$1
    
    # Get service endpoint
    local service_ip=$(kubectl get svc $service_name -n $NAMESPACE -o jsonpath='{.spec.clusterIP}' 2>/dev/null || echo "")
    local service_port=$(kubectl get svc $service_name -n $NAMESPACE -o jsonpath='{.spec.ports[0].port}' 2>/dev/null || echo "")
    
    if [[ -z "$service_ip" || -z "$service_port" ]]; then
        echo "SERVICE_NOT_FOUND"
        return
    fi
    
    # Test health endpoint
    if kubectl run health-check-temp --rm -i --restart=Never --image=curlimages/curl:latest --timeout=10s \
       -- curl -f -s --max-time 5 "http://$service_ip:$service_port/health" &> /dev/null; then
        echo "HEALTHY"
    else
        echo "UNHEALTHY"
    fi
}

# Get resource usage
get_resource_usage() {
    local app_label=$1
    
    # Get pods for the app
    local pods=$(kubectl get pods -n $NAMESPACE -l app=$app_label -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -z "$pods" ]]; then
        echo "NO_PODS"
        return
    fi
    
    local total_cpu=0
    local total_memory=0
    local pod_count=0
    
    for pod in $pods; do
        local metrics=$(kubectl top pod $pod -n $NAMESPACE --no-headers 2>/dev/null || echo "")
        if [[ -n "$metrics" ]]; then
            local cpu=$(echo $metrics | awk '{print $2}' | sed 's/m//')
            local memory=$(echo $metrics | awk '{print $3}' | sed 's/Mi//')
            
            total_cpu=$((total_cpu + cpu))
            total_memory=$((total_memory + memory))
            pod_count=$((pod_count + 1))
        fi
    done
    
    if [[ $pod_count -gt 0 ]]; then
        local avg_cpu=$((total_cpu / pod_count))
        local avg_memory=$((total_memory / pod_count))
        echo "CPU:${avg_cpu}m,MEMORY:${avg_memory}Mi"
    else
        echo "NO_METRICS"
    fi
}

# Get recent events
get_recent_events() {
    local since_minutes=$1
    
    kubectl get events -n $NAMESPACE --sort-by='.lastTimestamp' --field-selector type!=Normal \
        -o custom-columns="TIME:.lastTimestamp,TYPE:.type,REASON:.reason,OBJECT:.involvedObject.name,MESSAGE:.message" \
        2>/dev/null | tail -n 10 || echo "No recent events"
}

# Monitor deployment
monitor_deployment() {
    local end_time=$(($(date +%s) + $DURATION_MINUTES * 60))
    local check_interval=30
    local alert_count=0
    local max_alerts=5
    
    log "Starting deployment monitoring for $DURATION_MINUTES minutes"
    log "Namespace: $NAMESPACE"
    log "Check interval: ${check_interval}s"
    echo ""
    
    while [[ $(date +%s) -lt $end_time ]]; do
        local timestamp=$(date +'%H:%M:%S')
        
        # Clear screen and show header
        clear
        echo "=========================================="
        echo "  NeuroNews Deployment Monitor"
        echo "  Namespace: $NAMESPACE"
        echo "  Time: $timestamp"
        echo "  Remaining: $(( (end_time - $(date +%s)) / 60 )) minutes"
        echo "=========================================="
        echo ""
        
        # Check main API deployment
        echo "🔍 API Service Status:"
        local api_status=$(get_deployment_status "$SERVICE_NAME")
        local api_pods=$(get_pod_status "$SERVICE_NAME")
        local api_health=$(check_service_health "$SERVICE_NAME")
        local api_resources=$(get_resource_usage "$SERVICE_NAME")
        
        case $api_status in
            "HEALTHY")
                echo -e "  Deployment: ${GREEN}✅ HEALTHY${NC}"
                ;;
            "DEGRADED")
                echo -e "  Deployment: ${YELLOW}⚠️  DEGRADED${NC}"
                alert_count=$((alert_count + 1))
                ;;
            "FAILED")
                echo -e "  Deployment: ${RED}❌ FAILED${NC}"
                alert_count=$((alert_count + 1))
                ;;
            *)
                echo -e "  Deployment: ${RED}❓ NOT_FOUND${NC}"
                alert_count=$((alert_count + 1))
                ;;
        esac
        
        echo "  Pods: $api_pods"
        echo "  Health: $api_health"
        echo "  Resources: $api_resources"
        echo ""
        
        # Check dashboard deployment
        echo "🖥️  Dashboard Service Status:"
        local dashboard_status=$(get_deployment_status "neuronews-dashboard")
        local dashboard_pods=$(get_pod_status "neuronews-dashboard")
        local dashboard_health=$(check_service_health "neuronews-dashboard")
        
        case $dashboard_status in
            "HEALTHY")
                echo -e "  Deployment: ${GREEN}✅ HEALTHY${NC}"
                ;;
            "DEGRADED")
                echo -e "  Deployment: ${YELLOW}⚠️  DEGRADED${NC}"
                ;;
            "FAILED")
                echo -e "  Deployment: ${RED}❌ FAILED${NC}"
                ;;
            *)
                echo -e "  Deployment: ${BLUE}ℹ️  NOT_DEPLOYED${NC}"
                ;;
        esac
        
        echo "  Pods: $dashboard_pods"
        echo "  Health: $dashboard_health"
        echo ""
        
        # Check for canary deployment
        echo "🐦 Canary Deployment Status:"
        local canary_status=$(get_deployment_status "${SERVICE_NAME}-canary")
        if [[ "$canary_status" != "NOT_FOUND" ]]; then
            local canary_pods=$(get_pod_status "${SERVICE_NAME}-canary")
            local canary_health=$(check_service_health "${SERVICE_NAME}-canary")
            
            case $canary_status in
                "HEALTHY")
                    echo -e "  Canary: ${GREEN}✅ ACTIVE & HEALTHY${NC}"
                    ;;
                "DEGRADED")
                    echo -e "  Canary: ${YELLOW}⚠️  ACTIVE & DEGRADED${NC}"
                    ;;
                "FAILED")
                    echo -e "  Canary: ${RED}❌ ACTIVE & FAILED${NC}"
                    ;;
            esac
            
            echo "  Pods: $canary_pods"
            echo "  Health: $canary_health"
        else
            echo -e "  Canary: ${BLUE}ℹ️  NOT_ACTIVE${NC}"
        fi
        echo ""
        
        # Show recent events if there are alerts
        if [[ $alert_count -gt 0 ]]; then
            echo "🚨 Recent Events (Warnings/Errors):"
            get_recent_events 5
            echo ""
        fi
        
        # Show overall status
        echo "📊 Overall Status:"
        if [[ $alert_count -eq 0 ]]; then
            echo -e "  System: ${GREEN}✅ ALL_HEALTHY${NC}"
        elif [[ $alert_count -lt 3 ]]; then
            echo -e "  System: ${YELLOW}⚠️  MINOR_ISSUES (Alert count: $alert_count)${NC}"
        else
            echo -e "  System: ${RED}❌ MAJOR_ISSUES (Alert count: $alert_count)${NC}"
        fi
        
        # Break if too many alerts
        if [[ $alert_count -gt $max_alerts ]]; then
            error "Too many alerts detected ($alert_count). Stopping monitoring."
            echo ""
            echo "Recent events:"
            get_recent_events 10
            exit 1
        fi
        
        # Reset alert count periodically
        if [[ $(( $(date +%s) % 300 )) -eq 0 ]]; then
            alert_count=0
        fi
        
        # Wait for next check
        sleep $check_interval
    done
    
    log "Monitoring completed successfully"
    
    # Final status report
    echo ""
    echo "=========================================="
    echo "  Final Status Report"
    echo "=========================================="
    
    local final_api_status=$(get_deployment_status "$SERVICE_NAME")
    local final_dashboard_status=$(get_deployment_status "neuronews-dashboard")
    local final_canary_status=$(get_deployment_status "${SERVICE_NAME}-canary")
    
    echo "API Status: $final_api_status"
    echo "Dashboard Status: $final_dashboard_status"
    echo "Canary Status: $final_canary_status"
    
    if [[ "$final_api_status" == "HEALTHY" ]]; then
        log "✅ Deployment monitoring completed - System is healthy"
        exit 0
    else
        error "❌ Deployment monitoring completed - System has issues"
        exit 1
    fi
}

# Main function
main() {
    check_prerequisites
    monitor_deployment
}

# Handle interrupts
trap 'echo ""; log "Monitoring interrupted"; exit 130' INT TERM

# Run main function
main "$@"
