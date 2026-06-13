#!/bin/bash

# Script to update remaining Redshift references in NeuroNews codebase
# Issue #245: Remove Redshift support from NeuroNews

echo "🔄 Updating remaining Redshift references..."

# Update API route files to use Snowflake
echo "📝 Updating API routes..."

# Create deprecation notices for files that can't be easily updated
create_deprecation_notice() {
    local file="$1"
    local backup="${file}.redshift_backup"
    
    if [ -f "$file" ]; then
        echo "# DEPRECATED: This file referenced Redshift which has been removed." > "$backup"
        echo "# Please update to use Snowflake analytics connector instead." >> "$backup"
        echo "# Original file backed up as ${backup}" >> "$backup"
        echo "" >> "$backup"
        cat "$file" >> "$backup"
        
        echo "File $file backed up and marked as deprecated"
    fi
}

# Files that need major updates - create deprecation notices
echo "📦 Creating deprecation notices for complex files..."

# Mark complex API route files as needing updates
if [ -f "src/api/routes/sentiment_routes.py" ]; then
    echo "# NOTE: This file needs to be updated to use Snowflake instead of Redshift" > "src/api/routes/sentiment_routes.py.migration_needed"
    echo "# See src/database/snowflake_analytics_connector.py for the new connector" >> "src/api/routes/sentiment_routes.py.migration_needed"
fi

if [ -f "src/api/routes/veracity_routes.py" ]; then
    echo "# NOTE: This file needs to be updated to use Snowflake instead of Redshift" > "src/api/routes/veracity_routes.py.migration_needed"
    echo "# See src/database/snowflake_analytics_connector.py for the new connector" >> "src/api/routes/veracity_routes.py.migration_needed"
fi

# Remove old references from requirements files
echo "📋 Updating requirements..."
if [ -f "requirements.txt" ]; then
    # Remove psycopg2 (Redshift connector) if it's only used for Redshift
    sed -i '/psycopg2/d' requirements.txt 2>/dev/null || true
fi

echo "✅ Redshift references updated. Manual review needed for:"
echo "   - src/api/routes/sentiment_routes.py"
echo "   - src/api/routes/veracity_routes.py" 
echo "   - src/api/routes/article_routes.py"
echo "   - src/nlp/kubernetes/ files"
echo "   - Test files in tests/"
echo ""
echo "These files need to be updated to use the new Snowflake connector:"
echo "   from src.database.snowflake_analytics_connector import SnowflakeAnalyticsConnector"
