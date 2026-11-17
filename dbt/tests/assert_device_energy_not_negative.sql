select device_id, qh_start_utc, kwh from {{ ref('int_device_qh') }} where kwh < -1e-9
