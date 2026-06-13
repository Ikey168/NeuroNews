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

-- Daily aggregated metrics for trend analysis
-- Time-series data for dashboards and monitoring

with daily_metrics as (
    select
        published_date,
        
        -- Volume metrics
        count(*) as total_articles,
        count(distinct source) as unique_sources,
        count(distinct category) as unique_categories,
        count(case when is_fully_enriched then 1 end) as enriched_articles,
        
        -- Content quality metrics
        avg(content_quality_score) as avg_content_quality,
        avg(bias_score) as avg_bias_score,
        avg(factuality_score) as avg_factuality_score,
        
        -- Sentiment metrics
        avg(sentiment_score) as avg_sentiment_score,
        count(case when sentiment_category = 'positive' then 1 end) as positive_articles,
        count(case when sentiment_category = 'negative' then 1 end) as negative_articles,
        count(case when sentiment_category = 'neutral' then 1 end) as neutral_articles,
        
        -- Engagement metrics
        avg(viral_potential) as avg_viral_potential,
        avg(engagement_prediction) as avg_engagement_prediction,
        avg(trend_score) as avg_trend_score,
        
        -- Content characteristics
        avg(word_count) as avg_word_count,
        avg(readability_score) as avg_readability_score,
        avg(content_length) as avg_content_length,
        
        -- Processing metrics
        avg(hours_since_processed) as avg_processing_delay,
        avg(hours_since_enriched) as avg_enrichment_delay,
        
        -- Language distribution
        count(case when language = 'en' then 1 end) as english_articles,
        count(case when language != 'en' then 1 end) as non_english_articles,
        
        -- Quality distribution
        count(case when content_quality_tier = 'high' then 1 end) as high_quality_articles,
        count(case when content_quality_tier = 'medium' then 1 end) as medium_quality_articles,
        count(case when content_quality_tier = 'low' then 1 end) as low_quality_articles,
        count(case when content_quality_tier = 'very_low' then 1 end) as very_low_quality_articles,
        
        -- Viral potential distribution
        count(case when viral_potential_tier = 'high' then 1 end) as high_viral_potential,
        count(case when viral_potential_tier = 'medium' then 1 end) as medium_viral_potential,
        count(case when viral_potential_tier = 'low' then 1 end) as low_viral_potential,
        count(case when viral_potential_tier = 'very_low' then 1 end) as very_low_viral_potential,
        
        -- Partitioning fields
        year,
        month,
        day

    from {{ ref('fact_articles') }}
    group by published_date, year, month, day
),

daily_metrics_enhanced as (
    select
        *,
        
        -- Calculate day-over-day changes
        lag(total_articles, 1) over (order by published_date) as prev_day_articles,
        total_articles - lag(total_articles, 1) over (order by published_date) as articles_change,
        
        -- Calculate moving averages
        avg(total_articles) over (
            order by published_date 
            rows between 6 preceding and current row
        ) as articles_7day_avg,
        
        avg(avg_sentiment_score) over (
            order by published_date 
            rows between 6 preceding and current row
        ) as sentiment_7day_avg,
        
        avg(avg_content_quality) over (
            order by published_date 
            rows between 6 preceding and current row
        ) as quality_7day_avg,
        
        -- Calculate percentages
        round(positive_articles * 100.0 / total_articles, 2) as positive_pct,
        round(negative_articles * 100.0 / total_articles, 2) as negative_pct,
        round(neutral_articles * 100.0 / total_articles, 2) as neutral_pct,
        round(enriched_articles * 100.0 / total_articles, 2) as enrichment_rate,
        round(english_articles * 100.0 / total_articles, 2) as english_pct,
        
        -- Data quality indicators
        case 
            when enrichment_rate >= 95 then 'excellent'
            when enrichment_rate >= 85 then 'good'
            when enrichment_rate >= 70 then 'fair'
            else 'poor'
        end as data_quality_status,
        
        -- Volume categorization
        case 
            when total_articles >= 10000 then 'very_high'
            when total_articles >= 5000 then 'high'
            when total_articles >= 1000 then 'medium'
            when total_articles >= 100 then 'low'
            else 'very_low'
        end as volume_category,
        
        -- Day of week analysis
        extract(dayofweek from published_date) as day_of_week,
        case extract(dayofweek from published_date)
            when 1 then 'Sunday'
            when 2 then 'Monday'
            when 3 then 'Tuesday'
            when 4 then 'Wednesday'
            when 5 then 'Thursday'
            when 6 then 'Friday'
            when 7 then 'Saturday'
        end as day_name

    from daily_metrics
)

select * from daily_metrics_enhanced
