"""
Batch job with OpenLineage data lineage tracking
Issue #296

Enhanced version of batch_write_raw.py with OpenLineage integration
for tracking data lineage from source files to Iceberg tables.
"""
import os
import sys
from pathlib import Path

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from jobs.spark.openlineage_config import create_spark_session_with_lineage, add_lineage_metadata, log_lineage_event
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, current_timestamp, lit

# Path to latest scraped files (CSV, Parquet, or JSON)
SCRAPED_DATA_PATH = os.getenv("SCRAPED_DATA_PATH", "data/scraped/latest/*.csv")
ICEBERG_TABLE = os.getenv("ICEBERG_TABLE", "demo.news.articles_raw")

def main():
    """Main function for batch write with lineage tracking."""
    print("🚀 Starting batch write job with OpenLineage tracking")
    print(f"Source: {SCRAPED_DATA_PATH}")
    print(f"Target: {ICEBERG_TABLE}")
    
    spark = None
    try:
        # Create Spark session with OpenLineage configuration
        spark = create_spark_session_with_lineage(
            app_name="BatchWriteRawWithLineage",
            additional_configs={
                "spark.sql.adaptive.enabled": "true",
                "spark.sql.adaptive.coalescePartitions.enabled": "true"
            }
        )
        
        # Add lineage metadata for this job
        add_lineage_metadata(
            spark, 
            job_type="batch",
            source_system="file_system", 
            target_system="iceberg"
        )
        
        # Log job start event
        log_lineage_event(spark, "start", SCRAPED_DATA_PATH, "read")
        
        # Load latest scraped data
        df = load_scraped_data(spark, SCRAPED_DATA_PATH)
        
        # Add processing metadata for lineage tracking
        df_with_metadata = add_processing_metadata(df)
        
        # Log transformation event
        log_lineage_event(spark, "transform", "add_metadata", "transform")
        
        # Write to Iceberg table
        write_to_iceberg_with_lineage(spark, df_with_metadata, ICEBERG_TABLE)
        
        # Validate and log completion
        row_count = df_with_metadata.count()
        print(f"✅ Batch job completed successfully")
        print(f"📊 Rows processed: {row_count}")
        
        # Log job completion event
        log_lineage_event(spark, "complete", ICEBERG_TABLE, "write")
        
        # DoD: Print row count for validation
        assert row_count > 0, "No rows written!"
        
        return 0
        
    except Exception as e:
        print(f"❌ Batch job failed: {e}")
        if spark:
            log_lineage_event(spark, "fail", ICEBERG_TABLE, "write")
        return 1
        
    finally:
        if spark:
            spark.stop()

def load_scraped_data(spark, data_path):
    """Load scraped data with appropriate format detection."""
    print(f"📖 Loading data from: {data_path}")
    
    if data_path.endswith(".csv"):
        df = spark.read.option("header", True).csv(data_path)
    elif data_path.endswith(".parquet"):
        df = spark.read.parquet(data_path)
    elif data_path.endswith(".json"):
        df = spark.read.json(data_path)
    else:
        # Try to detect format from first file
        if "*.csv" in data_path:
            df = spark.read.option("header", True).csv(data_path)
        elif "*.parquet" in data_path:
            df = spark.read.parquet(data_path)
        elif "*.json" in data_path:
            df = spark.read.json(data_path)
        else:
            raise ValueError(f"Unsupported file type: {data_path}")
    
    print(f"📊 Loaded {df.count()} records from source")
    return df

def add_processing_metadata(df):
    """Add processing metadata for lineage tracking."""
    return df.withColumn("batch_processed_at", current_timestamp()) \
             .withColumn("processing_job", lit("BatchWriteRawWithLineage")) \
             .withColumn("lineage_enabled", lit(True))

def write_to_iceberg_with_lineage(spark, df, table_name):
    """Write to Iceberg table with lineage tracking."""
    print(f"📝 Writing to Iceberg table: {table_name}")
    
    # Check if table exists
    table_exists = spark.catalog.tableExists(table_name)
    
    if table_exists:
        print(f"📋 Table {table_name} exists, appending data")
        
        # Use writeTo for Iceberg-specific operations
        df.writeTo(table_name).append()
        
        # Log append operation
        log_lineage_event(spark, "append", table_name, "write")
        
    else:
        print(f"🆕 Table {table_name} does not exist, creating new table")
        
        # Create table with partitioning for better lineage tracking
        df.writeTo(table_name) \
          .tableProperty("write.format.default", "parquet") \
          .tableProperty("write.parquet.compression-codec", "snappy") \
          .createOrReplace()
        
        # Log create operation
        log_lineage_event(spark, "create", table_name, "write")
    
    print(f"✅ Successfully written to {table_name}")

def validate_lineage_integration(spark):
    """Validate that OpenLineage integration is working."""
    print("🔍 Validating OpenLineage integration...")
    
    # Check OpenLineage configurations
    lineage_configs = [
        "spark.extraListeners",
        "spark.openlineage.transport.type", 
        "spark.openlineage.transport.url",
        "spark.openlineage.namespace"
    ]
    
    for config in lineage_configs:
        value = spark.conf.get(config, None)
        if value:
            print(f"✅ {config}: {value}")
        else:
            print(f"⚠️  {config}: Not configured")
    
    # Test if Marquez endpoint is reachable (optional)
    try:
        import urllib.request
        marquez_url = spark.conf.get("spark.openlineage.transport.url", "http://marquez:5000")
        
        # Try to reach the health endpoint
        health_url = f"{marquez_url}/api/v1/health"
        with urllib.request.urlopen(health_url, timeout=5) as response:
            if response.status == 200:
                print(f"✅ Marquez endpoint reachable: {marquez_url}")
            else:
                print(f"⚠️  Marquez endpoint returned status {response.status}")
                
    except Exception as e:
        print(f"⚠️  Could not reach Marquez endpoint: {e}")
        print("   This is normal if Marquez is not running locally")

if __name__ == "__main__":
    exit(main())
