-- The desk's position per quarter hour from the latest version of every trade; cancelled trades count for nothing.
with latest as (
    select * exclude (rn) from (
        select *, row_number() over (partition by trade_id order by version desc) as rn from {{ ref('stg_trades') }}
    ) where rn = 1
)
select
    qh_start_utc,
    sum(case when product = 'DA' and status = 'active' then (case side when 'buy' then mw else -mw end) else 0 end) as da_mw,
    sum(case when product = 'ID' and status = 'active' then (case side when 'buy' then mw else -mw end) else 0 end) as id_mw,
    sum(case when product = 'DA' and status = 'active' then (case side when 'buy' then mw else -mw end) / 4 * price_eur_mwh else 0 end) as da_cost_eur,
    sum(case when product = 'ID' and status = 'active' then (case side when 'buy' then mw else -mw end) / 4 * price_eur_mwh else 0 end) as id_cost_eur,
    count(case when status = 'cancelled' then 1 end) as cancelled_trades
from latest
group by qh_start_utc
