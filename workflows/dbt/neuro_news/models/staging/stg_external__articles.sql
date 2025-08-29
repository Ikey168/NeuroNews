{{
  config(
    materialized='view',
    description='Staging layer for news articles from external sources'
  )
}}

-- Staging model that uses the external raw news source
-- This replaces the previous staging model to use external files instead of database sources
with source as (
    select * from {{ source('raw_bronze', 'raw__news') }}
),

cleaned as (
    select
        id,
        trim(title) as title,
        trim(content) as content,
        trim(url) as url,
        trim(lower(source)) as source,
        published_at::timestamp as published_at,
        scraped_at::timestamp as scraped_at,
        trim(lower(language)) as language,
        trim(lower(category)) as category,
        trim(author) as author,
        created_at::timestamp as created_at,
        updated_at::timestamp as updated_at,
        dbt_loaded_at,
        
        -- Data quality indicators
        case 
            when length(trim(content)) = 0 then true 
            else false 
        end as is_content_empty,
        
        case 
            when length(trim(title)) = 0 then true 
            else false 
        end as is_title_empty,
        
        -- Derived fields
        length(content) as content_length,
        length(title) as title_length,
        
        -- Metadata
        current_timestamp as dbt_processed_at
        
    from source
    where 
        id is not null
        and title is not null
        and content is not null
        and url is not null
        and scraped_at is not null
        -- Filter out empty content
        and length(trim(content)) > 0
        and length(trim(title)) > 0
)

select * from cleaned
