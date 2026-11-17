-- What the portfolio's devices did per quarter hour, in MWh with the sign they have at the meter:
-- consumption positive, PV production negative, battery charging positive and discharging negative.
select
    qh_start_utc,
    sum(case when kind = 'ev' then kwh else 0 end) / 1000 as ev_mwh,
    sum(case when kind = 'heat_pump' then kwh else 0 end) / 1000 as heat_pump_mwh,
    -sum(case when kind = 'pv' then kwh else 0 end) / 1000 as pv_mwh,
    sum(case when kind = 'battery' and counter = 'main' then kwh when kind = 'battery' then -kwh else 0 end) / 1000 as battery_mwh,
    count(distinct case when in_gap then device_id end) as devices_in_gap
from {{ ref('int_device_qh') }}
group by qh_start_utc
