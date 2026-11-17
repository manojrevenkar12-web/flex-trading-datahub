{# The delivery day a quarter hour belongs to, in Europe/Berlin: 25 October 2026 has 100 quarter hours. #}
{% macro delivery_day(utc_ts) -%}
cast(timezone('Europe/Berlin', timezone('UTC', {{ utc_ts }})) as date)
{%- endmacro %}

{# Local midnight of a delivery day, as a UTC timestamp. #}
{% macro local_midnight_utc(day) -%}
timezone('UTC', timezone('Europe/Berlin', cast({{ day }} as timestamp)))
{%- endmacro %}

{# The day-ahead gate for a delivery day: 12:00 local on the day before, as UTC. #}
{% macro gate_utc(day) -%}
timezone('UTC', timezone('Europe/Berlin', cast({{ day }} as timestamp) - interval 1 day + to_hours({{ var('gate_hour_local') }})))
{%- endmacro %}

{# Energy in kWh from a value and its unit: one metering operator sends Wh, another kWh. #}
{% macro to_kwh(value, unit) -%}
cast({{ value }} as double) * case {{ unit }} when 'Wh' then 0.001 when 'kWh' then 1.0 when 'MWh' then 1000.0 end
{%- endmacro %}
