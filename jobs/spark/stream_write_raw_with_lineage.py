"""
Streaming job with OpenLineage data lineage tracking
Issue #296

Enhanced version of stream_write_raw_exactly_once.py with OpenLineage integration
for tracking data lineage from Kafka to Iceberg tables.
"""
import os
import sys
import signal
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from jobs.spark.openlineage_config import create_spark_session_with_lineage, add_lineage_metadata, log_lineage_event
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

def create_table_if_not_exists_with_lineage(spark):
    """Create the raw table if it doesn't exist, with lineage tracking."""
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
        processed_at TIMESTAMP,
        lineage_job_id STRING
    ) USING iceberg
    PARTITIONED BY (days(published_at))
    TBLPROPERTIES (
        'write.format.default'='parquet',
        'write.parquet.compression-codec'='snappy',
        'openlineage.enabled'='true'
    )
    """
    
    spark.sql(create_table_sql)
    print(f"✓ Ensured {ICEBERG_TABLE} table exists with lineage metadata")
    
    # Log table creation/verification
    log_lineage_event(spark, "table_ready", ICEBERG_TABLE, "create_or_verify")

def read_kafka_stream_with_lineage(spark):
    """Read streaming data from Kafka with lineage tracking."""
    print(f"📖 Reading from Kafka topic: {KAFKA_TOPIC}")
    
    # Log source read event
    log_lineage_event(spark, "stream_start", KAFKA_TOPIC, "read")
    
    return spark.readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", KAFKA_TOPIC) \
        .option("startingOffsets", "earliest") \
        .option("failOnDataLoss", "false") \
        .option("kafka.consumer.group.id", "exactly-once-consumer-with-lineage") \
        .option("kafka.consumer.enable.auto.commit", "false") \
        .load()

def parse_and_transform_with_lineage(raw_stream, spark):
    """Parse Kafka messages and add lineage metadata."""
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
    
    # Flatten article structure and add lineage metadata
    flattened_stream = article_stream.select(
        col("article.id"),
        col("article.published_at"),
        col("article.title"),
        col("article.body"),
        col("article.source"),
        col("article.url"),
        col("kafka_partition"),
        col("kafka_offset"),
        col("processed_at"),
        lit(spark.conf.get("spark.app.id", "unknown")).alias("lineage_job_id")
    )
    
    # Log transformation event
    log_lineage_event(spark, "transform", "kafka_to_iceberg", "transform")
    
    return flattened_stream

def setup_graceful_shutdown_with_lineage(query, spark):
    """Setup graceful shutdown handler with lineage logging."""
    def signal_handler(signum, frame):
        print("\n🛑 Received shutdown signal, stopping gracefully...")
        log_lineage_event(spark, "shutdown", "streaming_job", "stop")
        query.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

def write_to_iceberg_with_lineage(spark, parsed_stream):
    """Write stream to Iceberg with lineage tracking using foreachBatch."""
    
    def write_batch_with_lineage(batch_df, batch_id):
        """Write each batch with lineage tracking."""
        if batch_df.count() > 0:
            print(f"📝 Processing batch {batch_id} with {batch_df.count()} records")
            
            # Log batch start
            log_lineage_event(spark, "batch_start", f"batch_{batch_id}", "write")
            
            # Create temporary view for MERGE operation
            batch_df.createOrReplaceTempView(f"kafka_batch_{batch_id}")
            
            # Use MERGE INTO for idempotent writes (prevents duplicates)
            merge_sql = f"""
            MERGE INTO {ICEBERG_TABLE} t
            USING kafka_batch_{batch_id} s
            ON t.id = s.id
            WHEN MATCHED THEN UPDATE SET 
                t.published_at = s.published_at,
                t.title = s.title,
                t.body = s.body,
                t.source = s.source,
                t.url = s.url,
                t.kafka_partition = s.kafka_partition,
                t.kafka_offset = s.kafka_offset,
                t.processed_at = s.processed_at,
                t.lineage_job_id = s.lineage_job_id
            WHEN NOT MATCHED THEN INSERT (
                id, published_at, title, body, source, url,
                kafka_partition, kafka_offset, processed_at, lineage_job_id
            ) VALUES (
                s.id, s.published_at, s.title, s.body, s.source, s.url,
                s.kafka_partition, s.kafka_offset, s.processed_at, s.lineage_job_id
            )
            """
            
            spark.sql(merge_sql)
            
            # Log batch completion
            log_lineage_event(spark, "batch_complete", f"batch_{batch_id}", "write")
            print(f"✓ Batch {batch_id} written successfully with lineage tracking")
    
    return parsed_stream.writeStream \
        .foreachBatch(write_batch_with_lineage) \
        .outputMode("update") \
        .option("checkpointLocation", CHECKPOINT_LOCATION) \
        .trigger(processingTime='10 seconds') \
        .start()

def validate_lineage_setup(spark):
    """Validate OpenLineage configuration for streaming job."""
    print("🔍 Validating OpenLineage setup for streaming...")
    
    # Check required configurations
    required_configs = [
        "spark.extraListeners",
        "spark.openlineage.transport.type",
        "spark.openlineage.transport.url",
        "spark.openlineage.namespace"
    ]
    
    missing_configs = []
    for config in required_configs:
        value = spark.conf.get(config, None)
        if value:
            print(f"✅ {config}: {value}")
        else:
            missing_configs.append(config)
            print(f"❌ {config}: Missing")
    
    if missing_configs:
        print(f"⚠️  Missing OpenLineage configurations: {missing_configs}")
        return False
    
    print("✅ OpenLineage configuration validated")
    return True

def main():
    """Main function for streaming with lineage tracking."""
    print("🚀 Starting streaming job with OpenLineage tracking")
    print(f"Topic: {KAFKA_TOPIC}")
    print(f"Table: {ICEBERG_TABLE}")
    print(f"Checkpoint: {CHECKPOINT_LOCATION}")
    
    spark = None
    query = None
    
    try:
        # Create Spark session with OpenLineage configuration
        spark = create_spark_session_with_lineage(
            app_name="StreamWriteRawWithLineage",
            additional_configs={
                "spark.sql.streaming.checkpointLocation": CHECKPOINT_LOCATION,
                "spark.sql.streaming.minBatchesToRetain": "10",
                "spark.sql.adaptive.enabled": "true",
                "spark.sql.adaptive.coalescePartitions.enabled": "true"
            }
        )
        
        # Validate OpenLineage setup
        if not validate_lineage_setup(spark):
            print("⚠️  Continuing without full lineage validation...")
        
        # Add lineage metadata for this job
        add_lineage_metadata(
            spark,
            job_type="streaming",
            source_system="kafka",
            target_system="iceberg"
        )
        
        # Create table if needed
        create_table_if_not_exists_with_lineage(spark)
        
        # Read from Kafka
        raw_stream = read_kafka_stream_with_lineage(spark)
        
        # Parse and transform with lineage tracking
        parsed_stream = parse_and_transform_with_lineage(raw_stream, spark)
        
        # Write to Iceberg with lineage tracking
        query = write_to_iceberg_with_lineage(spark, parsed_stream)
        
        # Setup graceful shutdown with lineage logging
        setup_graceful_shutdown_with_lineage(query, spark)
        
        print("✅ Streaming job started successfully with lineage tracking")
        print("📊 Monitoring progress...")
        
        # Monitor progress with lineage events
        while query.isActive:
            progress = query.lastProgress
            if progress:
                input_rate = progress.get('inputRowsPerSecond', 0)
                processing_rate = progress.get('processingRowsPerSecond', 0)
                print(f"📈 Input: {input_rate:.1f} rows/sec, Processing: {processing_rate:.1f} rows/sec")
                
                # Log progress event
                if input_rate > 0:
                    log_lineage_event(spark, "progress", "streaming_metrics", "monitor")
            
            query.awaitTermination(30)  # Check every 30 seconds
    
    except Exception as e:
        print(f"❌ Error in streaming job: {e}")
        if spark:
            log_lineage_event(spark, "error", "streaming_job", "fail")
        raise
    
    finally:
        if query and query.isActive:
            print("🛑 Stopping streaming query...")
            log_lineage_event(spark, "stop", "streaming_job", "shutdown")
            query.stop()
        
        if spark:
            spark.stop()
        
        print("✅ Streaming job stopped with lineage tracking")

if __name__ == "__main__":
    main()
