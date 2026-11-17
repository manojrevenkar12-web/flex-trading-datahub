-- The desk's class forecasts at the day-ahead gate: what was traded on.
select
    cast(qh_start_utc as timestamp) as qh_start_utc,
    cast(fc_base_mwh as double) as fc_base_mwh,
    cast(fc_heat_pump_mwh as double) as fc_heat_pump_mwh,
    cast(fc_ev_mwh as double) as fc_ev_mwh,
    cast(fc_pv_mwh as double) as fc_pv_mwh,
    cast(fc_battery_mwh as double) as fc_battery_mwh
from read_parquet('{{ var("lake") }}/bronze/desk_forecasts/*.parquet')
