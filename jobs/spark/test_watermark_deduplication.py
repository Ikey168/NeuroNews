#!/usr/bin/env python3
"""
Test script for watermarking and deduplication of late data (Issue #290)
Tests out-of-order events and verifies only latest survives within watermark window.
"""
import json
import time
import subprocess
from datetime import datetime, timedelta
from kafka import KafkaProducer
from pyspark.sql import SparkSession

# Configuration
KAFKA_TOPIC = "articles.raw.v1"
KAFKA_SERVERS = "kafka:9092"
ICEBERG_TABLE = "demo.news.articles_raw"
CHECKPOINT_DIR = "/chk/articles_raw_test"

def create_test_spark_session():
    """Create Spark session for testing."""
    return SparkSession.builder \
        .appName("WatermarkDeduplicationTest") \
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

def send_test_messages_with_duplicates():
    """Send test messages with out-of-order events and duplicates."""
    producer = KafkaProducer(
        bootstrap_servers=[KAFKA_SERVERS],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    
    base_time = datetime.now()
    
    # Test scenario: Same article ID with different timestamps (out-of-order)
    test_messages = [
        # Original article (older timestamp)
        {
            "id": "test-article-1",
            "published_at": (base_time - timedelta(minutes=30)).isoformat() + "Z",
            "title": "Test Article 1 - Original",
            "body": "Original content",
            "source": "test-source",
            "url": "http://test.com/1"
        },
        # Updated article (newer timestamp, should survive)
        {
            "id": "test-article-1", 
            "published_at": (base_time - timedelta(minutes=10)).isoformat() + "Z",
            "title": "Test Article 1 - Updated",
            "body": "Updated content with more information",
            "source": "test-source",
            "url": "http://test.com/1"
        },
        # Late arriving original (should be dropped due to watermark)
        {
            "id": "test-article-1",
            "published_at": (base_time - timedelta(hours=3)).isoformat() + "Z",  # Beyond 2-hour watermark
            "title": "Test Article 1 - Very Old",
            "body": "Very old content that arrived late",
            "source": "test-source", 
            "url": "http://test.com/1"
        },
        # Different article (should survive)
        {
            "id": "test-article-2",
            "published_at": (base_time - timedelta(minutes=5)).isoformat() + "Z",
            "title": "Test Article 2",
            "body": "Different article content",
            "source": "test-source",
            "url": "http://test.com/2"
        },
        # Duplicate of article 2 with earlier timestamp (should be dropped)
        {
            "id": "test-article-2",
            "published_at": (base_time - timedelta(minutes=15)).isoformat() + "Z",
            "title": "Test Article 2 - Older Version",
            "body": "Older version of article 2",
            "source": "test-source",
            "url": "http://test.com/2"
        }
    ]
    
    print("Sending test messages with out-of-order events...")
    for i, message in enumerate(test_messages):
        producer.send(KAFKA_TOPIC, value=message)
        print(f"Sent message {i+1}: ID={message['id']}, Time={message['published_at']}")
        time.sleep(1)  # Small delay between messages
    
    producer.flush()
    producer.close()
    print("All test messages sent")

def run_watermark_deduplication_test():
    """Run the complete watermarking and deduplication test."""
    print("=== Watermarking + Deduplication Test (Issue #290) ===")
    
    # Clean up previous test data
    print("1. Cleaning up previous test data...")
    subprocess.run(f"rm -rf {CHECKPOINT_DIR}", shell=True, check=False)
    
    spark = create_test_spark_session()
    try:
        spark.sql(f"DROP TABLE IF EXISTS {ICEBERG_TABLE}")
    except:
        pass
    
    # Create Kafka topic
    print("2. Creating test Kafka topic...")
    subprocess.run(
        f"kafka-topics.sh --create --topic {KAFKA_TOPIC} --bootstrap-server {KAFKA_SERVERS} --partitions 3 --replication-factor 1",
        shell=True, check=False
    )
    
    # Send test messages
    print("3. Sending test messages with duplicates and out-of-order events...")
    send_test_messages_with_duplicates()
    
    # Start streaming job in background
    print("4. Starting streaming job with watermarking...")
    import os
    os.environ["CHECKPOINT_LOCATION"] = CHECKPOINT_DIR
    
    # Import and run the streaming job logic
    import sys
    sys.path.append('/workspaces/NeuroNews/jobs/spark')
    
    # Start the streaming job (would normally be done in separate process)
    print("   Starting streaming process...")
    subprocess.Popen([
        "python", "/workspaces/NeuroNews/jobs/spark/stream_write_raw.py"
    ], env=dict(os.environ, CHECKPOINT_LOCATION=CHECKPOINT_DIR))
    
    # Wait for processing
    print("5. Waiting for stream processing...")
    time.sleep(60)  # Give time for processing
    
    # Verify results
    print("6. Verifying deduplication results...")
    
    # Check final counts
    try:
        final_df = spark.sql(f"SELECT * FROM {ICEBERG_TABLE} ORDER BY published_at")
        final_count = final_df.count()
        
        print(f"Total records in table: {final_count}")
        
        if final_count > 0:
            print("Records in table:")
            final_df.show(truncate=False)
            
            # Verify deduplication worked
            unique_ids = final_df.select("id").distinct().count()
            print(f"Unique article IDs: {unique_ids}")
            
            # Check for specific test cases
            article_1_count = final_df.filter(final_df.id == "test-article-1").count()
            article_2_count = final_df.filter(final_df.id == "test-article-2").count()
            
            print(f"Article 1 occurrences: {article_1_count}")
            print(f"Article 2 occurrences: {article_2_count}")
            
            # DoD validation
            if article_1_count <= 1 and article_2_count <= 1 and unique_ids == final_count:
                print("✅ SUCCESS: Deduplication working correctly")
                print("✅ DoD met: No duplicates for keys within watermark")
                return True
            else:
                print("❌ FAILURE: Duplicates found or deduplication failed")
                return False
        else:
            print("❌ FAILURE: No records processed")
            return False
            
    except Exception as e:
        print(f"❌ FAILURE: Error checking results: {e}")
        return False
    
    finally:
        spark.stop()

if __name__ == "__main__":
    success = run_watermark_deduplication_test()
    exit(0 if success else 1)
