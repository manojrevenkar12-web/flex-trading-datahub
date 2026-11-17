-- One row per delivery day: is the day complete, settled and trustworthy enough to trade and report on?
with days as (
    select delivery_day, count(*) as quarter_hours,
           cast(epoch({{ local_midnight_utc('delivery_day + 1') }} - {{ local_midnight_utc('delivery_day') }}) / 900 as integer) as expected_quarter_hours,
           min(meters_reporting * 1.0 / meters_expected) as min_meter_coverage,
           sum(substitute_values) as substitute_values,
           sum(estimated_values) as estimated_values,
           max(devices_in_gap) as max_devices_in_gap,
           avg(case when rebap_is_final then 1.0 else 0.0 end) as rebap_final_share,
           count(case when da_mw = 0 then 1 end) as quarter_hours_without_position
    from {{ ref('fct_portfolio_qh') }}
    group by delivery_day
), resets as (
    select {{ delivery_day('reported_at_utc') }} as delivery_day, count(*) as counter_resets
    from {{ ref('int_device_counters') }} where is_reset group by 1
), stuck as (
    select d.delivery_day, count(distinct s.meter_id) as stuck_meters
    from days d join {{ ref('dq_stuck_meters') }} s
      on {{ delivery_day('s.stuck_from_utc') }} <= d.delivery_day and {{ delivery_day('s.stuck_to_utc') }} >= d.delivery_day
    group by 1
), trades as (
    select {{ delivery_day('qh_start_utc') }} as delivery_day,
           count(distinct case when status = 'cancelled' then trade_id end) as cancelled_trades,
           count(distinct case when version > 1 and status = 'active' then trade_id end) as amended_trades
    from {{ ref('stg_trades') }} group by 1
)
select
    days.*,
    quarter_hours = expected_quarter_hours as calendar_ok,
    coalesce(resets.counter_resets, 0) as counter_resets,
    coalesce(stuck.stuck_meters, 0) as stuck_meters,
    coalesce(trades.cancelled_trades, 0) as cancelled_trades,
    coalesce(trades.amended_trades, 0) as amended_trades,
    (quarter_hours = expected_quarter_hours) and min_meter_coverage >= 0.98 and rebap_final_share = 1 as ready_to_settle
from days
left join resets using (delivery_day)
left join stuck using (delivery_day)
left join trades using (delivery_day)
