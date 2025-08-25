{{
  config(
    materialized='view',
    description='Staging model for extracted entities with clean, typed data'
  )
}}

with raw_entities as (
    select * from {{ ref('raw__entities') }}
),

-- First, get the article mapping from raw news to staging
stg_news_mapping as (
    select 
        rn.id as raw_article_id,
        sn.article_id as staging_article_id,
        sn.url,
        sn.source_name
    from {{ ref('raw__news') }} rn
    inner join {{ ref('stg_news') }} sn 
        on {{ dbt_utils.generate_surrogate_key(['rn.url', 'rn.source']) }} = sn.article_id
),

cleaned as (
    select
        -- Generate deterministic natural key
        {{ dbt_utils.generate_surrogate_key(['re.article_id', 'entity_text', 'entity_type', 'start_char']) }} as entity_id,
        
        -- Map to canonical article ID from staging news
        snm.staging_article_id as article_id,
        
        -- Clean entity text
        trim(entity_text) as entity_text,
        
        -- Normalize entity types
        case 
            when upper(trim(entity_type)) in ('PERSON', 'PER') then 'PERSON'
            when upper(trim(entity_type)) in ('ORG', 'ORGANIZATION') then 'ORG'
            when upper(trim(entity_type)) in ('GPE', 'GEOPOLITICAL') then 'GPE'
            when upper(trim(entity_type)) in ('LOC', 'LOCATION') then 'LOC'
            when upper(trim(entity_type)) in ('EVENT') then 'EVENT'
            when upper(trim(entity_type)) in ('PRODUCT', 'PROD') then 'PRODUCT'
            when upper(trim(entity_type)) in ('WORK_OF_ART', 'WORK-OF-ART', 'ART') then 'WORK_OF_ART'
            when upper(trim(entity_type)) in ('LAW', 'LEGAL') then 'LAW'
            when upper(trim(entity_type)) in ('LANGUAGE', 'LANG') then 'LANGUAGE'
            when upper(trim(entity_type)) in ('DATE') then 'DATE'
            when upper(trim(entity_type)) in ('TIME') then 'TIME'
            when upper(trim(entity_type)) in ('PERCENT', 'PERCENTAGE', '%') then 'PERCENT'
            when upper(trim(entity_type)) in ('MONEY', 'MONETARY', 'CURRENCY') then 'MONEY'
            when upper(trim(entity_type)) in ('QUANTITY', 'QTY') then 'QUANTITY'
            when upper(trim(entity_type)) in ('ORDINAL', 'ORD') then 'ORDINAL'
            when upper(trim(entity_type)) in ('CARDINAL', 'CARD', 'NUMBER') then 'CARDINAL'
            when entity_type is null or trim(entity_type) = '' then 'MISC'
            else 'MISC'
        end as entity_type,
        
        -- Ensure confidence score is within valid range
        case 
            when confidence_score < 0 then 0.0
            when confidence_score > 1 then 1.0
            when confidence_score is null then 0.0
            else confidence_score::double
        end as confidence_score,
        
        -- Clean position fields
        coalesce(start_char, 0) as start_position,
        coalesce(end_char, start_char + length(entity_text), length(entity_text)) as end_position,
        
        -- Calculate entity length
        length(trim(entity_text)) as entity_length,
        
        -- Parse timestamp to UTC
        extracted_at::timestamp as extracted_at_utc,
        created_at::timestamp as created_at_utc,
        
        -- Add metadata
        current_timestamp as dbt_loaded_at,
        
        -- Row number for deduplication
        row_number() over (
            partition by 
                re.article_id,
                trim(entity_text),
                upper(trim(entity_type)),
                start_char
            order by extracted_at desc, created_at desc
        ) as row_num
        
    from raw_entities re
    inner join stg_news_mapping snm 
        on re.article_id = snm.raw_article_id
        
    where 
        -- Filter out records with missing required fields
        entity_text is not null 
        and trim(entity_text) != ''
        and entity_type is not null 
        and trim(entity_type) != ''
        and confidence_score is not null
        and extracted_at is not null
        and created_at is not null
        -- Filter out very low confidence entities
        and confidence_score >= 0.5
),

deduplicated as (
    select 
        entity_id,
        article_id,
        entity_text,
        entity_type,
        confidence_score,
        start_position,
        end_position,
        entity_length,
        extracted_at_utc,
        created_at_utc,
        dbt_loaded_at
        
    from cleaned
    where row_num = 1  -- Keep only the latest version of each entity
)

select * from deduplicated
