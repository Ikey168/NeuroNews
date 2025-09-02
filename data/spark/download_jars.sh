#!/bin/bash
# Download required JAR dependencies for Spark + Iceberg setup
# This script downloads the necessary JAR files for local development

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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
JARS_DIR="$SCRIPT_DIR/jars"
SCALA_VERSION="2.12"
SPARK_VERSION="3.5"
ICEBERG_VERSION="1.4.2"
HADOOP_VERSION="3.3.4"
AWS_SDK_VERSION="1.12.423"

# JAR URLs
declare -A JARS=(
    ["iceberg-spark-runtime"]="https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}/${ICEBERG_VERSION}/iceberg-spark-runtime-${SPARK_VERSION}_${SCALA_VERSION}-${ICEBERG_VERSION}.jar"
    ["hadoop-aws"]="https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-aws/${HADOOP_VERSION}/hadoop-aws-${HADOOP_VERSION}.jar"
    ["aws-java-sdk-bundle"]="https://repo1.maven.org/maven2/com/amazonaws/aws-java-sdk-bundle/${AWS_SDK_VERSION}/aws-java-sdk-bundle-${AWS_SDK_VERSION}.jar"
    ["postgresql"]="https://repo1.maven.org/maven2/org/postgresql/postgresql/42.6.0/postgresql-42.6.0.jar"
)

# Create jars directory
create_jars_directory() {
    log_step "Creating JARs directory..."
    mkdir -p "$JARS_DIR"
    log_info "Created directory: $JARS_DIR"
}

# Download a single JAR file
download_jar() {
    local name=$1
    local url=$2
    local filename=$(basename "$url")
    local filepath="$JARS_DIR/$filename"
    
    if [[ -f "$filepath" ]]; then
        log_info "✓ Already exists: $filename"
        return 0
    fi
    
    log_info "Downloading: $filename"
    if curl -L -o "$filepath" "$url"; then
        local size=$(du -h "$filepath" | cut -f1)
        log_info "✓ Downloaded: $filename ($size)"
        return 0
    else
        log_error "✗ Failed to download: $filename"
        rm -f "$filepath"
        return 1
    fi
}

# Download all required JARs
download_all_jars() {
    log_step "Downloading required JAR dependencies..."
    
    local failed_downloads=()
    
    for name in "${!JARS[@]}"; do
        url=${JARS[$name]}
        if ! download_jar "$name" "$url"; then
            failed_downloads+=("$name")
        fi
    done
    
    if [[ ${#failed_downloads[@]} -gt 0 ]]; then
        log_error "Failed to download: ${failed_downloads[*]}"
        return 1
    fi
    
    log_info "✓ All JAR dependencies downloaded successfully"
    return 0
}

# Verify downloads
verify_downloads() {
    log_step "Verifying downloaded files..."
    
    local jar_count=$(find "$JARS_DIR" -name "*.jar" | wc -l)
    log_info "Found $jar_count JAR files in $JARS_DIR"
    
    for jar_file in "$JARS_DIR"/*.jar; do
        if [[ -f "$jar_file" ]]; then
            local size=$(du -h "$jar_file" | cut -f1)
            local name=$(basename "$jar_file")
            log_info "✓ $name ($size)"
        fi
    done
}

# Create classpath helper
create_classpath_helper() {
    log_step "Creating classpath helper script..."
    
    local classpath_script="$SCRIPT_DIR/setup_classpath.sh"
    
    cat > "$classpath_script" << 'EOF'
#!/bin/bash
# Helper script to set up classpath for Spark + Iceberg

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARS_DIR="$SCRIPT_DIR/jars"

# Build classpath from all JARs
if [[ -d "$JARS_DIR" ]]; then
    ICEBERG_CLASSPATH=""
    for jar in "$JARS_DIR"/*.jar; do
        if [[ -f "$jar" ]]; then
            if [[ -z "$ICEBERG_CLASSPATH" ]]; then
                ICEBERG_CLASSPATH="$jar"
            else
                ICEBERG_CLASSPATH="$ICEBERG_CLASSPATH:$jar"
            fi
        fi
    done
    
    export SPARK_CLASSPATH="$ICEBERG_CLASSPATH"
    echo "Classpath configured with $(echo "$ICEBERG_CLASSPATH" | tr ':' '\n' | wc -l) JAR files"
    echo "Set SPARK_CLASSPATH=$SPARK_CLASSPATH"
else
    echo "JARs directory not found: $JARS_DIR"
    echo "Run download_jars.sh first"
    exit 1
fi
EOF
    
    chmod +x "$classpath_script"
    log_info "Created classpath helper: $classpath_script"
}

# Display usage information
show_usage_info() {
    echo ""
    echo "=============================================="
    echo "Spark + Iceberg JAR Dependencies"
    echo "=============================================="
    echo ""
    echo "Downloaded JARs to: $JARS_DIR"
    echo ""
    echo "Usage options:"
    echo ""
    echo "1. Copy JARs to Spark installation:"
    echo "   cp $JARS_DIR/*.jar \$SPARK_HOME/jars/"
    echo ""
    echo "2. Use classpath helper:"
    echo "   source $SCRIPT_DIR/setup_classpath.sh"
    echo "   spark-sql"
    echo ""
    echo "3. Manual classpath:"
    echo "   spark-sql --jars \$(ls $JARS_DIR/*.jar | tr '\n' ',')"
    echo ""
    echo "4. PySpark with JARs:"
    echo "   pyspark --jars \$(ls $JARS_DIR/*.jar | tr '\n' ',')"
    echo ""
    echo "Required for Iceberg functionality:"
    echo "- Iceberg Spark runtime (core Iceberg support)"
    echo "- Hadoop AWS (S3A file system)"
    echo "- AWS SDK bundle (S3 client libraries)"
    echo "- PostgreSQL driver (catalog metadata)"
    echo ""
}

# Check if curl is available
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi
}

# Main function
main() {
    echo "=============================================="
    echo "Spark + Iceberg JAR Downloader"
    echo "=============================================="
    
    check_dependencies
    create_jars_directory
    
    if download_all_jars; then
        verify_downloads
        create_classpath_helper
        show_usage_info
        log_info "✅ JAR download completed successfully!"
    else
        log_error "❌ Some downloads failed. Please check your internet connection and try again."
        exit 1
    fi
}

# Run main function
main "$@"
