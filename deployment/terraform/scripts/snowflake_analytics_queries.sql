-- Snowflake Analytics Queries for NeuroNews
-- Migrated from Redshift to Snowflake-compatible syntax
-- Issue #244: Update analytics queries and integrations for Snowflake

-- Average sentiment by source over time
SELECT
    source,
    DATE_TRUNC('day', published_date) as date,
    AVG(sentiment) as avg_sentiment,
    COUNT(*) as article_count
FROM news_articles
WHERE sentiment IS NOT NULL
GROUP BY source, DATE_TRUNC('day', published_date)
ORDER BY source, date;

-- Most frequently mentioned entities using Snowflake JSON functions
WITH parsed_entities AS (
    SELECT 
        source,
        entities as entities_json
    FROM news_articles
    WHERE entities IS NOT NULL
),
entity_extraction AS (
    SELECT
        source,
        'ORG' as entity_type,
        PARSE_JSON(entities_json):ORG as entities_array
    FROM parsed_entities
    WHERE PARSE_JSON(entities_json):ORG IS NOT NULL
    UNION ALL
    SELECT
        source,
        'PERSON' as entity_type,
        PARSE_JSON(entities_json):PERSON as entities_array
    FROM parsed_entities
    WHERE PARSE_JSON(entities_json):PERSON IS NOT NULL
    UNION ALL
    SELECT
        source,
        'LOC' as entity_type,
        PARSE_JSON(entities_json):LOC as entities_array
    FROM parsed_entities
    WHERE PARSE_JSON(entities_json):LOC IS NOT NULL
),
flattened_entities AS (
    SELECT
        source,
        entity_type,
        f.value::string as entity_name
    FROM entity_extraction e,
    LATERAL FLATTEN(input => entities_array) f
)
SELECT
    entity_type,
    entity_name,
    COUNT(*) as mention_count
FROM flattened_entities
WHERE entity_name IS NOT NULL
GROUP BY entity_type, entity_name
ORDER BY mention_count DESC
LIMIT 20;

-- Top keywords analysis using Snowflake array functions
WITH keyword_extraction AS (
    SELECT
        source,
        PARSE_JSON(keywords) as keywords_json
    FROM news_articles
    WHERE keywords IS NOT NULL
),
flattened_keywords AS (
    SELECT
        source,
        f.value::string as keyword
    FROM keyword_extraction k,
    LATERAL FLATTEN(input => keywords_json) f
)
SELECT
    source,
    LISTAGG(DISTINCT 
        CASE 
            WHEN LOWER(keyword) = 'ai' THEN 'AI'
            WHEN LOWER(keyword) = 'technology' THEN 'technology'
            WHEN LOWER(keyword) = 'research' THEN 'research'
            WHEN LOWER(keyword) = 'science' THEN 'science'
            WHEN LOWER(keyword) = 'business' THEN 'business'
            ELSE NULL
        END, 
        ', ' 
    ) WITHIN GROUP (ORDER BY source) as common_keywords
FROM flattened_keywords
GROUP BY source;

-- Articles with highest positive sentiment
SELECT
    title,
    source,
    published_date,
    sentiment
FROM news_articles
WHERE sentiment IS NOT NULL
ORDER BY sentiment DESC
LIMIT 10;

-- Articles with lowest negative sentiment
SELECT
    title,
    source,
    published_date,
    sentiment
FROM news_articles
WHERE sentiment IS NOT NULL
ORDER BY sentiment ASC
LIMIT 10;

-- Source statistics with keyword counts using Snowflake JSON functions
WITH keyword_stats AS (
    SELECT
        source,
        PARSE_JSON(keywords) as keywords_json
    FROM news_articles
    WHERE keywords IS NOT NULL
),
keyword_counts AS (
    SELECT
        source,
        SUM(CASE WHEN ARRAY_CONTAINS('AI'::variant, keywords_json) THEN 1 ELSE 0 END) as ai_mentions,
        SUM(CASE WHEN ARRAY_CONTAINS('technology'::variant, keywords_json) THEN 1 ELSE 0 END) as tech_mentions,
        SUM(CASE WHEN ARRAY_CONTAINS('research'::variant, keywords_json) THEN 1 ELSE 0 END) as research_mentions
    FROM keyword_stats
    GROUP BY source
)
SELECT
    n.source,
    COUNT(*) as article_count,
    AVG(n.sentiment) as avg_sentiment,
    COALESCE(k.ai_mentions, 0) as ai_mentions,
    COALESCE(k.tech_mentions, 0) as tech_mentions,
    COALESCE(k.research_mentions, 0) as research_mentions
FROM news_articles n
LEFT JOIN keyword_counts k ON n.source = k.source
GROUP BY n.source, k.ai_mentions, k.tech_mentions, k.research_mentions
ORDER BY article_count DESC;

-- Daily article count by source
SELECT
    source,
    DATE_TRUNC('day', published_date) as date,
    COUNT(*) as article_count
FROM news_articles
GROUP BY source, DATE_TRUNC('day', published_date)
ORDER BY date DESC, article_count DESC;

-- Entity type distribution by source using Snowflake JSON functions
WITH entity_extraction AS (
    SELECT 
        source,
        entities as entities_json
    FROM news_articles
    WHERE entities IS NOT NULL
),
entity_types AS (
    SELECT DISTINCT
        source,
        CASE
            WHEN PARSE_JSON(entities_json):ORG IS NOT NULL THEN 'ORG'
            WHEN PARSE_JSON(entities_json):PERSON IS NOT NULL THEN 'PERSON'
            WHEN PARSE_JSON(entities_json):LOC IS NOT NULL THEN 'LOC'
            WHEN PARSE_JSON(entities_json):GPE IS NOT NULL THEN 'GPE'
            WHEN PARSE_JSON(entities_json):EVENT IS NOT NULL THEN 'EVENT'
        END as entity_type
    FROM entity_extraction
)
SELECT
    source,
    entity_type,
    COUNT(*) as type_count
FROM entity_types
WHERE entity_type IS NOT NULL
GROUP BY source, entity_type
ORDER BY source, type_count DESC;

-- Content length analysis
SELECT
    source,
    AVG(LENGTH(content)) as avg_content_length,
    MIN(LENGTH(content)) as min_content_length,
    MAX(LENGTH(content)) as max_content_length,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY LENGTH(content)) as median_content_length
FROM news_articles
GROUP BY source
ORDER BY avg_content_length DESC;

-- Hourly publishing patterns
SELECT
    source,
    EXTRACT(HOUR FROM published_date) as hour_of_day,
    COUNT(*) as article_count
FROM news_articles
GROUP BY source, EXTRACT(HOUR FROM published_date)
ORDER BY source, hour_of_day;

-- Advanced analytics queries for Snowflake

-- Sentiment trend analysis with time series
SELECT
    source,
    DATE_TRUNC('hour', published_date) as hour,
    AVG(sentiment) as avg_sentiment,
    STDDEV(sentiment) as sentiment_volatility,
    COUNT(*) as article_count,
    -- Rolling average sentiment over last 24 hours
    AVG(sentiment) OVER (
        PARTITION BY source 
        ORDER BY DATE_TRUNC('hour', published_date) 
        ROWS BETWEEN 23 PRECEDING AND CURRENT ROW
    ) as rolling_24h_sentiment
FROM news_articles
WHERE sentiment IS NOT NULL
    AND published_date >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY source, DATE_TRUNC('hour', published_date)
ORDER BY source, hour;

-- Entity co-occurrence analysis
WITH entity_pairs AS (
    SELECT 
        source,
        e1.value::string as entity1,
        e2.value::string as entity2
    FROM news_articles n,
    LATERAL FLATTEN(input => PARSE_JSON(entities):ORG) e1,
    LATERAL FLATTEN(input => PARSE_JSON(entities):PERSON) e2
    WHERE entities IS NOT NULL
        AND e1.value::string != e2.value::string
)
SELECT
    entity1,
    entity2,
    COUNT(*) as co_occurrence_count,
    COUNT(DISTINCT source) as sources_count
FROM entity_pairs
GROUP BY entity1, entity2
HAVING COUNT(*) >= 3
ORDER BY co_occurrence_count DESC
LIMIT 50;

-- Topic trending analysis
WITH hourly_keywords AS (
    SELECT
        DATE_TRUNC('hour', published_date) as hour,
        f.value::string as keyword
    FROM news_articles n,
    LATERAL FLATTEN(input => PARSE_JSON(keywords)) f
    WHERE keywords IS NOT NULL
        AND published_date >= DATEADD('day', -1, CURRENT_TIMESTAMP())
),
keyword_velocity AS (
    SELECT
        keyword,
        hour,
        COUNT(*) as hourly_count,
        -- Calculate velocity (change from previous hour)
        COUNT(*) - LAG(COUNT(*), 1, 0) OVER (
            PARTITION BY keyword 
            ORDER BY hour
        ) as velocity
    FROM hourly_keywords
    GROUP BY keyword, hour
)
SELECT
    keyword,
    SUM(hourly_count) as total_mentions,
    AVG(velocity) as avg_velocity,
    MAX(velocity) as peak_velocity,
    STDDEV(velocity) as velocity_volatility
FROM keyword_velocity
WHERE keyword IS NOT NULL
GROUP BY keyword
HAVING SUM(hourly_count) >= 5
ORDER BY avg_velocity DESC
LIMIT 20;

-- Geographic sentiment analysis
WITH location_sentiment AS (
    SELECT
        f.value::string as location,
        sentiment,
        published_date
    FROM news_articles n,
    LATERAL FLATTEN(input => PARSE_JSON(entities):LOC) f
    WHERE entities IS NOT NULL
        AND sentiment IS NOT NULL
        AND f.value::string IS NOT NULL
)
SELECT
    location,
    COUNT(*) as mention_count,
    AVG(sentiment) as avg_sentiment,
    STDDEV(sentiment) as sentiment_variance,
    MIN(sentiment) as min_sentiment,
    MAX(sentiment) as max_sentiment,
    -- Sentiment trend over time
    CORR(EXTRACT(EPOCH FROM published_date), sentiment) as sentiment_time_correlation
FROM location_sentiment
GROUP BY location
HAVING COUNT(*) >= 10
ORDER BY avg_sentiment DESC;

-- Source reliability and coverage analysis
WITH source_metrics AS (
    SELECT
        source,
        COUNT(*) as total_articles,
        COUNT(DISTINCT DATE_TRUNC('day', published_date)) as active_days,
        AVG(LENGTH(content)) as avg_article_length,
        STDDEV(sentiment) as sentiment_consistency,
        COUNT(DISTINCT PARSE_JSON(entities):ORG[0]::string) as unique_orgs_covered,
        COUNT(DISTINCT PARSE_JSON(entities):PERSON[0]::string) as unique_people_covered
    FROM news_articles
    WHERE published_date >= DATEADD('month', -1, CURRENT_TIMESTAMP())
    GROUP BY source
)
SELECT
    source,
    total_articles,
    active_days,
    ROUND(total_articles::float / active_days, 2) as articles_per_day,
    avg_article_length,
    sentiment_consistency,
    unique_orgs_covered,
    unique_people_covered,
    -- Diversity score based on unique entities
    ROUND(
        (unique_orgs_covered + unique_people_covered)::float / total_articles * 100, 
        2
    ) as entity_diversity_score
FROM source_metrics
ORDER BY total_articles DESC;
