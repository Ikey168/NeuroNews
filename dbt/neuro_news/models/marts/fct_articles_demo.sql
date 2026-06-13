{{ config(materialized='table') }}

-- Demo fact table for articles - simplified for seed data
-- In production, use the full version with all enrichment fields

with articles as (
    select * from {{ ref('stg_postgres__articles_demo') }}
),

enriched as (
    select
        id,
        title,
        content,
        url,
        source,
        sentiment,
        created_at,
        updated_at,
        scraped_at,
        
        -- Derived fields from staging
        content_length,
        title_length,
        is_content_empty,
        is_title_empty,
        
        -- Date dimensions
        date(created_at) as created_date_key,
        extract(year from created_at) as created_year,
        extract(month from created_at) as created_month,
        extract(day from created_at) as created_day,
        
        -- Content categorization
        case 
            when content_length < 500 then 'short'
            when content_length < 2000 then 'medium'
            else 'long'
        end as content_category,
        
        -- Sentiment flags
        case when sentiment = 'positive' then 1 else 0 end as is_positive,
        case when sentiment = 'negative' then 1 else 0 end as is_negative,
        case when sentiment = 'neutral' then 1 else 0 end as is_neutral,
        
        -- Quality scores
        case 
            when is_content_empty or is_title_empty then 'poor'
            when content_length < 100 then 'fair'
            else 'good'
        end as content_quality,
        
        -- Analytics metadata
        dbt_processed_at,
        current_timestamp as fact_table_created_at
        
    from articles
    where not is_content_empty
)

select * from enriched
