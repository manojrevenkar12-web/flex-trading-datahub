"""The trading data pipeline as Airflow runs it, every hour from 06:00 to 23:00 Berlin time:

land_raw     copy new files from the raw prefix into bronze, once per file (content hash)
dbt_build    build and test staging, intermediate and marts; a failing test stops the run
data_quality publish the day-quality table and alert when a delivery day is not ready to settle
forecast     at 10:00, before the 12:00 day-ahead gate, refit the load forecast on features known at the gate
             and report its error on the last delivered day

Tasks call the same functions the tests and the evaluation use (ftd.pipeline, ftd.forecast)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

LAKE = Path(os.environ.get("FTD_LAKE", "/opt/flex/lake"))
DB = Path(os.environ.get("FTD_DUCKDB", "/opt/flex/warehouse/flex.duckdb"))


@dag(
    dag_id="flex_trading_data",
    schedule="0 6-23 * * *",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["trading", "dbt"],
)
def flex_trading_data():
    @task
    def land_raw() -> dict:
        from ftd.ingest import land
        return land(LAKE)

    @task
    def dbt_build(landed: dict) -> dict:
        from ftd.pipeline import dbt
        res = dbt(["build"], LAKE, DB)
        if not res["ok"]:
            raise RuntimeError("dbt build failed: " + "; ".join(res["failed"])[:2000])
        return {"landed": landed, **res}

    @task
    def data_quality(_: dict) -> list[dict]:
        import duckdb
        con = duckdb.connect(str(DB), read_only=True)
        rows = con.sql("select delivery_day, ready_to_settle, min_meter_coverage, stuck_meters, counter_resets "
                       "from fct_data_quality_daily where not ready_to_settle order by delivery_day").df()
        con.close()
        return rows.astype(str).to_dict("records")

    @task
    def forecast(_: dict) -> dict:
        from zoneinfo import ZoneInfo
        if datetime.now(ZoneInfo("Europe/Berlin")).hour != 10:
            return {"skipped": "the forecast is refitted once a day, at 10:00 before the 12:00 gate"}
        import duckdb

        from ftd import forecast as fc
        con = duckdb.connect(str(DB), read_only=True)
        feat = con.sql("select * from feat_load_qh").df()
        con.close()
        train, last_day = fc.split(feat, test_days=1)
        pred = fc.fit_predict(train, last_day)
        mae_kwh = float(abs(pred - last_day["target_net_mwh"]).mean() * 1000)
        return {"trained_on_quarter_hours": len(train), "last_delivered_day_mae_kwh": round(mae_kwh, 2)}

    built = dbt_build(land_raw())
    data_quality(built)
    forecast(built)


dag_object = flex_trading_data()
