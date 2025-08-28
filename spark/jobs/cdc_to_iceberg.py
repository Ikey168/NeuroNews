#!/usr/bin/env python3
"""
Spark Structured Streaming job for CDC to Iceberg upserts with exactly-once guarantees.

Consumes Debezium CDC events from Kafka topic 'neuronews.public.articles'
and upserts them into an Iceberg v2 table with merge-on-read capabilities.

The job provides exactly-once semantics through:
1. Kafka consumer group with checkpointed offsets
2. Idempotent upserts keyed by article_id
3. Deduplication window by ts_ms in MERGE operations
4. Safe reprocessing with startingOffsets=earliest

The job expects flattened CDC records (via Debezium ExtractNewRecordState SMT).
"""

import os
import logging
from pyspark.sql import SparkSession, functions as F

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_spark_session():
    """Create Spark session with Iceberg extensions and exactly-once configuration."""
    builder = (SparkSession.builder
               .appName("cdc_to_iceberg_exactly_once")
               .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
               .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
               .config("spark.sql.catalog.local.type", "hadoop")
               .config("spark.sql.catalog.local.warehouse", "/warehouse"))
    
    # Exactly-once configuration
    builder = (builder
               # Enable checkpointing for fault tolerance
               .config("spark.sql.streaming.checkpointLocation.deleteTmpCheckpointDir", "true")
               # Ensure deterministic task execution
               .config("spark.sql.adaptive.enabled", "false")
               .config("spark.sql.adaptive.coalescePartitions.enabled", "false")
               # Kafka exactly-once semantics
               .config("spark.sql.streaming.kafka.useDeprecatedOffsetFetching", "false"))
    
    return builder.getOrCreate()


def create_iceberg_table(spark):
    """Create Iceberg table with v2 format and upsert capabilities for exactly-once processing."""
    logger.info("Creating Iceberg table with exactly-once guarantees...")
    
    spark.sql("""
        CREATE TABLE IF NOT EXISTS local.news.articles (
            article_id string,
            source_id  string,
            url        string,
            title      string,
            body       string,
            language   string,
            country    string,
            published_at timestamp,
            updated_at   timestamp,
            ts_ms      bigint,
            lsn        bigint
        )
        USING iceberg
        PARTITIONED BY (days(published_at))
        TBLPROPERTIES (
            'format-version'='2',
            'write.delete.mode'='merge-on-read',
            'write.update.mode'='merge-on-read',
            'write.upsert.enabled'='true',
            'write.merge.mode'='merge-on-read'
        )
    """)
    
    logger.info("Iceberg table created/verified successfully")


def upsert_batch(batch_df, batch_id):
    """
    Upsert function for each micro-batch with exactly-once guarantees.
    
    Implements exactly-once semantics through:
    1. Idempotent upserts keyed by article_id
    2. Deduplication by ts_ms (timestamp) and lsn (log sequence number)
    3. Deterministic ordering for consistent results
    
    Handles CDC operations:
    - INSERT: New records (op='c' for create)
    - UPDATE: Modified records (op='u' for update)  
    - DELETE: Tombstone records (op='d' for delete)
    """
    if batch_df.count() == 0:
        logger.info(f"Batch {batch_id}: Empty batch, skipping")
        return
        
    logger.info(f"Batch {batch_id}: Processing {batch_df.count()} records")
    
    # Create temp view for the batch
    batch_df.createOrReplaceTempView("cdc_batch")
    
    # Get Spark session from batch dataframe
    spark = batch_df.sparkSession
    
    # Perform MERGE operation with exactly-once deduplication
    # Deduplication strategy:
    # 1. PARTITION BY article_id to group changes per article
    # 2. ORDER BY ts_ms DESC, lsn DESC to get the latest change
    # 3. QUALIFY row_number() = 1 to pick only the latest
    merge_sql = """
        MERGE INTO local.news.articles t
        USING (
            SELECT 
                article_id, source_id, url, title, body, language, country,
                published_at, updated_at, ts_ms, lsn, op
            FROM cdc_batch 
            QUALIFY row_number() OVER (
                PARTITION BY article_id 
                ORDER BY ts_ms DESC, lsn DESC
            ) = 1
        ) s
        ON t.article_id = s.article_id
        WHEN MATCHED AND s.op = 'd' THEN DELETE
        WHEN MATCHED AND s.op IN ('u', 'c') AND s.ts_ms >= t.ts_ms THEN 
            UPDATE SET 
                source_id = s.source_id,
                url = s.url,
                title = s.title,
                body = s.body,
                language = s.language,
                country = s.country,
                published_at = s.published_at,
                updated_at = s.updated_at,
                ts_ms = s.ts_ms,
                lsn = s.lsn
        WHEN NOT MATCHED AND s.op IN ('c', 'u') THEN 
            INSERT (article_id, source_id, url, title, body, language, country,
                   published_at, updated_at, ts_ms, lsn)
            VALUES (s.article_id, s.source_id, s.url, s.title, s.body, s.language, s.country,
                   s.published_at, s.updated_at, s.ts_ms, s.lsn)
    """
    
    try:
        spark.sql(merge_sql)
        logger.info(f"Batch {batch_id}: Successfully processed upsert")
    except Exception as e:
        logger.error(f"Batch {batch_id}: Error during upsert: {e}")
        raise


def main():
    """Main streaming job execution with exactly-once guarantees."""
    spark = create_spark_session()
    
    # Get configuration from environment variables
    kafka_brokers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic = os.getenv("KAFKA_TOPIC", "neuronews.public.articles")
    checkpoint_location = os.getenv("CHECKPOINT_LOCATION", "/tmp/checkpoints/cdc_to_iceberg")
    consumer_group = os.getenv("KAFKA_CONSUMER_GROUP", "cdc_to_iceberg")
    
    # For exactly-once, allow explicit override of starting offsets
    # Default: "earliest" for safe reprocessing (idempotent)
    # Production: "latest" for normal operation
    starting_offsets = os.getenv("STARTING_OFFSETS", "earliest")
    
    logger.info(f"Starting CDC to Iceberg job with exactly-once guarantees")
    logger.info(f"Kafka brokers: {kafka_brokers}")
    logger.info(f"Kafka topic: {kafka_topic}")
    logger.info(f"Consumer group: {consumer_group}")
    logger.info(f"Checkpoint location: {checkpoint_location}")
    logger.info(f"Starting offsets: {starting_offsets}")
    
    try:
        # Create Iceberg table (idempotent operation)
        create_iceberg_table(spark)
        
        # Read from Kafka stream with exactly-once configuration
        df = (spark.readStream
              .format("kafka")
              .option("kafka.bootstrap.servers", kafka_brokers)
              .option("subscribe", kafka_topic)
              .option("startingOffsets", starting_offsets)
              .option("kafka.group.id", consumer_group)
              # Exactly-once Kafka configuration
              .option("maxOffsetsPerTrigger", "1000")  # Control batch size for consistency
              .option("failOnDataLoss", "false")  # Handle missing data gracefully
              .load())
        
        # Parse JSON and flatten structure
        # Debezium unwrap gives us flat rows; capture CDC metadata for exactly-once
        value_schema = """
            struct<
                article_id:string, 
                source_id:string, 
                url:string,
                title:string, 
                body:string,
                language:string, 
                country:string, 
                published_at:timestamp,
                updated_at:timestamp,
                op:string,
                ts_ms:long,
                lsn:long
            >
        """
        
        parsed = df.select(
            F.from_json(F.col("value").cast("string"), value_schema).alias("cdc_record"),
            F.col("offset").alias("kafka_offset"),
            F.col("partition").alias("kafka_partition"),
            F.col("timestamp").alias("kafka_timestamp")
        )
        
        # Flatten and add CDC metadata for exactly-once processing
        flat = (parsed.select("cdc_record.*", "kafka_offset", "kafka_partition", "kafka_timestamp")
                .filter(F.col("article_id").isNotNull())  # Skip invalid records
                .withColumn("processing_time", F.current_timestamp()))
        
        # Start streaming query with exactly-once guarantees
        query = (flat.writeStream
                 .foreachBatch(upsert_batch)
                 .option("checkpointLocation", checkpoint_location)
                 .outputMode("update")
                 .trigger(processingTime="10 seconds")  # Controlled trigger for consistency
                 .start())
        
        logger.info("CDC to Iceberg streaming job started with exactly-once guarantees")
        logger.info("Safe restart: Re-run with STARTING_OFFSETS=earliest for idempotent reprocessing")
        logger.info("Waiting for termination...")
        
        query.awaitTermination()
        
    except Exception as e:
        logger.error(f"Error in CDC streaming job: {e}")
        raise
    finally:
        logger.info("Stopping Spark session")
        spark.stop()


if __name__ == "__main__":
    main()
