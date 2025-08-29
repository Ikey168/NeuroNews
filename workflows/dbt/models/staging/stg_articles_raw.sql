{{
  config(
    materialized='view',
    schema='staging'
  )
}}

-- Staging view for raw articles from Iceberg
-- Standardizes data types and basic transformations

with source_data as (
    select
        -- Primary identifiers
        id as article_id,
        url,
        
        -- Content fields
        title,
        body as content,
        summary,
        
        -- Source information
        source,
        category,
        
        -- Temporal fields
        published_at,
        processed_at,
        created_at,
        updated_at,
        
        -- Partitioning fields
        year,
        month,
        day,
        hour,
        
        -- Metadata
        language,
        tags,
        sentiment_score,
        sentiment_label,
        
        -- Technical fields
        hash_content,
        dedup_key

    from {{ source('iceberg', 'articles_raw') }}
),

cleaned_data as (
    select
        article_id,
        url,
        
        -- Clean and standardize content
        trim(title) as title,
        trim(content) as content,
        trim(summary) as summary,
        
        -- Standardize source
        lower(trim(source)) as source,
        coalesce(category, 'unknown') as category,
        
        -- Convert timestamps to proper format
        published_at,
        processed_at,
        created_at,
        updated_at,
        
        -- Ensure partitioning fields are integers
        cast(year as int) as year,
        cast(month as int) as month,
        cast(day as int) as day,
        cast(hour as int) as hour,
        
        -- Clean metadata
        coalesce(language, 'en') as language,
        tags,
        sentiment_score,
        sentiment_label,
        
        -- Technical fields
        hash_content,
        dedup_key,
        
        -- Add row quality indicators
        case 
            when title is null or trim(title) = '' then false
            when content is null or trim(content) = '' then false
            when published_at is null then false
            else true
        end as is_valid_row,
        
        -- Add data freshness indicator
        datediff('hour', processed_at, current_timestamp()) as hours_since_processed

    from source_data
)

select * from cleaned_data
