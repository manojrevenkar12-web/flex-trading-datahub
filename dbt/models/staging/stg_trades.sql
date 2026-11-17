-- One row per trade version, as the trading system exports it.
select
    trade_id,
    cast(version as integer) as version,
    status,
    product,
    cast(delivery_start as timestamp) as qh_start_utc,
    side,
    cast(mw as double) as mw,
    cast(price_eur_mwh as double) as price_eur_mwh,
    _source_file as source_file
from read_parquet('{{ var("lake") }}/bronze/trades/*.parquet')
