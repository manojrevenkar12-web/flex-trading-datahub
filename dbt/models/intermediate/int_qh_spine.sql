-- Every quarter hour of every delivery day the market priced, with its local delivery day.
select
    qh_start_utc,
    {{ delivery_day('qh_start_utc') }} as delivery_day
from {{ ref('stg_market_prices') }}
