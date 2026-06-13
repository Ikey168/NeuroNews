{{
  config(
    materialized='view',
    schema='staging'
  )
}}

-- Staging view for enriched articles from Iceberg
-- Includes NLP enrichments and entity extractions

with source_data as (
    select
        -- Primary identifiers
        id as article_id,
        url,
        
        -- Content fields
        title,
        body as content,
        summary,
        
        -- Source information
        source,
        category,
        
        -- Temporal fields
        published_at,
        processed_at,
        enriched_at,
        created_at,
        updated_at,
        
        -- NLP enrichments
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
        entity_sentiment,
        
        -- Keywords and tags
        keywords,
        tags,
        auto_tags,
        
        -- Text analytics
        readability_score,
        word_count,
        language,
        language_confidence,
        
        -- Similarity and clustering
        embedding_vector,
        cluster_id,
        similar_articles,
        
        -- Trend indicators
        trend_score,
        viral_potential,
        engagement_prediction,
        
        -- Quality metrics
        content_quality_score,
        bias_score,
        factuality_score,
        
        -- Partitioning fields
        year,
        month,
        day,
        hour,
        
        -- Technical fields
        hash_content,
        enrichment_version

    from {{ source('iceberg', 'articles_enriched') }}
),

cleaned_data as (
    select
        article_id,
        url,
        
        -- Clean content
        trim(title) as title,
        trim(content) as content,
        trim(summary) as summary,
        
        -- Standardize source
        lower(trim(source)) as source,
        coalesce(category, 'unknown') as category,
        
        -- Temporal fields
        published_at,
        processed_at,
        enriched_at,
        created_at,
        updated_at,
        
        -- Sentiment analysis
        coalesce(sentiment_score, 0.0) as sentiment_score,
        coalesce(sentiment_label, 'neutral') as sentiment_label,
        coalesce(sentiment_confidence, 0.0) as sentiment_confidence,
        
        -- Topic modeling
        topics,
        topic_scores,
        primary_topic,
        
        -- Named entities
        entities,
        entity_types,
        entity_sentiment,
        
        -- Keywords and tags
        keywords,
        tags,
        auto_tags,
        
        -- Text analytics
        coalesce(readability_score, 0.0) as readability_score,
        coalesce(word_count, 0) as word_count,
        coalesce(language, 'en') as language,
        coalesce(language_confidence, 0.0) as language_confidence,
        
        -- Similarity and clustering
        embedding_vector,
        cluster_id,
        similar_articles,
        
        -- Trend indicators
        coalesce(trend_score, 0.0) as trend_score,
        coalesce(viral_potential, 0.0) as viral_potential,
        coalesce(engagement_prediction, 0.0) as engagement_prediction,
        
        -- Quality metrics
        coalesce(content_quality_score, 0.0) as content_quality_score,
        coalesce(bias_score, 0.0) as bias_score,
        coalesce(factuality_score, 0.0) as factuality_score,
        
        -- Partitioning fields
        cast(year as int) as year,
        cast(month as int) as month,
        cast(day as int) as day,
        cast(hour as int) as hour,
        
        -- Technical fields
        hash_content,
        enrichment_version,
        
        -- Add enrichment quality indicators
        case 
            when enriched_at is null then false
            when sentiment_score is null then false
            when topics is null or size(topics) = 0 then false
            else true
        end as is_fully_enriched,
        
        -- Add enrichment freshness
        datediff('hour', enriched_at, current_timestamp()) as hours_since_enriched

    from source_data
)

select * from cleaned_data
