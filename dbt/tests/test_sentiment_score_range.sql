-- Test that articles_enriched has valid sentiment scores
select *
from {{ ref('stg_articles_enriched') }}
where sentiment_score < -1.0 or sentiment_score > 1.0
