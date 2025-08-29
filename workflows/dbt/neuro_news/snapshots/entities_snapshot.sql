{% snapshot entities_snapshot %}

{{
    config(
      target_schema='snapshots',
      unique_key='entity_id',
      strategy='check',
      check_cols=['entity_text', 'entity_type', 'confidence_score', 'article_id'],
      updated_at='extracted_at_utc',
      invalidate_hard_deletes=True
    )
}}

-- Snapshot for tracking changes in entity metadata and canonical names
-- This captures:
-- - Entity text standardization/renaming (e.g., "MIT" -> "Massachusetts Institute of Technology")
-- - Entity type reclassification (e.g., "PRODUCT" -> "ORG")
-- - Confidence score updates from model improvements
-- - Entity association changes (different articles)

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
    
from {{ ref('stg_entities') }}

{% endsnapshot %}
