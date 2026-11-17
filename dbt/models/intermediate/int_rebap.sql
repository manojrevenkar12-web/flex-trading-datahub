-- The imbalance price to settle on: the final value once published, the preliminary one until then.
select * exclude (rn) from (
    select
        qh_start_utc, rebap_eur_mwh, status = 'final' as rebap_is_final, published_on,
        row_number() over (partition by qh_start_utc order by (status = 'final') desc, published_on desc) as rn
    from {{ ref('stg_rebap') }}
) where rn = 1
