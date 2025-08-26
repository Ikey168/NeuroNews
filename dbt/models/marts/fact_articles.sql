{{
  config(
    materialized='table',
    schema='marts',
    file_format='iceberg',
    table_type='iceberg',
    partition_by=['year', 'month'],
    table_properties={
      'write.format.default': 'parquet',
      'write.parquet.compression-codec': 'snappy',
      'history.expire.max-snapshot-age-ms': '432000000',
      'history.expire.min-snapshots-to-keep': '5'
    }
  )
}}

-- Articles fact table for analytics
-- Combines raw and enriched data for comprehensive analysis

with articles_base as (
    select
        -- Identifiers
        article_id,
        url,
        
        -- Content
        title,
        content,
        summary,
        
        -- Source metadata
        source,
        category,
        language,
        
        -- Temporal
        published_at,
        processed_at,
        
        -- Quality indicators
        is_valid_row,
        hours_since_processed,
        
        -- Partitioning
        year,
        month,
        day,
        hour

    from {{ ref('stg_articles_raw') }}
    where is_valid_row = true
),

articles_enriched as (
    select
        -- Identifiers
        article_id,
        
        -- Enrichment timestamps
        enriched_at,
        
        -- Sentiment analysis
        sentiment_score,
        sentiment_label,
        sentiment_confidence,
        
        -- Topic modeling
        topics,
        topic_scores,
        primary_topic,
        
        -- Named entities
        entities,
        entity_types,
        
        -- Content analytics
        keywords,
        readability_score,
        word_count,
        language_confidence,
        
        -- Quality metrics
        content_quality_score,
        bias_score,
        factuality_score,
        
        -- Trend indicators
        trend_score,
        viral_potential,
        engagement_prediction,
        
        -- Clustering
        cluster_id,
        
        -- Quality indicators
        is_fully_enriched,
        hours_since_enriched

    from {{ ref('stg_articles_enriched') }}
),

combined_articles as (
    select
        -- Identifiers and basic info
        b.article_id,
        b.url,
        b.title,
        b.content,
        b.summary,
        
        -- Source metadata
        b.source,
        b.category,
        b.language,
        
        -- Temporal fields
        b.published_at,
        b.processed_at,
        e.enriched_at,
        
        -- Content metrics
        length(b.content) as content_length,
        coalesce(e.word_count, 0) as word_count,
        coalesce(e.readability_score, 0.0) as readability_score,
        
        -- Sentiment analysis
        coalesce(e.sentiment_score, 0.0) as sentiment_score,
        coalesce(e.sentiment_label, 'neutral') as sentiment_label,
        coalesce(e.sentiment_confidence, 0.0) as sentiment_confidence,
        
        -- Topic modeling
        e.topics,
        e.topic_scores,
        e.primary_topic,
        
        -- Named entities
        e.entities,
        e.entity_types,
        
        -- Keywords
        e.keywords,
        
        -- Quality scores
        coalesce(e.content_quality_score, 0.0) as content_quality_score,
        coalesce(e.bias_score, 0.0) as bias_score,
        coalesce(e.factuality_score, 0.0) as factuality_score,
        
        -- Trend and engagement
        coalesce(e.trend_score, 0.0) as trend_score,
        coalesce(e.viral_potential, 0.0) as viral_potential,
        coalesce(e.engagement_prediction, 0.0) as engagement_prediction,
        
        -- Clustering
        e.cluster_id,
        
        -- Data quality flags
        b.is_valid_row,
        coalesce(e.is_fully_enriched, false) as is_fully_enriched,
        
        -- Freshness indicators
        b.hours_since_processed,
        coalesce(e.hours_since_enriched, 999999) as hours_since_enriched,
        
        -- Derived metrics
        case 
            when e.sentiment_score > 0.1 then 'positive'
            when e.sentiment_score < -0.1 then 'negative'
            else 'neutral'
        end as sentiment_category,
        
        case 
            when e.content_quality_score >= 0.8 then 'high'
            when e.content_quality_score >= 0.6 then 'medium'
            when e.content_quality_score >= 0.4 then 'low'
            else 'very_low'
        end as content_quality_tier,
        
        case 
            when e.viral_potential >= 0.7 then 'high'
            when e.viral_potential >= 0.5 then 'medium'
            when e.viral_potential >= 0.3 then 'low'
            else 'very_low'
        end as viral_potential_tier,
        
        -- Time-based features
        extract(dayofweek from b.published_at) as day_of_week,
        extract(hour from b.published_at) as hour_of_day,
        date(b.published_at) as published_date,
        
        -- Partitioning fields
        b.year,
        b.month,
        b.day,
        b.hour

    from articles_base b
    left join articles_enriched e
        on b.article_id = e.article_id
)

select * from combined_articles
