-- For each hour of each delivery day, the latest forecast that had been issued by that day's day-ahead gate.
-- Joining the newest run for each hour instead would hand a backtest weather it could not have known.
with hours as (
    select distinct date_trunc('hour', qh_start_utc) as valid_hour_utc, delivery_day, {{ gate_utc('delivery_day') }} as gate_utc
    from {{ ref('int_qh_spine') }}
)
select h.valid_hour_utc, h.delivery_day, h.gate_utc,
       arg_max(f.temp_c, f.issued_at_utc) as temp_c,
       arg_max(f.cloud, f.issued_at_utc) as cloud,
       max(f.issued_at_utc) as issued_at_utc
from hours h
join {{ ref('stg_weather_forecasts') }} f
  on f.valid_hour_utc = h.valid_hour_utc and f.issued_at_utc <= h.gate_utc
group by all
