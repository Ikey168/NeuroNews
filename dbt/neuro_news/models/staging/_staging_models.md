# Staging Layer Models

This directory contains staging models that:
- Clean and standardize raw data from source systems
- Apply consistent naming conventions
- Handle basic data type conversions
- Remove duplicates and filter out invalid records

## Model Naming Convention
- All staging models should be prefixed with `stg_`
- Use descriptive names that reflect the source system and entity
- Example: `stg_postgres__articles.sql`, `stg_api__sentiment.sql`

## Documentation
Each model should include:
- Column descriptions
- Data quality tests
- Source freshness checks where applicable
