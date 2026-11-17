-- One value per meter, register and quarter hour: the highest version wins, so a measured value replaces the
-- substitute sent first, and a correction replaces the original. A resent file never got this far.
select * exclude (rn)
from (
    select
        *,
        row_number() over (partition by meter_id, obis, qh_start_utc order by version desc, received_on desc, source_file desc) as rn
    from {{ ref('stg_meter_readings') }}
)
where rn = 1
