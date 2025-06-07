#!/bin/bash

# Redshift Disaster Recovery Testing Script
# This script simulates Redshift failure and tests snapshot restore functionality

set -e

# Configuration
CLUSTER_IDENTIFIER="${REDSHIFT_CLUSTER_IDENTIFIER:-news-cluster-dev}"
REGION="${AWS_REGION:-us-east-1}"
TEST_CLUSTER_IDENTIFIER="${CLUSTER_IDENTIFIER}-dr-test"
BACKUP_CLUSTER_IDENTIFIER="${CLUSTER_IDENTIFIER}-backup"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed"
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Get the latest snapshot
get_latest_snapshot() {
    log_info "Getting latest snapshot for cluster: $CLUSTER_IDENTIFIER"
    
    SNAPSHOT_ID=$(aws redshift describe-cluster-snapshots \
        --cluster-identifier "$CLUSTER_IDENTIFIER" \
        --snapshot-type automated \
        --region "$REGION" \
        --query 'Snapshots | sort_by(@, &SnapshotCreateTime) | [-1].SnapshotIdentifier' \
        --output text)
    
    if [[ "$SNAPSHOT_ID" == "None" || -z "$SNAPSHOT_ID" ]]; then
        log_error "No automated snapshots found for cluster $CLUSTER_IDENTIFIER"
        exit 1
    fi
    
    log_info "Latest snapshot found: $SNAPSHOT_ID"
    echo "$SNAPSHOT_ID"
}

# Simulate failure by modifying security group
simulate_failure() {
    log_warn "Simulating Redshift failure by blocking access..."
    
    # Get security group ID for the cluster
    SG_ID=$(aws redshift describe-clusters \
        --cluster-identifier "$CLUSTER_IDENTIFIER" \
        --region "$REGION" \
        --query 'Clusters[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
        --output text)
    
    if [[ "$SG_ID" != "None" && -n "$SG_ID" ]]; then
        # Backup current security group rules
        aws ec2 describe-security-groups \
            --group-ids "$SG_ID" \
            --region "$REGION" > "/tmp/sg_backup_${SG_ID}.json"
        
        # Remove inbound rules to simulate failure
        aws ec2 revoke-security-group-ingress \
            --group-id "$SG_ID" \
            --protocol tcp \
            --port 5439 \
            --cidr 0.0.0.0/0 \
            --region "$REGION" 2>/dev/null || true
        
        log_warn "Access to Redshift cluster blocked (simulated failure)"
        echo "$SG_ID"
    else
        log_error "Could not find security group for cluster"
        exit 1
    fi
}

# Test connection failure
test_connection_failure() {
    log_info "Testing connection failure..."
    
    # Try to connect using psql (this should fail)
    REDSHIFT_HOST=$(aws redshift describe-clusters \
        --cluster-identifier "$CLUSTER_IDENTIFIER" \
        --region "$REGION" \
        --query 'Clusters[0].Endpoint.Address' \
        --output text)
    
    if timeout 10 nc -z "$REDSHIFT_HOST" 5439 2>/dev/null; then
        log_error "Connection should have failed but didn't"
        return 1
    else
        log_info "Connection failure confirmed - disaster simulation successful"
        return 0
    fi
}

# Restore from snapshot
restore_from_snapshot() {
    local snapshot_id=$1
    
    log_info "Restoring cluster from snapshot: $snapshot_id"
    
    # Check if test cluster already exists and delete it
    if aws redshift describe-clusters --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" --region "$REGION" &>/dev/null; then
        log_warn "Test cluster $TEST_CLUSTER_IDENTIFIER already exists, deleting..."
        aws redshift delete-cluster \
            --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
            --skip-final-snapshot \
            --region "$REGION"
        
        # Wait for deletion
        log_info "Waiting for cluster deletion..."
        aws redshift wait cluster-deleted \
            --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
            --region "$REGION"
    fi
    
    # Restore from snapshot
    aws redshift restore-from-cluster-snapshot \
        --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
        --snapshot-identifier "$snapshot_id" \
        --region "$REGION"
    
    log_info "Restore initiated. Waiting for cluster to become available..."
    
    # Wait for cluster to be available
    aws redshift wait cluster-available \
        --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
        --region "$REGION"
    
    log_info "Cluster restore completed successfully"
}

# Test restored cluster
test_restored_cluster() {
    log_info "Testing restored cluster connectivity..."
    
    RESTORED_HOST=$(aws redshift describe-clusters \
        --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
        --region "$REGION" \
        --query 'Clusters[0].Endpoint.Address' \
        --output text)
    
    log_info "Restored cluster endpoint: $RESTORED_HOST"
    
    # Test connection (basic connectivity test)
    if timeout 10 nc -z "$RESTORED_HOST" 5439; then
        log_info "✅ Restored cluster is accessible"
        return 0
    else
        log_error "❌ Cannot connect to restored cluster"
        return 1
    fi
}

# Restore original access
restore_access() {
    local sg_id=$1
    
    log_info "Restoring original access to primary cluster..."
    
    if [[ -f "/tmp/sg_backup_${sg_id}.json" ]]; then
        # Restore security group rules
        aws ec2 authorize-security-group-ingress \
            --group-id "$sg_id" \
            --protocol tcp \
            --port 5439 \
            --cidr 0.0.0.0/0 \
            --region "$REGION" 2>/dev/null || true
        
        log_info "Access restored to primary cluster"
        rm -f "/tmp/sg_backup_${sg_id}.json"
    fi
}

# Cleanup test resources
cleanup() {
    log_info "Cleaning up test resources..."
    
    # Delete test cluster
    if aws redshift describe-clusters --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" --region "$REGION" &>/dev/null; then
        aws redshift delete-cluster \
            --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
            --skip-final-snapshot \
            --region "$REGION"
        
        log_info "Test cluster deletion initiated"
    fi
}

# Main execution function
main() {
    log_info "Starting Redshift Disaster Recovery Test"
    log_info "Cluster: $CLUSTER_IDENTIFIER"
    log_info "Region: $REGION"
    
    # Check prerequisites
    check_prerequisites
    
    # Get latest snapshot
    SNAPSHOT_ID=$(get_latest_snapshot)
    
    # Simulate failure
    SG_ID=$(simulate_failure)
    
    # Test that failure occurred
    if ! test_connection_failure; then
        log_error "Failure simulation did not work properly"
        restore_access "$SG_ID"
        exit 1
    fi
    
    # Restore from snapshot
    restore_from_snapshot "$SNAPSHOT_ID"
    
    # Test restored cluster
    if test_restored_cluster; then
        log_info "✅ Disaster Recovery Test PASSED"
        echo "Restored cluster endpoint: $(aws redshift describe-clusters \
            --cluster-identifier "$TEST_CLUSTER_IDENTIFIER" \
            --region "$REGION" \
            --query 'Clusters[0].Endpoint.Address' \
            --output text)"
    else
        log_error "❌ Disaster Recovery Test FAILED"
        exit 1
    fi
    
    # Restore original access
    restore_access "$SG_ID"
    
    # Ask user if they want to cleanup
    echo
    read -p "Do you want to cleanup the test cluster? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cleanup
    else
        log_info "Test cluster $TEST_CLUSTER_IDENTIFIER left running for further testing"
    fi
    
    log_info "Redshift Disaster Recovery Test completed"
}

# Handle script interruption
trap 'log_error "Script interrupted"; cleanup; exit 1' INT TERM

# Run main function
main "$@"
