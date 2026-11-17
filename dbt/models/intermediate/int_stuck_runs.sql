-- Meters that repeat exactly the same non-zero value for two days or more: a stuck register, not a household.
with r as (
    select meter_id, qh_start_utc, kwh,
           kwh = lag(kwh) over (partition by meter_id order by qh_start_utc) as same
    from {{ ref('int_meter_readings') }}
    where obis = '1-0:1.8.0'
), runs as (
    select *, sum(case when same then 0 else 1 end) over (partition by meter_id order by qh_start_utc) as run_id from r
)
select meter_id, min(qh_start_utc) as stuck_from_utc, max(qh_start_utc) as stuck_to_utc, count(*) as quarter_hours, any_value(kwh) as kwh
from runs
group by meter_id, run_id
having count(*) >= 192 and any_value(kwh) > 0
