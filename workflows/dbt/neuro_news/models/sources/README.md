# External Sources Documentation

This directory contains the external source definitions and raw data views for the NeuroNews dbt project. These sources link to raw/bronze files produced by data pipelines, enabling dbt to work with external data files.

## Architecture

```
data/bronze/
├── news/           # News articles (Parquet files)
├── entities/       # NER results (JSONL files)
└── sources/        # Source configurations (Parquet files)
```

## Source Definitions

### `raw_bronze.raw__news`
- **Format**: Parquet files
- **Pattern**: `data/bronze/news/**/*.parquet`
- **Content**: Raw news articles scraped by pipelines
- **Freshness**: Warns after 24h, errors after 48h
- **Key fields**: id, title, content, url, source, scraped_at

### `raw_bronze.raw__entities`
- **Format**: JSONL files
- **Pattern**: `data/bronze/entities/**/*.jsonl`
- **Content**: Named entity recognition results
- **Freshness**: Warns after 48h, errors after 72h
- **Key fields**: article_id, entity_text, entity_type, confidence_score

### `raw_bronze.raw__sources`
- **Format**: Parquet files
- **Pattern**: `data/bronze/sources/**/*.parquet`
- **Content**: News source configurations and metadata
- **Freshness**: Warns after 7 days, errors after 14 days
- **Key fields**: source_id, source_name, base_url, scraping_enabled

## Raw Views

### `raw__news.sql`
A view that reads Parquet files using DuckDB's `read_parquet()` function with:
- Glob pattern support for multiple files
- Hive partitioning enabled
- Union by name for schema evolution
- Deduplication based on URL and scraped timestamp

### `raw__entities.sql`
A view that reads JSONL files using DuckDB's `read_json_auto()` function with:
- Newline-delimited JSON format
- Type casting for numeric fields
- Data quality filtering
- Union by name for schema flexibility

### `raw__sources.sql`
A view that reads source configuration Parquet files with:
- Latest record deduplication by source_id
- Boolean casting for flags
- Timestamp normalization

## Usage

### Running Models
```bash
# Run all raw views
dbt run --select raw__news raw__entities raw__sources

# Run specific raw view
dbt run --select raw__news
```

### Testing Data Quality
```bash
# Test all source data quality
dbt test --select source:raw_bronze

# Test specific source
dbt test --select source:raw_bronze.raw__news
```

### Checking Freshness
```bash
# Check all source freshness
dbt source freshness

# Check specific source freshness
dbt source freshness --select source:raw_bronze.raw__news
```

## Data Quality

The external sources include comprehensive data quality tests:
- **Not null** checks on critical fields
- **Unique** constraints on identifiers
- **Accepted values** for categorical fields
- **Range validation** for numeric scores
- **Freshness monitoring** with configurable thresholds

## Sample Data

Sample data files are included for testing:
- `data/bronze/news/news_batch_001.parquet` (3 sample articles)
- `data/bronze/entities/entities_batch_001.jsonl` (4 sample entities)
- `data/bronze/sources/sources_config.parquet` (3 sample sources)

## Production Setup

For production deployment:
1. Update file paths in the raw views to point to your actual data lake
2. Configure appropriate freshness thresholds based on your pipeline schedules
3. Set up monitoring and alerting for source freshness failures
4. Implement partitioning strategies for large datasets
5. Consider using external tables or materialized views for performance

## Benefits

- **Schema Evolution**: Union by name allows adding new columns without breaking existing models
- **Performance**: DuckDB's columnar engine provides fast analytics on Parquet files
- **Flexibility**: Supports both structured (Parquet) and semi-structured (JSONL) data
- **Data Quality**: Built-in testing ensures data integrity
- **Monitoring**: Freshness checks detect pipeline issues early
- **Documentation**: Self-documenting schema with descriptions and metadata
