{{
  config(
    materialized='view',
    description='Raw news source configurations from parquet files using DuckDB read_parquet function'
  )
}}

-- Raw sources view that reads from parquet files in the bronze layer
-- Contains configuration and metadata for news sources being scraped
select 
    source_id,
    source_name,
    base_url,
    rss_feed_url,
    language,
    country,
    category,
    scraping_enabled::boolean as scraping_enabled,
    last_scraped_at::timestamp as last_scraped_at,
    created_at::timestamp as created_at,
    updated_at::timestamp as updated_at,
    
    -- Add metadata
    current_timestamp as dbt_loaded_at
    
from read_parquet('/workspaces/NeuroNews/data/bronze/sources/**/*.parquet',
                  hive_partitioning=true,
                  union_by_name=true)

-- Filter out any potential duplicate records based on source_id
qualify row_number() over (
    partition by source_id 
    order by updated_at desc
) = 1
