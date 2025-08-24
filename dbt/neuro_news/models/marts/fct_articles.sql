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
        published_date,
        scraped_at,
        sentiment,
        sentiment_score,
        language,
        translated_title,
        translated_content,
        
        -- Derived fields
        length(content) as content_length,
        length(title) as title_length,
        
        -- Date dimensions
        date(published_date) as published_date_key,
        extract(year from published_date) as published_year,
        extract(month from published_date) as published_month,
        extract(day from published_date) as published_day,
        extract(hour from published_date) as published_hour,
        
        -- Language flags
        case when language = 'en' then true else false end as is_english,
        case when translated_title is not null then true else false end as is_translated,
        
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
        
        created_at,
        updated_at
    from articles
)

select * from enriched
