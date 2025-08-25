{{ config(materialized='table') }}

SELECT 
    e.article_id as entity_article_id,
    n.article_id as news_article_id,
    CASE WHEN n.article_id IS NULL THEN 'MISSING' ELSE 'FOUND' END as status
FROM {{ ref('stg_entities') }} e
LEFT JOIN {{ ref('stg_news') }} n ON e.article_id = n.article_id
WHERE n.article_id IS NULL
