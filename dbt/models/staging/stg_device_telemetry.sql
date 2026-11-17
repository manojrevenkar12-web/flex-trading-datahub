-- Energy counters from home energy management systems, reported every few minutes, in arrival order.
select distinct
    device_id,
    customer_id,
    kind,
    epoch_ms(cast(ts_ms as bigint)) as reported_at_utc,
    cast(energy_kwh as double) as energy_kwh,
    try_cast(nullif(energy2_kwh, '') as double) as energy2_kwh
from read_parquet('{{ var("lake") }}/bronze/hems/*.parquet', union_by_name = true)
