{{
  config(
    materialized='view',
    description='Staging model for news source configurations with clean, typed data'
  )
}}

with raw_sources as (
    select * from {{ ref('raw__sources') }}
),

cleaned as (
    select
        -- Keep original source_id as primary key
        source_id,
        
        -- Clean and normalize source name
        trim(regexp_replace(source_name, '\s+', ' ', 'g')) as source_name,
        
        -- Normalize URLs (remove trailing slashes, convert to lowercase)
        case 
            when base_url is not null then 
                lower(trim(regexp_replace(base_url, '/$', '', 'g')))
            else null
        end as base_url,
        
        case 
            when rss_feed_url is not null and trim(rss_feed_url) != '' then 
                lower(trim(rss_feed_url))
            else null
        end as rss_feed_url,
        
        -- Normalize language codes to ISO 639-1
        case 
            when lower(trim(language)) in ('en', 'english') then 'en'
            when lower(trim(language)) in ('es', 'spanish', 'español') then 'es'
            when lower(trim(language)) in ('fr', 'french', 'français') then 'fr'
            when lower(trim(language)) in ('de', 'german', 'deutsch') then 'de'
            when lower(trim(language)) in ('it', 'italian', 'italiano') then 'it'
            when lower(trim(language)) in ('pt', 'portuguese', 'português') then 'pt'
            when lower(trim(language)) in ('ru', 'russian', 'русский') then 'ru'
            when lower(trim(language)) in ('zh', 'chinese', '中文') then 'zh'
            when lower(trim(language)) in ('ja', 'japanese', '日本語') then 'ja'
            when lower(trim(language)) in ('ar', 'arabic', 'العربية') then 'ar'
            when language is null or trim(language) = '' then 'unknown'
            else 'unknown'
        end as language_code,
        
        -- Normalize country codes to ISO 3166-1 alpha-2
        case 
            when upper(trim(country)) in ('US', 'USA', 'UNITED STATES') then 'US'
            when upper(trim(country)) in ('UK', 'GB', 'UNITED KINGDOM', 'BRITAIN') then 'UK'
            when upper(trim(country)) in ('CA', 'CANADA') then 'CA'
            when upper(trim(country)) in ('AU', 'AUSTRALIA') then 'AU'
            when upper(trim(country)) in ('DE', 'GERMANY', 'DEUTSCHLAND') then 'DE'
            when upper(trim(country)) in ('FR', 'FRANCE') then 'FR'
            when upper(trim(country)) in ('ES', 'SPAIN', 'ESPAÑA') then 'ES'
            when upper(trim(country)) in ('IT', 'ITALY', 'ITALIA') then 'IT'
            when upper(trim(country)) in ('JP', 'JAPAN') then 'JP'
            when upper(trim(country)) in ('CN', 'CHINA') then 'CN'
            when upper(trim(country)) in ('RU', 'RUSSIA') then 'RU'
            when upper(trim(country)) in ('BR', 'BRAZIL') then 'BR'
            when upper(trim(country)) in ('IN', 'INDIA') then 'IN'
            when upper(trim(country)) in ('MX', 'MEXICO') then 'MX'
            when upper(trim(country)) in ('NL', 'NETHERLANDS') then 'NL'
            when upper(trim(country)) in ('SE', 'SWEDEN') then 'SE'
            when upper(trim(country)) in ('NO', 'NORWAY') then 'NO'
            when upper(trim(country)) in ('FI', 'FINLAND') then 'FI'
            when upper(trim(country)) in ('DK', 'DENMARK') then 'DK'
            when country is null or trim(country) = '' then 'unknown'
            else 'unknown'
        end as country_code,
        
        -- Normalize categories
        case 
            when lower(trim(category)) in ('tech', 'technology', 'ai', 'artificial intelligence') then 'technology'
            when lower(trim(category)) in ('politics', 'political', 'government') then 'politics'
            when lower(trim(category)) in ('business', 'finance', 'financial', 'economy', 'economic') then 'business'
            when lower(trim(category)) in ('sports', 'sport', 'athletics') then 'sports'
            when lower(trim(category)) in ('entertainment', 'celebrity', 'movies', 'music') then 'entertainment'
            when lower(trim(category)) in ('science', 'research', 'scientific') then 'science'
            when lower(trim(category)) in ('health', 'medical', 'medicine', 'healthcare') then 'health'
            when lower(trim(category)) in ('environment', 'environmental', 'climate', 'green') then 'environment'
            when lower(trim(category)) in ('news', 'general', 'breaking news') then 'general'
            when category is null or trim(category) = '' then 'other'
            else 'other'
        end as category,
        
        -- Normalize boolean field
        case 
            when scraping_enabled::text in ('true', '1', 'yes', 'y', 'on', 'enabled') then true
            when scraping_enabled::text in ('false', '0', 'no', 'n', 'off', 'disabled') then false
            when scraping_enabled is null then false
            else scraping_enabled::boolean
        end as is_scraping_enabled,
        
        -- Parse timestamps to UTC
        case 
            when last_scraped_at is not null then last_scraped_at::timestamp
            else null
        end as last_scraped_at_utc,
        
        created_at::timestamp as created_at_utc,
        updated_at::timestamp as updated_at_utc,
        
        -- Add metadata
        current_timestamp as dbt_loaded_at,
        
        -- Row number for deduplication (prefer latest updated_at)
        row_number() over (
            partition by source_id
            order by updated_at desc, created_at desc
        ) as row_num
        
    from raw_sources
    where 
        -- Filter out records with missing required fields
        source_id is not null 
        and trim(source_id) != ''
        and source_name is not null 
        and trim(source_name) != ''
        and base_url is not null 
        and trim(base_url) != ''
        and language is not null 
        and trim(language) != ''
        and created_at is not null
        and updated_at is not null
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
