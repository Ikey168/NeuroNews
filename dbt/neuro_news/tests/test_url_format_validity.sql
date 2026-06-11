-- Test to ensure URL format validity in news articles

select *
from {{ ref('stg_news') }}
where url not like 'http%'
   or url is null
   or length(url) < 10
