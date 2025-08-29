# Spark + Iceberg Local Development Guide

This guide explains how to run Spark with Iceberg support in local development environments.

## Prerequisites

- Apache Spark installed locally
- MinIO running (for S3-compatible storage)
- Iceberg REST catalog service running
- Required JAR dependencies

## Required Dependencies

Download these JAR files to your Spark `jars/` directory or specify in classpath:

```bash
# Iceberg Spark runtime
iceberg-spark-runtime-3.5_2.12-1.4.2.jar

# AWS SDK for S3A
aws-java-sdk-bundle-1.12.423.jar
hadoop-aws-3.3.4.jar

# Additional dependencies
bundle-2.20.18.jar  # AWS SDK v2 (if using newer versions)
url-connection-client-2.20.18.jar
```

## Configuration

The Spark configuration is automatically loaded from `spark/conf/spark-defaults.conf`.

Key configurations:
- **Iceberg Extensions**: Enables Iceberg SQL features
- **REST Catalog**: Connects to Iceberg REST service at `http://iceberg-rest:8181`
- **S3A Storage**: Configured for MinIO at `http://minio:9000`
- **Performance**: Vectorized reads and adaptive query execution enabled

## Local Development Commands

### Starting Spark SQL Shell

```bash
# Basic Spark SQL with Iceberg support
spark-sql

# With specific driver memory and additional JARs
spark-sql \
  --driver-memory 2g \
  --conf spark.sql.adaptive.enabled=true
```

### Running Spark Applications

```bash
# Submit a Spark application with Iceberg support
spark-submit \
  --class your.main.Class \
  --master local[*] \
  --driver-memory 2g \
  --executor-memory 1g \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.demo=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.demo.type=rest \
  --conf spark.sql.catalog.demo.uri=http://iceberg-rest:8181 \
  your-application.jar
```

### PySpark with Iceberg

```bash
# Start PySpark shell with Iceberg support
pyspark \
  --driver-memory 2g \
  --conf spark.sql.extensions=org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions \
  --conf spark.sql.catalog.demo=org.apache.iceberg.spark.SparkCatalog \
  --conf spark.sql.catalog.demo.type=rest \
  --conf spark.sql.catalog.demo.uri=http://iceberg-rest:8181
```

## Testing the Setup

### Verify Iceberg Catalog Connection

```sql
-- Check available namespaces in demo catalog
SHOW NAMESPACES IN demo;

-- Create a test namespace
CREATE NAMESPACE IF NOT EXISTS demo.test;

-- List namespaces again to verify creation
SHOW NAMESPACES IN demo;
```

### Create and Query Test Table

```sql
-- Create a test Iceberg table
CREATE TABLE demo.test.sample_table (
    id BIGINT,
    name STRING,
    timestamp TIMESTAMP
) USING ICEBERG;

-- Insert sample data
INSERT INTO demo.test.sample_table VALUES 
    (1, 'Alice', current_timestamp()),
    (2, 'Bob', current_timestamp()),
    (3, 'Charlie', current_timestamp());

-- Query the table
SELECT * FROM demo.test.sample_table;

-- Check table metadata
DESCRIBE EXTENDED demo.test.sample_table;
```

### Time Travel Queries

```sql
-- Show table history
SELECT * FROM demo.test.sample_table FOR SYSTEM_VERSION AS OF 1;

-- Show snapshots
SELECT * FROM demo.test.sample_table.snapshots;
```

## Docker Compose Integration

If using Docker Compose for the full stack:

```yaml
# Add to your docker-compose.yml
spark:
  image: apache/spark:3.5.0
  volumes:
    - ./spark/conf:/opt/spark/conf
    - ./data:/data
  environment:
    - SPARK_MODE=master
  ports:
    - "8080:8080"
    - "7077:7077"
  depends_on:
    - minio
    - iceberg-rest
```

## Troubleshooting

### Common Issues

1. **ClassNotFoundException for Iceberg**
   - Ensure Iceberg JAR is in classpath
   - Verify Spark version compatibility

2. **S3A Connection Errors**
   - Check MinIO is running and accessible
   - Verify credentials in configuration
   - Ensure path-style access is enabled

3. **REST Catalog Connection Failed**
   - Verify Iceberg REST service is running
   - Check network connectivity to `iceberg-rest:8181`

### Debug Commands

```bash
# Test S3A connectivity
spark-shell --conf spark.sql.execution.arrow.pyspark.enabled=false
# Then in Spark shell:
# spark.sparkContext.hadoopConfiguration.set("fs.s3a.endpoint", "http://minio:9000")
# val df = spark.read.text("s3a://warehouse/")

# Check loaded catalogs
spark-sql -e "SHOW CATALOGS;"

# Verify Iceberg extensions
spark-sql -e "SET spark.sql.extensions;"
```

## Performance Tips

1. **Use appropriate file sizes**: Configure `fs.s3a.block.size` based on your data
2. **Enable vectorized reads**: Already configured in spark-defaults.conf
3. **Partition your tables**: Use appropriate partitioning strategy for your queries
4. **Monitor memory usage**: Adjust driver and executor memory based on workload

## Integration with NeuroNews Pipeline

For NeuroNews data processing:

```python
# Example PySpark integration
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("NeuroNews-Iceberg") \
    .getOrCreate()

# Read news data into Iceberg table
news_df = spark.read.json("data/news/*.json")

# Write to Iceberg table with partitioning
news_df.write \
    .format("iceberg") \
    .mode("overwrite") \
    .option("path", "s3a://warehouse/news_data") \
    .partitionBy("date") \
    .saveAsTable("demo.news.articles")

# Query with time travel
latest_articles = spark.sql("""
    SELECT * FROM demo.news.articles 
    WHERE date >= current_date() - 7
""")
```

## Next Steps

1. Set up automated tests for Iceberg functionality
2. Integrate with existing NeuroNews data pipelines
3. Configure production-ready storage settings
4. Implement data governance and schema evolution policies
