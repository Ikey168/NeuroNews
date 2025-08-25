#!/usr/bin/env python3
"""
Test script for enrichment upsert idempotency (Issue #291)
Validates DoD: Re-running for a day updates rows in place (no dupes)
"""
import os
import subprocess
import time
from datetime import datetime, timedelta
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, lit, current_timestamp

# Configuration
RAW_TABLE = "demo.news.articles_raw"
ENRICHED_TABLE = "demo.news.articles_enriched"
TEST_DATE = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def create_test_spark_session():
    """Create Spark session for testing."""
    return SparkSession.builder \
        .appName("UpsertIdempotencyTest") \
        .config("spark.sql.catalog.demo", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.demo.catalog-impl", "org.apache.iceberg.rest.RESTCatalog") \
        .config("spark.sql.catalog.demo.uri", "http://localhost:8181") \
        .config("spark.sql.catalog.demo.warehouse", "s3a://demo-warehouse/") \
        .config("spark.sql.catalog.demo.io-impl", "org.apache.iceberg.aws.s3.S3FileIO") \
        .config("spark.hadoop.fs.s3a.access.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.secret.key", "minioadmin") \
        .config("spark.hadoop.fs.s3a.endpoint", "http://localhost:9000") \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .getOrCreate()

def create_test_data(spark):
    """Create test data in raw table for testing."""
    # Create test articles with known IDs
    test_data = [
        {
            "id": "test-article-1",
            "published_at": f"{TEST_DATE} 10:00:00",
            "title": "Test Article 1",
            "body": "This is a great test article with positive sentiment",
            "source": "test-source",
            "url": "http://test.com/1"
        },
        {
            "id": "test-article-2", 
            "published_at": f"{TEST_DATE} 11:00:00",
            "title": "Test Article 2",
            "body": "This is a terrible article with negative sentiment",
            "source": "test-source",
            "url": "http://test.com/2"
        },
        {
            "id": "test-article-3",
            "published_at": f"{TEST_DATE} 12:00:00",
            "title": "Test Article 3",
            "body": "This is a neutral article with no strong sentiment",
            "source": "test-source", 
            "url": "http://test.com/3"
        }
    ]
    
    # Create DataFrame
    from pyspark.sql.types import StructType, StructField, StringType, TimestampType
    
    schema = StructType([
        StructField("id", StringType(), True),
        StructField("published_at", TimestampType(), True),
        StructField("title", StringType(), True),
        StructField("body", StringType(), True),
        StructField("source", StringType(), True),
        StructField("url", StringType(), True)
    ])
    
    # Convert string timestamps to proper timestamp format
    rows = []
    for item in test_data:
        rows.append((
            item["id"],
            datetime.strptime(item["published_at"], "%Y-%m-%d %H:%M:%S"),
            item["title"],
            item["body"],
            item["source"],
            item["url"]
        ))
    
    test_df = spark.createDataFrame(rows, schema)
    
    # Write to raw table (create or replace for testing)
    test_df.writeTo(RAW_TABLE).createOrReplace()
    
    print(f"✓ Created {test_df.count()} test articles in {RAW_TABLE}")
    return test_df

def run_enrichment_job():
    """Run the enrichment upsert job."""
    env = os.environ.copy()
    env["PROCESS_DATE"] = TEST_DATE
    
    result = subprocess.run([
        "python", "/workspaces/NeuroNews/jobs/spark/upsert_enriched.py"
    ], env=env, capture_output=True, text=True)
    
    print("Enrichment job output:")
    print(result.stdout)
    if result.stderr:
        print("Enrichment job errors:")
        print(result.stderr)
    
    return result.returncode == 0

def validate_enrichment_results(spark):
    """Validate the enrichment results."""
    try:
        enriched_df = spark.table(ENRICHED_TABLE)
        total_count = enriched_df.count()
        
        print(f"Total enriched records: {total_count}")
        
        if total_count > 0:
            print("Sample enriched records:")
            enriched_df.select("id", "sentiment_label", "sentiment_score", "version").show()
            
            # Check for required columns
            expected_columns = ["id", "sentiment_score", "sentiment_label", "entities", "keywords", "version"]
            actual_columns = enriched_df.columns
            
            missing_columns = set(expected_columns) - set(actual_columns)
            if missing_columns:
                print(f"❌ Missing columns: {missing_columns}")
                return False
            
            # Check for null sentiment scores
            null_sentiment_count = enriched_df.filter(col("sentiment_score").isNull()).count()
            if null_sentiment_count > 0:
                print(f"❌ Found {null_sentiment_count} records with null sentiment scores")
                return False
            
            print("✅ Enrichment results validation passed")
            return True
        else:
            print("❌ No enriched records found")
            return False
            
    except Exception as e:
        print(f"❌ Error validating enrichment results: {e}")
        return False

def validate_idempotency(spark):
    """Validate idempotency by checking for duplicates."""
    try:
        # Check for duplicate IDs
        duplicates_df = spark.sql(f"""
            SELECT id, count(*) as cnt 
            FROM {ENRICHED_TABLE} 
            GROUP BY id 
            HAVING cnt > 1
        """)
        
        duplicate_count = duplicates_df.count()
        
        if duplicate_count > 0:
            print(f"❌ Found {duplicate_count} duplicate IDs:")
            duplicates_df.show()
            return False
        else:
            print("✅ No duplicates found - idempotency maintained")
            return True
            
    except Exception as e:
        print(f"❌ Error checking idempotency: {e}")
        return False

def test_version_increment(spark, initial_versions):
    """Test that versions are incremented on updates."""
    try:
        current_df = spark.table(ENRICHED_TABLE)
        current_versions = {row.id: row.version for row in current_df.select("id", "version").collect()}
        
        print("Version comparison:")
        for article_id in initial_versions:
            initial_ver = initial_versions[article_id]
            current_ver = current_versions.get(article_id, 0)
            print(f"  {article_id}: {initial_ver} → {current_ver}")
            
            if current_ver <= initial_ver:
                print(f"❌ Version not incremented for {article_id}")
                return False
        
        print("✅ Versions properly incremented on updates")
        return True
        
    except Exception as e:
        print(f"❌ Error checking version increments: {e}")
        return False

def run_idempotency_test():
    """Run the complete idempotency test."""
    print("=== Enrichment Upsert Idempotency Test (Issue #291) ===")
    print(f"Test date: {TEST_DATE}")
    
    spark = create_test_spark_session()
    
    try:
        # Step 1: Clean up previous test data
        print("1. Cleaning up previous test data...")
        try:
            spark.sql(f"DROP TABLE IF EXISTS {RAW_TABLE}")
            spark.sql(f"DROP TABLE IF EXISTS {ENRICHED_TABLE}")
        except:
            pass
        
        # Step 2: Create test data
        print("2. Creating test data...")
        create_test_data(spark)
        
        # Step 3: Run enrichment job first time
        print("3. Running enrichment job (first time)...")
        success1 = run_enrichment_job()
        
        if not success1:
            print("❌ First enrichment run failed")
            return False
        
        # Step 4: Validate first run results
        print("4. Validating first run results...")
        if not validate_enrichment_results(spark):
            return False
        
        # Get initial state
        initial_count = spark.table(ENRICHED_TABLE).count()
        initial_versions = {row.id: row.version for row in spark.table(ENRICHED_TABLE).select("id", "version").collect()}
        
        print(f"Initial enriched count: {initial_count}")
        print(f"Initial versions: {initial_versions}")
        
        # Step 5: Run enrichment job second time (idempotency test)
        print("5. Running enrichment job (second time for idempotency test)...")
        time.sleep(2)  # Brief pause
        
        success2 = run_enrichment_job()
        
        if not success2:
            print("❌ Second enrichment run failed")
            return False
        
        # Step 6: Validate idempotency
        print("6. Validating idempotency...")
        final_count = spark.table(ENRICHED_TABLE).count()
        
        print(f"Final enriched count: {final_count}")
        
        # Check count hasn't changed (no new duplicates)
        if final_count != initial_count:
            print(f"❌ Record count changed: {initial_count} → {final_count}")
            return False
        
        # Check for duplicates
        if not validate_idempotency(spark):
            return False
        
        # Check version increments
        if not test_version_increment(spark, initial_versions):
            return False
        
        print("✅ DoD validated: Re-running for a day updates rows in place (no dupes)")
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    finally:
        spark.stop()

if __name__ == "__main__":
    success = run_idempotency_test()
    exit(0 if success else 1)
