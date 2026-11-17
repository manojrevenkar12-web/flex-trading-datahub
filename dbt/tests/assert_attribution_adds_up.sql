-- The imbalance cost is fully explained: class errors, intraday trades and rounding sum to it.
select qh_start_utc
from {{ ref('fct_portfolio_qh') }}
where abs(imbalance_cost_eur - (attr_base_eur + attr_heat_pump_eur + attr_ev_eur + attr_pv_eur + attr_battery_eur
          + attr_intraday_eur + attr_rounding_eur)) > 1e-6
