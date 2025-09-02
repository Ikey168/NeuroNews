{% macro incremental_filter(date_column='published_at_utc', updated_column='updated_at_utc') %}
  {%- if is_incremental() -%}
    {{ date_column }}::date > (
        SELECT COALESCE(MAX({{ date_column }}::date), '1900-01-01'::date) 
        FROM {{ this }}
    )
       OR {{ updated_column }} > (
        SELECT COALESCE(MAX({{ updated_column }}), '1900-01-01'::timestamp) 
        FROM {{ this }}
    )
  {%- endif -%}
{% endmacro %}
