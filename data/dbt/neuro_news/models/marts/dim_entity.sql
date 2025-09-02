{{ config(
    materialized='table',
    tags=['marts', 'dimension'],
    contract={'enforced': true}
) }}

WITH entity_data AS (
    SELECT * FROM {{ ref('stg_entities') }}
),

entity_aggregates AS (
    SELECT
        entity_text,
        entity_type,
        
        -- High-level category mapping
        CASE 
            WHEN entity_type = 'PERSON' THEN 'PERSON'
            WHEN entity_type IN ('ORG') THEN 'ORGANIZATION'
            WHEN entity_type IN ('GPE', 'LOC') THEN 'LOCATION'
            WHEN entity_type IN ('EVENT') THEN 'EVENT'
            WHEN entity_type IN ('PRODUCT', 'WORK_OF_ART', 'LAW', 'LANGUAGE') THEN 'PRODUCT'
            WHEN entity_type IN ('DATE', 'TIME') THEN 'TEMPORAL'
            WHEN entity_type IN ('PERCENT', 'MONEY', 'QUANTITY', 'ORDINAL', 'CARDINAL') THEN 'NUMERICAL'
            ELSE 'OTHER'
        END AS entity_category,
        
        -- Aggregated metrics
        AVG(confidence_score) AS avg_confidence_score,
        COUNT(*) AS mention_count,
        MIN(extracted_at_utc) AS first_mention_at_utc,
        MAX(extracted_at_utc) AS last_mention_at_utc,
        MAX(dbt_loaded_at) AS dbt_loaded_at
        
    FROM entity_data
    GROUP BY 
        entity_text,
        entity_type
),

final AS (
    SELECT
        -- Surrogate key
        {{ dbt_utils.generate_surrogate_key(['entity_text', 'entity_type']) }} AS entity_key,
        
        -- Natural key (using text + type combination)
        CONCAT(entity_text, '_', entity_type) AS entity_id,
        
        -- Descriptive attributes
        entity_text,
        entity_type,
        entity_category,
        
        -- Aggregated metrics
        ROUND(avg_confidence_score, 3) AS avg_confidence_score,
        mention_count,
        first_mention_at_utc,
        last_mention_at_utc,
        dbt_loaded_at
        
    FROM entity_aggregates
)

SELECT * FROM final
