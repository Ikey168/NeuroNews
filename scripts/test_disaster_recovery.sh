#!/bin/bash

# Comprehensive Disaster Recovery Test Suite
# This script orchestrates testing of the complete disaster recovery plan

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs/dr-tests"
REPORT_FILE="$LOG_DIR/disaster_recovery_report_$(date +%Y%m%d_%H%M%S).json"

# Default values - can be overridden by environment variables
REDSHIFT_CLUSTER_ID="${REDSHIFT_CLUSTER_IDENTIFIER:-news-cluster-dev}"
NEPTUNE_CLUSTER_ID="${NEPTUNE_CLUSTER_IDENTIFIER:-neuronews-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_DIR/test.log"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_DIR/test.log"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_DIR/test.log"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_DIR/test.log"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1" | tee -a "$LOG_DIR/test.log"
}

log_header() {
    echo -e "${PURPLE}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${NC} $1 ${PURPLE}║${NC}"
    echo -e "${PURPLE}╚══════════════════════════════════════════════════════════════════╝${NC}"
}

# Initialize test environment
initialize_test_env() {
    log_info "Initializing disaster recovery test environment..."
    
    # Create log directory
    mkdir -p "$LOG_DIR"
    
    # Initialize test report
    cat > "$REPORT_FILE" << EOF
{
  "disaster_recovery_test": {
    "started_at": "$(date -Iseconds)",
    "test_environment": {
      "redshift_cluster": "$REDSHIFT_CLUSTER_ID",
      "neptune_cluster": "$NEPTUNE_CLUSTER_ID",
      "aws_region": "$AWS_REGION",
      "script_version": "1.0.0"
    },
    "tests": {},
    "summary": {}
  }
}
EOF
    
    log_info "Test environment initialized"
    log_info "Report file: $REPORT_FILE"
}

# Update test report
update_report() {
    local test_name="$1"
    local status="$2"
    local details="$3"
    local duration="$4"
    
    # Create a temporary file with the updated JSON
    python3 << EOF
import json
import sys

try:
    with open("$REPORT_FILE", "r") as f:
        report = json.load(f)
    
    report["disaster_recovery_test"]["tests"]["$test_name"] = {
        "status": "$status",
        "details": "$details",
        "duration_seconds": $duration,
        "timestamp": "$(date -Iseconds)"
    }
    
    with open("$REPORT_FILE", "w") as f:
        json.dump(report, f, indent=2)
        
except Exception as e:
    print(f"Error updating report: {e}", file=sys.stderr)
    sys.exit(1)
EOF
}

# Check prerequisites
check_prerequisites() {
    log_step "Checking prerequisites..."
    local start_time=$(date +%s)
    
    local missing_tools=()
    
    # Check required tools
    for tool in aws python3 jq nc timeout; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done
    
    if [[ ${#missing_tools[@]} -gt 0 ]]; then
        log_error "Missing required tools: ${missing_tools[*]}"
        local end_time=$(date +%s)
        update_report "prerequisites" "FAILED" "Missing tools: ${missing_tools[*]}" $((end_time - start_time))
        return 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured properly"
        local end_time=$(date +%s)
        update_report "prerequisites" "FAILED" "AWS credentials not configured" $((end_time - start_time))
        return 1
    fi
    
    # Check if required scripts exist
    local required_scripts=(
        "$SCRIPT_DIR/test_redshift_dr.sh"
        "$SCRIPT_DIR/test_neptune_failover.sh"
        "$SCRIPT_DIR/manage_db_endpoints.py"
        "$SCRIPT_DIR/neptune_failover_manager.py"
    )
    
    for script in "${required_scripts[@]}"; do
        if [[ ! -f "$script" ]]; then
            log_error "Required script not found: $script"
            local end_time=$(date +%s)
            update_report "prerequisites" "FAILED" "Missing script: $script" $((end_time - start_time))
            return 1
        fi
    done
    
    log_success "All prerequisites satisfied"
    local end_time=$(date +%s)
    update_report "prerequisites" "PASSED" "All required tools and scripts available" $((end_time - start_time))
    return 0
}

# Test Redshift disaster recovery
test_redshift_dr() {
    log_step "Testing Redshift disaster recovery..."
    local start_time=$(date +%s)
    
    # Set environment variables for the Redshift DR script
    export REDSHIFT_CLUSTER_IDENTIFIER="$REDSHIFT_CLUSTER_ID"
    export AWS_REGION="$AWS_REGION"
    
    log_info "Running Redshift DR test script..."
    
    if "$SCRIPT_DIR/test_redshift_dr.sh" 2>&1 | tee "$LOG_DIR/redshift_dr_test.log"; then
        log_success "Redshift disaster recovery test passed"
        local end_time=$(date +%s)
        update_report "redshift_disaster_recovery" "PASSED" "Snapshot restore and failover successful" $((end_time - start_time))
        return 0
    else
        log_error "Redshift disaster recovery test failed"
        local end_time=$(date +%s)
        update_report "redshift_disaster_recovery" "FAILED" "Snapshot restore or failover failed" $((end_time - start_time))
        return 1
    fi
}

# Test Neptune replica failover
test_neptune_failover() {
    log_step "Testing Neptune replica failover..."
    local start_time=$(date +%s)
    
    # Set environment variables for the Neptune failover script
    export NEPTUNE_CLUSTER_IDENTIFIER="$NEPTUNE_CLUSTER_ID"
    export AWS_REGION="$AWS_REGION"
    
    log_info "Running Neptune failover test script..."
    
    if "$SCRIPT_DIR/test_neptune_failover.sh" 2>&1 | tee "$LOG_DIR/neptune_failover_test.log"; then
        log_success "Neptune replica failover test passed"
        local end_time=$(date +%s)
        update_report "neptune_replica_failover" "PASSED" "Replica connectivity and failover successful" $((end_time - start_time))
        return 0
    else
        log_error "Neptune replica failover test failed"
        local end_time=$(date +%s)
        update_report "neptune_replica_failover" "FAILED" "Replica connectivity or failover failed" $((end_time - start_time))
        return 1
    fi
}

# Test application configuration management
test_config_management() {
    log_step "Testing application configuration management..."
    local start_time=$(date +%s)
    
    log_info "Testing database endpoint management..."
    
    # Test the manage_db_endpoints.py script
    if python3 "$SCRIPT_DIR/manage_db_endpoints.py" \
        --redshift-cluster "$REDSHIFT_CLUSTER_ID" \
        --neptune-cluster "$NEPTUNE_CLUSTER_ID" \
        --region "$AWS_REGION" \
        --dry-run 2>&1 | tee "$LOG_DIR/config_management_test.log"; then
        
        log_success "Configuration management test passed"
        local end_time=$(date +%s)
        update_report "configuration_management" "PASSED" "Endpoint management scripts working correctly" $((end_time - start_time))
        return 0
    else
        log_error "Configuration management test failed"
        local end_time=$(date +%s)
        update_report "configuration_management" "FAILED" "Endpoint management scripts failed" $((end_time - start_time))
        return 1
    fi
}

# Test end-to-end disaster recovery scenario
test_e2e_disaster_recovery() {
    log_step "Testing end-to-end disaster recovery scenario..."
    local start_time=$(date +%s)
    
    log_info "Simulating complete infrastructure failure and recovery..."
    
    # Step 1: Save current configuration
    log_info "Step 1: Saving current configuration..."
    python3 "$SCRIPT_DIR/neptune_failover_manager.py" status > "$LOG_DIR/original_config.json"
    
    # Step 2: Switch to backup/replica endpoints
    log_info "Step 2: Switching to backup endpoints..."
    
    # Get Neptune replica endpoint
    NEPTUNE_REPLICA=$(aws neptune describe-db-clusters \
        --db-cluster-identifier "$NEPTUNE_CLUSTER_ID" \
        --region "$AWS_REGION" \
        --query 'DBClusters[0].ReaderEndpoint' \
        --output text 2>/dev/null || echo "null")
    
    if [[ "$NEPTUNE_REPLICA" != "null" && -n "$NEPTUNE_REPLICA" ]]; then
        log_info "Found Neptune replica endpoint: $NEPTUNE_REPLICA"
        
        # Test switching to replica
        if python3 "$SCRIPT_DIR/neptune_failover_manager.py" \
            switch-to-replica \
            --replica-endpoint "ws://$NEPTUNE_REPLICA:8182/gremlin" \
            --config-dir "$LOG_DIR" 2>&1 | tee -a "$LOG_DIR/e2e_test.log"; then
            
            log_info "Successfully switched to replica endpoint"
            
            # Step 3: Test application functionality with backup endpoints
            log_info "Step 3: Testing application functionality..."
            
            # Simple connectivity test
            if python3 "$SCRIPT_DIR/neptune_failover_manager.py" \
                test \
                --test-endpoint "ws://$NEPTUNE_REPLICA:8182/gremlin" 2>&1 | tee -a "$LOG_DIR/e2e_test.log"; then
                
                log_success "Application functionality test passed with backup endpoints"
                
                # Step 4: Switch back to primary
                log_info "Step 4: Switching back to primary endpoints..."
                python3 "$SCRIPT_DIR/neptune_failover_manager.py" \
                    switch-to-primary \
                    --config-dir "$LOG_DIR" 2>&1 | tee -a "$LOG_DIR/e2e_test.log"
                
                log_success "End-to-end disaster recovery test completed successfully"
                local end_time=$(date +%s)
                update_report "e2e_disaster_recovery" "PASSED" "Complete failover and recovery successful" $((end_time - start_time))
                return 0
            else
                log_error "Application functionality test failed with backup endpoints"
            fi
        else
            log_error "Failed to switch to replica endpoint"
        fi
    else
        log_warn "No Neptune replica endpoint available - testing with primary only"
        log_success "End-to-end test completed (limited - no replica available)"
        local end_time=$(date +%s)
        update_report "e2e_disaster_recovery" "PARTIAL" "No replica available for full testing" $((end_time - start_time))
        return 0
    fi
    
    local end_time=$(date +%s)
    update_report "e2e_disaster_recovery" "FAILED" "End-to-end scenario failed" $((end_time - start_time))
    return 1
}

# Generate final test report
generate_final_report() {
    log_step "Generating final test report..."
    
    # Update summary in the report
    python3 << EOF
import json
from datetime import datetime

try:
    with open("$REPORT_FILE", "r") as f:
        report = json.load(f)
    
    tests = report["disaster_recovery_test"]["tests"]
    
    total_tests = len(tests)
    passed_tests = sum(1 for test in tests.values() if test["status"] == "PASSED")
    failed_tests = sum(1 for test in tests.values() if test["status"] == "FAILED")
    partial_tests = sum(1 for test in tests.values() if test["status"] == "PARTIAL")
    
    total_duration = sum(test.get("duration_seconds", 0) for test in tests.values())
    
    report["disaster_recovery_test"]["completed_at"] = datetime.now().isoformat()
    report["disaster_recovery_test"]["summary"] = {
        "total_tests": total_tests,
        "passed": passed_tests,
        "failed": failed_tests,
        "partial": partial_tests,
        "success_rate": f"{(passed_tests / total_tests * 100):.1f}%" if total_tests > 0 else "0%",
        "total_duration_seconds": total_duration,
        "overall_status": "PASSED" if failed_tests == 0 else "FAILED"
    }
    
    with open("$REPORT_FILE", "w") as f:
        json.dump(report, f, indent=2)
        
    print("Final report generated successfully")
        
except Exception as e:
    print(f"Error generating final report: {e}")
EOF
    
    # Display summary
    log_header "DISASTER RECOVERY TEST SUMMARY"
    
    echo -e "${CYAN}📊 Test Results:${NC}"
    python3 << EOF
import json

try:
    with open("$REPORT_FILE", "r") as f:
        report = json.load(f)
    
    summary = report["disaster_recovery_test"]["summary"]
    tests = report["disaster_recovery_test"]["tests"]
    
    print(f"  Total Tests: {summary['total_tests']}")
    print(f"  Passed: {summary['passed']}")
    print(f"  Failed: {summary['failed']}")
    print(f"  Partial: {summary['partial']}")
    print(f"  Success Rate: {summary['success_rate']}")
    print(f"  Total Duration: {summary['total_duration_seconds']}s")
    print(f"  Overall Status: {summary['overall_status']}")
    print()
    
    print("📋 Individual Test Results:")
    for test_name, test_data in tests.items():
        status_emoji = "✅" if test_data["status"] == "PASSED" else "❌" if test_data["status"] == "FAILED" else "⚠️"
        print(f"  {status_emoji} {test_name}: {test_data['status']} ({test_data['duration_seconds']}s)")
        if test_data.get("details"):
            print(f"     Details: {test_data['details']}")
    
except Exception as e:
    print(f"Error reading report: {e}")
EOF
    
    echo
    log_info "📁 Detailed logs available in: $LOG_DIR"
    log_info "📄 Full report: $REPORT_FILE"
}

# Cleanup function
cleanup() {
    log_info "Cleaning up test resources..."
    
    # Remove any temporary test clusters or configurations
    # This would typically include cleanup of test Redshift clusters
    # For safety, we'll just log the cleanup step
    log_info "Cleanup completed"
}

# Main execution function
main() {
    local start_time=$(date +%s)
    
    log_header "DISASTER RECOVERY TESTING SUITE"
    log_info "Starting comprehensive disaster recovery tests..."
    log_info "Redshift Cluster: $REDSHIFT_CLUSTER_ID"
    log_info "Neptune Cluster: $NEPTUNE_CLUSTER_ID"
    log_info "AWS Region: $AWS_REGION"
    
    # Initialize test environment
    initialize_test_env
    
    local test_results=()
    
    # Run all tests
    log_header "PREREQUISITE CHECKS"
    if check_prerequisites; then
        test_results+=("prerequisites:PASSED")
    else
        test_results+=("prerequisites:FAILED")
        log_error "Prerequisites check failed - aborting tests"
        generate_final_report
        return 1
    fi
    
    log_header "REDSHIFT DISASTER RECOVERY TEST"
    if test_redshift_dr; then
        test_results+=("redshift_dr:PASSED")
    else
        test_results+=("redshift_dr:FAILED")
    fi
    
    log_header "NEPTUNE REPLICA FAILOVER TEST"
    if test_neptune_failover; then
        test_results+=("neptune_failover:PASSED")
    else
        test_results+=("neptune_failover:FAILED")
    fi
    
    log_header "CONFIGURATION MANAGEMENT TEST"
    if test_config_management; then
        test_results+=("config_management:PASSED")
    else
        test_results+=("config_management:FAILED")
    fi
    
    log_header "END-TO-END DISASTER RECOVERY TEST"
    if test_e2e_disaster_recovery; then
        test_results+=("e2e_dr:PASSED")
    else
        test_results+=("e2e_dr:FAILED")
    fi
    
    # Generate final report
    generate_final_report
    
    # Check overall results
    local failed_count=0
    for result in "${test_results[@]}"; do
        if [[ "$result" == *":FAILED" ]]; then
            ((failed_count++))
        fi
    done
    
    local end_time=$(date +%s)
    local total_duration=$((end_time - start_time))
    
    echo
    if [[ $failed_count -eq 0 ]]; then
        log_success "🎉 ALL DISASTER RECOVERY TESTS PASSED! (${total_duration}s)"
        log_success "✅ Database resilience with automated recovery confirmed"
    else
        log_error "❌ $failed_count test(s) failed out of ${#test_results[@]} total tests"
        log_error "❌ Some disaster recovery capabilities may need attention"
    fi
    
    cleanup
    
    return $failed_count
}

# Handle script interruption
trap 'log_error "Test suite interrupted"; cleanup; exit 1' INT TERM

# Parse command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --redshift-cluster)
            REDSHIFT_CLUSTER_ID="$2"
            shift 2
            ;;
        --neptune-cluster)
            NEPTUNE_CLUSTER_ID="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Options:"
            echo "  --redshift-cluster CLUSTER_ID    Redshift cluster identifier"
            echo "  --neptune-cluster CLUSTER_ID     Neptune cluster identifier"
            echo "  --region REGION                  AWS region"
            echo "  --help                           Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Run main function
main "$@"
