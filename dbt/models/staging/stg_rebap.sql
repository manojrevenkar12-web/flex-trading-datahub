-- The German imbalance price, first preliminary, later final and sometimes revised.
select
    cast(qh_start_utc as timestamp) as qh_start_utc,
    cast(rebap_eur_mwh as double) as rebap_eur_mwh,
    status,
    cast(published as date) as published_on
from read_parquet('{{ var("lake") }}/bronze/rebap/*.parquet')
