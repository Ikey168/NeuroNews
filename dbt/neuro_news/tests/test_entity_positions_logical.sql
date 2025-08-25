-- Test to ensure entity positions are logically consistent
-- end_position should always be greater than start_position

select *
from {{ ref('stg_entities') }}
where end_position <= start_position
