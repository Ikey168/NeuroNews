"""
Kafka-based batch backfill job
Issue #295

This script performs batch backfills from Kafka topics for specific offset ranges
or timestamp windows, enabling gap filling while streaming is paused.
"""
import argparse
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import StructType, StructField, StringType, TimestampType
from datetime import datetime
import os

# Article schema for JSON parsing
article_schema = StructType([
    StructField("id", StringType(), True),
    StructField("published_at", TimestampType(), True),
    StructField("title", StringType(), True),
    StructField("body", StringType(), True),
    StructField("source", StringType(), True),
    StructField("url", StringType(), True)
])

def create_spark_session(app_name="KafkaBackfill"):
    """Create Spark session for batch backfill."""
    return SparkSession.builder \
        .appName(app_name) \
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
        .config("spark.sql.adaptive.enabled", "true") \
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
        .getOrCreate()

def read_kafka_batch_by_offsets(spark, topic, bootstrap_servers, start_offset, end_offset):
    """Read Kafka data by offset range."""
    # Build offset range for all partitions
    # Format: {"topic":{"partition":{"starting_offset","ending_offset"}}}
    
    print(f"Reading Kafka topic {topic} from offset {start_offset} to {end_offset}")
    
    return spark.read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", bootstrap_servers) \
        .option("subscribe", topic) \
        .option("startingOffsets", f'{{"{}":{{0:{}}}}}'.format(topic, start_offset)) \
        .option("endingOffsets", f'{{"{}":{{0:{}}}}}'.format(topic, end_offset)) \
        .load()

def read_kafka_batch_by_timestamp(spark, topic, bootstrap_servers, start_timestamp, end_timestamp):
    """Read Kafka data by timestamp range."""
    print(f"Reading Kafka topic {topic} from {start_timestamp} to {end_timestamp}")
    
    # Convert timestamps to milliseconds since epoch
    start_ts = int(datetime.strptime(start_timestamp, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    end_ts = int(datetime.strptime(end_timestamp, "%Y-%m-%d %H:%M:%S").timestamp() * 1000)
    
    return spark.read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", bootstrap_servers) \
        .option("subscribe", topic) \
        .option("startingOffsets", f'{{"{}":{{0:{}}}}}'.format(topic, start_ts)) \
        .option("endingOffsets", f'{{"{}":{{0:{}}}}}'.format(topic, end_ts)) \
        .load()

def read_kafka_batch_from_beginning(spark, topic, bootstrap_servers):
    """Read all available data from Kafka topic."""
    print(f"Reading all available data from Kafka topic {topic}")
    
    return spark.read \
        .format("kafka") \
        .option("kafka.bootstrap.servers", bootstrap_servers) \
        .option("subscribe", topic) \
        .option("startingOffsets", "earliest") \
        .option("endingOffsets", "latest") \
        .load()

def parse_kafka_messages(raw_df):
    """Parse Kafka messages and extract article data."""
    # Parse JSON messages
    parsed_df = raw_df.select(
        col("key").cast("string").alias("message_key"),
        col("value").cast("string").alias("message_value"),
        col("timestamp").alias("kafka_timestamp"),
        col("partition").alias("kafka_partition"),
        col("offset").alias("kafka_offset")
    )
    
    # Extract article data from JSON
    article_df = parsed_df.select(
        from_json(col("message_value"), article_schema).alias("article"),
        col("kafka_partition"),
        col("kafka_offset"),
        current_timestamp().alias("processed_at")
    )
    
    # Flatten article structure
    flattened_df = article_df.select(
        col("article.id"),
        col("article.published_at"),
        col("article.title"),
        col("article.body"),
        col("article.source"),
        col("article.url"),
        col("kafka_partition"),
        col("kafka_offset"),
        col("processed_at")
    ).filter(col("id").isNotNull())  # Filter out invalid records
    
    return flattened_df

def write_to_iceberg_idempotent(spark, df, table_name):
    """Write to Iceberg table using MERGE INTO for idempotency."""
    if df.count() == 0:
        print("No data to write")
        return
    
    # Create temporary view
    df.createOrReplaceTempView("backfill_data")
    
    # Use MERGE INTO for idempotent writes
    merge_sql = f"""
    MERGE INTO {table_name} t
    USING backfill_data s
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
    print(f"✓ Backfill data merged into {table_name}")

def validate_backfill_results(spark, table_name, expected_range=None):
    """Validate backfill results."""
    # Count total records
    total_count = spark.sql(f"SELECT COUNT(*) as count FROM {table_name}").collect()[0]['count']
    print(f"Total records in {table_name}: {total_count}")
    
    # Check for duplicates
    duplicate_count = spark.sql(f"""
        SELECT COUNT(*) as duplicates 
        FROM (
            SELECT id, COUNT(*) as cnt 
            FROM {table_name} 
            GROUP BY id 
            HAVING cnt > 1
        )
    """).collect()[0]['duplicates']
    
    if duplicate_count > 0:
        print(f"⚠️  Found {duplicate_count} duplicate IDs")
        return False
    else:
        print("✓ No duplicates found")
    
    # Check data quality
    quality_check = spark.sql(f"""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN title IS NULL THEN 1 END) as null_titles,
            COUNT(CASE WHEN body IS NULL THEN 1 END) as null_bodies,
            COUNT(CASE WHEN source IS NULL THEN 1 END) as null_sources
        FROM {table_name}
    """).collect()[0]
    
    print(f"Data quality: {quality_check['total']} total, "
          f"{quality_check['null_titles']} null titles, "
          f"{quality_check['null_bodies']} null bodies, "
          f"{quality_check['null_sources']} null sources")
    
    return True

def main():
    """Main function for Kafka backfill."""
    parser = argparse.ArgumentParser(description='Kafka batch backfill for Iceberg tables')
    parser.add_argument('--topic', required=True, help='Kafka topic name')
    parser.add_argument('--bootstrap-servers', default='kafka:9092', help='Kafka bootstrap servers')
    parser.add_argument('--table', required=True, help='Target Iceberg table name')
    
    # Offset-based options
    parser.add_argument('--start-offset', type=int, help='Starting offset for backfill')
    parser.add_argument('--end-offset', type=int, help='Ending offset for backfill')
    
    # Timestamp-based options
    parser.add_argument('--start-timestamp', help='Start timestamp (YYYY-MM-DD HH:MM:SS)')
    parser.add_argument('--end-timestamp', help='End timestamp (YYYY-MM-DD HH:MM:SS)')
    
    # Special options
    parser.add_argument('--from-beginning', action='store_true', help='Read from beginning of topic')
    
    # Performance options
    parser.add_argument('--partitions', type=int, default=None, help='Number of partitions for processing')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not any([
        args.start_offset is not None and args.end_offset is not None,
        args.start_timestamp and args.end_timestamp,
        args.from_beginning
    ]):
        print("❌ Must specify either offset range, timestamp range, or --from-beginning")
        return 1
    
    spark = None
    try:
        print("🚀 Starting Kafka batch backfill")
        print(f"Topic: {args.topic}")
        print(f"Table: {args.table}")
        
        # Create Spark session
        spark = create_spark_session()
        
        # Read data based on specified range
        if args.from_beginning:
            raw_df = read_kafka_batch_from_beginning(spark, args.topic, args.bootstrap_servers)
        elif args.start_offset is not None:
            raw_df = read_kafka_batch_by_offsets(
                spark, args.topic, args.bootstrap_servers, 
                args.start_offset, args.end_offset
            )
        else:
            raw_df = read_kafka_batch_by_timestamp(
                spark, args.topic, args.bootstrap_servers,
                args.start_timestamp, args.end_timestamp
            )
        
        # Parse messages
        parsed_df = parse_kafka_messages(raw_df)
        
        # Repartition if specified
        if args.partitions:
            parsed_df = parsed_df.repartition(args.partitions)
        
        print(f"Processed {parsed_df.count()} records for backfill")
        
        # Write to Iceberg
        write_to_iceberg_idempotent(spark, parsed_df, args.table)
        
        # Validate results
        if validate_backfill_results(spark, args.table):
            print("✅ Backfill completed successfully")
            return 0
        else:
            print("❌ Backfill validation failed")
            return 1
    
    except Exception as e:
        print(f"❌ Backfill failed: {e}")
        return 1
    
    finally:
        if spark:
            spark.stop()

if __name__ == "__main__":
    sys.exit(main())
