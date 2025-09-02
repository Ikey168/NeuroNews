#!/bin/bash
# Test script for Spark Iceberg setup (Issue #287)
# Validates that Spark can connect to Iceberg REST catalog and query namespaces

set -e

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

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SPARK_CONF_DIR="$SCRIPT_DIR/conf"

# Check if Spark is installed
check_spark_installation() {
    log_step "Checking Spark installation..."
    
    if ! command -v spark-sql &> /dev/null; then
        log_error "spark-sql command not found"
        log_info "Please install Apache Spark and ensure it's in your PATH"
        log_info "Download from: https://spark.apache.org/downloads.html"
        return 1
    fi
    
    local spark_version=$(spark-sql --version 2>&1 | head -1 || echo "Unknown")
    log_info "Found Spark: $spark_version"
    return 0
}

# Check if required services are running
check_services() {
    log_step "Checking required services..."
    
    # Check Iceberg REST catalog
    log_info "Checking Iceberg REST catalog..."
    if ! curl -s -f http://iceberg-rest:8181/v1/config >/dev/null 2>&1; then
        if ! curl -s -f http://localhost:8181/v1/config >/dev/null 2>&1; then
            log_warn "Iceberg REST catalog not accessible at iceberg-rest:8181 or localhost:8181"
            log_info "Please start the Iceberg REST service"
            return 1
        else
            log_info "Iceberg REST catalog accessible at localhost:8181"
        fi
    else
        log_info "Iceberg REST catalog accessible at iceberg-rest:8181"
    fi
    
    # Check MinIO
    log_info "Checking MinIO S3 service..."
    if ! curl -s -f http://minio:9000/minio/health/live >/dev/null 2>&1; then
        if ! curl -s -f http://localhost:9000/minio/health/live >/dev/null 2>&1; then
            log_warn "MinIO not accessible at minio:9000 or localhost:9000"
            log_info "Please start MinIO service"
            return 1
        else
            log_info "MinIO accessible at localhost:9000"
        fi
    else
        log_info "MinIO accessible at minio:9000"
    fi
    
    return 0
}

# Verify Spark configuration
check_spark_config() {
    log_step "Verifying Spark configuration..."
    
    if [[ ! -f "$SPARK_CONF_DIR/spark-defaults.conf" ]]; then
        log_error "spark-defaults.conf not found at $SPARK_CONF_DIR/spark-defaults.conf"
        return 1
    fi
    
    log_info "Configuration file found: $SPARK_CONF_DIR/spark-defaults.conf"
    
    # Check key configurations
    local config_file="$SPARK_CONF_DIR/spark-defaults.conf"
    
    if grep -q "spark.sql.extensions.*IcebergSparkSessionExtensions" "$config_file"; then
        log_info "✓ Iceberg extensions configured"
    else
        log_warn "✗ Iceberg extensions not found in configuration"
    fi
    
    if grep -q "spark.sql.catalog.demo.*SparkCatalog" "$config_file"; then
        log_info "✓ Demo catalog configured"
    else
        log_warn "✗ Demo catalog not found in configuration"
    fi
    
    if grep -q "fs.s3a.endpoint" "$config_file"; then
        log_info "✓ S3A endpoint configured"
    else
        log_warn "✗ S3A endpoint not found in configuration"
    fi
    
    return 0
}

# Test basic Spark functionality
test_spark_basic() {
    log_step "Testing basic Spark functionality..."
    
    local test_output
    test_output=$(spark-sql -e "SELECT 1 as test" 2>&1)
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        log_info "✓ Basic Spark SQL test passed"
        return 0
    else
        log_error "✗ Basic Spark SQL test failed"
        echo "$test_output"
        return 1
    fi
}

# Test Iceberg catalog connection (DoD requirement)
test_iceberg_catalog() {
    log_step "Testing Iceberg catalog connection (DoD requirement)..."
    
    log_info "Running: spark-sql -e \"SHOW NAMESPACES IN demo\""
    
    # Set SPARK_CONF_DIR to use our configuration
    export SPARK_CONF_DIR="$SPARK_CONF_DIR"
    
    local test_output
    local exit_code
    
    # Run the DoD command
    test_output=$(spark-sql -e "SHOW NAMESPACES IN demo" 2>&1)
    exit_code=$?
    
    echo "Output:"
    echo "$test_output"
    
    if [[ $exit_code -eq 0 ]]; then
        log_info "✓ DoD requirement satisfied: SHOW NAMESPACES IN demo returned results"
        
        # Check if output contains actual namespaces
        if echo "$test_output" | grep -q "namespace"; then
            log_info "✓ Namespaces found in demo catalog"
        else
            log_warn "Command succeeded but no namespaces found (this may be expected for a new setup)"
        fi
        
        return 0
    else
        log_error "✗ DoD requirement failed: SHOW NAMESPACES IN demo command failed"
        return 1
    fi
}

# Create test namespace and table
test_iceberg_operations() {
    log_step "Testing Iceberg table operations..."
    
    export SPARK_CONF_DIR="$SPARK_CONF_DIR"
    
    log_info "Creating test namespace..."
    local create_output
    create_output=$(spark-sql -e "CREATE NAMESPACE IF NOT EXISTS demo.test" 2>&1)
    local exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        log_info "✓ Test namespace created successfully"
    else
        log_warn "✗ Failed to create test namespace"
        echo "$create_output"
    fi
    
    log_info "Listing namespaces again..."
    local list_output
    list_output=$(spark-sql -e "SHOW NAMESPACES IN demo" 2>&1)
    echo "$list_output"
    
    log_info "Creating test table..."
    local table_sql="CREATE TABLE IF NOT EXISTS demo.test.spark_iceberg_test (
        id BIGINT,
        message STRING,
        created_at TIMESTAMP
    ) USING ICEBERG"
    
    local table_output
    table_output=$(spark-sql -e "$table_sql" 2>&1)
    exit_code=$?
    
    if [[ $exit_code -eq 0 ]]; then
        log_info "✓ Test table created successfully"
        
        # Insert test data
        log_info "Inserting test data..."
        local insert_sql="INSERT INTO demo.test.spark_iceberg_test VALUES 
            (1, 'Spark Iceberg setup test', current_timestamp())"
        
        local insert_output
        insert_output=$(spark-sql -e "$insert_sql" 2>&1)
        exit_code=$?
        
        if [[ $exit_code -eq 0 ]]; then
            log_info "✓ Test data inserted successfully"
            
            # Query test data
            log_info "Querying test data..."
            local query_output
            query_output=$(spark-sql -e "SELECT * FROM demo.test.spark_iceberg_test" 2>&1)
            echo "$query_output"
            
            log_info "✓ Iceberg table operations test completed successfully"
        else
            log_warn "✗ Failed to insert test data"
            echo "$insert_output"
        fi
    else
        log_warn "✗ Failed to create test table"
        echo "$table_output"
    fi
}

# Cleanup test resources
cleanup_tests() {
    log_step "Cleaning up test resources..."
    
    export SPARK_CONF_DIR="$SPARK_CONF_DIR"
    
    log_info "Dropping test table..."
    spark-sql -e "DROP TABLE IF EXISTS demo.test.spark_iceberg_test" 2>/dev/null || true
    
    log_info "Dropping test namespace..."
    spark-sql -e "DROP NAMESPACE IF EXISTS demo.test" 2>/dev/null || true
    
    log_info "✓ Cleanup completed"
}

# Display setup summary
show_summary() {
    echo ""
    echo "=============================================="
    echo "Spark Iceberg Setup Test Summary"
    echo "=============================================="
    echo ""
    echo "Configuration:"
    echo "- Spark config: $SPARK_CONF_DIR/spark-defaults.conf"
    echo "- Iceberg REST: http://iceberg-rest:8181"
    echo "- MinIO S3: http://minio:9000"
    echo ""
    echo "Key commands for development:"
    echo "- Start Spark SQL: spark-sql"
    echo "- List namespaces: spark-sql -e \"SHOW NAMESPACES IN demo\""
    echo "- Create namespace: spark-sql -e \"CREATE NAMESPACE demo.myns\""
    echo ""
    echo "Documentation: $PROJECT_ROOT/spark/README.md"
    echo ""
}

# Main test function
main() {
    echo "=============================================="
    echo "Spark Iceberg Setup Test (Issue #287)"
    echo "=============================================="
    
    local test_passed=true
    
    # Run checks
    if ! check_spark_installation; then
        test_passed=false
    fi
    
    if ! check_services; then
        log_warn "Some services are not running - tests may fail"
        log_info "Consider starting services with docker-compose up"
    fi
    
    if ! check_spark_config; then
        test_passed=false
    fi
    
    if $test_passed; then
        if ! test_spark_basic; then
            test_passed=false
        fi
        
        if $test_passed; then
            # This is the main DoD requirement
            if test_iceberg_catalog; then
                log_info "🎉 DoD requirement satisfied!"
                
                # Additional tests (optional)
                read -p "Run additional Iceberg operations tests? (y/n): " -n 1 -r
                echo
                if [[ $REPLY =~ ^[Yy]$ ]]; then
                    test_iceberg_operations
                    cleanup_tests
                fi
            else
                test_passed=false
            fi
        fi
    fi
    
    show_summary
    
    if $test_passed; then
        log_info "✅ All tests passed! Spark Iceberg setup is working correctly."
        exit 0
    else
        log_error "❌ Some tests failed. Please check the configuration and services."
        exit 1
    fi
}

# Handle script interruption
trap 'echo -e "\n${YELLOW}Test interrupted. Cleaning up...${NC}"; cleanup_tests; exit 1' INT TERM

# Run main function
main "$@"
