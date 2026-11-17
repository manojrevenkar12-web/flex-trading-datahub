-- Stuck registers found, for the data-quality page and the metering operator.
select * from {{ ref('int_stuck_runs') }}
