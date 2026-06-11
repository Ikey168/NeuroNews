{{ config(materialized='view') }}

-- Staging model for articles from PostgreSQL source
-- This model cleans and standardizes article data for downstream consumption

with source as (
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
        created_at,
        updated_at
    from {{ source('postgres', 'articles') }}
),

cleaned as (
    select
        id,
        trim(title) as title,
        trim(content) as content,
        trim(url) as url,
        trim(lower(source)) as source,
        published_date::timestamp as published_date,
        scraped_at::timestamp as scraped_at,
        case 
            when sentiment in ('positive', 'negative', 'neutral') then sentiment
            else null
        end as sentiment,
        case 
            when sentiment_score between -1 and 1 then sentiment_score
            else null
        end as sentiment_score,
        trim(lower(language)) as language,
        trim(translated_title) as translated_title,
        trim(translated_content) as translated_content,
        created_at::timestamp as created_at,
        updated_at::timestamp as updated_at
    from source
    where 
        id is not null
        and title is not null
        and content is not null
        and url is not null
        and length(trim(title)) > 0
        and length(trim(content)) > 10  -- Filter out articles with minimal content
)

select * from cleaned
