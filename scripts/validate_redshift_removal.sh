#!/bin/bash

# Redshift Removal Migration Script
# Issue #245: Remove Redshift support from NeuroNews
#
# This script helps identify and clean up any remaining Redshift references
# after the main removal process.

set -e

echo "🗑️  NeuroNews Redshift Removal Migration Script"
echo "================================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [[ ! -f "README.md" ]] || [[ ! -d "src" ]]; then
    print_error "This script must be run from the NeuroNews project root directory"
    exit 1
fi

print_status "Starting Redshift removal validation..."
echo ""

# 1. Check for remaining Redshift file references
print_status "Checking for remaining Redshift files..."

REDSHIFT_FILES=(
    "src/database/redshift_loader.py"
    "src/database/redshift_schema.sql"
    "src/scraper/redshift_pipelines.py"
    "deployment/terraform/redshift.tf"
    "tests/database/test_redshift_loader.py"
    "tests/integration/test_redshift_etl.py"
    "demo/demo_redshift_etl.py"
    "scripts/test_redshift_dr.sh"
)

for file in "${REDSHIFT_FILES[@]}"; do
    if [[ -f "$file" ]]; then
        print_error "Redshift file still exists: $file"
        echo "  Run: rm $file"
    else
        print_success "✓ Removed: $file"
    fi
done

echo ""

# 2. Check for Redshift references in code
print_status "Scanning for remaining Redshift references in code..."

# Search for redshift imports and class references
REDSHIFT_PATTERNS=(
    "from.*redshift_loader"
    "import.*redshift_loader"
    "RedshiftETLProcessor"
    "RedshiftLoader"
    "redshift_host"
    "REDSHIFT_HOST"
    "REDSHIFT_USER"
    "REDSHIFT_PASSWORD"
    "REDSHIFT_DB"
)

for pattern in "${REDSHIFT_PATTERNS[@]}"; do
    print_status "Searching for pattern: $pattern"
    
    # Search in Python files
    if grep -r --include="*.py" -n "$pattern" src/ tests/ 2>/dev/null; then
        print_warning "Found Redshift references that may need updating"
    else
        print_success "✓ No references found for: $pattern"
    fi
done

echo ""

# 3. Check Terraform configuration
print_status "Checking Terraform configuration..."

if grep -r "redshift" deployment/terraform/ 2>/dev/null | grep -v "# Migrated from Redshift"; then
    print_warning "Found Redshift references in Terraform files"
else
    print_success "✓ No Redshift references in Terraform configuration"
fi

echo ""

# 4. Check requirements files
print_status "Checking Python requirements..."

if grep -i "psycopg2" requirements*.txt airflow/requirements.txt 2>/dev/null; then
    print_warning "psycopg2 found - may be needed for Airflow PostgreSQL, verify usage"
else
    print_success "✓ No Redshift-specific database drivers found"
fi

echo ""

# 5. Check for test mocks that need updating
print_status "Checking test files for outdated mocks..."

if grep -r --include="*.py" "spec=RedshiftLoader" tests/ 2>/dev/null; then
    print_warning "Found test mocks that need updating to SnowflakeAnalyticsConnector"
else
    print_success "✓ No outdated RedshiftLoader mocks found"
fi

echo ""

# 6. Environment variable documentation check
print_status "Checking for Redshift environment variables in documentation..."

if grep -r "REDSHIFT_" docs/ README.md 2>/dev/null | grep -v "removed\|migration\|deprecated"; then
    print_warning "Found REDSHIFT_ environment variable references in documentation"
else
    print_success "✓ Documentation updated to remove Redshift environment variables"
fi

echo ""

# 7. Generate summary report
print_status "Generating migration summary..."

echo ""
echo "📊 MIGRATION SUMMARY"
echo "===================="

# Count removed files
removed_count=0
for file in "${REDSHIFT_FILES[@]}"; do
    if [[ ! -f "$file" ]]; then
        ((removed_count++))
    fi
done

echo "Files removed: $removed_count/${#REDSHIFT_FILES[@]}"

# Check API routes
if grep -q "SnowflakeAnalyticsConnector" src/api/routes/news_routes.py src/api/routes/article_routes.py 2>/dev/null; then
    print_success "✓ API routes migrated to Snowflake"
else
    print_warning "⚠ API routes may need Snowflake migration"
fi

# Check QuickSight service
if grep -q "snowflake" src/dashboards/quicksight_service.py 2>/dev/null; then
    print_success "✓ QuickSight service updated for Snowflake"
else
    print_warning "⚠ QuickSight service may need Snowflake migration"
fi

echo ""

# 8. Next steps
print_status "NEXT STEPS"
echo "==========="
echo ""
echo "1. Update test files to use SnowflakeAnalyticsConnector mocks"
echo "2. Verify CI/CD pipelines no longer reference Redshift"
echo "3. Update environment variables in production/staging:"
echo "   - Remove: REDSHIFT_HOST, REDSHIFT_USER, REDSHIFT_PASSWORD, REDSHIFT_DB"
echo "   - Add: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, etc."
echo ""
echo "4. Test API endpoints with Snowflake connection"
echo "5. Validate dashboard integrations"
echo "6. Clean up AWS Redshift infrastructure (manual)"
echo ""

print_success "Redshift removal validation complete!"
echo ""
echo "📝 See docs/REDSHIFT_REMOVAL_DOCUMENTATION.md for detailed migration guide"
echo ""

# Optional: Create a cleanup script for any remaining references
if [[ "$1" == "--generate-cleanup" ]]; then
    print_status "Generating automated cleanup script..."
    
    cat > cleanup_redshift_references.sh << 'EOF'
#!/bin/bash
# Auto-generated cleanup script for remaining Redshift references

echo "🧹 Cleaning up remaining Redshift references..."

# Update test mocks (example - review before running)
find tests/ -name "*.py" -exec sed -i 's/spec=RedshiftLoader/spec=SnowflakeAnalyticsConnector/g' {} \;
find tests/ -name "*.py" -exec sed -i 's/from src.database.redshift_loader import RedshiftLoader/from src.database.snowflake_analytics_connector import SnowflakeAnalyticsConnector/g' {} \;

echo "✅ Cleanup complete - review changes before committing"
EOF
    
    chmod +x cleanup_redshift_references.sh
    print_success "Created cleanup_redshift_references.sh (review before running)"
fi

exit 0
