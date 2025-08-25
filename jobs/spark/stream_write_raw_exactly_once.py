"""
Enhanced streaming job with exactly-once guarantees
Issue #294

This version of the streaming job includes enhanced failure handling,
checkpoint management, and exactly-once delivery guarantees.
"""
import os
import sys
import signal
from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, current_timestamp, lit
from pyspark.sql.types import StructType, StructField, StringType, TimestampType

# Configuration
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "articles.raw.v1")
ICEBERG_TABLE = os.getenv("ICEBERG_TABLE", "demo.news.articles_raw")
CHECKPOINT_LOCATION = os.getenv("CHECKPOINT_LOCATION", "/chk/articles_raw")

# Article schema for JSON parsing
article_schema = StructType([
    StructField("id", StringType(), True),
    StructField("published_at", TimestampType(), True),
    StructField("title", StringType(), True),
    StructField("body", StringType(), True),
    StructField("source", StringType(), True),
    StructField("url", StringType(), True)
])

def create_spark_session():
    """Create Spark session with exactly-once configurations."""
    return SparkSession.builder \
        .appName("ExactlyOnceStreamWriteRaw") \
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
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.sql.streaming.minBatchesToRetain", "10") \
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .getOrCreate()

def create_table_if_not_exists(spark):
    """Create the raw table if it doesn't exist."""
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {ICEBERG_TABLE} (
        id STRING,
        published_at TIMESTAMP,
        title STRING,
        body STRING,
        source STRING,
        url STRING,
        kafka_partition INT,
        kafka_offset BIGINT,
        processed_at TIMESTAMP
    ) USING iceberg
    PARTITIONED BY (days(published_at))
    TBLPROPERTIES (
        'write.format.default'='parquet',
        'write.parquet.compression-codec'='snappy'
    )
    """
    
    spark.sql(create_table_sql)
    print(f"✓ Ensured {ICEBERG_TABLE} table exists")

def read_kafka_stream(spark):
    """Read streaming data from Kafka with exactly-once configurations."""
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .option("kafka.consumer.group.id", "exactly-once-consumer") \
        .option("kafka.consumer.enable.auto.commit", "false") \
        .load()

def parse_and_transform(raw_stream):
    """Parse Kafka messages and add metadata for exactly-once processing."""
    # Parse JSON messages
    parsed_stream = raw_stream.select(
        col("key").cast("string").alias("message_key"),
        col("value").cast("string").alias("message_value"),
        col("timestamp").alias("kafka_timestamp"),
        col("partition").alias("kafka_partition"),
        col("offset").alias("kafka_offset")
    )
    
    # Extract article data from JSON
    article_stream = parsed_stream.select(
        from_json(col("message_value"), article_schema).alias("article"),
        col("kafka_partition"),
        col("kafka_offset"),
        current_timestamp().alias("processed_at")
    )
    
    # Flatten article structure and add metadata
    flattened_stream = article_stream.select(
        col("article.id"),
        col("article.published_at"),
        col("article.title"),
        col("article.body"),
        col("article.source"),
        col("article.url"),
        col("kafka_partition"),
        col("kafka_offset"),
        col("processed_at")
    )
    
    return flattened_stream

def setup_graceful_shutdown(query):
    """Setup graceful shutdown handler."""
    def signal_handler(signum, frame):
        print("\n🛑 Received shutdown signal, stopping gracefully...")
        query.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

def write_to_iceberg_exactly_once(spark, parsed_stream):
    """Write stream to Iceberg with exactly-once guarantees."""
    # Use foreachBatch for more control over exactly-once semantics
    def write_batch(batch_df, batch_id):
        if batch_df.count() > 0:
            print(f"Processing batch {batch_id} with {batch_df.count()} records")
            
            # Create temporary view for MERGE operation
            batch_df.createOrReplaceTempView("kafka_batch")
            
            # Use MERGE INTO for idempotent writes (prevents duplicates)
            merge_sql = f"""
            MERGE INTO {ICEBERG_TABLE} t
            USING kafka_batch s
            ON t.id = s.id
            WHEN MATCHED THEN UPDATE SET 
                t.published_at = s.published_at,
                t.title = s.title,
                t.body = s.body,
                t.source = s.source,
                t.url = s.url,
                t.kafka_partition = s.kafka_partition,
                t.kafka_offset = s.kafka_offset,
                t.processed_at = s.processed_at
            WHEN NOT MATCHED THEN INSERT (
                id, published_at, title, body, source, url,
                kafka_partition, kafka_offset, processed_at
            ) VALUES (
                s.id, s.published_at, s.title, s.body, s.source, s.url,
                s.kafka_partition, s.kafka_offset, s.processed_at
            )
            """
            
            spark.sql(merge_sql)
            print(f"✓ Batch {batch_id} written successfully")
    
    return parsed_stream.writeStream \
        .foreachBatch(write_batch) \
        .outputMode("update") \
        .option("checkpointLocation", CHECKPOINT_LOCATION) \
        .trigger(processingTime='10 seconds') \
        .start()

def main():
    """Main function for exactly-once streaming."""
    print("🚀 Starting exactly-once Kafka → Iceberg streaming job")
    print(f"Topic: {KAFKA_TOPIC}")
    print(f"Table: {ICEBERG_TABLE}")
    print(f"Checkpoint: {CHECKPOINT_LOCATION}")
    
    spark = None
    query = None
    
    try:
        # Create Spark session
        spark = create_spark_session()
        
        # Create table if needed
        create_table_if_not_exists(spark)
        
        # Read from Kafka
        raw_stream = read_kafka_stream(spark)
        
        # Parse and transform
        parsed_stream = parse_and_transform(raw_stream)
        
        # Write to Iceberg with exactly-once guarantees
        query = write_to_iceberg_exactly_once(spark, parsed_stream)
        
        # Setup graceful shutdown
        setup_graceful_shutdown(query)
        
        print("✅ Streaming job started successfully")
        print("📊 Monitoring progress...")
        
        # Monitor progress
        while query.isActive:
            progress = query.lastProgress
            if progress:
                input_rate = progress.get('inputRowsPerSecond', 0)
                processing_rate = progress.get('processingRowsPerSecond', 0)
                print(f"Input: {input_rate:.1f} rows/sec, Processing: {processing_rate:.1f} rows/sec")
            
            query.awaitTermination(30)  # Check every 30 seconds
    
    except Exception as e:
        print(f"❌ Error in streaming job: {e}")
        raise
    
    finally:
        if query and query.isActive:
            print("🛑 Stopping streaming query...")
            query.stop()
        
        if spark:
            spark.stop()
        
        print("✅ Streaming job stopped")

if __name__ == "__main__":
    main()
