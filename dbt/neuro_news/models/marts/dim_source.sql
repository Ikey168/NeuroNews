{{ config(
    materialized='table',
    tags=['marts', 'dimension'],
    contract={'enforced': true}
) }}

WITH source_data AS (
    SELECT * FROM {{ ref('stg_sources') }}
),

final AS (
    SELECT
        -- Surrogate key
        {{ dbt_utils.generate_surrogate_key(['source_id']) }} AS source_key,
        
        -- Natural key
        source_id,
        
        -- Descriptive attributes
        source_name,
        REGEXP_EXTRACT(base_url, 'https?://(?:www\.)?([^/]+)', 1) AS domain,
        base_url,
        country_code,
        language_code,
        category,
        is_scraping_enabled,
        
        -- Timestamps
        created_at_utc,
        updated_at_utc,
        dbt_loaded_at
        
    FROM source_data
)

SELECT * FROM final
