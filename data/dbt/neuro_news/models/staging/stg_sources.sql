{{
  config(
    materialized='view',
    description='Staging model for news source configurations with clean, typed data'
  )
}}

with raw_sources as (
    select * from {{ ref('raw__sources') }}
),

language_map as (
    select * from {{ ref('language_map') }}
),

country_region as (
    select * from {{ ref('country_region') }}
),

cleaned as (
    select
        -- Keep original source_id as primary key
        rs.source_id,
        
        -- Clean and normalize source name
        trim(regexp_replace(rs.source_name, '\s+', ' ', 'g')) as source_name,
        
        -- Normalize URLs (remove trailing slashes, convert to lowercase)
        case 
            when rs.base_url is not null then 
                lower(trim(regexp_replace(rs.base_url, '/$', '', 'g')))
            else null
        end as base_url,
        
        case 
            when rs.rss_feed_url is not null and trim(rs.rss_feed_url) != '' then 
                lower(trim(rs.rss_feed_url))
            else null
        end as rss_feed_url,
        
        -- Normalize language codes using language_map seed
        coalesce(lm.language_code, 
            case 
                when lower(trim(rs.language)) in ('en', 'english') then 'en'
                when lower(trim(rs.language)) in ('es', 'spanish', 'español') then 'es'
                when lower(trim(rs.language)) in ('fr', 'french', 'français') then 'fr'
                when lower(trim(rs.language)) in ('de', 'german', 'deutsch') then 'de'
                when lower(trim(rs.language)) in ('it', 'italian', 'italiano') then 'it'
                when lower(trim(rs.language)) in ('pt', 'portuguese', 'português') then 'pt'
                when lower(trim(rs.language)) in ('ru', 'russian', 'русский') then 'ru'
                when lower(trim(rs.language)) in ('zh', 'chinese', '中文') then 'zh'
                when lower(trim(rs.language)) in ('ja', 'japanese', '日本語') then 'ja'
                when lower(trim(rs.language)) in ('ar', 'arabic', 'العربية') then 'ar'
                when rs.language is null or trim(rs.language) = '' then 'unknown'
                else 'unknown'
            end) as language_code,
        
        -- Normalize country codes using country_region seed
        coalesce(cr.country_code,
            case 
                when upper(trim(rs.country)) in ('US', 'USA', 'UNITED STATES') then 'US'
                when upper(trim(rs.country)) in ('UK', 'GB', 'UNITED KINGDOM', 'BRITAIN') then 'UK'
                when upper(trim(rs.country)) in ('CA', 'CANADA') then 'CA'
                when upper(trim(rs.country)) in ('AU', 'AUSTRALIA') then 'AU'
                when upper(trim(rs.country)) in ('DE', 'GERMANY', 'DEUTSCHLAND') then 'DE'
                when upper(trim(rs.country)) in ('FR', 'FRANCE') then 'FR'
                when upper(trim(rs.country)) in ('ES', 'SPAIN', 'ESPAÑA') then 'ES'
                when upper(trim(rs.country)) in ('IT', 'ITALY', 'ITALIA') then 'IT'
                when upper(trim(rs.country)) in ('JP', 'JAPAN') then 'JP'
                when upper(trim(rs.country)) in ('CN', 'CHINA') then 'CN'
                when upper(trim(rs.country)) in ('RU', 'RUSSIA') then 'RU'
                when upper(trim(rs.country)) in ('BR', 'BRAZIL') then 'BR'
                when upper(trim(rs.country)) in ('IN', 'INDIA') then 'IN'
                when upper(trim(rs.country)) in ('MX', 'MEXICO') then 'MX'
                when upper(trim(rs.country)) in ('NL', 'NETHERLANDS') then 'NL'
                when upper(trim(rs.country)) in ('SE', 'SWEDEN') then 'SE'
                when upper(trim(rs.country)) in ('NO', 'NORWAY') then 'NO'
                when upper(trim(rs.country)) in ('FI', 'FINLAND') then 'FI'
                when upper(trim(rs.country)) in ('DK', 'DENMARK') then 'DK'
                when rs.country is null or trim(rs.country) = '' then 'unknown'
                else 'unknown'
            end) as country_code,
        
        -- Normalize categories
        case 
            when lower(trim(rs.category)) in ('tech', 'technology', 'ai', 'artificial intelligence') then 'technology'
            when lower(trim(rs.category)) in ('politics', 'political', 'government') then 'politics'
            when lower(trim(rs.category)) in ('business', 'finance', 'financial', 'economy', 'economic') then 'business'
            when lower(trim(rs.category)) in ('sports', 'sport', 'athletics') then 'sports'
            when lower(trim(rs.category)) in ('entertainment', 'celebrity', 'movies', 'music') then 'entertainment'
            when lower(trim(rs.category)) in ('science', 'research', 'scientific') then 'science'
            when lower(trim(rs.category)) in ('health', 'medical', 'medicine', 'healthcare') then 'health'
            when lower(trim(rs.category)) in ('environment', 'environmental', 'climate', 'green') then 'environment'
            when lower(trim(rs.category)) in ('news', 'general', 'breaking news') then 'general'
            when rs.category is null or trim(rs.category) = '' then 'other'
            else 'other'
        end as category,
        
        -- Normalize boolean field
        case 
            when rs.scraping_enabled::text in ('true', '1', 'yes', 'y', 'on', 'enabled') then true
            when rs.scraping_enabled::text in ('false', '0', 'no', 'n', 'off', 'disabled') then false
            when rs.scraping_enabled is null then false
            else rs.scraping_enabled::boolean
        end as is_scraping_enabled,
        
        -- Parse timestamps to UTC
        case 
            when rs.last_scraped_at is not null then rs.last_scraped_at::timestamp
            else null
        end as last_scraped_at_utc,
        
        rs.created_at::timestamp as created_at_utc,
        rs.updated_at::timestamp as updated_at_utc,
        
        -- Add metadata
        current_timestamp as dbt_loaded_at,
        
        -- Row number for deduplication (prefer latest updated_at)
        row_number() over (
            partition by rs.source_id
            order by rs.updated_at desc, rs.created_at desc
        ) as row_num
        
    from raw_sources rs
    left join language_map lm on lower(trim(rs.language)) = lm.language_code 
        or lower(trim(rs.language)) = lower(lm.language_name)
        or lower(trim(rs.language)) = lower(lm.native_name)
    left join country_region cr on upper(trim(rs.country)) = cr.country_code
        or upper(trim(rs.country)) = upper(cr.country_name)
    where 
        -- Filter out records with missing required fields
        rs.source_id is not null 
        and trim(rs.source_id) != ''
        and rs.source_name is not null 
        and trim(rs.source_name) != ''
        and rs.base_url is not null 
        and trim(rs.base_url) != ''
        and rs.language is not null 
        and trim(rs.language) != ''
        and rs.created_at is not null
        and rs.updated_at is not null
),

deduplicated as (
    select 
        source_id,
        source_name,
        base_url,
        rss_feed_url,
        language_code,
        country_code,
        category,
        is_scraping_enabled,
        last_scraped_at_utc,
        created_at_utc,
        updated_at_utc,
        dbt_loaded_at
        
    from cleaned
    where row_num = 1  -- Keep only the latest version of each source
)

select * from deduplicated
