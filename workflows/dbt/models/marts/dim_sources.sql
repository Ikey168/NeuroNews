{{
  config(
    materialized='table',
    schema='marts',
    file_format='iceberg',
    table_type='iceberg',
    partition_by=['year', 'month'],
    table_properties={
      'write.format.default': 'parquet',
      'write.parquet.compression-codec': 'snappy'
    }
  )
}}

-- Source dimension table for analytics
-- Aggregates metrics by news source

with source_metrics as (
    select
        source,
        
        -- Article counts
        count(*) as total_articles,
        count(case when is_fully_enriched then 1 end) as enriched_articles,
        
        -- Quality metrics
        avg(content_quality_score) as avg_content_quality,
        avg(bias_score) as avg_bias_score,
        avg(factuality_score) as avg_factuality_score,
        
        -- Sentiment distribution
        avg(sentiment_score) as avg_sentiment_score,
        count(case when sentiment_category = 'positive' then 1 end) as positive_articles,
        count(case when sentiment_category = 'negative' then 1 end) as negative_articles,
        count(case when sentiment_category = 'neutral' then 1 end) as neutral_articles,
        
        -- Engagement metrics
        avg(viral_potential) as avg_viral_potential,
        avg(engagement_prediction) as avg_engagement_prediction,
        
        -- Content metrics
        avg(word_count) as avg_word_count,
        avg(readability_score) as avg_readability_score,
        
        -- Temporal metrics
        min(published_at) as first_article_date,
        max(published_at) as last_article_date,
        
        -- Categories covered
        count(distinct category) as categories_covered,
        
        -- Language distribution
        count(distinct language) as languages_covered,
        
        -- Partitioning
        year,
        month

    from {{ ref('fact_articles') }}
    group by source, year, month
),

source_rankings as (
    select
        *,
        
        -- Calculate rankings within each time period
        rank() over (partition by year, month order by total_articles desc) as volume_rank,
        rank() over (partition by year, month order by avg_content_quality desc) as quality_rank,
        rank() over (partition by year, month order by avg_factuality_score desc) as factuality_rank,
        rank() over (partition by year, month order by avg_engagement_prediction desc) as engagement_rank,
        
        -- Calculate percentiles
        percent_rank() over (partition by year, month order by total_articles) as volume_percentile,
        percent_rank() over (partition by year, month order by avg_content_quality) as quality_percentile,
        
        -- Derived metrics
        case 
            when avg_content_quality >= 0.8 then 'premium'
            when avg_content_quality >= 0.6 then 'standard'
            when avg_content_quality >= 0.4 then 'basic'
            else 'low_quality'
        end as quality_tier,
        
        case 
            when total_articles >= 1000 then 'high_volume'
            when total_articles >= 100 then 'medium_volume'
            when total_articles >= 10 then 'low_volume'
            else 'minimal_volume'
        end as volume_tier,
        
        -- Sentiment distribution percentages
        round(positive_articles * 100.0 / total_articles, 2) as positive_pct,
        round(negative_articles * 100.0 / total_articles, 2) as negative_pct,
        round(neutral_articles * 100.0 / total_articles, 2) as neutral_pct,
        
        -- Enrichment rate
        round(enriched_articles * 100.0 / total_articles, 2) as enrichment_rate

    from source_metrics
)

select * from source_rankings
