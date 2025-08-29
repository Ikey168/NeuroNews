{% snapshot sources_snapshot %}

{{
    config(
      target_schema='snapshots',
      unique_key='source_id',
      strategy='check',
      check_cols=['source_name', 'base_url', 'language_code', 'country_code', 'category', 'is_scraping_enabled'],
      updated_at='updated_at_utc',
      invalidate_hard_deletes=True
    )
}}

-- Snapshot for tracking changes in news source metadata and publisher information
-- This captures:
-- - Source name changes/rebranding (e.g., "CNN International" -> "CNN")
-- - URL changes due to website restructuring
-- - Language/country code updates for better categorization
-- - Category reclassification (e.g., "general" -> "technology")
-- - Scraping status changes (enabled/disabled)
-- - RSS feed URL updates

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
    
from {{ ref('stg_sources') }}

{% endsnapshot %}
