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

-- Most frequently mentioned entities using parse_json
WITH parsed_entities AS (
    SELECT 
        source,
        entities::VARCHAR as entities_json
    FROM news_articles
),
entity_counts AS (
    SELECT
        source,
        'ORG' as entity_type,
        json_extract_path_text(entities_json::VARCHAR, 'ORG') as entities_array
    FROM parsed_entities
    UNION ALL
    SELECT
        source,
        'PERSON' as entity_type,
        json_extract_path_text(entities_json::VARCHAR, 'PERSON') as entities_array
    FROM parsed_entities
    UNION ALL
    SELECT
        source,
        'LOC' as entity_type,
        json_extract_path_text(entities_json::VARCHAR, 'LOC') as entities_array
    FROM parsed_entities
)
SELECT
    entity_type,
    entities_array,
    COUNT(*) as mention_count
FROM entity_counts
WHERE entities_array IS NOT NULL
GROUP BY entity_type, entities_array
ORDER BY mention_count DESC
LIMIT 20;

-- Top keywords analysis (simplified)
SELECT
    source,
    LISTAGG(DISTINCT 
        CASE 
            WHEN keywords::VARCHAR LIKE '%"AI"%' THEN 'AI'
            WHEN keywords::VARCHAR LIKE '%"technology"%' THEN 'technology'
            WHEN keywords::VARCHAR LIKE '%"research"%' THEN 'research'
            WHEN keywords::VARCHAR LIKE '%"science"%' THEN 'science'
            WHEN keywords::VARCHAR LIKE '%"business"%' THEN 'business'
            ELSE NULL
        END, 
        ', ' 
    ) WITHIN GROUP (ORDER BY source) as common_keywords
FROM news_articles
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

-- Source statistics with keyword counts
SELECT
    source,
    COUNT(*) as article_count,
    AVG(sentiment) as avg_sentiment,
    SUM(CASE WHEN keywords::VARCHAR LIKE '%"AI"%' THEN 1 ELSE 0 END) as ai_mentions,
    SUM(CASE WHEN keywords::VARCHAR LIKE '%"technology"%' THEN 1 ELSE 0 END) as tech_mentions,
    SUM(CASE WHEN keywords::VARCHAR LIKE '%"research"%' THEN 1 ELSE 0 END) as research_mentions
FROM news_articles
GROUP BY source
ORDER BY article_count DESC;

-- Daily article count by source
SELECT
    source,
    DATE_TRUNC('day', published_date) as date,
    COUNT(*) as article_count
FROM news_articles
GROUP BY source, DATE_TRUNC('day', published_date)
ORDER BY date DESC, article_count DESC;

-- Entity type distribution by source
WITH parsed_entities AS (
    SELECT 
        source,
        entities::VARCHAR as entities_json
    FROM news_articles
),
entity_types AS (
    SELECT DISTINCT
        source,
        CASE
            WHEN json_extract_path_text(entities_json::VARCHAR, 'ORG') IS NOT NULL THEN 'ORG'
            WHEN json_extract_path_text(entities_json::VARCHAR, 'PERSON') IS NOT NULL THEN 'PERSON'
            WHEN json_extract_path_text(entities_json::VARCHAR, 'LOC') IS NOT NULL THEN 'LOC'
        END as entity_type
    FROM parsed_entities
    WHERE entities_json IS NOT NULL
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