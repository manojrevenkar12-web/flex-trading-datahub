-- Day-ahead (15-minute products since EPEX moved to a quarter-hour MTU) and the intraday ID3 index.
with da as (
    select cast(delivery_start as timestamp) as qh_start_utc, cast(price_eur_mwh as double) as da_eur_mwh
    from read_parquet('{{ var("lake") }}/bronze/day_ahead/*.parquet')
), id as (
    select cast(delivery_start as timestamp) as qh_start_utc, cast(id3_eur_mwh as double) as id_eur_mwh
    from read_parquet('{{ var("lake") }}/bronze/intraday/*.parquet')
)
select da.qh_start_utc, da.da_eur_mwh, id.id_eur_mwh
from da left join id using (qh_start_utc)
