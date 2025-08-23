#!/bin/bash

# Health Check Script for NeuroNews Services
# Comprehensive health monitoring for all deployed services

set -euo pipefail

# Configuration
NAMESPACE="${NAMESPACE:-neuronews}"
BASE_URL="${BASE_URL:-https://neuronews.com}"
TIMEOUT="${TIMEOUT:-30}"
RETRY_COUNT="${RETRY_COUNT:-3}"
RETRY_DELAY="${RETRY_DELAY:-5}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
NeuroNews Health Check Script

Usage: $0 [OPTIONS]

Options:
    -h, --help           Show this help message
    -n, --namespace      Kubernetes namespace (default: neuronews)
    -u, --base-url       Base URL for health checks (default: https://neuronews.com)
    -t, --timeout        Request timeout in seconds (default: 30)
    -r, --retry-count    Number of retries for failed checks (default: 3)
    -d, --retry-delay    Delay between retries in seconds (default: 5)
    -s, --service        Check specific service (api|dashboard|scraper|nlp-processor|all)
    -c, --continuous     Run continuous health monitoring
    -i, --interval       Interval for continuous monitoring in seconds (default: 60)
    --json               Output results in JSON format
    --export-metrics     Export metrics to file
    --alert-webhook      Webhook URL for alerts
    --detailed           Show detailed health information

Examples:
    $0 --service api
    $0 --continuous --interval 30
    $0 --json --export-metrics
EOF
}

# Parse command line arguments
SERVICE="all"
CONTINUOUS=false
INTERVAL=60
JSON_OUTPUT=false
EXPORT_METRICS=false
ALERT_WEBHOOK=""
DETAILED=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -u|--base-url)
            BASE_URL="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -r|--retry-count)
            RETRY_COUNT="$2"
            shift 2
            ;;
        -d|--retry-delay)
            RETRY_DELAY="$2"
            shift 2
            ;;
        -s|--service)
            SERVICE="$2"
            shift 2
            ;;
        -c|--continuous)
            CONTINUOUS=true
            shift
            ;;
        -i|--interval)
            INTERVAL="$2"
            shift 2
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        --export-metrics)
            EXPORT_METRICS=true
            shift
            ;;
        --alert-webhook)
            ALERT_WEBHOOK="$2"
            shift 2
            ;;
        --detailed)
            DETAILED=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Initialize metrics
declare -A METRICS
METRICS[total_checks]=0
METRICS[successful_checks]=0
METRICS[failed_checks]=0
METRICS[start_time]=$(date +%s)

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
}

# Get list of services to check
get_services() {
    if [ "$SERVICE" = "all" ]; then
        echo "api dashboard scraper nlp-processor"
    else
        echo "$SERVICE"
    fi
}

# Check if deployment exists
deployment_exists() {
    local service=$1
    kubectl get deployment "neuronews-$service" -n "$NAMESPACE" &> /dev/null
}

# Get deployment status
get_deployment_status() {
    local service=$1
    local deployment="neuronews-$service"
    
    if ! deployment_exists "$service"; then
        echo "NOT_FOUND"
        return
    fi
    
    local ready_replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" \
        -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    local desired_replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" \
        -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")
    local available_replicas=$(kubectl get deployment "$deployment" -n "$NAMESPACE" \
        -o jsonpath='{.status.availableReplicas}' 2>/dev/null || echo "0")
    
    if [ "$ready_replicas" = "$desired_replicas" ] && [ "$available_replicas" = "$desired_replicas" ]; then
        echo "HEALTHY"
    elif [ "$ready_replicas" -gt 0 ]; then
        echo "PARTIAL"
    else
        echo "UNHEALTHY"
    fi
}

# Get pod status
get_pod_status() {
    local service=$1
    local pods_info
    
    pods_info=$(kubectl get pods -l "app=neuronews-$service" -n "$NAMESPACE" \
        --no-headers 2>/dev/null || echo "")
    
    if [ -z "$pods_info" ]; then
        echo "NO_PODS"
        return
    fi
    
    local total_pods=0
    local ready_pods=0
    local running_pods=0
    
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            total_pods=$((total_pods + 1))
            local ready=$(echo "$line" | awk '{print $2}' | cut -d'/' -f1)
            local status=$(echo "$line" | awk '{print $3}')
            
            if [ "$ready" != "0" ]; then
                ready_pods=$((ready_pods + 1))
            fi
            
            if [ "$status" = "Running" ]; then
                running_pods=$((running_pods + 1))
            fi
        fi
    done <<< "$pods_info"
    
    echo "$ready_pods/$total_pods ready, $running_pods/$total_pods running"
}

# HTTP health check with retries
http_health_check() {
    local url=$1
    local service_name=$2
    local attempt=1
    
    while [ $attempt -le $RETRY_COUNT ]; do
        local start_time=$(date +%s%3N)
        local response_code=0
        local response_time=0
        
        if response_code=$(curl -s -o /dev/null -w "%{http_code}" \
            --max-time "$TIMEOUT" \
            --connect-timeout 10 \
            "$url" 2>/dev/null); then
            
            local end_time=$(date +%s%3N)
            response_time=$((end_time - start_time))
            
            if [ "$response_code" -eq 200 ]; then
                if [ "$JSON_OUTPUT" = false ]; then
                    log_success "$service_name HTTP check passed (${response_time}ms, attempt $attempt)"
                fi
                echo "HEALTHY,$response_code,$response_time"
                return 0
            else
                if [ "$JSON_OUTPUT" = false ]; then
                    log_warning "$service_name HTTP check failed with code $response_code (attempt $attempt/$RETRY_COUNT)"
                fi
            fi
        else
            if [ "$JSON_OUTPUT" = false ]; then
                log_warning "$service_name HTTP check failed to connect (attempt $attempt/$RETRY_COUNT)"
            fi
        fi
        
        if [ $attempt -lt $RETRY_COUNT ]; then
            sleep "$RETRY_DELAY"
        fi
        attempt=$((attempt + 1))
    done
    
    echo "UNHEALTHY,$response_code,0"
    return 1
}

# Check service health
check_service_health() {
    local service=$1
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    METRICS[total_checks]=$((METRICS[total_checks] + 1))
    
    # Get deployment status
    local deployment_status=$(get_deployment_status "$service")
    local pod_status=$(get_pod_status "$service")
    
    # Initialize result object
    local result_status="HEALTHY"
    local http_status=""
    local response_code=0
    local response_time=0
    local error_message=""
    
    # Check deployment health
    if [ "$deployment_status" != "HEALTHY" ]; then
        result_status="UNHEALTHY"
        error_message="Deployment status: $deployment_status"
    fi
    
    # HTTP health check for web services
    if [[ "$service" == "api" || "$service" == "dashboard" ]]; then
        local health_url="$BASE_URL"
        if [ "$service" = "api" ]; then
            health_url="$BASE_URL/api/health"
        else
            health_url="$BASE_URL/health"
        fi
        
        local http_result
        if http_result=$(http_health_check "$health_url" "$service"); then
            IFS=',' read -r http_status response_code response_time <<< "$http_result"
            if [ "$http_status" != "HEALTHY" ]; then
                result_status="UNHEALTHY"
                error_message="${error_message:+$error_message; }HTTP check failed"
            fi
        else
            result_status="UNHEALTHY"
            error_message="${error_message:+$error_message; }HTTP check failed"
        fi
    fi
    
    # Update metrics
    if [ "$result_status" = "HEALTHY" ]; then
        METRICS[successful_checks]=$((METRICS[successful_checks] + 1))
    else
        METRICS[failed_checks]=$((METRICS[failed_checks] + 1))
    fi
    
    # Output results
    if [ "$JSON_OUTPUT" = true ]; then
        cat << EOF
{
  "service": "$service",
  "timestamp": "$timestamp",
  "status": "$result_status",
  "deployment_status": "$deployment_status",
  "pod_status": "$pod_status",
  "http_response_code": $response_code,
  "response_time_ms": $response_time,
  "error_message": "$error_message"
}
EOF
    else
        local status_color=""
        case $result_status in
            "HEALTHY") status_color="$GREEN" ;;
            "UNHEALTHY") status_color="$RED" ;;
            *) status_color="$YELLOW" ;;
        esac
        
        echo -e "${status_color}[$result_status]${NC} $service"
        if [ "$DETAILED" = true ]; then
            echo "  Deployment: $deployment_status"
            echo "  Pods: $pod_status"
            if [ -n "$http_status" ]; then
                echo "  HTTP: $http_status (${response_time}ms)"
            fi
            if [ -n "$error_message" ]; then
                echo "  Error: $error_message"
            fi
        fi
    fi
    
    # Send alert if configured and service is unhealthy
    if [ -n "$ALERT_WEBHOOK" ] && [ "$result_status" = "UNHEALTHY" ]; then
        send_alert "$service" "$error_message"
    fi
    
    return $([ "$result_status" = "HEALTHY" ])
}

# Send alert to webhook
send_alert() {
    local service=$1
    local error_message=$2
    
    local payload=$(cat << EOF
{
  "text": "🚨 NeuroNews Health Alert",
  "attachments": [
    {
      "color": "danger",
      "fields": [
        {
          "title": "Service",
          "value": "$service",
          "short": true
        },
        {
          "title": "Namespace",
          "value": "$NAMESPACE",
          "short": true
        },
        {
          "title": "Error",
          "value": "$error_message",
          "short": false
        },
        {
          "title": "Timestamp",
          "value": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
          "short": true
        }
      ]
    }
  ]
}
EOF
)
    
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$payload" \
        "$ALERT_WEBHOOK" &>/dev/null || true
}

# Export metrics to file
export_metrics() {
    local metrics_file="health-metrics-$(date +%Y%m%d-%H%M%S).json"
    local current_time=$(date +%s)
    local duration=$((current_time - METRICS[start_time]))
    
    cat > "$metrics_file" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "namespace": "$NAMESPACE",
  "duration_seconds": $duration,
  "total_checks": ${METRICS[total_checks]},
  "successful_checks": ${METRICS[successful_checks]},
  "failed_checks": ${METRICS[failed_checks]},
  "success_rate": $(echo "scale=2; ${METRICS[successful_checks]} * 100 / ${METRICS[total_checks]}" | bc -l 2>/dev/null || echo "0")
}
EOF
    
    log_info "Metrics exported to: $metrics_file"
}

# Run single health check cycle
run_health_check() {
    local services
    read -ra services <<< "$(get_services)"
    
    local all_healthy=true
    local results=()
    
    if [ "$JSON_OUTPUT" = true ]; then
        echo "["
    else
        log_info "Checking health of NeuroNews services in namespace: $NAMESPACE"
        echo "$(date)"
        echo "---"
    fi
    
    local first=true
    for service in "${services[@]}"; do
        if [ "$JSON_OUTPUT" = true ]; then
            if [ "$first" = false ]; then
                echo ","
            fi
            first=false
        fi
        
        if ! check_service_health "$service"; then
            all_healthy=false
        fi
    done
    
    if [ "$JSON_OUTPUT" = true ]; then
        echo "]"
    else
        echo "---"
        if [ "$all_healthy" = true ]; then
            log_success "All services are healthy!"
        else
            log_error "Some services are unhealthy!"
        fi
        
        # Show metrics summary
        local success_rate=0
        if [ "${METRICS[total_checks]}" -gt 0 ]; then
            success_rate=$(echo "scale=1; ${METRICS[successful_checks]} * 100 / ${METRICS[total_checks]}" | bc -l 2>/dev/null || echo "0")
        fi
        echo "Health check summary: ${METRICS[successful_checks]}/${METRICS[total_checks]} successful (${success_rate}%)"
    fi
    
    return $([ "$all_healthy" = true ])
}

# Main function
main() {
    check_kubectl
    
    if [ "$CONTINUOUS" = true ]; then
        log_info "Starting continuous health monitoring (interval: ${INTERVAL}s)"
        log_info "Press Ctrl+C to stop"
        
        trap cleanup EXIT INT TERM
        
        while true; do
            run_health_check
            echo
            sleep "$INTERVAL"
        done
    else
        run_health_check
        
        if [ "$EXPORT_METRICS" = true ]; then
            export_metrics
        fi
    fi
}

# Cleanup function
cleanup() {
    if [ "$EXPORT_METRICS" = true ]; then
        export_metrics
    fi
    log_info "Health monitoring stopped"
    exit 0
}

# Run main function
main "$@"
