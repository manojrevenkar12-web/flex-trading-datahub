-- The trading desk's quarter hour: what the portfolio drew, what each device class contributed, what was bought,
-- the imbalance left over, what it cost at the imbalance price, and which class's forecast error caused it.
-- The attribution adds up to the imbalance cost exactly: the desk's class forecast errors, the intraday trades that
-- closed part of the gap, and what is left (the day-ahead lot rounding).
with q as (
    select
        s.qh_start_utc, s.delivery_day,
        m.import_mwh, m.export_mwh, m.import_mwh - m.export_mwh as net_mwh,
        m.meters_reporting, m.meters_expected, m.substitute_values, m.estimated_values, m.metered_import_mwh,
        d.ev_mwh, d.heat_pump_mwh, d.pv_mwh, d.battery_mwh, d.devices_in_gap,
        (m.import_mwh - m.export_mwh) - d.ev_mwh - d.heat_pump_mwh - d.pv_mwh - d.battery_mwh as base_mwh,
        f.fc_base_mwh, f.fc_heat_pump_mwh, f.fc_ev_mwh, f.fc_pv_mwh, f.fc_battery_mwh,
        coalesce(p.da_mw, 0) as da_mw, coalesce(p.id_mw, 0) as id_mw,
        coalesce(p.da_cost_eur, 0) as da_cost_eur, coalesce(p.id_cost_eur, 0) as id_cost_eur,
        pr.da_eur_mwh, pr.id_eur_mwh, r.rebap_eur_mwh, r.rebap_is_final
    from {{ ref('int_qh_spine') }} s
    left join {{ ref('int_portfolio_meters_qh') }} m using (qh_start_utc)
    left join {{ ref('int_portfolio_devices_qh') }} d using (qh_start_utc)
    left join {{ ref('stg_desk_forecasts') }} f using (qh_start_utc)
    left join {{ ref('int_positions_qh') }} p using (qh_start_utc)
    left join {{ ref('stg_market_prices') }} pr using (qh_start_utc)
    left join {{ ref('int_rebap') }} r using (qh_start_utc)
), imb as (
    select *, net_mwh - (da_mw + id_mw) / 4 as imbalance_mwh from q
)
select
    *,
    imbalance_mwh * rebap_eur_mwh as imbalance_cost_eur,
    (base_mwh - fc_base_mwh) * rebap_eur_mwh as attr_base_eur,
    (heat_pump_mwh - fc_heat_pump_mwh) * rebap_eur_mwh as attr_heat_pump_eur,
    (ev_mwh - fc_ev_mwh) * rebap_eur_mwh as attr_ev_eur,
    (pv_mwh - fc_pv_mwh) * rebap_eur_mwh as attr_pv_eur,
    (battery_mwh - fc_battery_mwh) * rebap_eur_mwh as attr_battery_eur,
    -(id_mw / 4) * rebap_eur_mwh as attr_intraday_eur,
    (imbalance_mwh - ((base_mwh - fc_base_mwh) + (heat_pump_mwh - fc_heat_pump_mwh) + (ev_mwh - fc_ev_mwh)
        + (pv_mwh - fc_pv_mwh) + (battery_mwh - fc_battery_mwh) - id_mw / 4)) * rebap_eur_mwh as attr_rounding_eur
from imb
