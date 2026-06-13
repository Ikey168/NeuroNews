{{ config(materialized='table') }}

-- Fact table for articles with enriched analytics data
-- This serves as the primary table for article analytics and reporting

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
        created_at,
        updated_at,
        scraped_at,
        sentiment,
        
        -- Derived fields
        length(content) as content_length,
        length(title) as title_length,
        
        -- Date dimensions
        date(created_at) as created_date_key,
        extract(year from created_at) as created_year,
        extract(month from created_at) as created_month,
        extract(day from created_at) as created_day,
        extract(hour from created_at) as created_hour,
        
        -- Content categorization
        case 
            when content_length < 500 then 'short'
            when content_length < 2000 then 'medium'
            else 'long'
        end as content_category,
        
        -- Sentiment flags
        case when sentiment = 'positive' then 1 else 0 end as is_positive,
        case when sentiment = 'negative' then 1 else 0 end as is_negative,
        case when sentiment = 'neutral' then 1 else 0 end as is_neutral
    from articles
)

select * from enriched
