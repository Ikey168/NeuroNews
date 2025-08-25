{{
  config(
    materialized='view',
    description='Staging model for news articles with clean, typed, and deduplicated data'
  )
}}

with raw_news as (
    select * from {{ ref('raw__news') }}
),

cleaned as (
    select
        -- Generate deterministic natural key
        {{ dbt_utils.generate_surrogate_key(['url', 'source']) }} as article_id,
        
        -- Clean and normalize text fields
        trim(regexp_replace(title, '\s+', ' ', 'g')) as title,
        trim(regexp_replace(content, '\s+', ' ', 'g')) as content,
        lower(trim(url)) as url,
        lower(trim(source)) as source_name,
        
        -- Parse and normalize timestamps to UTC
        case 
            when published_at is not null then published_at::timestamp
            else null
        end as published_at_utc,
        scraped_at::timestamp as scraped_at_utc,
        
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
            when category is null or trim(category) = '' then 'other'
            else 'other'
        end as category,
        
        -- Clean author field
        case 
            when author is not null and trim(author) != '' then trim(author)
            else null
        end as author,
        
        -- Calculate content metrics
        length(trim(content)) as content_length,
        length(trim(title)) as title_length,
        
        -- Convert timestamps to UTC
        created_at::timestamp as created_at_utc,
        updated_at::timestamp as updated_at_utc,
        
        -- Add metadata
        current_timestamp as dbt_loaded_at,
        
        -- Row number for deduplication (prefer latest scraped_at)
        row_number() over (
            partition by lower(trim(url))
            order by scraped_at desc, created_at desc
        ) as row_num
        
    from raw_news
    where 
        -- Filter out records with missing required fields
        title is not null 
        and trim(title) != ''
        and content is not null 
        and trim(content) != ''
        and url is not null 
        and trim(url) != ''
        and source is not null 
        and trim(source) != ''
        and scraped_at is not null
        and created_at is not null
        and updated_at is not null
),

deduplicated as (
    select 
        article_id,
        title,
        content,
        url,
        source_name,
        published_at_utc,
        scraped_at_utc,
        language_code,
        category,
        author,
        content_length,
        title_length,
        
        -- Flag duplicates (keep only row_num = 1)
        case when row_num > 1 then true else false end as is_duplicate,
        
        created_at_utc,
        updated_at_utc,
        dbt_loaded_at
        
    from cleaned
    where row_num = 1  -- Keep only the latest version of each URL
)

select * from deduplicated
