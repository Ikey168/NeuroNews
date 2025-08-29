-- Test to ensure fact news has referential integrity with dim_source

select fn.source_key
from {{ ref('fact_news') }} fn
left join {{ ref('dim_source') }} ds
    on fn.source_key = ds.source_key
where ds.source_key is null
