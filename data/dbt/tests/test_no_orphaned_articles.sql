-- Test that fact_articles has no orphaned records
select *
from {{ ref('fact_articles') }}
where article_id not in (
    select article_id 
    from {{ ref('stg_articles_raw') }}
)
