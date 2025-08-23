#!/bin/bash

# NGINX Performance Monitoring Test Script
# Tests the complete monitoring stack under high load

set -euo pipefail

# Configuration
NAMESPACE="neuronews"
TEST_DURATION=300  # 5 minutes
CONCURRENT_USERS=50
REQUESTS_PER_SECOND=100
LOG_FILE="nginx_monitoring_test_$(date +%Y%m%d_%H%M%S).log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}" | tee -a "$LOG_FILE"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}" | tee -a "$LOG_FILE"
}

# Prerequisites check
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check if kubectl is available
    if ! command -v kubectl &> /dev/null; then
        error "kubectl is not installed or not in PATH"
    fi
    
    # Check if curl is available
    if ! command -v curl &> /dev/null; then
        error "curl is not installed or not in PATH"
    fi
    
    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        error "jq is not installed or not in PATH"
    fi
    
    # Check cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster"
    fi
    
    # Check namespace exists
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        warn "Namespace $NAMESPACE does not exist, creating it..."
        kubectl create namespace "$NAMESPACE"
    fi
    
    log "Prerequisites check passed"
}

# Deploy monitoring stack
deploy_monitoring() {
    log "Deploying NGINX monitoring stack..."
    
    # Apply configurations
    info "Applying configurations..."
    kubectl apply -f k8s/nginx/monitoring-configmap.yaml
    kubectl apply -f k8s/nginx/fluentd-config.yaml
    kubectl apply -f k8s/monitoring/prometheus-nginx-config.yaml
    
    # Deploy Prometheus
    info "Deploying Prometheus..."
    kubectl apply -f k8s/monitoring/prometheus-deployment.yaml
    
    # Deploy NGINX with monitoring
    info "Deploying NGINX monitoring..."
    kubectl apply -f k8s/nginx/monitoring-deployment.yaml
    kubectl apply -f k8s/nginx/monitoring-service.yaml
    
    # Wait for deployments to be ready
    info "Waiting for deployments to be ready..."
    kubectl wait --for=condition=available --timeout=300s deployment/prometheus-nginx -n "$NAMESPACE"
    kubectl wait --for=condition=available --timeout=300s deployment/nginx-monitoring -n "$NAMESPACE"
    
    log "Monitoring stack deployed successfully"
}

# Setup port forwarding
setup_port_forwarding() {
    log "Setting up port forwarding..."
    
    # Kill any existing port forwards
    pkill -f "kubectl port-forward" || true
    sleep 2
    
    # Setup port forwards
    kubectl port-forward -n "$NAMESPACE" svc/prometheus-nginx-service 9090:9090 &
    PROMETHEUS_PF_PID=$!
    
    kubectl port-forward -n "$NAMESPACE" svc/nginx-monitoring-service 9113:9113 &
    METRICS_PF_PID=$!
    
    kubectl port-forward -n "$NAMESPACE" svc/nginx-monitoring-loadbalancer 8080:80 &
    NGINX_PF_PID=$!
    
    # Wait for port forwards to be ready
    sleep 10
    
    # Verify port forwards
    if ! curl -s http://localhost:9090/-/ready &> /dev/null; then
        error "Prometheus port forward failed"
    fi
    
    if ! curl -s http://localhost:9113/metrics &> /dev/null; then
        error "NGINX metrics port forward failed"
    fi
    
    if ! curl -s http://localhost:8080/nginx_status &> /dev/null; then
        error "NGINX port forward failed"
    fi
    
    log "Port forwarding setup complete"
}

# Test basic functionality
test_basic_functionality() {
    log "Testing basic functionality..."
    
    # Test NGINX response
    info "Testing NGINX response..."
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ | grep -q "200\|404\|302"; then
        log "NGINX is responding"
    else
        error "NGINX is not responding correctly"
    fi
    
    # Test metrics endpoint
    info "Testing metrics endpoint..."
    METRICS_COUNT=$(curl -s http://localhost:9113/metrics | grep -c "nginx_" || echo "0")
    if [ "$METRICS_COUNT" -gt 0 ]; then
        log "NGINX metrics are available ($METRICS_COUNT metrics found)"
    else
        error "NGINX metrics are not available"
    fi
    
    # Test Prometheus targets
    info "Testing Prometheus targets..."
    TARGETS=$(curl -s http://localhost:9090/api/v1/targets | jq -r '.data.activeTargets[] | select(.labels.job=="nginx-monitoring") | .health')
    if echo "$TARGETS" | grep -q "up"; then
        log "Prometheus is scraping NGINX metrics"
    else
        warn "Prometheus may not be scraping NGINX metrics correctly"
    fi
    
    log "Basic functionality tests passed"
}

# Generate load test
generate_load() {
    log "Starting load test (Duration: ${TEST_DURATION}s, Users: ${CONCURRENT_USERS}, RPS: ${REQUESTS_PER_SECOND})..."
    
    # Create a list of endpoints to test
    ENDPOINTS=(
        "/"
        "/api/v1/news"
        "/api/v1/analytics"
        "/api/v1/health"
        "/nginx_status"
    )
    
    # Function to generate requests
    generate_requests() {
        local endpoint=$1
        local duration=$2
        local rps=$3
        local delay=$(awk "BEGIN {print 1/$rps}")
        
        local end_time=$(($(date +%s) + duration))
        local request_count=0
        
        while [ $(date +%s) -lt $end_time ]; do
            curl -s -o /dev/null -w "%{http_code},%{time_total},%{size_download}\n" \
                "http://localhost:8080$endpoint" >> "${LOG_FILE}.requests" &
            
            request_count=$((request_count + 1))
            if [ $((request_count % 100)) -eq 0 ]; then
                info "Generated $request_count requests to $endpoint"
            fi
            
            sleep "$delay"
        done
    }
    
    # Start load generation
    for i in $(seq 1 $CONCURRENT_USERS); do
        endpoint=${ENDPOINTS[$((i % ${#ENDPOINTS[@]}))]}
        generate_requests "$endpoint" "$TEST_DURATION" "$((REQUESTS_PER_SECOND / CONCURRENT_USERS))" &
    done
    
    # Monitor the load test
    LOAD_START_TIME=$(date +%s)
    while [ $(($(date +%s) - LOAD_START_TIME)) -lt $TEST_DURATION ]; do
        # Get current metrics
        ACTIVE_CONNECTIONS=$(curl -s http://localhost:9113/metrics | grep "nginx_connections_active" | awk '{print $2}')
        TOTAL_REQUESTS=$(curl -s http://localhost:9113/metrics | grep "nginx_http_requests_total" | grep 'status="200"' | awk '{print $2}' | head -1)
        
        info "Active connections: ${ACTIVE_CONNECTIONS:-0}, Total requests: ${TOTAL_REQUESTS:-0}"
        sleep 10
    done
    
    # Wait for background processes to finish
    wait
    
    log "Load test completed"
}

# Analyze results
analyze_results() {
    log "Analyzing test results..."
    
    # Get final metrics from Prometheus
    info "Collecting final metrics..."
    
    # Request rate
    REQUEST_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=rate(nginx_http_requests_total[5m])" | \
        jq -r '.data.result[0].value[1] // "0"')
    
    # Error rate
    ERROR_RATE=$(curl -s "http://localhost:9090/api/v1/query?query=rate(nginx_http_requests_total{status=~\"4..|5..\"}[5m])" | \
        jq -r '.data.result[0].value[1] // "0"')
    
    # Average response time
    AVG_RESPONSE_TIME=$(curl -s "http://localhost:9090/api/v1/query?query=nginx_http_request_duration_seconds" | \
        jq -r '.data.result[0].value[1] // "0"')
    
    # Connection statistics
    ACTIVE_CONNECTIONS=$(curl -s "http://localhost:9090/api/v1/query?query=nginx_connections_active" | \
        jq -r '.data.result[0].value[1] // "0"')
    
    # Analyze request log if available
    if [ -f "${LOG_FILE}.requests" ]; then
        TOTAL_REQUESTS=$(wc -l < "${LOG_FILE}.requests")
        SUCCESS_REQUESTS=$(grep -c "^200," "${LOG_FILE}.requests" || echo "0")
        AVG_RESPONSE_TIME_LOG=$(awk -F',' '{sum+=$2; count++} END {print sum/count}' "${LOG_FILE}.requests")
    else
        TOTAL_REQUESTS=0
        SUCCESS_REQUESTS=0
        AVG_RESPONSE_TIME_LOG=0
    fi
    
    # Generate report
    cat << EOF | tee -a "$LOG_FILE"

========================================
NGINX PERFORMANCE MONITORING TEST REPORT
========================================

Test Configuration:
- Duration: ${TEST_DURATION} seconds
- Concurrent Users: ${CONCURRENT_USERS}
- Target RPS: ${REQUESTS_PER_SECOND}

Metrics from Prometheus:
- Request Rate: ${REQUEST_RATE} req/s
- Error Rate: ${ERROR_RATE} errors/s
- Average Response Time: ${AVG_RESPONSE_TIME}s
- Active Connections: ${ACTIVE_CONNECTIONS}

Metrics from Test Log:
- Total Requests: ${TOTAL_REQUESTS}
- Successful Requests: ${SUCCESS_REQUESTS}
- Success Rate: $(awk "BEGIN {print ($SUCCESS_REQUESTS/$TOTAL_REQUESTS)*100}")%
- Average Response Time: ${AVG_RESPONSE_TIME_LOG}s

Performance Assessment:
EOF

    # Performance assessment
    if (( $(echo "$REQUEST_RATE > 50" | bc -l) )); then
        echo "✅ High request rate achieved" | tee -a "$LOG_FILE"
    else
        echo "⚠️  Low request rate, may need optimization" | tee -a "$LOG_FILE"
    fi
    
    if (( $(echo "$ERROR_RATE < 1" | bc -l) )); then
        echo "✅ Low error rate maintained" | tee -a "$LOG_FILE"
    else
        echo "❌ High error rate detected" | tee -a "$LOG_FILE"
    fi
    
    if (( $(echo "$AVG_RESPONSE_TIME < 1" | bc -l) )); then
        echo "✅ Good response time performance" | tee -a "$LOG_FILE"
    else
        echo "⚠️  High response time, may need optimization" | tee -a "$LOG_FILE"
    fi
    
    log "Results analysis completed"
}

# Cleanup function
cleanup() {
    log "Cleaning up..."
    
    # Kill port forward processes
    if [ -n "${PROMETHEUS_PF_PID:-}" ]; then
        kill "$PROMETHEUS_PF_PID" 2>/dev/null || true
    fi
    if [ -n "${METRICS_PF_PID:-}" ]; then
        kill "$METRICS_PF_PID" 2>/dev/null || true
    fi
    if [ -n "${NGINX_PF_PID:-}" ]; then
        kill "$NGINX_PF_PID" 2>/dev/null || true
    fi
    
    # Kill any remaining background processes
    pkill -f "kubectl port-forward" 2>/dev/null || true
    
    log "Cleanup completed"
}

# Main execution
main() {
    log "Starting NGINX Performance Monitoring Test"
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    # Execute test phases
    check_prerequisites
    deploy_monitoring
    setup_port_forwarding
    test_basic_functionality
    generate_load
    analyze_results
    
    log "NGINX Performance Monitoring Test completed successfully"
    info "Log file: $LOG_FILE"
    info "Request log: ${LOG_FILE}.requests"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--duration)
            TEST_DURATION="$2"
            shift 2
            ;;
        -u|--users)
            CONCURRENT_USERS="$2"
            shift 2
            ;;
        -r|--rps)
            REQUESTS_PER_SECOND="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  -d, --duration SECONDS    Test duration (default: 300)"
            echo "  -u, --users NUMBER        Concurrent users (default: 50)"
            echo "  -r, --rps NUMBER          Requests per second (default: 100)"
            echo "  -n, --namespace NAME      Kubernetes namespace (default: neuronews)"
            echo "  -h, --help                Show this help message"
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Run main function
main
