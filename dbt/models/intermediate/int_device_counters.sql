-- Device energy counters made continuous: a counter that restarts at zero after a firmware update is stitched on,
-- so energy is never lost or counted negative.
with long as (
    select device_id, customer_id, kind, reported_at_utc, 'main' as counter, energy_kwh as reading from {{ ref('stg_device_telemetry') }}
    union all
    select device_id, customer_id, kind, reported_at_utc, 'second', energy2_kwh from {{ ref('stg_device_telemetry') }} where energy2_kwh is not null
), dedup as (
    select device_id, customer_id, kind, counter, reported_at_utc, max(reading) as reading
    from long group by all
), deltas as (
    select *, reading - lag(reading) over w as delta
    from dedup
    window w as (partition by device_id, counter order by reported_at_utc)
)
select
    device_id, customer_id, kind, counter, reported_at_utc, reading,
    delta < -0.5 as is_reset,
    sum(case when delta is null then 0 when delta < -0.5 then reading else greatest(delta, 0) end)
        over (partition by device_id, counter order by reported_at_utc rows unbounded preceding) as energy_kwh
from deltas
