# dbt on Spark for Iceberg Marts - Option A

This implementation provides a complete dbt setup using Spark as the compute engine to materialize Iceberg marts for the NeuroNews analytics platform.

## 🎯 Issue #297 Implementation

**Option A**: Configure dbt-spark (Thrift/HTTP) profile, materialize marts on Iceberg.

### Definition of Done ✅
- [x] dbt-spark configured with Thrift/HTTP connection
- [x] Marts materialized on Iceberg tables
- [x] Tests (not_null, unique id) on articles_enriched
- [x] dbt run + dbt test succeed
- [x] CI integration with GitHub Actions

## 🏗️ Architecture

```
Kafka → Spark Streaming → Iceberg (Raw/Enriched)
                             ↓
                          dbt-spark
                             ↓
                    Iceberg Marts (Analytics)
```

### Components

- **dbt-spark**: SQL transformation engine using Spark compute
- **Spark Thrift Server**: SQL interface for dbt connectivity
- **Iceberg Tables**: ACID-compliant data lake storage
- **Hive Metastore**: Metadata catalog (PostgreSQL-backed)

## 📁 Project Structure

```
dbt/
├── dbt_project.yml          # Project configuration
├── profiles.yml             # Connection profiles
├── requirements.txt         # Python dependencies
├── packages.yml             # dbt package dependencies
├── docker-compose.spark.yml # Spark services
├── models/
│   ├── sources/
│   │   └── sources.yml      # Source table definitions
│   ├── staging/
│   │   ├── stg_articles_raw.sql       # Raw articles staging
│   │   └── stg_articles_enriched.sql  # Enriched articles staging
│   ├── marts/
│   │   ├── fact_articles.sql          # Main fact table
│   │   ├── dim_sources.sql            # Source dimension
│   │   └── agg_daily_metrics.sql      # Daily aggregations
│   └── schema.yml           # Model tests and documentation
└── tests/
    ├── test_sentiment_score_range.sql   # Custom test
    └── test_no_orphaned_articles.sql    # Referential integrity
```

## 🚀 Quick Start

### 1. Prerequisites

```bash
# Install Python dependencies
cd dbt
pip install -r requirements.txt

# Start Spark services
docker-compose -f docker-compose.spark.yml up -d
```

### 2. Run dbt Workflow

```bash
# Install dbt packages
dbt deps

# Test connection
dbt debug

# Run models
dbt run

# Run tests
dbt test

# Generate documentation
dbt docs generate
dbt docs serve
```

### 3. Demo Script

```bash
# Run complete demo
python demo_dbt_spark_iceberg.py
```

## 🔧 Configuration

### Spark Connection Profiles

#### Development (Thrift)
```yaml
dev:
  type: spark
  method: thrift
  host: localhost
  port: 10000
  user: spark
  database: demo
  schema: neuronews
  threads: 4
```

#### Production (HTTP)
```yaml
prod:
  type: spark
  method: http
  host: spark-thrift-server
  port: 10001
  user: spark
  database: demo
  schema: neuronews_prod
  threads: 8
```

### Iceberg Table Properties

```yaml
table_properties:
  'write.format.default': 'parquet'
  'write.parquet.compression-codec': 'snappy'
  'history.expire.max-snapshot-age-ms': '432000000'  # 5 days
  'history.expire.min-snapshots-to-keep': '5'
```

## 📊 Data Models

### Staging Layer

#### `stg_articles_raw`
- Standardizes raw article data
- Data quality validation
- Type conversions and cleaning

#### `stg_articles_enriched` 
- NLP enrichment staging
- Sentiment and topic analysis
- Entity extraction and keywords

### Marts Layer

#### `fact_articles`
- Central fact table combining raw + enriched
- Article-level analytics
- Quality indicators and metrics

#### `dim_sources`
- Source-level aggregations
- Quality rankings and percentiles
- Volume and engagement metrics

#### `agg_daily_metrics`
- Daily time-series aggregations
- Trend analysis and monitoring
- Moving averages and comparisons

## 🧪 Testing Strategy

### Data Quality Tests

#### Standard Tests
```yaml
columns:
  - name: article_id
    tests:
      - not_null
      - unique
  - name: title
    tests:
      - not_null
  - name: published_at
    tests:
      - not_null
```

#### Custom Tests
- Sentiment score range validation (-1 to 1)
- Referential integrity checks
- Data freshness monitoring

### CI/CD Integration

GitHub Actions workflow automatically:
1. Starts Spark cluster
2. Creates test Iceberg tables
3. Runs dbt models
4. Executes all tests
5. Validates mart creation

## 🔍 Monitoring & Observability

### Key Metrics
- Model run duration
- Test failure rates
- Data freshness
- Quality scores

### Alerts
- Failed dbt runs
- Test failures
- Data quality degradation
- Processing delays

## 🚀 Production Deployment

### Environment Variables
```bash
# Spark Configuration
export SPARK_THRIFT_HOST=spark-cluster.company.com
export SPARK_THRIFT_PORT=10000
export SPARK_DATABASE=prod
export SPARK_SCHEMA=neuronews_prod

# Iceberg Configuration
export ICEBERG_CATALOG_TYPE=hive
export HIVE_METASTORE_URIS=thrift://hive-metastore:9083
```

### Scaling Considerations
- Increase Spark executor resources
- Optimize partition strategies
- Implement incremental models
- Add data quality monitoring

## 📚 Commands Reference

### Development
```bash
# Setup
dbt deps                     # Install packages
dbt debug                    # Test connection

# Development
dbt run                      # Run all models
dbt run --models staging.*  # Run staging only
dbt run --models marts.*    # Run marts only

# Testing
dbt test                     # Run all tests
dbt test --models fact_articles  # Test specific model

# Documentation
dbt docs generate           # Generate docs
dbt docs serve              # Serve documentation
```

### Production
```bash
# Full refresh
dbt run --full-refresh

# Specific target
dbt run --target prod

# Incremental runs
dbt run --models +fact_articles  # Run model and dependencies
```

## 🔧 Troubleshooting

### Common Issues

#### Connection Timeout
```bash
# Check Spark Thrift Server
nc -zv localhost 10000

# Restart services
docker-compose -f docker-compose.spark.yml restart
```

#### Memory Issues
```bash
# Increase Spark resources in docker-compose.spark.yml
environment:
  - SPARK_WORKER_MEMORY=4G
  - SPARK_WORKER_CORES=4
```

#### Metastore Issues
```bash
# Reset metastore
docker-compose -f docker-compose.spark.yml down -v
docker-compose -f docker-compose.spark.yml up -d
```

## 🎯 Success Metrics

- ✅ **dbt run success**: All models materialize successfully
- ✅ **dbt test success**: All data quality tests pass
- ✅ **CI integration**: Automated testing in GitHub Actions
- ✅ **Iceberg marts**: Tables created with proper partitioning
- ✅ **Performance**: Sub-10 minute model runs
- ✅ **Data quality**: 99%+ test pass rate

## 🔗 Related Links

- [dbt-spark Documentation](https://docs.getdbt.com/reference/warehouse-setups/spark-setup)
- [Apache Spark Thrift Server](https://spark.apache.org/docs/latest/sql-distributed-sql-engine.html)
- [Apache Iceberg](https://iceberg.apache.org/)
- [GitHub Actions for dbt](https://docs.getdbt.com/guides/orchestration/github-actions)

---

*This implementation satisfies Issue #297 Option A requirements with dbt-spark targeting Iceberg marts, complete with testing and CI integration.*
