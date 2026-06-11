# Data Marts Layer

This directory contains business logic models that:
- Implement business rules and calculations
- Join staging models to create analysis-ready tables
- Apply aggregations and metrics calculations
- Serve as the primary interface for downstream consumers

## Model Naming Convention
- Use descriptive business terms
- Group related models with prefixes (e.g., `fct_`, `dim_`, `agg_`)
- Examples: `fct_articles.sql`, `dim_sources.sql`, `agg_daily_sentiment.sql`

## Documentation
Each model should include:
- Business logic documentation
- Column descriptions with business context
- Data quality tests and expectations
