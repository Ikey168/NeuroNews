#!/bin/bash

# NeuroNews Python to Go Scraper Migration Script
# This script helps migrate from Python Scrapy to Go async scraper

echo "🔄 NeuroNews Scraper Migration Tool"
echo "===================================="
echo ""

# Configuration
PYTHON_SCRAPER_DIR="../src/scraper"
GO_SCRAPER_DIR="."
BACKUP_DIR="migration_backup_$(date +%Y%m%d_%H%M%S)"
OUTPUT_COMPARISON_DIR="migration_comparison"

# Migration modes
MIGRATION_MODE=${1:-"validate"}  # validate, parallel, migrate, complete

print_usage() {
    echo "Usage: $0 [mode]"
    echo ""
    echo "Migration Modes:"
    echo "  validate  - Compare outputs without changing production (default)"
    echo "  parallel  - Run both scrapers simultaneously"
    echo "  migrate   - Gradually replace Python with Go"
    echo "  complete  - Full migration to Go scraper"
    echo ""
    echo "Examples:"
    echo "  $0 validate   # Test compatibility"
    echo "  $0 parallel   # Run both scrapers"
    echo "  $0 migrate    # Start migration process"
    echo "  $0 complete   # Complete migration"
}

# Validation mode - compare outputs
run_validation() {
    echo "🧪 VALIDATION MODE: Comparing Python and Go scraper outputs"
    echo "--------------------------------------------------------"
    
    mkdir -p "$OUTPUT_COMPARISON_DIR/python" "$OUTPUT_COMPARISON_DIR/go"
    
    echo "📊 Running Python scraper for comparison..."
    cd "$PYTHON_SCRAPER_DIR"
    timeout 300s python run.py --output "../../go-scraper/$OUTPUT_COMPARISON_DIR/python" || true
    cd - > /dev/null
    
    echo "🚀 Running Go scraper for comparison..."
    ./neuronews-scraper -config config_integrated.json -test -output "$OUTPUT_COMPARISON_DIR/go"
    
    # Compare outputs
    echo ""
    echo "📈 COMPARISON RESULTS:"
    echo "====================="
    
    python_articles=$(find "$OUTPUT_COMPARISON_DIR/python" -name "*.json" -exec jq '. | length' {} \; 2>/dev/null | awk '{sum+=$1} END {print sum+0}')
    go_articles=$(find "$OUTPUT_COMPARISON_DIR/go" -name "*.json" -exec jq '. | length' {} \; 2>/dev/null | awk '{sum+=$1} END {print sum+0}')
    
    echo "  Python Scraper: $python_articles articles"
    echo "  Go Scraper: $go_articles articles"
    echo "  Difference: $((go_articles - python_articles)) articles"
    
    # Validate data structure compatibility
    echo ""
    echo "🔍 Validating data structure compatibility..."
    
    python_sample=$(find "$OUTPUT_COMPARISON_DIR/python" -name "*.json" -exec jq '.[0]' {} \; 2>/dev/null | head -1)
    go_sample=$(find "$OUTPUT_COMPARISON_DIR/go" -name "*.json" -exec jq '.[0]' {} \; 2>/dev/null | head -1)
    
    if [ "$python_sample" != "" ] && [ "$go_sample" != "" ]; then
        echo "✅ Both scrapers produced valid JSON output"
        
        # Check field compatibility
        python_fields=$(echo "$python_sample" | jq -r 'keys[]' 2>/dev/null | sort)
        go_fields=$(echo "$go_sample" | jq -r 'keys[]' 2>/dev/null | sort)
        
        if [ "$python_fields" = "$go_fields" ]; then
            echo "✅ Field structures are compatible"
        else
            echo "⚠️  Field structures differ - manual review needed"
            echo "   Python fields: $(echo $python_fields | tr '\n' ' ')"
            echo "   Go fields: $(echo $go_fields | tr '\n' ' ')"
        fi
    else
        echo "❌ Unable to validate data structure compatibility"
    fi
    
    echo ""
    echo "✅ Validation complete. Review outputs in: $OUTPUT_COMPARISON_DIR/"
}

# Parallel mode - run both scrapers
run_parallel() {
    echo "⚡ PARALLEL MODE: Running both scrapers simultaneously"
    echo "====================================================="
    
    mkdir -p "$OUTPUT_COMPARISON_DIR/python_parallel" "$OUTPUT_COMPARISON_DIR/go_parallel"
    
    echo "🔄 Starting parallel execution..."
    
    # Start Python scraper in background
    echo "📍 Starting Python scraper..."
    cd "$PYTHON_SCRAPER_DIR"
    python run.py --output "../../go-scraper/$OUTPUT_COMPARISON_DIR/python_parallel" &
    PYTHON_PID=$!
    cd - > /dev/null
    
    # Start Go scraper
    echo "📍 Starting Go scraper..."
    ./neuronews-scraper -config config_integrated.json -output "$OUTPUT_COMPARISON_DIR/go_parallel" &
    GO_PID=$!
    
    # Wait for both to complete
    echo "⏳ Waiting for scrapers to complete..."
    wait $PYTHON_PID
    python_exit=$?
    
    wait $GO_PID
    go_exit=$?
    
    echo ""
    echo "📊 PARALLEL EXECUTION RESULTS:"
    echo "=============================="
    echo "  Python scraper exit code: $python_exit"
    echo "  Go scraper exit code: $go_exit"
    
    # Analyze outputs
    python_articles=$(find "$OUTPUT_COMPARISON_DIR/python_parallel" -name "*.json" -exec jq '. | length' {} \; 2>/dev/null | awk '{sum+=$1} END {print sum+0}')
    go_articles=$(find "$OUTPUT_COMPARISON_DIR/go_parallel" -name "*.json" -exec jq '. | length' {} \; 2>/dev/null | awk '{sum+=$1} END {print sum+0}')
    
    echo "  Python articles: $python_articles"
    echo "  Go articles: $go_articles"
    echo "  Performance improvement: $(echo "scale=1; ($go_articles - $python_articles) / $python_articles * 100" | bc -l 2>/dev/null || echo "N/A")%"
    
    echo ""
    echo "✅ Parallel execution complete"
}

# Migration mode - gradual replacement
run_migration() {
    echo "🔄 MIGRATION MODE: Gradual replacement strategy"
    echo "=============================================="
    
    # Create backup
    echo "💾 Creating backup of current configuration..."
    mkdir -p "$BACKUP_DIR"
    cp -r "$PYTHON_SCRAPER_DIR/settings.py" "$BACKUP_DIR/" 2>/dev/null || true
    cp -r "../config/settings.json" "$BACKUP_DIR/" 2>/dev/null || true
    
    echo "📋 Migration Strategy:"
    echo "1. Backup created: $BACKUP_DIR"
    echo "2. Configuring source splitting..."
    
    # Create source-specific configs
    cat > "config_python_sources.json" << EOF
{
  "sources_for_python": [
    "Complex sites requiring Scrapy features",
    "Sites with authentication",
    "Custom middleware requirements"
  ],
  "sources_for_go": [
    "BBC", "CNN", "Reuters", "TechCrunch", "Ars Technica", "The Guardian", "NPR"
  ]
}
EOF
    
    cat > "config_go_sources.json" << EOF
{
  "max_workers": 8,
  "rate_limit": 1.5,
  "timeout": "45s",
  "output_dir": "output/go_production",
  "s3_enabled": true,
  "s3_prefix": "news_articles/go_production",
  "validation_enabled": true,
  "quality_threshold": 60,
  "sources": [
    {
      "name": "BBC",
      "base_url": "https://www.bbc.com/news",
      "article_selectors": {
        "title": "h1[data-testid='headline'], h1",
        "content": "div[data-component='text-block'] p",
        "author": "span[data-testid='byline']",
        "date": "time[datetime]"
      },
      "link_patterns": ["/news/.*"],
      "requires_js": false,
      "rate_limit": 1
    },
    {
      "name": "CNN", 
      "base_url": "https://www.cnn.com",
      "article_selectors": {
        "title": "h1.headline__text, h1",
        "content": ".zn-body__paragraph, article p",
        "author": ".byline__name",
        "date": ".update-time"
      },
      "link_patterns": ["/2024/.*", "/2025/.*"],
      "requires_js": false,
      "rate_limit": 1
    }
  ]
}
EOF
    
    echo "3. Testing Go scraper with production-like config..."
    ./neuronews-scraper -config config_go_sources.json -test
    
    if [ $? -eq 0 ]; then
        echo "✅ Go scraper test successful"
        echo "4. Ready for gradual migration"
        echo ""
        echo "Next steps:"
        echo "  - Monitor Go scraper performance for 24-48 hours"
        echo "  - Compare article quality and quantity"
        echo "  - Gradually move more sources to Go scraper"
        echo "  - Update deployment scripts to use Go scraper"
    else
        echo "❌ Go scraper test failed - migration halted"
        echo "   Review logs and fix issues before proceeding"
        return 1
    fi
    
    echo ""
    echo "🔄 Migration phase 1 complete"
}

# Complete migration
run_complete_migration() {
    echo "🎯 COMPLETE MIGRATION: Full replacement with Go scraper"
    echo "===================================================="
    
    # Final validation
    echo "🧪 Running final validation..."
    
    # Build production Go scraper
    echo "🔨 Building production Go scraper..."
    go build -o neuronews-scraper-production
    
    if [ ! -f "neuronews-scraper-production" ]; then
        echo "❌ Failed to build production binary"
        return 1
    fi
    
    # Create production config
    cat > "config_production.json" << EOF
{
  "max_workers": 12,
  "rate_limit": 1.0,
  "timeout": "90s",
  "output_dir": "output/production",
  "user_agent": "NeuroNews-Production/1.0",
  "retry_count": 3,
  "retry_delay": "10s",
  "concurrent_browsers": 4,
  "s3_enabled": true,
  "s3_bucket": "neuronews-raw-articles-prod",
  "s3_prefix": "news_articles/production",
  "aws_region": "us-east-1",
  "validation_enabled": true,
  "duplicate_check": true,
  "quality_threshold": 70,
  "cloudwatch_enabled": true,
  "cloudwatch_log_group": "NeuroNews-Scraper",
  "cloudwatch_log_stream": "go-scraper-production"
}
EOF
    
    echo "📋 Production Configuration:"
    echo "  - 12 concurrent workers"
    echo "  - S3 integration enabled"
    echo "  - CloudWatch logging enabled"
    echo "  - Quality threshold: 70"
    echo "  - Full source coverage"
    
    # Test production config
    echo "🧪 Testing production configuration..."
    ./neuronews-scraper-production -config config_production.json -test
    
    if [ $? -eq 0 ]; then
        echo "✅ Production configuration test successful"
        
        # Update deployment files
        echo "📝 Updating deployment configuration..."
        
        # Create systemd service file
        cat > "neuronews-scraper.service" << EOF
[Unit]
Description=NeuroNews Go Async Scraper
After=network.target

[Service]
Type=simple
User=neuronews
WorkingDirectory=/opt/neuronews/go-scraper
ExecStart=/opt/neuronews/go-scraper/neuronews-scraper-production -config config_production.json
Restart=always
RestartSec=10
Environment=AWS_REGION=us-east-1

[Install]
WantedBy=multi-user.target
EOF
        
        # Create deployment script
        cat > "deploy_production.sh" << EOF
#!/bin/bash
# Production deployment script for Go scraper

echo "🚀 Deploying NeuroNews Go Scraper to Production"

# Stop Python scraper service
sudo systemctl stop neuronews-python-scraper || true

# Install Go scraper
sudo cp neuronews-scraper-production /opt/neuronews/go-scraper/
sudo cp config_production.json /opt/neuronews/go-scraper/
sudo cp neuronews-scraper.service /etc/systemd/system/

# Enable and start Go scraper service
sudo systemctl daemon-reload
sudo systemctl enable neuronews-scraper
sudo systemctl start neuronews-scraper

echo "✅ Go scraper deployed and started"
echo "📊 Check status: sudo systemctl status neuronews-scraper"
echo "📜 View logs: sudo journalctl -u neuronews-scraper -f"
EOF
        
        chmod +x deploy_production.sh
        
        echo ""
        echo "🎉 MIGRATION COMPLETE!"
        echo "===================="
        echo "✅ Production binary built: neuronews-scraper-production"
        echo "✅ Production config ready: config_production.json"
        echo "✅ Systemd service created: neuronews-scraper.service"
        echo "✅ Deployment script ready: deploy_production.sh"
        echo ""
        echo "Final steps:"
        echo "1. Run: ./deploy_production.sh"
        echo "2. Monitor: sudo systemctl status neuronews-scraper"
        echo "3. Verify S3 uploads and CloudWatch logs"
        echo "4. Remove Python scraper after validation period"
        
    else
        echo "❌ Production test failed - migration incomplete"
        return 1
    fi
}

# Check dependencies
check_dependencies() {
    echo "🔍 Checking dependencies..."
    
    # Check if Go binary exists
    if [ ! -f "neuronews-scraper" ]; then
        echo "📦 Go scraper binary not found, building..."
        go build -o neuronews-scraper
        if [ $? -ne 0 ]; then
            echo "❌ Failed to build Go scraper"
            return 1
        fi
    fi
    
    # Check for jq (for JSON processing)
    if ! command -v jq &> /dev/null; then
        echo "⚠️  jq not found - some features may be limited"
    fi
    
    # Check for bc (for calculations)
    if ! command -v bc &> /dev/null; then
        echo "⚠️  bc not found - performance calculations may be limited"
    fi
    
    return 0
}

# Main execution
main() {
    if [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
        print_usage
        exit 0
    fi
    
    # Check dependencies
    if ! check_dependencies; then
        echo "❌ Dependency check failed"
        exit 1
    fi
    
    case "$MIGRATION_MODE" in
        "validate")
            run_validation
            ;;
        "parallel")
            run_parallel
            ;;
        "migrate")
            run_migration
            ;;
        "complete")
            run_complete_migration
            ;;
        *)
            echo "❌ Invalid migration mode: $MIGRATION_MODE"
            print_usage
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
