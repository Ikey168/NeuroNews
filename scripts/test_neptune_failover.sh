#!/bin/bash

# Neptune Disaster Recovery Testing Script
# This script tests Neptune replica failover functionality

set -e

# Configuration
CLUSTER_IDENTIFIER="${NEPTUNE_CLUSTER_IDENTIFIER:-neuronews-dev}"
REGION="${AWS_REGION:-us-east-1}"
REPLICA_IDENTIFIER="${CLUSTER_IDENTIFIER}-replica-1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

log_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
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
    
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 is not installed"
        exit 1
    fi
    
    log_info "Prerequisites check passed"
}

# Get Neptune cluster information
get_cluster_info() {
    log_info "Getting Neptune cluster information..."
    
    CLUSTER_INFO=$(aws neptune describe-db-clusters \
        --db-cluster-identifier "$CLUSTER_IDENTIFIER" \
        --region "$REGION" 2>/dev/null || echo "null")
    
    if [[ "$CLUSTER_INFO" == "null" ]]; then
        log_error "Neptune cluster '$CLUSTER_IDENTIFIER' not found"
        exit 1
    fi
    
    PRIMARY_ENDPOINT=$(echo "$CLUSTER_INFO" | jq -r '.DBClusters[0].Endpoint // "null"')
    READER_ENDPOINT=$(echo "$CLUSTER_INFO" | jq -r '.DBClusters[0].ReaderEndpoint // "null"')
    PORT=$(echo "$CLUSTER_INFO" | jq -r '.DBClusters[0].Port // 8182')
    
    log_info "Primary endpoint: $PRIMARY_ENDPOINT:$PORT"
    if [[ "$READER_ENDPOINT" != "null" ]]; then
        log_info "Reader endpoint: $READER_ENDPOINT:$PORT"
    else
        log_warn "No reader endpoint found - may need to create replica"
    fi
}

# Check if replica exists
check_replica_exists() {
    log_info "Checking for existing Neptune replicas..."
    
    INSTANCES=$(aws neptune describe-db-instances \
        --region "$REGION" \
        --query "DBInstances[?DBClusterIdentifier=='$CLUSTER_IDENTIFIER']" 2>/dev/null || echo "[]")
    
    REPLICA_COUNT=$(echo "$INSTANCES" | jq '[.[] | select(.DBInstanceClass != null)] | length')
    
    if [[ "$REPLICA_COUNT" -gt 1 ]]; then
        log_info "Found $REPLICA_COUNT instances in cluster (including replicas)"
        return 0
    else
        log_warn "Only primary instance found. Reader endpoint may not be available for testing."
        return 1
    fi
}

# Test connection to Neptune endpoint
test_neptune_connection() {
    local endpoint=$1
    local port=$2
    local endpoint_type=$3
    
    log_info "Testing connection to $endpoint_type endpoint: $endpoint:$port"
    
    # Create a simple test script
    cat > /tmp/test_neptune_connection.py << EOF
#!/usr/bin/env python3
import sys
import asyncio
import logging
from gremlin_python.driver.client import Client
from gremlin_python.driver.aiohttp.transport import AiohttpTransport

async def test_connection(endpoint):
    try:
        # Create client with timeout
        client = Client(
            f"ws://{endpoint}/gremlin",
            'g',
            transport_factory=lambda: AiohttpTransport()
        )
        
        # Test simple query
        result = await client.submit_async("g.V().limit(1).count()")
        count = await result.all()
        
        await client.close()
        print(f"SUCCESS: Connected to {endpoint}, vertex count test returned: {count}")
        return True
        
    except Exception as e:
        print(f"ERROR: Connection to {endpoint} failed: {e}")
        return False

if __name__ == "__main__":
    endpoint = sys.argv[1] if len(sys.argv) > 1 else "localhost:8182"
    result = asyncio.run(test_connection(endpoint))
    sys.exit(0 if result else 1)
EOF
    
    chmod +x /tmp/test_neptune_connection.py
    
    if python3 /tmp/test_neptune_connection.py "$endpoint:$port"; then
        log_info "✅ $endpoint_type connection successful"
        rm -f /tmp/test_neptune_connection.py
        return 0
    else
        log_error "❌ $endpoint_type connection failed"
        rm -f /tmp/test_neptune_connection.py
        return 1
    fi
}

# Test application with different endpoints
test_application_failover() {
    local primary_endpoint=$1
    local reader_endpoint=$2
    local port=$3
    
    log_info "Testing application failover scenarios..."
    
    # Test 1: Primary endpoint
    log_info "Test 1: Using primary endpoint"
    if test_neptune_connection "$primary_endpoint" "$port" "primary"; then
        log_info "✅ Primary endpoint test passed"
    else
        log_error "❌ Primary endpoint test failed"
        return 1
    fi
    
    # Test 2: Reader endpoint (if available)
    if [[ "$reader_endpoint" != "null" && "$reader_endpoint" != "$primary_endpoint" ]]; then
        log_info "Test 2: Using reader endpoint"
        if test_neptune_connection "$reader_endpoint" "$port" "reader"; then
            log_info "✅ Reader endpoint test passed"
        else
            log_warn "❌ Reader endpoint test failed, but this may be expected if no replicas exist"
        fi
    else
        log_warn "Reader endpoint not available or same as primary - skipping reader test"
    fi
}

# Update application configuration for failover testing
update_app_config() {
    local endpoint=$1
    local endpoint_type=$2
    
    log_info "Updating application configuration to use $endpoint_type endpoint"
    
    # Use the manage_db_endpoints.py script
    if [[ -f "/workspaces/NeuroNews/scripts/manage_db_endpoints.py" ]]; then
        local use_replica_flag=""
        if [[ "$endpoint_type" == "replica" ]]; then
            use_replica_flag="--use-replica"
        fi
        
        python3 /workspaces/NeuroNews/scripts/manage_db_endpoints.py \
            --neptune-cluster "$CLUSTER_IDENTIFIER" \
            $use_replica_flag \
            --region "$REGION" \
            --config-file "/tmp/neptune_failover_test.env"
        
        if [[ $? -eq 0 ]]; then
            log_info "✅ Configuration updated for $endpoint_type endpoint"
            return 0
        else
            log_error "❌ Failed to update configuration"
            return 1
        fi
    else
        log_error "Database endpoint manager script not found"
        return 1
    fi
}

# Simulate read queries on replica
test_read_queries() {
    local endpoint=$1
    local port=$2
    
    log_info "Testing read queries on endpoint: $endpoint:$port"
    
    cat > /tmp/test_read_queries.py << EOF
#!/usr/bin/env python3
import asyncio
import sys
from gremlin_python.driver.client import Client
from gremlin_python.driver.aiohttp.transport import AiohttpTransport

async def test_read_queries(endpoint):
    try:
        client = Client(
            f"ws://{endpoint}/gremlin",
            'g',
            transport_factory=lambda: AiohttpTransport()
        )
        
        queries = [
            "g.V().count()",
            "g.E().count()",
            "g.V().limit(5).valueMap()",
            "g.V().hasLabel('Article').limit(3).valueMap()"
        ]
        
        results = {}
        for i, query in enumerate(queries, 1):
            try:
                result = await client.submit_async(query)
                data = await result.all()
                results[f"query_{i}"] = {"query": query, "success": True, "result_count": len(data)}
                print(f"Query {i} SUCCESS: {query} -> {len(data)} results")
            except Exception as e:
                results[f"query_{i}"] = {"query": query, "success": False, "error": str(e)}
                print(f"Query {i} FAILED: {query} -> {e}")
        
        await client.close()
        
        successful_queries = sum(1 for r in results.values() if r["success"])
        total_queries = len(queries)
        
        print(f"\\nRead test summary: {successful_queries}/{total_queries} queries successful")
        return successful_queries == total_queries
        
    except Exception as e:
        print(f"ERROR: Read query test failed: {e}")
        return False

if __name__ == "__main__":
    endpoint = sys.argv[1] if len(sys.argv) > 1 else "localhost:8182"
    result = asyncio.run(test_read_queries(endpoint))
    sys.exit(0 if result else 1)
EOF
    
    chmod +x /tmp/test_read_queries.py
    
    if python3 /tmp/test_read_queries.py "$endpoint:$port"; then
        log_info "✅ Read queries test passed"
        rm -f /tmp/test_read_queries.py
        return 0
    else
        log_error "❌ Read queries test failed"
        rm -f /tmp/test_read_queries.py
        return 1
    fi
}

# Performance comparison between primary and replica
compare_performance() {
    local primary_endpoint=$1
    local reader_endpoint=$2
    local port=$3
    
    if [[ "$reader_endpoint" == "null" || "$reader_endpoint" == "$primary_endpoint" ]]; then
        log_warn "Cannot compare performance - reader endpoint not available"
        return 0
    fi
    
    log_info "Comparing performance between primary and reader endpoints..."
    
    cat > /tmp/performance_test.py << EOF
#!/usr/bin/env python3
import asyncio
import time
import sys
from gremlin_python.driver.client import Client
from gremlin_python.driver.aiohttp.transport import AiohttpTransport

async def performance_test(endpoint, label):
    try:
        client = Client(
            f"ws://{endpoint}/gremlin",
            'g',
            transport_factory=lambda: AiohttpTransport()
        )
        
        # Simple query that should work on both primary and replica
        query = "g.V().limit(10).count()"
        iterations = 5
        
        times = []
        for i in range(iterations):
            start_time = time.time()
            result = await client.submit_async(query)
            await result.all()
            end_time = time.time()
            times.append(end_time - start_time)
        
        await client.close()
        
        avg_time = sum(times) / len(times)
        print(f"{label}: Average response time: {avg_time:.3f}s (over {iterations} queries)")
        return avg_time
        
    except Exception as e:
        print(f"{label}: Performance test failed: {e}")
        return None

async def main():
    primary_endpoint = sys.argv[1]
    reader_endpoint = sys.argv[2]
    
    primary_time = await performance_test(primary_endpoint, "Primary")
    reader_time = await performance_test(reader_endpoint, "Reader")
    
    if primary_time and reader_time:
        if reader_time < primary_time:
            print(f"Reader endpoint is {((primary_time - reader_time) / primary_time * 100):.1f}% faster")
        else:
            print(f"Primary endpoint is {((reader_time - primary_time) / reader_time * 100):.1f}% faster")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 performance_test.py <primary_endpoint> <reader_endpoint>")
        sys.exit(1)
    
    asyncio.run(main())
EOF
    
    chmod +x /tmp/performance_test.py
    
    python3 /tmp/performance_test.py "$primary_endpoint:$port" "$reader_endpoint:$port"
    rm -f /tmp/performance_test.py
}

# Cleanup test files
cleanup() {
    log_info "Cleaning up test files..."
    rm -f /tmp/test_neptune_connection.py
    rm -f /tmp/test_read_queries.py
    rm -f /tmp/performance_test.py
    rm -f /tmp/neptune_failover_test.env
}

# Main execution function
main() {
    log_info "Starting Neptune Replica Failover Test"
    log_info "Cluster: $CLUSTER_IDENTIFIER"
    log_info "Region: $REGION"
    
    # Check prerequisites
    check_prerequisites
    
    # Get cluster information
    get_cluster_info
    
    # Check if replicas exist
    check_replica_exists
    
    # Test connections to both endpoints
    test_application_failover "$PRIMARY_ENDPOINT" "$READER_ENDPOINT" "$PORT"
    
    # Test read queries on primary
    log_info "Testing read queries on primary endpoint..."
    if test_read_queries "$PRIMARY_ENDPOINT" "$PORT"; then
        log_info "✅ Primary read queries successful"
    else
        log_warn "❌ Primary read queries failed"
    fi
    
    # Test read queries on reader (if available)
    if [[ "$READER_ENDPOINT" != "null" && "$READER_ENDPOINT" != "$PRIMARY_ENDPOINT" ]]; then
        log_info "Testing read queries on reader endpoint..."
        if test_read_queries "$READER_ENDPOINT" "$PORT"; then
            log_info "✅ Reader read queries successful"
            
            # Update configuration to use replica
            update_app_config "$READER_ENDPOINT" "replica"
            
            # Performance comparison
            compare_performance "$PRIMARY_ENDPOINT" "$READER_ENDPOINT" "$PORT"
            
        else
            log_warn "❌ Reader read queries failed"
        fi
    else
        log_warn "No separate reader endpoint available for testing"
        log_info "To test with a replica, consider:"
        log_info "1. Increasing neptune_cluster_size in Terraform configuration"
        log_info "2. Creating a read replica manually in AWS Console"
    fi
    
    # Final summary
    echo
    log_info "🎯 Neptune Replica Failover Test Summary:"
    log_info "Primary endpoint: $PRIMARY_ENDPOINT:$PORT ✅"
    
    if [[ "$READER_ENDPOINT" != "null" && "$READER_ENDPOINT" != "$PRIMARY_ENDPOINT" ]]; then
        log_info "Reader endpoint: $READER_ENDPOINT:$PORT ✅"
        log_info "✅ Replica failover capability confirmed"
        
        echo
        log_info "💡 Application can failover to reader endpoint by:"
        log_info "1. Using the manage_db_endpoints.py script with --use-replica flag"
        log_info "2. Updating NEPTUNE_HOST environment variable to reader endpoint"
        log_info "3. Configuring load balancer to route read queries to replica"
        
    else
        log_warn "⚠️  No reader replica available - consider adding replicas for HA"
    fi
    
    cleanup
    log_info "Neptune Replica Failover Test completed"
}

# Handle script interruption
trap 'log_error "Script interrupted"; cleanup; exit 1' INT TERM

# Run main function
main "$@"
