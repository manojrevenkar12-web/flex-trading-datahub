"""The comparison design: a plausible first version of the same warehouse, written as plain SQL over the same bronze
files. It handles units and offsets, so it is not a straw man, but it:
- keeps every version of a meter value and every version of a trade, cancelled ones included;
- reads local times without an offset as ordinary local times, so the repeated hour on the night summer time ends
  lands on one hour;
- settles on the first imbalance price published;
- differences device counters without noticing resets, and books each difference to the quarter hour it was
  reported in;
- joins the newest weather run for each hour, whenever it was issued, so its forecast backtest sees weather it
  would not have had at the gate."""
from __future__ import annotations

from pathlib import Path

import duckdb

SQL = """
create or replace table meters as
select distinct meter_id, obis,
    case when ts is not null then timezone('UTC', cast(ts as timestamptz))
         else timezone('UTC', timezone('Europe/Berlin', cast(ts_local as timestamp))) end as qh_start_utc,
    cast(value as double) * case unit when 'Wh' then 0.001 when 'kWh' then 1 when 'MWh' then 1000 end as kwh,
    status, cast(version as integer) as version
from read_parquet('{lake}/bronze/meters/*.parquet', union_by_name = true);

create or replace table spine as
select cast(delivery_start as timestamp) as qh_start_utc,
       cast(timezone('Europe/Berlin', timezone('UTC', cast(delivery_start as timestamp))) as date) as delivery_day,
       cast(price_eur_mwh as double) as da_eur_mwh
from read_parquet('{lake}/bronze/day_ahead/*.parquet');

create or replace table devices as
with t as (
    select distinct device_id, kind, epoch_ms(cast(ts_ms as bigint)) as ts,
           cast(energy_kwh as double) as e1, try_cast(nullif(energy2_kwh, '') as double) as e2
    from read_parquet('{lake}/bronze/hems/*.parquet', union_by_name = true)
), d as (
    select *, e1 - lag(e1) over w as d1, e2 - lag(e2) over w as d2
    from t window w as (partition by device_id order by ts)
)
select time_bucket(interval 15 minute, ts) as qh_start_utc,
       sum(case when kind = 'ev' then d1 else 0 end) / 1000 as ev_mwh,
       sum(case when kind = 'heat_pump' then d1 else 0 end) / 1000 as heat_pump_mwh,
       -sum(case when kind = 'pv' then d1 else 0 end) / 1000 as pv_mwh,
       sum(case when kind = 'battery' then coalesce(d1, 0) - coalesce(d2, 0) else 0 end) / 1000 as battery_mwh
from d group by 1;

create or replace table positions as
select cast(delivery_start as timestamp) as qh_start_utc,
       sum(case when product = 'DA' then (case side when 'buy' then 1 else -1 end) * cast(mw as double) else 0 end) as da_mw,
       sum(case when product = 'ID' then (case side when 'buy' then 1 else -1 end) * cast(mw as double) else 0 end) as id_mw,
       sum(case when product = 'DA' then (case side when 'buy' then 1 else -1 end) * cast(mw as double) / 4 * cast(price_eur_mwh as double) else 0 end) as da_cost_eur,
       sum(case when product = 'ID' then (case side when 'buy' then 1 else -1 end) * cast(mw as double) / 4 * cast(price_eur_mwh as double) else 0 end) as id_cost_eur
from read_parquet('{lake}/bronze/trades/*.parquet') group by 1;

create or replace table rebap as
select qh_start_utc, arg_min(rebap_eur_mwh, published) as rebap_eur_mwh from (
    select cast(qh_start_utc as timestamp) as qh_start_utc, cast(rebap_eur_mwh as double) as rebap_eur_mwh, published
    from read_parquet('{lake}/bronze/rebap/*.parquet')) group by 1;

create or replace table desk as
select cast(qh_start_utc as timestamp) as qh_start_utc, * exclude (qh_start_utc)
from read_parquet('{lake}/bronze/desk_forecasts/*.parquet');

create or replace table portfolio as
with m as (
    select qh_start_utc,
           sum(case when obis = '1-0:1.8.0' then kwh end) / 1000 as import_mwh,
           coalesce(sum(case when obis = '1-0:2.8.0' then kwh end), 0) / 1000 as export_mwh
    from meters group by 1
)
select s.qh_start_utc, s.delivery_day, s.da_eur_mwh,
       m.import_mwh - m.export_mwh as net_mwh,
       coalesce(d.ev_mwh, 0) as ev_mwh, coalesce(d.heat_pump_mwh, 0) as heat_pump_mwh, coalesce(d.pv_mwh, 0) as pv_mwh, coalesce(d.battery_mwh, 0) as battery_mwh,
       coalesce(p.da_mw, 0) as da_mw, coalesce(p.id_mw, 0) as id_mw, coalesce(p.da_cost_eur, 0) as da_cost_eur, coalesce(p.id_cost_eur, 0) as id_cost_eur,
       r.rebap_eur_mwh,
       cast(f.fc_base_mwh as double) as fc_base_mwh, cast(f.fc_heat_pump_mwh as double) as fc_heat_pump_mwh, cast(f.fc_ev_mwh as double) as fc_ev_mwh,
       cast(f.fc_pv_mwh as double) as fc_pv_mwh, cast(f.fc_battery_mwh as double) as fc_battery_mwh
from spine s left join m using (qh_start_utc) left join devices d using (qh_start_utc)
left join positions p using (qh_start_utc) left join rebap r using (qh_start_utc) left join desk f using (qh_start_utc);

create or replace table portfolio_out as
select *, net_mwh - ev_mwh - heat_pump_mwh - pv_mwh - battery_mwh as base_mwh,
       net_mwh - (da_mw + id_mw) / 4 as imbalance_mwh,
       (net_mwh - (da_mw + id_mw) / 4) * rebap_eur_mwh as imbalance_cost_eur
from portfolio;

create or replace table features as
with w as (
    select timezone('UTC', cast(valid_time as timestamptz)) as valid_hour_utc,
           arg_max(cast(temp_c as double), issue_time) as fc_temp_c, arg_max(cast(cloud as double), issue_time) as fc_cloud
    from read_parquet('{lake}/bronze/weather/*.parquet') group by 1
), p as (select *, timezone('Europe/Berlin', timezone('UTC', qh_start_utc)) as local_ts from portfolio_out)
select p.qh_start_utc, p.delivery_day, p.net_mwh as target_net_mwh,
       hour(p.local_ts) + minute(p.local_ts) / 60.0 as local_hour, dayofweek(p.local_ts) as weekday,
       w.fc_temp_c, w.fc_cloud,
       greatest(sin(pi() * (hour(p.qh_start_utc) + minute(p.qh_start_utc) / 60.0 - 5.5) / 11.5), 0) * (1 - 0.75 * w.fc_cloud) as fc_sun,
       l7.net_mwh as net_7d_mwh,
       l1.net_mwh as d2_net_known_mwh
from p
left join w on w.valid_hour_utc = date_trunc('hour', p.qh_start_utc)
left join p l7 on l7.local_ts = p.local_ts - interval 7 day
left join p l1 on l1.local_ts = p.local_ts - interval 1 day;
"""


def build(lake: Path, db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db))
    con.execute("set TimeZone = 'UTC'")
    con.execute(SQL.format(lake=lake))
    con.close()
