{{ config(
    materialized='incremental',
    unique_key='article_id',
    on_schema_change='append_new_columns',
    tags=['marts', 'fact'],
    contract={'enforced': true}
) }}

WITH news_data AS (
    SELECT * FROM {{ ref('stg_news') }}
    {% if is_incremental() %}
        WHERE published_at_utc::date > (
            SELECT COALESCE(MAX(published_at_utc::date), '1900-01-01'::date) 
            FROM {{ this }}
        )
           OR updated_at_utc > (
            SELECT COALESCE(MAX(updated_at_utc), '1900-01-01'::timestamp) 
            FROM {{ this }}
        )
    {% endif %}
),

source_dim AS (
    SELECT * FROM {{ ref('dim_source') }}
),

entity_metrics AS (
    SELECT 
        article_id,
        COUNT(*) AS entity_count,
        AVG(confidence_score) AS avg_entity_confidence
    FROM {{ ref('stg_entities') }}
    GROUP BY article_id
),

final AS (
    SELECT
        -- Surrogate key
        {{ dbt_utils.generate_surrogate_key(['n.article_id']) }} AS article_key,
        
        -- Natural key
        n.article_id,
        
        -- Foreign keys
        ds.source_key,
        
        -- Descriptive attributes
        n.title,
        n.content_length,
        n.title_length,
        n.url,
        n.language_code,
        n.category,
        n.is_duplicate,
        
        -- Entity-related metrics
        COALESCE(em.entity_count, 0) AS entity_count,
        ROUND(em.avg_entity_confidence, 3) AS avg_entity_confidence,
        
        -- Timestamps
        n.published_at_utc,
        n.scraped_at_utc,
        n.created_at_utc,
        n.updated_at_utc,
        n.dbt_loaded_at
        
    FROM news_data n
    LEFT JOIN source_dim ds 
        ON LOWER(n.source_name) = LOWER(ds.source_name)
    LEFT JOIN entity_metrics em 
        ON n.article_id = em.article_id
)

SELECT * FROM final
