-- Procurement P&L per delivery day, and where the imbalance cost came from.
select
    delivery_day,
    count(*) as quarter_hours,
    sum(net_mwh) as net_mwh,
    sum(da_cost_eur) as da_cost_eur,
    sum(id_cost_eur) as id_cost_eur,
    sum(imbalance_cost_eur) as imbalance_cost_eur,
    sum(da_cost_eur) + sum(id_cost_eur) + sum(imbalance_cost_eur) as procurement_cost_eur,
    sum(abs(imbalance_mwh)) as abs_imbalance_mwh,
    sum(attr_base_eur) as attr_base_eur,
    sum(attr_heat_pump_eur) as attr_heat_pump_eur,
    sum(attr_ev_eur) as attr_ev_eur,
    sum(attr_pv_eur) as attr_pv_eur,
    sum(attr_battery_eur) as attr_battery_eur,
    sum(attr_intraday_eur) as attr_intraday_eur,
    sum(attr_rounding_eur) as attr_rounding_eur,
    bool_and(rebap_is_final) as settled_on_final_prices,
    min(meters_reporting * 1.0 / meters_expected) as min_meter_coverage
from {{ ref('fct_portfolio_qh') }}
group by delivery_day
