"""One evaluation: simulate a month, land it, build the warehouse with dbt and the comparison SQL, and score both
against the world's truth: energy, imbalance cost, P&L, attribution, the faults that were planted, the forecast built
on top, and whether a second run changes anything."""
from __future__ import annotations

import json
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from ftd import forecast
from ftd.eval import naive
from ftd.pipeline import build as build_warehouse
from ftd.world import portfolio

ROOT = Path(__file__).resolve().parents[2]
CLASSES = ["base", "heat_pump", "ev", "pv", "battery"]


def r(x, k=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), k)


def read(db: Path, sql: str) -> pd.DataFrame:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.sql(sql).df()
    finally:
        con.close()


def snapshot(db: Path, table: str) -> pd.DataFrame:
    return read(db, f"select * from {table} order by all")


def same(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    """Equal rows and values. Floating-point sums may differ in the last bits between parallel runs, so numbers are
    compared to a billionth."""
    if list(a.columns) != list(b.columns) or len(a) != len(b):
        return False
    num = a.select_dtypes("number").columns
    other = [c for c in a.columns if c not in num]
    return bool(np.allclose(a[num].to_numpy(float), b[num].to_numpy(float), atol=1e-9, equal_nan=True)) and a[other].equals(b[other])


def utc(s: pd.Series) -> pd.Series:
    return s.dt.tz_convert("UTC").dt.tz_localize(None) if getattr(s.dt, "tz", None) is not None else s


def score_design(out: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """out has qh_start_utc, delivery_day, net_mwh, class columns, da/id costs, imbalance and its cost."""
    m = truth.merge(out, on="qh_start_utc", how="left", suffixes=("_t", ""))
    net_err = (m["net_mwh"] - m["net_mwh_t"]).abs()
    within = (net_err <= 0.005 * m["net_mwh_t"].abs().clip(lower=1e-3)).mean()
    daily = m.groupby("delivery_day_t").agg(t=("imbalance_cost_eur_t", "sum"), p=("imbalance_cost_eur", "sum"),
                                            pt=("da_cost_eur_t", "sum"), pp=("da_cost_eur", "sum"),
                                            it=("id_cost_eur_t", "sum"), ip=("id_cost_eur", "sum"))
    proc_t = daily["pt"] + daily["it"] + daily["t"]
    proc_p = daily["pp"] + daily["ip"] + daily["p"]
    cls = {}
    for c in CLASSES:
        if f"{c}_mwh" in out:
            cls[c] = r((m[f"{c}_mwh"] - m[f"{c}_mwh_t"]).abs().sum(), 3)
    attr = {}
    for c in CLASSES:
        t = (m[f"{c}_mwh_t"] - m[f"fc_{c}_mwh_t"]) * m["rebap_eur_mwh_t"]
        p = (m[f"{c}_mwh"] - m[f"fc_{c}_mwh_t"]) * m["rebap_eur_mwh"]
        attr[c] = {"truth_eur": r(t.sum(), 2), "built_eur": r(p.sum(), 2)}
    return {
        "quarter_hours": int(len(out)),
        "quarter_hours_expected": int(len(truth)),
        "net_mwh_truth": r(m["net_mwh_t"].sum(), 3),
        "net_mwh_built": r(m["net_mwh"].sum(), 3),
        "net_abs_error_mwh": r(net_err.sum(), 3),
        "net_within_half_percent": r(within),
        "class_abs_error_mwh": cls,
        "imbalance_cost_truth_eur": r(daily["t"].sum(), 2),
        "imbalance_cost_built_eur": r(daily["p"].sum(), 2),
        "imbalance_cost_daily_abs_error_eur": r((daily["p"] - daily["t"]).abs().sum(), 2),
        "procurement_cost_truth_eur": r(proc_t.sum(), 2),
        "procurement_cost_built_eur": r(proc_p.sum(), 2),
        "procurement_daily_abs_error_eur": r((proc_p - proc_t).abs().sum(), 2),
        "days_procurement_within_1pct": r(((proc_p - proc_t).abs() <= 0.01 * proc_t.abs()).mean()),
        "attribution": attr,
        "attribution_abs_error_eur": r(sum(abs((a["built_eur"] or 0) - a["truth_eur"]) for a in attr.values()), 2),
    }


def forecast_eval(prod_feat: pd.DataFrame, naive_feat: pd.DataFrame, truth: pd.DataFrame, test_days: int) -> dict:
    """Backtest each feature set on itself, then run each trained model on what production would hand it: the
    features known at the gate. A leaking feature set backtests well and loses the gap in production."""
    out = {}
    tr_p, te_p = forecast.split(prod_feat, test_days)
    tr_n, te_n = forecast.split(naive_feat, test_days)
    t = truth[["qh_start_utc", "net_mwh", "rebap_eur_mwh", "da_mw"]]
    te_live = te_p.merge(t, on="qh_start_utc")
    desk_err = (te_live["net_mwh"] - te_live["da_mw"] / 4).abs()    # the desk's own day-ahead position, before intraday
    for name, tr, te in (("gate_features", tr_p, te_p), ("leaky_features", tr_n, te_n)):
        from lightgbm import LGBMRegressor  # noqa: F401  (imported in forecast.model)
        m = forecast.model()
        m.fit(tr[forecast.FEATURES], tr["target_net_mwh"])
        backtest = te.merge(t, on="qh_start_utc")
        bt_err = np.abs(m.predict(backtest[forecast.FEATURES]) - backtest["net_mwh"])
        live_err = np.abs(m.predict(te_live[forecast.FEATURES]) - te_live["net_mwh"])
        out[name] = {
            "backtest_mae_kwh": r(bt_err.mean() * 1000, 2),
            "live_mae_kwh": r(live_err.mean() * 1000, 2),
            "live_exposure_eur": r((live_err * te_live["rebap_eur_mwh"].abs()).sum(), 2),
            "optimism_kwh": r((live_err.mean() - bt_err.mean()) * 1000, 2),
        }
    out["desk_day_ahead"] = {"live_mae_kwh": r(desk_err.mean() * 1000, 2),
                                  "live_exposure_eur": r((desk_err * te_live["rebap_eur_mwh"].abs()).sum(), 2)}
    out["test_days"] = test_days
    out["test_quarter_hours"] = int(len(te_live))
    return out


def evaluate(world_file: str = "config/world.yaml", quick: bool = False, work: Path | None = None, log=print, keep: bool = False) -> dict:
    t0 = time.perf_counter()
    cfg = portfolio.load(ROOT / world_file, quick)
    work = work or ROOT / "work" / (cfg["name"] + ("-quick" if quick else ""))
    sim = portfolio.simulate(cfg)
    planted = portfolio.write(sim, work)
    log(f"world written ({time.perf_counter() - t0:.0f} s)")
    lake, db, ndb = work / "lake", work / "warehouse.duckdb", work / "naive.duckdb"
    for p in (db, ndb):
        p.unlink(missing_ok=True)
    for p in (lake / "bronze",):
        if p.exists():
            import shutil
            shutil.rmtree(p)
    first = build_warehouse(lake, db)
    marts = ("fct_portfolio_qh", "fct_pnl_daily", "fct_data_quality_daily")
    before = {t: snapshot(db, t) for t in marts}
    log(f"warehouse built: {first['ok']} ({time.perf_counter() - t0:.0f} s)")
    second = build_warehouse(lake, db)
    unchanged = all(same(before[t], snapshot(db, t)) for t in marts)
    naive.build(lake, ndb)
    log(f"comparison built ({time.perf_counter() - t0:.0f} s)")
    truth = pd.read_parquet(work / "truth" / "portfolio_qh.parquet")
    truth["qh_start_utc"] = utc(truth["qh_start_utc"])
    truth["delivery_day"] = truth["delivery_day"].astype(str)
    prod = read(db, "select * from fct_portfolio_qh")
    nv = read(ndb, "select * from portfolio_out")
    for df in (prod, nv):
        df["delivery_day"] = df["delivery_day"].astype(str)
    dq = read(db, "select * from fct_data_quality_daily order by delivery_day")
    stuck = set(read(db, "select distinct meter_id from dq_stuck_meters")["meter_id"])
    resets = int(read(db, "select count(distinct device_id) as n from int_device_counters where is_reset")["n"][0])
    subst = int(read(db, "select count(distinct meter_id || cast(" + "delivery_day" + " as varchar)) as n from (select meter_id, cast(timezone('Europe/Berlin', timezone('UTC', qh_start_utc)) as date) as delivery_day from stg_meter_readings where status = 'substitute')")["n"][0])
    replaced = int(read(db, "select count(*) as n from int_meter_readings where status = 'substitute'")["n"][0])
    manifest = read(db, "select status, count(*) as n from stg_deliveries group by 1")
    dst_days = dq[dq["expected_quarter_hours"] != 96][["delivery_day", "quarter_hours", "expected_quarter_hours"]]
    naive_qh = nv.groupby("delivery_day").size()
    rep = {
        "world": cfg["name"], "start": cfg["start"], "days": cfg["days"], "customers": cfg["customers"],
        "devices": int(len(sim["devices"])),
        "raw": {"meter_values": int(read(db, "select count(*) as n from stg_meter_readings")["n"][0]),
                "device_reports": int(read(db, "select count(*) as n from stg_device_telemetry")["n"][0]),
                "trade_versions": int(read(db, "select count(*) as n from stg_trades")["n"][0]),
                "weather_runs": int(read(db, "select count(distinct issued_at_utc) as n from stg_weather_forecasts")["n"][0]),
                "files": {k: int(v) for k, v in zip(manifest["status"], manifest["n"])}},
        "dbt": {"ok": first["ok"], "failed": first["failed"], "second_run_ok": second["ok"]},
        "designs": {"datahub": score_design(prod, truth), "first_version_sql": score_design(nv, truth)},
        "faults": {
            "stuck_meters_planted": len(planted["stuck_meters"]),
            "stuck_meters_found": len(stuck & set(planted["stuck_meters"])),
            "stuck_meters_false_alarms": len(stuck - set(planted["stuck_meters"])),
            "counter_resets_planted": planted["counter_resets"],
            "counter_resets_found": resets,
            "substitute_meter_days_planted": planted["substitute_meter_days"],
            "substitute_meter_days_seen": subst,
            "substitute_values_left_after_versions": replaced,
            "duplicate_deliveries_skipped": int(manifest.loc[manifest["status"] == "duplicate", "n"].sum()),
            "dst_days": [{"day": str(x.delivery_day)[:10], "quarter_hours": int(x.quarter_hours), "expected": int(x.expected_quarter_hours),
                          "first_version_sql": int(naive_qh.get(str(x.delivery_day)[:10], 0))} for x in dst_days.itertuples()],
            "calendar_ok_days": int(dq["calendar_ok"].sum()),
            "ready_to_settle_days": int(dq["ready_to_settle"].sum()),
        },
        "idempotent": {"second_landing": second["landed"], "marts_unchanged": unchanged},
        "daily": [{"day": str(x.delivery_day)[:10], "imbalance_cost_eur": r(x.imbalance_cost_eur, 2), "procurement_cost_eur": r(x.procurement_cost_eur, 2),
                   "net_mwh": r(x.net_mwh, 3), "attr_base_eur": r(x.attr_base_eur, 2), "attr_heat_pump_eur": r(x.attr_heat_pump_eur, 2),
                   "attr_ev_eur": r(x.attr_ev_eur, 2), "attr_pv_eur": r(x.attr_pv_eur, 2), "attr_battery_eur": r(x.attr_battery_eur, 2),
                   "attr_intraday_eur": r(x.attr_intraday_eur, 2), "attr_rounding_eur": r(x.attr_rounding_eur, 2)}
                  for x in read(db, "select * from fct_pnl_daily order by delivery_day").itertuples()],
    }
    dh, fv = rep["designs"]["datahub"], rep["designs"]["first_version_sql"]
    rep["relative"] = {
        "net_abs_error_share": r(dh["net_abs_error_mwh"] / abs(dh["net_mwh_truth"])),
        "first_version_net_abs_error_share": r(fv["net_abs_error_mwh"] / abs(fv["net_mwh_truth"])),
        "imbalance_error_vs_first_version": r(dh["imbalance_cost_daily_abs_error_eur"] / max(1e-9, fv["imbalance_cost_daily_abs_error_eur"])),
        "attribution_error_vs_first_version": r(dh["attribution_abs_error_eur"] / max(1e-9, fv["attribution_abs_error_eur"])),
        "calendar_ok_share": r(rep["faults"]["calendar_ok_days"] / cfg["days"]),
        "duplicates_skipped_share": r(rep["faults"]["duplicate_deliveries_skipped"] / max(1, planted["resent_files"])),
    }
    if cfg["days"] >= 21:
        pf = read(db, "select * from feat_load_qh")
        nf = read(ndb, "select * from features")
        for df in (pf, nf):
            df["delivery_day"] = df["delivery_day"].astype(str)
        rep["forecast"] = forecast_eval(pf, nf, truth, test_days=7)
    if not quick and cfg["name"] == "D1":           # the dashboard's snapshot of the dev marts
        out = ROOT / "reports" / "marts"
        out.mkdir(parents=True, exist_ok=True)
        for t in ("fct_portfolio_qh", "fct_pnl_daily", "fct_data_quality_daily", "dq_stuck_meters"):
            read(db, f"select * from {t} order by all").to_parquet(out / f"{t}.parquet", index=False)
    rep["seconds"] = round(time.perf_counter() - t0)
    if not keep:                                   # the lake and warehouses are rebuilt from the world file on demand
        import shutil
        shutil.rmtree(work, ignore_errors=True)
    return rep


def write_report(rep: dict, name: str) -> Path:
    out = ROOT / "reports" / f"{name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(rep, indent=1) + "\n")
    return out
