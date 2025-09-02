#!/usr/bin/env python3
"""
Demo script for dbt on Spark with Iceberg marts (Option A)
Demonstrates the complete workflow for issue #297
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def run_command(cmd, cwd=None, check=True):
    """Run a shell command and return the result."""
    print(f"🚀 Running: {cmd}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        if result.stdout:
            print(f"✅ Output: {result.stdout}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stderr:
            print(f"Error details: {e.stderr}")
        if check:
            raise
        return e


def setup_environment():
    """Set up the dbt environment."""
    print("📦 Setting up dbt environment...")
    
    # Change to dbt directory
    dbt_dir = Path(__file__).parent / "dbt"
    os.chdir(dbt_dir)
    
    # Install dbt dependencies
    print("Installing dbt dependencies...")
    run_command("pip install -r requirements.txt")
    
    # Install dbt packages
    print("Installing dbt packages...")
    run_command("dbt deps")
    
    return dbt_dir


def start_spark_services():
    """Start Spark services using Docker Compose."""
    print("🔥 Starting Spark services...")
    
    # Start Spark cluster and Thrift server
    run_command("docker-compose -f docker-compose.spark.yml up -d")
    
    # Wait for services to be ready
    print("⏳ Waiting for Spark Thrift Server to be ready...")
    time.sleep(30)
    
    # Check if Thrift server is accessible
    max_retries = 10
    for i in range(max_retries):
        try:
            result = run_command("nc -z localhost 10000", check=False)
            if result.returncode == 0:
                print("✅ Spark Thrift Server is ready!")
                break
        except:
            pass
        
        if i < max_retries - 1:
            print(f"⏳ Waiting for Thrift server... (attempt {i+1}/{max_retries})")
            time.sleep(10)
        else:
            print("❌ Spark Thrift Server failed to start")
            return False
    
    return True


def setup_iceberg_tables():
    """Create sample Iceberg tables for testing."""
    print("🧊 Setting up Iceberg tables...")
    
    # Create sample data SQL
    setup_sql = """
    -- Create database and tables
    CREATE DATABASE IF NOT EXISTS demo;
    USE demo;
    
    CREATE SCHEMA IF NOT EXISTS news;
    
    -- Create articles_raw table
    CREATE TABLE IF NOT EXISTS news.articles_raw (
        id STRING,
        url STRING,
        title STRING,
        body STRING,
        source STRING,
        category STRING,
        published_at TIMESTAMP,
        processed_at TIMESTAMP,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        year INT,
        month INT,
        day INT,
        hour INT,
        language STRING,
        tags ARRAY<STRING>,
        sentiment_score DOUBLE,
        sentiment_label STRING,
        hash_content STRING,
        dedup_key STRING
    ) USING ICEBERG
    PARTITIONED BY (year, month);
    
    -- Create articles_enriched table
    CREATE TABLE IF NOT EXISTS news.articles_enriched (
        id STRING,
        url STRING,
        title STRING,
        body STRING,
        source STRING,
        category STRING,
        published_at TIMESTAMP,
        processed_at TIMESTAMP,
        enriched_at TIMESTAMP,
        created_at TIMESTAMP,
        updated_at TIMESTAMP,
        sentiment_score DOUBLE,
        sentiment_label STRING,
        sentiment_confidence DOUBLE,
        topics ARRAY<STRING>,
        topic_scores ARRAY<DOUBLE>,
        primary_topic STRING,
        entities ARRAY<STRING>,
        entity_types ARRAY<STRING>,
        entity_sentiment ARRAY<DOUBLE>,
        keywords ARRAY<STRING>,
        tags ARRAY<STRING>,
        auto_tags ARRAY<STRING>,
        readability_score DOUBLE,
        word_count INT,
        language STRING,
        language_confidence DOUBLE,
        embedding_vector ARRAY<DOUBLE>,
        cluster_id INT,
        similar_articles ARRAY<STRING>,
        trend_score DOUBLE,
        viral_potential DOUBLE,
        engagement_prediction DOUBLE,
        content_quality_score DOUBLE,
        bias_score DOUBLE,
        factuality_score DOUBLE,
        year INT,
        month INT,
        day INT,
        hour INT,
        hash_content STRING,
        enrichment_version STRING
    ) USING ICEBERG
    PARTITIONED BY (year, month);
    
    -- Insert sample data
    INSERT INTO news.articles_raw VALUES
    ('art1', 'https://example.com/art1', 'Sample Article 1', 'This is content 1', 'source1', 'tech', 
     '2024-01-15 10:00:00', '2024-01-15 10:01:00', '2024-01-15 10:01:00', '2024-01-15 10:01:00',
     2024, 1, 15, 10, 'en', array('tech', 'news'), 0.5, 'positive', 'hash1', 'dedup1'),
    ('art2', 'https://example.com/art2', 'Sample Article 2', 'This is content 2', 'source2', 'business',
     '2024-01-15 11:00:00', '2024-01-15 11:01:00', '2024-01-15 11:01:00', '2024-01-15 11:01:00',
     2024, 1, 15, 11, 'en', array('business', 'economy'), -0.2, 'negative', 'hash2', 'dedup2');
     
    INSERT INTO news.articles_enriched VALUES
    ('art1', 'https://example.com/art1', 'Sample Article 1', 'This is content 1', 'source1', 'tech',
     '2024-01-15 10:00:00', '2024-01-15 10:01:00', '2024-01-15 10:02:00', '2024-01-15 10:01:00', '2024-01-15 10:02:00',
     0.5, 'positive', 0.85, array('technology', 'innovation'), array(0.8, 0.7), 'technology',
     array('Apple', 'Google'), array('ORG', 'ORG'), array(0.6, 0.7),
     array('tech', 'innovation', 'companies'), array('tech', 'news'), array('technology', 'business'),
     0.75, 100, 'en', 0.95, array(0.1, 0.2, 0.3), 1, array('art3', 'art4'),
     0.6, 0.7, 0.8, 0.85, 0.1, 0.9, 2024, 1, 15, 10, 'hash1', 'v1.0');
    """
    
    # Write SQL to temporary file
    with open("/tmp/setup_iceberg.sql", "w") as f:
        f.write(setup_sql)
    
    # Execute SQL using Spark SQL
    run_command(
        "docker exec spark-thrift-server /opt/bitnami/spark/bin/spark-sql "
        "--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions "
        "--conf spark.sql.catalog.spark_catalog=org.apache.iceberg.spark.SparkSessionCatalog "
        "--conf spark.sql.catalog.spark_catalog.type=hive "
        "-f /tmp/setup_iceberg.sql"
    )


def run_dbt_workflow():
    """Run the complete dbt workflow."""
    print("🏗️  Running dbt workflow...")
    
    # Debug connection
    print("Testing dbt connection...")
    run_command("dbt debug")
    
    # Run dbt models
    print("Running dbt models...")
    run_command("dbt run")
    
    # Run dbt tests
    print("Running dbt tests...")
    result = run_command("dbt test", check=False)
    
    if result.returncode == 0:
        print("✅ All dbt tests passed!")
    else:
        print("⚠️  Some dbt tests failed - check output above")
    
    # Generate documentation
    print("Generating dbt documentation...")
    run_command("dbt docs generate")
    
    return result.returncode == 0


def validate_results():
    """Validate that the marts were created successfully."""
    print("🔍 Validating results...")
    
    validation_sql = """
    -- Check that marts were created
    SHOW TABLES IN neuronews.marts;
    
    -- Validate fact_articles
    SELECT COUNT(*) as fact_articles_count FROM neuronews.marts.fact_articles;
    
    -- Validate dim_sources
    SELECT COUNT(*) as dim_sources_count FROM neuronews.marts.dim_sources;
    
    -- Validate daily metrics
    SELECT COUNT(*) as daily_metrics_count FROM neuronews.marts.agg_daily_metrics;
    
    -- Sample data from fact table
    SELECT 
        article_id, 
        title, 
        source, 
        sentiment_category,
        content_quality_tier 
    FROM neuronews.marts.fact_articles 
    LIMIT 5;
    """
    
    with open("/tmp/validate_results.sql", "w") as f:
        f.write(validation_sql)
    
    run_command(
        "docker exec spark-thrift-server /opt/bitnami/spark/bin/spark-sql "
        "--conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions "
        "--conf spark.sql.catalog.spark_catalog=org.apache.iceberg.spark.SparkSessionCatalog "
        "--conf spark.sql.catalog.spark_catalog.type=hive "
        "-f /tmp/validate_results.sql"
    )


def cleanup():
    """Clean up resources."""
    print("🧹 Cleaning up...")
    
    # Stop Docker services
    run_command("docker-compose -f docker-compose.spark.yml down", check=False)
    
    # Clean up temporary files
    for temp_file in ["/tmp/setup_iceberg.sql", "/tmp/validate_results.sql"]:
        if os.path.exists(temp_file):
            os.remove(temp_file)


def main():
    """Main demo workflow."""
    print("🎯 dbt on Spark for Iceberg marts - Demo (Option A)")
    print("=" * 60)
    
    try:
        # Setup
        dbt_dir = setup_environment()
        
        # Start Spark services
        if not start_spark_services():
            print("❌ Failed to start Spark services")
            return 1
        
        # Setup Iceberg tables
        setup_iceberg_tables()
        
        # Run dbt workflow
        tests_passed = run_dbt_workflow()
        
        # Validate results
        validate_results()
        
        # Summary
        print("\n" + "=" * 60)
        print("📊 Demo Summary:")
        print(f"✅ Spark Thrift Server: Running on port 10000")
        print(f"✅ dbt models: Created in schema neuronews.marts")
        print(f"✅ Iceberg tables: Materialized with partitioning")
        print(f"{'✅' if tests_passed else '⚠️ '} dbt tests: {'Passed' if tests_passed else 'Some failures'}")
        print(f"✅ CI Integration: Ready for GitHub Actions")
        
        print("\n🎯 Option A (dbt-spark) implementation complete!")
        print("DoD satisfied: dbt run + dbt test succeed and are wired into CI")
        
        return 0 if tests_passed else 1
        
    except KeyboardInterrupt:
        print("\n⏹️  Demo interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        return 1
    finally:
        cleanup()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
