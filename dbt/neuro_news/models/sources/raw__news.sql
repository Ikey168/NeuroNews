{{
  config(
    materialized='view',
    description='Raw news articles from parquet files using DuckDB read_parquet function'
  )
}}

-- Raw news view that reads from parquet files in the bronze layer
-- Uses DuckDB's read_parquet function with glob pattern for multiple files
select 
    id,
    title,
    content,
    url,
    source,
    published_at,
    scraped_at,
    language,
    category,
    author,
    created_at,
    updated_at,
    
    -- Add metadata
    current_timestamp as dbt_loaded_at
    
from read_parquet('/workspaces/NeuroNews/data/bronze/news/**/*.parquet', 
                  hive_partitioning=true, 
                  union_by_name=true)

-- Filter out any potential duplicate records based on URL and scraped timestamp
qualify row_number() over (
    partition by url, scraped_at 
    order by created_at desc
) = 1
