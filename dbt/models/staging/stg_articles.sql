{{
  config(
    materialized='view',
    schema='staging',
    contract=dict(enforced=true)
  )
}}

-- Staging view for article ingestion data
-- Maps Avro schema fields to dbt staging columns with contract enforcement

with source_data as (
    select
        -- Primary identifiers (required in Avro schema)
        article_id,
        source_id,
        url,
        
        -- Content fields (optional in Avro schema)
        title,
        body as content,
        
        -- Metadata fields
        language,
        country,
        
        -- Temporal fields (required timestamps in Avro schema)
        -- Convert from milliseconds timestamp to standard timestamp
        timestamp_millis(published_at) as published_at,
        timestamp_millis(ingested_at) as ingested_at,
        
        -- NLP analysis fields (optional in Avro schema)
        sentiment_score,
        
        -- Topic fields (array in Avro schema)
        topics,
        
        -- Processing metadata
        current_timestamp() as processed_at

    from {{ source('kafka', 'article_ingest') }}
    
    -- Filter out invalid records
    where article_id is not null
      and source_id is not null
      and url is not null
      and language is not null
      and published_at is not null
      and ingested_at is not null
),

final as (
    select
        -- Primary identifiers
        article_id,
        source_id,
        url,
        
        -- Content fields
        title,
        content,
        
        -- Metadata
        language,
        country,
        
        -- Timestamps
        published_at,
        ingested_at,
        processed_at,
        
        -- Analytics
        sentiment_score,
        topics,
        
        -- Data quality flags
        case 
            when title is null and content is null then 'no_content'
            when title is null then 'no_title'
            when content is null then 'no_body'
            else 'complete'
        end as content_completeness,
        
        case
            when sentiment_score is not null then 'analyzed'
            else 'pending'
        end as sentiment_status,
        
        array_length(topics) as topic_count

    from source_data
)

select * from final
