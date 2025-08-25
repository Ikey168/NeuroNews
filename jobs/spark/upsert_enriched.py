"""
Enrichment upsert job: raw → enriched via Iceberg MERGE INTO
Issue #291

This module implements an enrichment pipeline that:
1. Reads from demo.news.articles_raw table
2. Computes sentiment analysis and entity extraction
3. Upserts to demo.news.articles_enriched using MERGE INTO
4. Handles late/corrected records with idempotent updates
5. Ensures re-running for a day updates rows in place (no duplicates)
"""
import os
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, lit, current_timestamp, regexp_extract, length, split
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, FloatType, ArrayType
from datetime import datetime, timedelta

# Configuration
RAW_TABLE = os.getenv("RAW_TABLE", "demo.news.articles_raw")
ENRICHED_TABLE = os.getenv("ENRICHED_TABLE", "demo.news.articles_enriched")
PROCESS_DATE = os.getenv("PROCESS_DATE", None)  # Format: YYYY-MM-DD, defaults to yesterday

def create_spark_session():
    """Create Spark session with Iceberg support."""
    return SparkSession.builder \
        .appName("EnrichmentUpsert") \
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

def create_enriched_table_if_not_exists(spark):
    """Create the enriched table schema if it doesn't exist."""
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS {ENRICHED_TABLE} (
        id STRING,
        published_at TIMESTAMP,
        title STRING,
        body STRING,
        source STRING,
        url STRING,
        sentiment_score FLOAT,
        sentiment_label STRING,
        entities ARRAY<STRING>,
        keywords ARRAY<STRING>,
        processed_at TIMESTAMP,
        version INT
    ) USING iceberg
    PARTITIONED BY (days(published_at))
    """
    
    spark.sql(create_table_sql)
    print(f"✓ Ensured {ENRICHED_TABLE} table exists")

        # Set write order and distribution mode for performance tuning
        spark.sql(f"ALTER TABLE {ENRICHED_TABLE} WRITE ORDERED BY published_at, id")
        spark.sql(f"ALTER TABLE {ENRICHED_TABLE} SET TBLPROPERTIES ('write.distribution-mode'='hash')")

def get_process_date():
    """Get the date to process (default to yesterday)."""
    if PROCESS_DATE:
        return PROCESS_DATE
    else:
        yesterday = datetime.now() - timedelta(days=1)
        return yesterday.strftime("%Y-%m-%d")

def read_raw_articles(spark, process_date):
    """Read raw articles for the specified date."""
    # Read from raw table for the specific date
    raw_df = spark.table(RAW_TABLE)
    
    # Filter by date (assuming published_at is the partitioning column)
    filtered_df = raw_df.filter(
        col("published_at").cast("date") == lit(process_date)
    )
    
    print(f"✓ Read {filtered_df.count()} raw articles for date: {process_date}")
    return filtered_df

def compute_sentiment_analysis(text_col):
    """Compute sentiment analysis (simplified implementation)."""
    # Simple rule-based sentiment for demo purposes
    # In production, use ML models like transformers or cloud APIs
    positive_words = ["good", "great", "excellent", "amazing", "wonderful", "fantastic", "positive"]
    negative_words = ["bad", "terrible", "awful", "horrible", "negative", "disappointing"]
    
    # Count positive and negative words
    text_lower = text_col.lower()
    
    # Simple scoring: count positive minus negative words, normalized
    sentiment_score = when(
        text_lower.rlike(r"\b(" + "|".join(positive_words) + r")\b"), 0.7
    ).when(
        text_lower.rlike(r"\b(" + "|".join(negative_words) + r")\b"), 0.3
    ).otherwise(0.5)  # neutral
    
    sentiment_label = when(
        sentiment_score > 0.6, "positive"
    ).when(
        sentiment_score < 0.4, "negative"
    ).otherwise("neutral")
    
    return sentiment_score, sentiment_label

def extract_entities(text_col):
    """Extract entities (simplified implementation)."""
    # Simple regex-based entity extraction for demo
    # In production, use NER models like spaCy or transformers
    
    # Extract entities that look like organizations (capitalized words)
    # This is a very simplified approach
    entities = split(regexp_extract(text_col, r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b", 0), "\\s+")
    
    return entities

def extract_keywords(title_col, body_col):
    """Extract keywords from title and body."""
    # Simple keyword extraction - get important words from title
    # Filter out common stop words and short words
    stop_words = ["the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "a", "an"]
    
    # Split title into words, filter stop words and short words
    title_words = split(title_col.lower(), "\\s+")
    
    # For simplicity, just return first few words from title as keywords
    # In production, use TF-IDF or other keyword extraction techniques
    return title_words

def enrich_articles(raw_df):
    """Apply enrichment transformations to raw articles."""
    # Compute sentiment analysis
    sentiment_score, sentiment_label = compute_sentiment_analysis(col("body"))
    
    # Extract entities and keywords
    entities = extract_entities(col("body"))
    keywords = extract_keywords(col("title"), col("body"))
    
    # Create enriched DataFrame
    enriched_df = raw_df.select(
        col("id"),
        col("published_at"),
        col("title"),
        col("body"),
        col("source"),
        col("url"),
        sentiment_score.alias("sentiment_score"),
        sentiment_label.alias("sentiment_label"),
        entities.alias("entities"),
        keywords.alias("keywords"),
        current_timestamp().alias("processed_at"),
        lit(1).alias("version")  # Version for tracking updates
    )
    
    print(f"✓ Applied enrichment to {enriched_df.count()} articles")
    return enriched_df

def upsert_to_enriched_table(spark, enriched_df):
    """Upsert enriched articles using Iceberg MERGE INTO."""
    # Create temporary view for the updates
    enriched_df.createOrReplaceTempView("tmp_updates")
    
    # Perform MERGE INTO operation
    merge_sql = f"""
    MERGE INTO {ENRICHED_TABLE} t
    USING tmp_updates s
    ON t.id = s.id
    WHEN MATCHED THEN UPDATE SET 
        t.published_at = s.published_at,
        t.title = s.title,
        t.body = s.body,
        t.source = s.source,
        t.url = s.url,
        t.sentiment_score = s.sentiment_score,
        t.sentiment_label = s.sentiment_label,
        t.entities = s.entities,
        t.keywords = s.keywords,
        t.processed_at = s.processed_at,
        t.version = t.version + 1
    WHEN NOT MATCHED THEN INSERT (
        id, published_at, title, body, source, url,
        sentiment_score, sentiment_label, entities, keywords,
        processed_at, version
    ) VALUES (
        s.id, s.published_at, s.title, s.body, s.source, s.url,
        s.sentiment_score, s.sentiment_label, s.entities, s.keywords,
        s.processed_at, s.version
    )
    """
    
    # Execute the MERGE operation
    result = spark.sql(merge_sql)
    
    # Get merge statistics (if available)
    print("✓ MERGE INTO operation completed")
    
    # Verify the operation
    enriched_count = spark.table(ENRICHED_TABLE).count()
    print(f"✓ Total records in enriched table: {enriched_count}")
    
    return result

def validate_idempotency(spark, process_date):
    """Validate that re-running produces no duplicates."""
    # Check for duplicates by ID
    duplicates_df = spark.sql(f"""
        SELECT id, count(*) as cnt 
        FROM {ENRICHED_TABLE} 
        GROUP BY id 
        HAVING cnt > 1
    """)
    
    duplicate_count = duplicates_df.count()
    
    if duplicate_count > 0:
        print(f"❌ Found {duplicate_count} duplicate IDs - idempotency violation!")
        duplicates_df.show()
        return False
    else:
        print("✅ No duplicates found - idempotency maintained")
        return True

def main():
    """Main enrichment upsert process."""
    process_date = get_process_date()
    
    print(f"=== Enrichment Upsert Process (Issue #291) ===")
    print(f"Processing date: {process_date}")
    print(f"Raw table: {RAW_TABLE}")
    print(f"Enriched table: {ENRICHED_TABLE}")
    
    # Create Spark session
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Ensure enriched table exists
        create_enriched_table_if_not_exists(spark)
        
        # Read raw articles for the specified date
        raw_df = read_raw_articles(spark, process_date)
        
        if raw_df.count() == 0:
            print(f"No raw articles found for date: {process_date}")
            return
        
        # Apply enrichment transformations
        enriched_df = enrich_articles(raw_df)
        
        # Upsert to enriched table using MERGE INTO
        upsert_to_enriched_table(spark, enriched_df)
        
        # Validate idempotency (DoD requirement)
        is_idempotent = validate_idempotency(spark, process_date)
        
        if is_idempotent:
            print("✅ DoD satisfied: Re-running updates rows in place (no dupes)")
        else:
            print("❌ DoD violation: Duplicates found")
            return 1
        
        print("✅ Enrichment upsert process completed successfully")
        return 0
        
    except Exception as e:
        print(f"❌ Error in enrichment process: {e}")
        raise
    finally:
        spark.stop()

if __name__ == "__main__":
    exit(main())
