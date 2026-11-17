-- Quarter-hour readings from both metering operators, in UTC and kWh. mdm_a sends ISO times with an offset;
-- mdm_b sends local wall-clock time without one, so the second 02:00 on the last Sunday of October can only be told
-- apart by its position in the day (seq). That position is what places it.
select
    meter_id,
    obis,
    case
        when ts is not null then timezone('UTC', cast(ts as timestamptz))
        else {{ local_midnight_utc("cast(substr(ts_local, 1, 10) as date)") }} + to_minutes(15 * (cast(seq as integer) - 1))
    end as qh_start_utc,
    {{ to_kwh('value', 'unit') }} as kwh,
    unit,
    status,
    cast(version as integer) as version,
    cast(_received as date) as received_on,
    _mdm as mdm,
    _source_file as source_file
from read_parquet('{{ var("lake") }}/bronze/meters/*.parquet', union_by_name = true)
