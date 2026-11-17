-- Portfolio grid import and export per quarter hour, with how complete the metering is.
with meters as (select count(distinct meter_id) as expected from {{ ref('int_meter_readings_clean') }} where obis = '1-0:1.8.0')
select
    r.qh_start_utc,
    sum(case when obis = '1-0:1.8.0' then kwh end) / 1000 as import_mwh,
    coalesce(sum(case when obis = '1-0:2.8.0' then kwh end), 0) / 1000 as export_mwh,
    count(distinct case when obis = '1-0:1.8.0' then meter_id end) as meters_reporting,
    any_value(m.expected) as meters_expected,
    sum(case when obis = '1-0:1.8.0' then metered_kwh end) / 1000 as metered_import_mwh,
    count(case when status = 'substitute' then 1 end) as substitute_values,
    count(case when is_estimated then 1 end) as estimated_values
from {{ ref('int_meter_readings_clean') }} r cross join meters m
group by r.qh_start_utc
