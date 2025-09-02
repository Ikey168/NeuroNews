{{
  config(
    materialized='view',
    description='Staging model for news articles with clean, typed, and deduplicated data'
  )
}}

with raw_news as (
    select * from {{ ref('raw__news') }}
),

language_map as (
    select * from {{ ref('language_map') }}
),

cleaned as (
    select
        -- Generate deterministic natural key
        {{ dbt_utils.generate_surrogate_key(['rn.url', 'rn.source']) }} as article_id,
        
        -- Clean and normalize text fields
        trim(regexp_replace(rn.title, '\s+', ' ', 'g')) as title,
        trim(regexp_replace(rn.content, '\s+', ' ', 'g')) as content,
        lower(trim(rn.url)) as url,
        lower(trim(rn.source)) as source_name,
        
        -- Parse and normalize timestamps to UTC
        case 
            when rn.published_at is not null then rn.published_at::timestamp
            else null
        end as published_at_utc,
        rn.scraped_at::timestamp as scraped_at_utc,
        
        -- Normalize language codes using language_map seed
        coalesce(lm.language_code, 
            case 
                when lower(trim(rn.language)) in ('en', 'english') then 'en'
                when lower(trim(rn.language)) in ('es', 'spanish', 'español') then 'es'
                when lower(trim(rn.language)) in ('fr', 'french', 'français') then 'fr'
                when lower(trim(rn.language)) in ('de', 'german', 'deutsch') then 'de'
                when lower(trim(rn.language)) in ('it', 'italian', 'italiano') then 'it'
                when lower(trim(rn.language)) in ('pt', 'portuguese', 'português') then 'pt'
                when lower(trim(rn.language)) in ('ru', 'russian', 'русский') then 'ru'
                when lower(trim(rn.language)) in ('zh', 'chinese', '中文') then 'zh'
                when lower(trim(rn.language)) in ('ja', 'japanese', '日本語') then 'ja'
                when lower(trim(rn.language)) in ('ar', 'arabic', 'العربية') then 'ar'
                when rn.language is null or trim(rn.language) = '' then 'unknown'
                else 'unknown'
            end) as language_code,
        
        -- Normalize categories
        case 
            when lower(trim(rn.category)) in ('tech', 'technology', 'ai', 'artificial intelligence') then 'technology'
            when lower(trim(rn.category)) in ('politics', 'political', 'government') then 'politics'
            when lower(trim(rn.category)) in ('business', 'finance', 'financial', 'economy', 'economic') then 'business'
            when lower(trim(rn.category)) in ('sports', 'sport', 'athletics') then 'sports'
            when lower(trim(rn.category)) in ('entertainment', 'celebrity', 'movies', 'music') then 'entertainment'
            when lower(trim(rn.category)) in ('science', 'research', 'scientific') then 'science'
            when lower(trim(rn.category)) in ('health', 'medical', 'medicine', 'healthcare') then 'health'
            when lower(trim(rn.category)) in ('environment', 'environmental', 'climate', 'green') then 'environment'
            when rn.category is null or trim(rn.category) = '' then 'other'
            else 'other'
        end as category,
        
        -- Clean author field
        case 
            when rn.author is not null and trim(rn.author) != '' then trim(rn.author)
            else null
        end as author,
        
        -- Calculate content metrics
        length(trim(rn.content)) as content_length,
        length(trim(rn.title)) as title_length,
        
        -- Convert timestamps to UTC
        rn.created_at::timestamp as created_at_utc,
        rn.updated_at::timestamp as updated_at_utc,
        
        -- Add metadata
        current_timestamp as dbt_loaded_at,
        
        -- Row number for deduplication (prefer latest scraped_at)
        row_number() over (
            partition by lower(trim(rn.url))
            order by rn.scraped_at desc, rn.created_at desc
        ) as row_num
        
    from raw_news rn
    left join language_map lm on lower(trim(rn.language)) = lm.language_code 
        or lower(trim(rn.language)) = lower(lm.language_name)
        or lower(trim(rn.language)) = lower(lm.native_name)
    where 
        -- Filter out records with missing required fields
        rn.title is not null 
        and trim(rn.title) != ''
        and rn.content is not null 
        and trim(rn.content) != ''
        and rn.url is not null 
        and trim(rn.url) != ''
        and rn.source is not null 
        and trim(rn.source) != ''
        and rn.scraped_at is not null
        and rn.created_at is not null
        and rn.updated_at is not null
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
