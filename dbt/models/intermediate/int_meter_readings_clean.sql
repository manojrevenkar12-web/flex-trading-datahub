-- Readings ready for trading analysis: a stuck register's values are replaced with that meter's own average for the
-- same local time of day on days it was working, and marked as estimated. Settlement still uses what was metered.
with r as (
    select m.*,
           strftime(timezone('Europe/Berlin', timezone('UTC', m.qh_start_utc)), '%H:%M') as local_clock,
           s.meter_id is not null as is_stuck
    from {{ ref('int_meter_readings') }} m
    left join {{ ref('int_stuck_runs') }} s
      on m.meter_id = s.meter_id and m.obis = '1-0:1.8.0' and m.qh_start_utc between s.stuck_from_utc and s.stuck_to_utc
), profile as (
    select meter_id, obis, local_clock, avg(kwh) as kwh from r where not is_stuck group by all
)
select r.* exclude (kwh, local_clock), coalesce(case when r.is_stuck then p.kwh end, r.kwh) as kwh, r.kwh as metered_kwh, r.is_stuck as is_estimated
from r left join profile p using (meter_id, obis, local_clock)
