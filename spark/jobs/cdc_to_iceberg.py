#!/usr/bin/env python3
"""
Spark Structured Streaming job for CDC to Iceberg upserts.

Consumes Debezium CDC events from Kafka topic 'neuronews.public.articles'
and upserts them into an Iceberg v2 table with merge-on-read capabilities.

The job expects flattened CDC records (via Debezium ExtractNewRecordState SMT).
"""

from pyspark.sql import SparkSession, functions as F


def create_spark_session():
    """Create Spark session with Iceberg extensions."""
    return (SparkSession.builder
            .appName("cdc_to_iceberg")
            .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
            .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
            .config("spark.sql.catalog.local.type", "hadoop")
            .config("spark.sql.catalog.local.warehouse", "/warehouse")
            .getOrCreate())


def create_iceberg_table(spark):
    """Create Iceberg table with v2 format and upsert capabilities."""
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
            updated_at   timestamp
        )
        USING iceberg
        PARTITIONED BY (days(published_at))
        TBLPROPERTIES (
            'format-version'='2',
            'write.delete.mode'='merge-on-read',
            'write.update.mode'='merge-on-read',
            'write.upsert.enabled'='true'
        )
    """)


def upsert_batch(batch_df, batch_id):
    """
    Upsert function for each micro-batch.
    
    Handles CDC operations:
    - INSERT: New records
    - UPDATE: Modified records  
    - DELETE: Tombstone records
    """
    if batch_df.count() == 0:
        return
        
    # Create temp view for the batch
    batch_df.createOrReplaceTempView("cdc")
    
    # Get Spark session from batch dataframe
    spark = batch_df.sparkSession
    
    # Perform MERGE operation with deduplication
    spark.sql("""
        MERGE INTO local.news.articles t
        USING (
            SELECT * FROM cdc 
            QUALIFY row_number() OVER (
                PARTITION BY article_id 
                ORDER BY ts_ms DESC
            ) = 1
        ) s
        ON t.article_id = s.article_id
        WHEN MATCHED AND s.op = 'd' THEN DELETE
        WHEN MATCHED THEN UPDATE SET *
        WHEN NOT MATCHED AND s.op != 'd' THEN INSERT *
    """)


def main():
    """Main streaming job execution."""
    spark = create_spark_session()
    
    try:
        # Create Iceberg table (idempotent)
        create_iceberg_table(spark)
        
        # Read from Kafka stream
        df = (spark.readStream
              .format("kafka")
              .option("kafka.bootstrap.servers", "localhost:9092")
              .option("subscribe", "neuronews.public.articles")
              .option("startingOffsets", "earliest")
              .load())
        
        # Parse JSON and flatten structure
        # Debezium unwrap gives us flat rows; add op from header/field if present
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
                source:struct<ts_ms:long,lsn:long,db:string,table:string>
            >
        """
        
        parsed = df.select(
            F.from_json(F.col("value").cast("string"), value_schema).alias("v")
        )
        
        flat = (parsed.select("v.*")
                .withColumn("ts_ms", F.col("source.ts_ms")))
        
        # Start streaming query with upsert logic
        query = (flat.writeStream
                 .foreachBatch(upsert_batch)
                 .option("checkpointLocation", "/chk/cdc_to_iceberg")
                 .outputMode("update")
                 .start())
        
        print("CDC to Iceberg streaming job started. Waiting for termination...")
        query.awaitTermination()
        
    except Exception as e:
        print(f"Error in CDC streaming job: {e}")
        raise
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
