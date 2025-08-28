# E2E Test Configuration for CDC Testing

## Requirements
pytest>=7.0.0
psycopg2-binary>=2.9.0
pyspark>=3.4.0

## Environment Variables for E2E Testing

### PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=neuronews
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

### Iceberg Configuration
ICEBERG_WAREHOUSE_PATH=/tmp/iceberg-warehouse
SPARK_SQL_CATALOG_LOCAL=org.apache.iceberg.spark.SparkCatalog

### CDC Configuration
CDC_PROCESSING_TIMEOUT=30

## Running the Tests

```bash
# Install dependencies
pip install pytest psycopg2-binary pyspark

# Set environment variables
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=neuronews
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres

# Run all E2E tests
pytest tests/e2e/test_cdc_articles.py -v

# Run specific test
pytest tests/e2e/test_cdc_articles.py::TestCDCArticles::test_cdc_insert_operation -v

# Run with detailed output
pytest tests/e2e/test_cdc_articles.py -v --tb=long --capture=no
```

## Test Structure

The test file implements the following CDC operations as specified in issue 349:

1. **INSERT Operation**: CREATE INSERT a2
   - Tests inserting new articles into PostgreSQL
   - Validates data appears in Iceberg table via CDC streaming

2. **UPDATE Operation**: UPDATE a1.title
   - Tests updating existing article titles
   - Validates changes are reflected in Iceberg table

3. **DELETE Operation**: DELETE a2
   - Tests deleting articles from PostgreSQL
   - Validates deletion is handled in Iceberg (soft or hard delete)

4. **End-to-End Scenario**: Complete workflow
   - Tests full sequence: INSERT → UPDATE → DELETE
   - Validates state consistency throughout the process

5. **Data Consistency**: Cross-system validation
   - Compares data between PostgreSQL source and Iceberg target
   - Ensures data integrity across the CDC pipeline

## Prerequisites

1. PostgreSQL database running with articles table
2. Debezium CDC connector configured
3. Spark Structured Streaming job running (cdc_to_iceberg.py)
4. Iceberg catalog accessible from test environment

## Notes

- Tests wait 30 seconds between operations for CDC processing
- Iceberg table location: `local.default.articles`
- Tests clean up automatically to avoid data pollution
- Replica identity should be set to FULL on articles table
