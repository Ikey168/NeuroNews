-- Simple sample data model for sources semantic layer demonstration
{{ config(materialized='table') }}

SELECT 
    'src_001' as source_id,
    'TechNews Daily' as source_name,
    'technology' as category,
    'US' as country_code
UNION ALL
SELECT 
    'src_002' as source_id,
    'Business Wire' as source_name,
    'business' as category,
    'UK' as country_code
UNION ALL
SELECT 
    'src_003' as source_id,
    'Sports Central' as source_name,
    'sports' as category,
    'CA' as country_code
