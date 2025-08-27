-- Time spine model for MetricFlow semantic layer
{{ config(materialized='table') }}

SELECT 
    date_day
FROM {{ ref('time_spine') }}
