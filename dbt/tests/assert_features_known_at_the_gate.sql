-- No feature may come from a forecast issued after the day-ahead gate.
select qh_start_utc from {{ ref('feat_load_qh') }} where weather_issued_at_utc > gate_utc
