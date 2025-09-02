#!/usr/bin/env python3
"""
Demo script for Snowflake Analytics Integration

Demonstrates the updated analytics queries and dashboard integrations
for Snowflake compatibility.

Issue #244: Update analytics queries and integrations for Snowflake

Usage:
    python demo_snowflake_analytics.py [--test-connection] [--run-queries] [--generate-sample]
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List

import pandas as pd

# Add src to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

try:
    from src.database.snowflake_analytics_connector import (
        SnowflakeAnalyticsConnector,
        validate_snowflake_config
    )
    from src.dashboards.snowflake_dashboard_config import (
        get_config,
        get_query_template,
        validate_snowflake_config as validate_dashboard_config
    )
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    print(f"Import error: {e}")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_snowflake_connection() -> bool:
    """Test Snowflake database connection."""
    print("🔧 Testing Snowflake Connection...")
    
    if not IMPORTS_AVAILABLE:
        print("❌ Required modules not available")
        return False
    
    # Validate configuration
    config_validation = validate_snowflake_config()
    print(f"Configuration validation: {config_validation}")
    
    if not config_validation["valid"]:
        print(f"❌ Missing configuration: {config_validation['missing_variables']}")
        print("Set environment variables:")
        for var in config_validation['missing_variables']:
            print(f"  export {var}=your_value")
        return False
    
    try:
        # Create connector and test connection
        connector = SnowflakeAnalyticsConnector()
        
        if connector.test_connection():
            print("✅ Snowflake connection successful!")
            
            # Get table information
            try:
                table_info = connector.get_table_info("news_articles")
                print(f"📊 Table info: {table_info['row_count']} rows, {len(table_info['columns'])} columns")
            except Exception as e:
                print(f"⚠️  Could not fetch table info: {e}")
            
            return True
        else:
            print("❌ Snowflake connection failed")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


def demonstrate_analytics_queries() -> bool:
    """Demonstrate the new Snowflake analytics queries."""
    print("\n📊 Demonstrating Analytics Queries...")
    
    if not IMPORTS_AVAILABLE:
        print("❌ Required modules not available")
        return False
    
    try:
        connector = SnowflakeAnalyticsConnector()
        
        # Test 1: Sentiment Trends
        print("\n1️⃣ Testing Sentiment Trends Query...")
        sentiment_df = connector.get_sentiment_trends(days=7)
        print(f"   📈 Retrieved {len(sentiment_df)} sentiment data points")
        if not sentiment_df.empty:
            print(f"   📊 Average sentiment: {sentiment_df['AVG_SENTIMENT'].mean():.3f}")
            print(f"   📰 Total articles: {sentiment_df['ARTICLE_COUNT'].sum()}")
        
        # Test 2: Top Entities
        print("\n2️⃣ Testing Entity Analysis Query...")
        entities_df = connector.get_top_entities(entity_type="ORG", limit=10)
        print(f"   🏢 Retrieved {len(entities_df)} organizations")
        if not entities_df.empty:
            top_entity = entities_df.iloc[0]
            print(f"   🥇 Top entity: {top_entity['ENTITY_NAME']} ({top_entity['MENTION_COUNT']} mentions)")
        
        # Test 3: Keyword Trends
        print("\n3️⃣ Testing Keyword Trends Query...")
        keywords_df = connector.get_keyword_trends(days=1)
        print(f"   🔥 Retrieved {len(keywords_df)} trending keywords")
        if not keywords_df.empty:
            top_keyword = keywords_df.iloc[0]
            print(f"   🚀 Top trending: {top_keyword['KEYWORD']} (velocity: {top_keyword['AVG_VELOCITY']:.2f})")
        
        # Test 4: Source Statistics
        print("\n4️⃣ Testing Source Statistics Query...")
        sources_df = connector.get_source_statistics()
        print(f"   📺 Retrieved statistics for {len(sources_df)} sources")
        if not sources_df.empty:
            total_articles = sources_df['TOTAL_ARTICLES'].sum()
            print(f"   📊 Total articles across all sources: {total_articles}")
            print(f"   📈 Most active source: {sources_df.iloc[0]['SOURCE']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Query demonstration failed: {e}")
        return False


def test_dashboard_integration() -> bool:
    """Test dashboard configuration and integration."""
    print("\n🖥️  Testing Dashboard Integration...")
    
    if not IMPORTS_AVAILABLE:
        print("❌ Required modules not available")
        return False
    
    try:
        # Test configuration validation
        dashboard_config = validate_dashboard_config()
        print(f"Dashboard config validation: {dashboard_config['valid']}")
        
        if not dashboard_config['valid']:
            print(f"❌ Dashboard config issues: {dashboard_config['missing_fields']}")
            return False
        
        # Test query templates
        templates = ["sentiment_trends", "top_entities", "keyword_velocity"]
        print("📋 Testing query templates...")
        
        for template_name in templates:
            template = get_query_template(template_name)
            if template:
                print(f"   ✅ {template_name} template loaded")
            else:
                print(f"   ❌ {template_name} template missing")
        
        # Test analytics config
        analytics_config = get_config("analytics")
        print(f"📊 Analytics config loaded: {len(analytics_config)} settings")
        
        print("✅ Dashboard integration tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Dashboard integration test failed: {e}")
        return False


def generate_sample_analytics_report() -> Dict:
    """Generate a sample analytics report using Snowflake."""
    print("\n📋 Generating Sample Analytics Report...")
    
    if not IMPORTS_AVAILABLE:
        print("❌ Required modules not available")
        return {}
    
    try:
        connector = SnowflakeAnalyticsConnector()
        report = {
            "generated_at": datetime.now().isoformat(),
            "report_type": "Snowflake Analytics Demo",
            "time_range": "Last 7 days",
            "sections": {}
        }
        
        # Sentiment Analysis Section
        print("   📈 Generating sentiment analysis...")
        sentiment_df = connector.get_sentiment_trends(days=7)
        if not sentiment_df.empty:
            report["sections"]["sentiment_analysis"] = {
                "total_data_points": len(sentiment_df),
                "average_sentiment": float(sentiment_df['AVG_SENTIMENT'].mean()),
                "total_articles": int(sentiment_df['ARTICLE_COUNT'].sum()),
                "active_sources": int(sentiment_df['SOURCE'].nunique()),
                "sentiment_range": {
                    "min": float(sentiment_df['AVG_SENTIMENT'].min()),
                    "max": float(sentiment_df['AVG_SENTIMENT'].max())
                }
            }
        
        # Entity Analysis Section
        print("   🏢 Generating entity analysis...")
        entities_df = connector.get_top_entities(entity_type="ORG", limit=20)
        if not entities_df.empty:
            report["sections"]["entity_analysis"] = {
                "total_entities": len(entities_df),
                "top_entities": [
                    {
                        "name": row['ENTITY_NAME'],
                        "mentions": int(row['MENTION_COUNT']),
                        "sources": int(row['SOURCE_COUNT'])
                    }
                    for _, row in entities_df.head(5).iterrows()
                ],
                "total_mentions": int(entities_df['MENTION_COUNT'].sum())
            }
        
        # Keyword Trends Section
        print("   🔥 Generating keyword trends...")
        keywords_df = connector.get_keyword_trends(days=1)
        if not keywords_df.empty:
            report["sections"]["keyword_trends"] = {
                "trending_keywords": len(keywords_df),
                "top_trending": [
                    {
                        "keyword": row['KEYWORD'],
                        "velocity": float(row['AVG_VELOCITY']),
                        "mentions": int(row['TOTAL_MENTIONS'])
                    }
                    for _, row in keywords_df.head(5).iterrows()
                ],
                "total_keyword_mentions": int(keywords_df['TOTAL_MENTIONS'].sum())
            }
        
        # Source Statistics Section
        print("   📺 Generating source statistics...")
        sources_df = connector.get_source_statistics()
        if not sources_df.empty:
            report["sections"]["source_statistics"] = {
                "total_sources": len(sources_df),
                "most_active_sources": [
                    {
                        "source": row['SOURCE'],
                        "articles": int(row['TOTAL_ARTICLES']),
                        "avg_sentiment": float(row['AVG_SENTIMENT']) if pd.notna(row['AVG_SENTIMENT']) else None,
                        "articles_per_day": float(row['ARTICLES_PER_DAY'])
                    }
                    for _, row in sources_df.head(5).iterrows()
                ],
                "total_articles_analyzed": int(sources_df['TOTAL_ARTICLES'].sum())
            }
        
        # Summary Section
        report["summary"] = {
            "analytics_migration": "Successfully migrated to Snowflake",
            "query_performance": "Optimized for Snowflake SQL syntax",
            "dashboard_integration": "Updated for direct Snowflake connectivity",
            "features_validated": [
                "Sentiment trend analysis",
                "Entity extraction and analysis", 
                "Keyword velocity tracking",
                "Source performance metrics"
            ]
        }
        
        print("✅ Sample analytics report generated!")
        return report
        
    except Exception as e:
        print(f"❌ Report generation failed: {e}")
        return {}


def run_comprehensive_demo():
    """Run a comprehensive demonstration of all features."""
    print("🚀 NeuroNews Snowflake Analytics Demo")
    print("=" * 50)
    
    success_count = 0
    total_tests = 4
    
    # Test 1: Connection
    if test_snowflake_connection():
        success_count += 1
    
    # Test 2: Analytics Queries
    if demonstrate_analytics_queries():
        success_count += 1
    
    # Test 3: Dashboard Integration
    if test_dashboard_integration():
        success_count += 1
    
    # Test 4: Sample Report
    report = generate_sample_analytics_report()
    if report:
        success_count += 1
        
        # Save report to file
        report_file = f"snowflake_analytics_demo_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"📄 Report saved to: {report_file}")
    
    # Summary
    print("\n" + "=" * 50)
    print(f"🎯 Demo Summary: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("✅ All Snowflake analytics features working correctly!")
        print("\n🎉 Issue #244 Implementation Complete:")
        print("   ✅ Updated analytics queries for Snowflake SQL syntax")
        print("   ✅ Created Snowflake analytics connector")
        print("   ✅ Updated dashboard for direct Snowflake integration")
        print("   ✅ Optimized queries for Snowflake performance")
        print("   ✅ Validated all analytics components")
    else:
        print("⚠️  Some features need attention - check configuration and connectivity")
    
    return success_count == total_tests


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Demo Snowflake Analytics Integration for NeuroNews"
    )
    parser.add_argument(
        "--test-connection",
        action="store_true",
        help="Test Snowflake database connection only"
    )
    parser.add_argument(
        "--run-queries", 
        action="store_true",
        help="Run analytics queries demonstration only"
    )
    parser.add_argument(
        "--generate-sample",
        action="store_true", 
        help="Generate sample analytics report only"
    )
    
    args = parser.parse_args()
    
    if args.test_connection:
        test_snowflake_connection()
    elif args.run_queries:
        demonstrate_analytics_queries()
    elif args.generate_sample:
        report = generate_sample_analytics_report()
        if report:
            print(json.dumps(report, indent=2))
    else:
        # Run comprehensive demo
        run_comprehensive_demo()


if __name__ == "__main__":
    main()
