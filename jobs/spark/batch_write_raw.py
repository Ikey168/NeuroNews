"""
Batch writer for Iceberg (bronze/raw) table: demo.news.articles_raw
Issue #288
"""
import os
from pyspark.sql import SparkSession
from pyspark.sql import DataFrame

# Path to latest scraped files (CSV, Parquet, or JSON)
SCRAPED_DATA_PATH = os.getenv("SCRAPED_DATA_PATH", "data/scraped/latest/*.csv")
ICEBERG_TABLE = "demo.news.articles_raw"

# Spark session with Iceberg support
spark = SparkSession.builder \
    .appName("BatchWriterRaw") \
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

# Load latest scraped data
if SCRAPED_DATA_PATH.endswith(".csv"):
    df = spark.read.option("header", True).csv(SCRAPED_DATA_PATH)
elif SCRAPED_DATA_PATH.endswith(".parquet"):
    df = spark.read.parquet(SCRAPED_DATA_PATH)
elif SCRAPED_DATA_PATH.endswith(".json"):
    df = spark.read.json(SCRAPED_DATA_PATH)
else:
    raise ValueError(f"Unsupported file type: {SCRAPED_DATA_PATH}")

# Write to Iceberg table (append or create/replace)
if spark.catalog.tableExists(ICEBERG_TABLE):
    df.writeTo(ICEBERG_TABLE).append()
else:
    df.writeTo(ICEBERG_TABLE).createOrReplace()

# DoD: Print row count
row_count = df.count()
print(f"Rows written to {ICEBERG_TABLE}: {row_count}")
assert row_count > 0, "No rows written!"

spark.stop()
