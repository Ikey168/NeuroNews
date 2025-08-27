-- Simple sample data model for semantic layer demonstration
{{ config(materialized='table') }}

SELECT 
    1 as article_id,
    'Technology' as category,
    '2024-08-27'::date as published_date,
    'Sample Article' as title
UNION ALL
SELECT 
    2 as article_id,
    'Business' as category,
    '2024-08-26'::date as published_date,
    'Another Article' as title
