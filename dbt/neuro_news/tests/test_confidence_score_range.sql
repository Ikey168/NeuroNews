-- Test to ensure confidence scores are within valid range [0,1]
-- across all entities

select *
from {{ ref('stg_entities') }}
where confidence_score < 0.0 
   or confidence_score > 1.0
   or confidence_score is null
