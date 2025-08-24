{{ config(materialized='view') }}

-- Demo staging model using seed data
-- In production, replace {{ ref('sample_articles') }} with {{ source('postgres', 'articles') }}

select
    id,
    trim(title) as title,
    trim(content) as content,
    trim(url) as url,
    trim(lower(source)) as source,
    case 
        when sentiment in ('positive', 'negative', 'neutral') then sentiment
        else null
    end as sentiment,
    created_at::timestamp as created_at,
    updated_at::timestamp as updated_at,
    scraped_at::timestamp as scraped_at,
    
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
    
from {{ ref('sample_articles') }}
where 
    id is not null
    and title is not null
    and content is not null
