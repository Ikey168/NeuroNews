# dbt Semantic Layer with MetricFlow

This directory contains the semantic layer configuration for NeuroNews analytics, enabling YAML-defined semantic models and metrics that can be queried via CLI and API.

## Overview

The dbt Semantic Layer provides a unified interface to define and query business metrics consistently across the organization. It leverages MetricFlow to enable:

- **Semantic Models**: Define business entities and their relationships
- **Metrics**: Create reusable metric definitions with proper aggregations
- **Saved Queries**: Store commonly used metric queries
- **Time Spine**: Support for time-based aggregations and cumulative metrics

## Directory Structure

```
semantic/
├── README.md              # This file
├── models/               # Semantic model definitions
│   ├── articles.yml     # Article-based semantic model
│   ├── users.yml        # User interaction semantic model
│   └── events.yml       # Event detection semantic model
├── metrics/             # Metric definitions
│   ├── content_metrics.yml
│   ├── engagement_metrics.yml
│   └── performance_metrics.yml
└── saved_queries/       # Commonly used queries
    ├── daily_content_summary.yml
    └── weekly_engagement_report.yml
```

## Getting Started

### 1. Install Dependencies

Ensure you have MetricFlow installed:

```bash
pip install -r requirements-dbt.txt
```

### 2. Validate Configuration

Check that your semantic layer configuration is valid:

```bash
# From the dbt/ directory
dbt deps && dbt parse
mf validate-configs
```

### 3. Query Metrics

Use the MetricFlow CLI to query metrics:

```bash
# Basic metric query
mf query --metrics articles_published --group-by published_date

# Query with time granularity
mf query --metrics articles_published,avg_article_length --group-by published_date__month

# Query with filters
mf query --metrics articles_published --group-by category --where "published_date >= '2024-01-01'"

# Multiple metrics with dimensions
mf query --metrics articles_published,unique_authors --group-by category,source
```

### 4. Available Metrics (Examples)

Once semantic models are implemented, you'll have access to metrics like:

**Content Metrics:**
- `articles_published`: Count of published articles
- `avg_article_length`: Average article word count
- `unique_authors`: Count of unique authors
- `articles_by_category`: Articles grouped by category

**Engagement Metrics:**
- `total_queries`: Count of user queries
- `avg_response_time`: Average query response time
- `citations_per_article`: Average citations per article

**Performance Metrics:**
- `retrieval_latency`: Average document retrieval time
- `rerank_success_rate`: Percentage of successful reranking operations

## MetricFlow Commands Reference

### Basic Commands

```bash
# Validate semantic layer configuration
mf validate-configs

# List available metrics
mf list metrics

# List available dimensions
mf list dimensions

# Get metric details
mf describe metric <metric_name>
```

### Query Commands

```bash
# Simple metric query
mf query --metrics <metric_name>

# Query with grouping
mf query --metrics <metric_name> --group-by <dimension>

# Query with time granularity
mf query --metrics <metric_name> --group-by <dimension>__<granularity>

# Query with filters
mf query --metrics <metric_name> --where "<filter_condition>"

# Export query results
mf query --metrics <metric_name> --group-by <dimension> --explain
```

### Time Granularities

Available time granularities for date dimensions:
- `day`, `week`, `month`, `quarter`, `year`
- Example: `published_date__month` for monthly aggregation

## Best Practices

1. **Metric Naming**: Use clear, business-friendly metric names
2. **Documentation**: Add descriptions to all metrics and dimensions
3. **Testing**: Validate metrics with known data samples
4. **Performance**: Consider materialization strategies for large datasets
5. **Governance**: Establish review processes for new metrics

## Example Queries

### Daily Content Production
```bash
mf query --metrics articles_published --group-by published_date__day --order-by published_date__day
```

### Monthly Engagement Summary
```bash
mf query --metrics total_queries,avg_response_time --group-by query_date__month
```

### Category Performance Analysis
```bash
mf query --metrics articles_published,avg_article_length --group-by category --where "published_date >= '2024-01-01'"
```

## Integration with NeuroNews

The semantic layer integrates with:
- **Analytics Dashboard**: Powers key metrics and KPIs
- **Data Quality Monitoring**: Tracks data freshness and completeness
- **ML Model Performance**: Monitors retrieval and ranking metrics
- **Business Intelligence**: Provides consistent metric definitions

## Troubleshooting

### Common Issues

1. **Validation Errors**: Check YAML syntax and metric definitions
2. **Missing Dependencies**: Ensure all required models are built
3. **Query Errors**: Verify dimension and metric names
4. **Performance Issues**: Consider adding time filters to large queries

### Getting Help

- [dbt Semantic Layer Docs](https://docs.getdbt.com/docs/build/semantic-models)
- [MetricFlow Commands](https://docs.getdbt.com/docs/build/metricflow-commands)
- [Metric Types Guide](https://docs.getdbt.com/docs/build/metrics-overview)

## Future Enhancements

- **Real-time Metrics**: Integration with streaming data
- **Advanced Analytics**: Time-series forecasting and anomaly detection
- **Custom Aggregations**: Business-specific calculation logic
- **API Integration**: RESTful metric serving endpoints
