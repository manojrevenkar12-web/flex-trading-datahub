-- A household connection cannot draw more than about 120 kW, i.e. 30 kWh in a quarter hour.
select meter_id, qh_start_utc, kwh from {{ ref('int_meter_readings') }} where kwh < 0 or kwh > 30
