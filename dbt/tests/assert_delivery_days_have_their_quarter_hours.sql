-- 92 quarter hours on the day summer time starts, 100 on the day it ends, 96 otherwise.
select delivery_day, quarter_hours, expected_quarter_hours
from {{ ref('fct_data_quality_daily') }}
where quarter_hours <> expected_quarter_hours or expected_quarter_hours not in (92, 96, 100)
