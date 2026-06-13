-- Simple sample data model for semantic layer demonstration
{{ config(materialized='table') }}

SELECT 
    1 as article_id,
    'src_001' as source_id,
    'Technology' as category,
    '2024-08-27'::date as published_date,
    'Sample Article' as title,
    'en' as language,
    0.75 as sentiment_score
UNION ALL
SELECT 
    2 as article_id,
    'src_002' as source_id,
    'Business' as category,
    '2024-08-26'::date as published_date,
    'Another Article' as title,
    'en' as language,
    -0.25 as sentiment_score
UNION ALL
SELECT 
    3 as article_id,
    'src_001' as source_id,
    'Sports' as category,
    '2024-08-25'::date as published_date,
    'Sports Update' as title,
    'es' as language,
    0.50 as sentiment_score
