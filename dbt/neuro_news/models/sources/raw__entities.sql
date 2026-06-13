{{
  config(
    materialized='view',
    description='Raw extracted entities from JSONL files using DuckDB read_json_auto function'
  )
}}

-- Raw entities view that reads from JSONL files in the bronze layer
-- Uses DuckDB's read_json_auto function with glob pattern for multiple files
select 
    article_id,
    entity_text,
    entity_type,
    confidence_score::double as confidence_score,
    start_char::int as start_char,
    end_char::int as end_char,
    extracted_at::timestamp as extracted_at,
    created_at::timestamp as created_at,
    
    -- Add metadata
    current_timestamp as dbt_loaded_at
    
from read_json_auto('/workspaces/NeuroNews/data/bronze/entities/**/*.jsonl',
                    format='newline_delimited',
                    union_by_name=true)

-- Filter out any records with missing required fields
where article_id is not null 
  and entity_text is not null 
  and entity_type is not null
  and confidence_score is not null
  and extracted_at is not null
  and created_at is not null
