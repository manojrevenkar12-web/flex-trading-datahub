-- Every forecast run the provider sent, with the time it was issued: features must use the run known at the gate.
select
    timezone('UTC', cast(issue_time as timestamptz)) as issued_at_utc,
    run,
    timezone('UTC', cast(valid_time as timestamptz)) as valid_hour_utc,
    cast(temp_c as double) as temp_c,
    cast(cloud as double) as cloud
from read_parquet('{{ var("lake") }}/bronze/weather/*.parquet', union_by_name = true)
