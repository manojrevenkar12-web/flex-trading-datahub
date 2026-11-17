-- Device energy per quarter hour: each counter is read at every quarter-hour boundary by interpolating between the
-- reports either side of it. A boundary with no report within an hour either side is marked as a gap.
with bounds as (
    select d.device_id, d.customer_id, d.kind, d.counter, s.qh_start_utc as t
    from (select distinct device_id, customer_id, kind, counter from {{ ref('int_device_counters') }}) d
    cross join (
        select qh_start_utc from {{ ref('int_qh_spine') }}
        union all select max(qh_start_utc) + interval 15 minute from {{ ref('int_qh_spine') }}
    ) s
), at_bound as (
    select
        b.*,
        p.reported_at_utc as t0, p.energy_kwh as e0,
        n.reported_at_utc as t1, n.energy_kwh as e1
    from bounds b
    asof left join {{ ref('int_device_counters') }} p
        on b.device_id = p.device_id and b.counter = p.counter and p.reported_at_utc <= b.t
    asof left join {{ ref('int_device_counters') }} n
        on b.device_id = n.device_id and b.counter = n.counter and n.reported_at_utc >= b.t
), interp as (
    select
        *,
        case
            when t0 is null or t1 is null then null
            when t1 = t0 then e0
            else e0 + (e1 - e0) * epoch(t - t0) / epoch(t1 - t0)
        end as energy_at,
        coalesce(epoch(t1 - t0) > 3600, true) as in_gap
    from at_bound
)
select
    device_id, customer_id, kind, counter,
    t as qh_start_utc,
    lead(energy_at) over w - energy_at as kwh,
    in_gap or lead(in_gap) over w as in_gap
from interp
window w as (partition by device_id, counter order by t)
qualify lead(t) over w is not null
