-- Features to forecast the portfolio's net load for a delivery day, using only what was known at that day's
-- day-ahead gate (12:00 local the day before): the forecast run issued by then, the load a week earlier, and the
-- part of the day before yesterday that had already been delivered.
with base as (
    select
        f.qh_start_utc, f.delivery_day, f.net_mwh as target_net_mwh,
        timezone('Europe/Berlin', timezone('UTC', f.qh_start_utc)) as local_ts
    from {{ ref('fct_portfolio_qh') }} f
), local_net as (
    select timezone('Europe/Berlin', timezone('UTC', qh_start_utc)) as local_ts, net_mwh from {{ ref('fct_portfolio_qh') }}
), l7 as (
    -- a week earlier at the same local time; on the night summer time ends two quarter hours share a local time
    select b.qh_start_utc, avg(n.net_mwh) as net_7d_mwh
    from base b join local_net n on n.local_ts = b.local_ts - interval 7 day
    group by b.qh_start_utc
), arrived as (
    -- meter values of two days earlier that had arrived by the gate (received on or before the day before delivery)
    select r.qh_start_utc, timezone('Europe/Berlin', timezone('UTC', r.qh_start_utc)) as local_ts,
           r.received_on, r.obis, r.kwh, r.meter_id
    from {{ ref('int_meter_readings_clean') }} r
), d2 as (
    select b.qh_start_utc,
           sum(case when a.obis = '1-0:1.8.0' then a.kwh when a.obis = '1-0:2.8.0' then -a.kwh end) / 1000 as d2_net_known_mwh,
           count(distinct case when a.obis = '1-0:1.8.0' then a.meter_id end) as d2_meters_known
    from base b
    left join arrived a
      on a.local_ts = b.local_ts - interval 2 day and a.received_on <= b.delivery_day - 1
    group by b.qh_start_utc
)
select
    b.qh_start_utc, b.delivery_day, b.target_net_mwh,
    {{ gate_utc('b.delivery_day') }} as gate_utc,
    w.issued_at_utc as weather_issued_at_utc,
    hour(b.local_ts) + minute(b.local_ts) / 60.0 as local_hour,
    dayofweek(b.local_ts) as weekday,
    w.temp_c as fc_temp_c,
    w.cloud as fc_cloud,
    greatest(sin(pi() * (hour(b.qh_start_utc) + minute(b.qh_start_utc) / 60.0 - 5.5) / 11.5), 0) * (1 - 0.75 * w.cloud) as fc_sun,
    l7.net_7d_mwh,
    d2.d2_net_known_mwh,
    d2.d2_meters_known
from base b
left join {{ ref('int_weather_at_gate') }} w on w.valid_hour_utc = date_trunc('hour', b.qh_start_utc)
left join l7 on l7.qh_start_utc = b.qh_start_utc
left join d2 on d2.qh_start_utc = b.qh_start_utc
