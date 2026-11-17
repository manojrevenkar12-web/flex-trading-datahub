"""The simulated supplier: households with smart meters and home devices, the weather they react to, the power
prices the desk trades at, and the desk's own forecasts and trades. It writes two things:

- the truth (truth/*.parquet), which only the evaluation reads;
- the raw feeds as the data team receives them (lake/raw/...): metering operators that deliver late, twice, in Wh
  or kWh and in local time without offsets; device counters that drift, reset and go offline; forecast runs; prices
  that are revised; trades that are amended and cancelled.

Nothing in ftd/ingest.py, the dbt project or the dashboard imports this module."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from ftd.keyed import rng

TZ = "Europe/Berlin"
QH = pd.Timedelta(minutes=15)


@dataclass
class Portfolio:
    cfg: dict
    qh: pd.DatetimeIndex          # UTC start of each quarter hour
    local_day: np.ndarray         # delivery day (Europe/Berlin) of each quarter hour, as 'YYYY-MM-DD'
    customers: pd.DataFrame
    devices: pd.DataFrame


def load(path: str | Path, quick: bool = False) -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    if quick:
        cfg = {**cfg, "days": cfg["quick"]["days"], "customers": cfg["quick"]["customers"], "start": cfg["quick"]["start"]}
    return cfg


def timeline(cfg: dict) -> tuple[pd.DatetimeIndex, np.ndarray]:
    start = pd.Timestamp(cfg["start"], tz=TZ)
    end = start + pd.DateOffset(days=cfg["days"])
    qh = pd.date_range(start.tz_convert("UTC"), end.tz_convert("UTC"), freq=QH, inclusive="left")
    local_day = qh.tz_convert(TZ).strftime("%Y-%m-%d").to_numpy()
    return qh, local_day


def people(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = rng(cfg["seed"], "customers")
    n = cfg["customers"]
    d = cfg["devices"]
    c = pd.DataFrame({
        "customer": [f"C{i:05d}" for i in range(n)],
        "meter": [f"DE0{r.integers(10**8, 10**9)}{i:05d}" for i in range(n)],
        "mdm": np.where(r.random(n) < cfg["meters"]["mdm_b_share"], "mdm_b", "mdm_a"),
        "scale": r.uniform(0.6, 1.6, n),
        "ev": r.random(n) < d["ev"],
        "heat_pump": r.random(n) < d["heat_pump"],
        "pv": r.random(n) < d["pv"],
    })
    c["ev_smart"] = c["ev"] & (r.random(n) < d["ev_smart"])
    c["battery"] = c["pv"] & (r.random(n) < d["battery_given_pv"])
    c["pv_kwp"] = np.where(c["pv"], r.uniform(4, 11, n), 0.0)
    c["battery_kwh"] = np.where(c["battery"], r.uniform(5, 12, n), 0.0)
    c["hp_coef"] = np.where(c["heat_pump"], r.uniform(0.12, 0.3, n), 0.0)
    rows = []
    for _, x in c.iterrows():
        for kind in ("ev", "heat_pump", "pv", "battery"):
            if x[kind]:
                rows.append({"device": f"{kind[:2].upper()}-{x['customer']}", "customer": x["customer"], "kind": kind})
    return c, pd.DataFrame(rows)


def ar1(r: np.random.Generator, n: int, phi: float, sd: float) -> np.ndarray:
    e = r.normal(0, sd * np.sqrt(1 - phi ** 2), n)
    out = np.empty(n)
    out[0] = r.normal(0, sd)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + e[i]
    return out


def weather(cfg: dict, qh: pd.DatetimeIndex) -> pd.DataFrame:
    """Hourly actuals: temperature and cloud cover, and the clear-sky irradiance they become."""
    w = cfg["weather"]
    hours = pd.date_range(qh[0].floor("h"), qh[-1].ceil("h") + pd.Timedelta(hours=1), freq="h")
    r = rng(cfg["seed"], "weather")
    n = len(hours)
    local = hours.tz_convert(TZ)
    hod = local.hour.to_numpy() + local.minute.to_numpy() / 60
    doy = local.day_of_year.to_numpy()
    temp = w["temp_mean"] - 0.12 * (doy - doy[0]) + w["temp_daily_swing"] / 2 * np.sin((hod - 9) / 24 * 2 * np.pi) + ar1(r, n, 0.97, w["temp_noise"])
    cloud = np.clip(0.55 + ar1(r, n, w["cloud_persistence"], 0.28), 0, 1)
    utc_h = hours.hour.to_numpy() + 0.0
    elev = np.clip(np.sin((utc_h - 5.5) / 11.5 * np.pi), 0, None) * (0.55 - 0.004 * (doy - doy[0]))
    ghi = 1000 * elev * (1 - 0.75 * cloud)
    return pd.DataFrame({"hour": hours, "temp_c": temp, "cloud": cloud, "ghi_wm2": np.clip(ghi, 0, None)})


def forecasts(cfg: dict, wx: pd.DataFrame) -> pd.DataFrame:
    """Forecast runs as a weather provider sends them: a day-ahead run at 06:00 UTC for the next local day and
    intraday runs every six hours for the next 36 hours. Each value carries the run's issue time."""
    w = cfg["weather"]
    rows = []
    days = sorted({h.tz_convert(TZ).normalize() for h in wx["hour"]})
    for day in days:
        issue = (day - pd.Timedelta(days=1)).tz_convert("UTC").normalize() + pd.Timedelta(hours=6)
        target = wx[(wx["hour"] >= day.tz_convert("UTC")) & (wx["hour"] < (day + pd.DateOffset(days=1)).tz_convert("UTC"))]
        r = rng(cfg["seed"], "fc-da", str(day.date()))
        e_t = ar1(r, len(target), 0.9, w["forecast_error_da"]["temp"])
        e_c = ar1(r, len(target), 0.9, w["forecast_error_da"]["cloud"])
        rows.append(pd.DataFrame({"issue_time": issue, "valid_time": target["hour"], "run": "da",
                                  "temp_c": target["temp_c"] + e_t, "cloud": np.clip(target["cloud"] + e_c, 0, 1)}))
    for issue in pd.date_range(wx["hour"].iloc[0], wx["hour"].iloc[-1], freq="6h"):
        target = wx[(wx["hour"] > issue) & (wx["hour"] <= issue + pd.Timedelta(hours=36))]
        if target.empty:
            continue
        r = rng(cfg["seed"], "fc-id", str(issue))
        lead = (target["hour"] - issue).dt.total_seconds().to_numpy() / 3600
        scale = np.sqrt(lead / 36)
        rows.append(pd.DataFrame({"issue_time": issue, "valid_time": target["hour"], "run": "id",
                                  "temp_c": target["temp_c"] + r.normal(0, w["forecast_error_id"]["temp"], len(target)) * scale * 2,
                                  "cloud": np.clip(target["cloud"] + r.normal(0, w["forecast_error_id"]["cloud"], len(target)) * scale * 2, 0, 1)}))
    out = pd.concat(rows, ignore_index=True)
    out["ghi_wm2"] = np.nan                     # providers send cloud cover; irradiance is derived downstream
    return out


def irradiance(cfg: dict, hours: pd.Series, cloud: np.ndarray) -> np.ndarray:
    local = hours.dt.tz_convert(TZ)
    doy = local.dt.day_of_year.to_numpy()
    start_doy = pd.Timestamp(cfg["start"]).day_of_year
    utc_h = hours.dt.hour.to_numpy() + hours.dt.minute.to_numpy() / 60
    elev = np.clip(np.sin((utc_h - 5.5) / 11.5 * np.pi), 0, None) * (0.55 - 0.004 * (doy - start_doy))
    return np.clip(1000 * elev * (1 - 0.75 * cloud), 0, None)


def h0(local: pd.DatetimeIndex) -> np.ndarray:
    """A household load shape: morning and evening peaks, more at weekends."""
    h = local.hour.to_numpy() + local.minute.to_numpy() / 60
    wd = local.weekday.to_numpy()
    shape = 0.25 + 0.35 * np.exp(-((h - 7.5) ** 2) / 2) + 0.6 * np.exp(-((h - 19.5) ** 2) / 5) + 0.15 * np.exp(-((h - 13) ** 2) / 4)
    return shape * np.where(wd >= 5, 1.12, 1.0)


def simulate(cfg: dict) -> dict:
    qh, local_day = timeline(cfg)
    cust, dev = people(cfg)
    wx = weather(cfg, qh)
    n, m = len(qh), len(cust)
    hour_of_qh = qh.floor("h")
    wx_i = wx.set_index("hour")
    temp = wx_i.loc[hour_of_qh, "temp_c"].to_numpy()
    ghi = wx_i.loc[hour_of_qh, "ghi_wm2"].to_numpy()
    local = qh.tz_convert(TZ)
    # ---- prices first: smart charging follows the day-ahead price
    mk = cfg["market"]
    r = rng(cfg["seed"], "prices")
    shape = h0(local)
    solar_share = ghi / 1000
    da = mk["da_base"] + mk["da_residual_slope"] * (shape - shape.mean()) - mk["da_solar_slope"] * solar_share + r.normal(0, mk["da_noise"], n)
    weekend = local.weekday.to_numpy() >= 5
    da = np.where(weekend & (solar_share > 0.35), da - 70, da)
    # ---- households, kW averages per quarter hour
    R = rng(cfg["seed"], "load")
    base = (cust["scale"].to_numpy()[None, :] * shape[:, None] * (1 + 0.012 * (15 - temp))[:, None]) * np.exp(R.normal(0, 0.18, (n, m)))
    hp = np.clip(16 - temp, 0, None)[:, None] * cust["hp_coef"].to_numpy()[None, :] * (1 + 0.25 * np.sin((local.hour.to_numpy() - 4) / 24 * 2 * np.pi))[:, None]
    hp *= np.exp(R.normal(0, 0.1, (n, m)))
    pv = cust["pv_kwp"].to_numpy()[None, :] * (ghi / 1000)[:, None] * 0.85 * np.exp(R.normal(0, 0.05, (n, m)))
    ev = np.zeros((n, m))
    days = pd.unique(local_day)
    day_idx = {d: np.where(local_day == d)[0] for d in days}
    for j in np.where(cust["ev"])[0]:
        rj = rng(cfg["seed"], "ev", j)
        for d in days:
            if rj.random() > 0.45:
                continue
            idx = day_idx[d]
            arrive = idx[min(len(idx) - 1, int(rj.uniform(17, 20.5) * 4))]
            need = rj.uniform(5, 26)                                   # kWh
            slots = int(np.ceil(need / (11 * 0.25)))
            window = np.arange(arrive, min(n, arrive + 13 * 4))       # plugged in until about 07:00
            if cust["ev_smart"][j]:
                pick = window[np.argsort(da[window], kind="stable")[:slots]]
            else:
                pick = window[:slots]
            ev[np.sort(pick), j] += 11.0
            over = slots * 11 * 0.25 - need
            ev[np.sort(pick)[-1], j] -= over / 0.25
    batt_c = np.zeros((n, m))
    batt_d = np.zeros((n, m))
    for j in np.where(cust["battery"])[0]:
        cap = cust["battery_kwh"][j]
        soc = cap * 0.3
        for t in range(n):
            surplus = pv[t, j] - base[t, j] - hp[t, j] - ev[t, j]
            if surplus > 0 and soc < cap:
                c = min(surplus, 5.0, (cap - soc) / 0.25)
                batt_c[t, j] = c
                soc += c * 0.25 * 0.95
            elif surplus < 0 and soc > 0.1 * cap:
                dch = min(-surplus, 5.0, (soc - 0.1 * cap) / 0.25)
                batt_d[t, j] = dch
                soc -= dch * 0.25
    net = base + hp + ev + batt_c - batt_d - pv
    imp = np.clip(net, 0, None) * 0.25                                  # kWh per quarter hour
    exp_ = np.clip(-net, 0, None) * 0.25
    # ---- the desk's class forecasts at the day-ahead gate, and its trades
    dk = cfg["desk"]
    rd = rng(cfg["seed"], "desk")
    fc = forecasts(cfg, wx)
    fc_da = fc[fc["run"] == "da"].set_index("valid_time")
    f_temp = fc_da.loc[hour_of_qh, "temp_c"].to_numpy()
    f_ghi = irradiance(cfg, pd.Series(hour_of_qh), fc_da.loc[hour_of_qh, "cloud"].to_numpy())
    def kwh(a):                                                          # portfolio MWh per quarter hour
        return a.sum(axis=1) * 0.25 / 1000

    true_cls = {"base": kwh(base), "heat_pump": kwh(hp), "ev": kwh(ev), "pv": -kwh(pv), "battery": kwh(batt_c - batt_d)}
    ev_naive = kwh(np.where(cust["ev_smart"].to_numpy()[None, :], 0, ev))
    fc_cls = {
        "base": kwh(base) * (1 + 0.012 * (temp - f_temp)) * np.exp(rd.normal(0, dk["base_error"], n)),
        "heat_pump": kwh(hp) * np.clip(16 - f_temp, 0, None) / np.clip(16 - temp, 1e-6, None) * (temp < 16) + kwh(hp) * (temp >= 16),
        "ev": (dk["ev_smart_shift_known"] * kwh(ev) + (1 - dk["ev_smart_shift_known"]) * (ev_naive + (kwh(ev) - ev_naive).mean())) * np.exp(rd.normal(0, dk["ev_error"], n)),
        "pv": -kwh(pv) * np.where(ghi > 1, f_ghi / np.clip(ghi, 1, None), 1),
        "battery": true_cls["battery"] * 0.5,
    }
    fc_total = sum(fc_cls.values())
    # MW bought per quarter hour. Exchanges trade 0.1 MW lots; this portfolio is a few hundred households, so the
    # desk is modelled as trading 1 kW steps through an aggregator (lot size in the world file would scale it up).
    da_mw = np.round(fc_total * 4, 3)
    true_total = sum(true_cls.values())
    id_mw = np.round(dk["intraday_cover"] * (true_total - da_mw / 4) * 4 * np.exp(rd.normal(0, 0.3, n)), 3)
    idp = da + mk["id_error_slope"] * (true_total - da_mw / 4) / max(1e-9, true_total.mean()) + rd.normal(0, mk["id_noise"], n)
    spread = rd.uniform(*mk["rebap_spread"], n)
    spikes = rd.random(n) < mk["rebap_spike_share"]
    rebap = idp + np.sign(rd.normal(0, 1, n)) * spread + spikes * rd.uniform(200, 600, n)
    rebap_pre = rebap.copy()
    revised = rd.random(n) < mk["rebap_revision_share"]
    rebap_pre[revised] += rd.normal(0, 40, revised.sum())
    truth = pd.DataFrame({
        "qh_start_utc": qh, "delivery_day": local_day,
        "import_mwh": imp.sum(axis=1) / 1000, "export_mwh": exp_.sum(axis=1) / 1000,
        **{f"{k}_mwh": v for k, v in true_cls.items()},
        **{f"fc_{k}_mwh": v for k, v in fc_cls.items()},
        "da_mw": da_mw, "id_mw": id_mw, "da_eur_mwh": np.round(da, 2), "id_eur_mwh": np.round(idp, 2),
        "rebap_eur_mwh": np.round(rebap, 2), "rebap_preliminary_eur_mwh": np.round(rebap_pre, 2), "rebap_revised": revised,
        "temp_c": temp, "ghi_wm2": ghi, "fc_temp_c": f_temp,
    })
    truth["net_mwh"] = truth["import_mwh"] - truth["export_mwh"]
    truth["imbalance_mwh"] = truth["net_mwh"] - (truth["da_mw"] + truth["id_mw"]) / 4
    truth["da_cost_eur"] = truth["da_mw"] / 4 * truth["da_eur_mwh"]
    truth["id_cost_eur"] = truth["id_mw"] / 4 * truth["id_eur_mwh"]
    truth["imbalance_cost_eur"] = truth["imbalance_mwh"] * truth["rebap_eur_mwh"]
    for k in true_cls:
        truth[f"attr_{k}_eur"] = (truth[f"{k}_mwh"] - truth[f"fc_{k}_mwh"]) * truth["rebap_eur_mwh"]
    truth["attr_intraday_eur"] = -(truth["id_mw"] / 4) * truth["rebap_eur_mwh"]
    # tiny residual from the 0.1 MW rounding of the day-ahead position, and from net vs class totals
    truth["attr_rounding_eur"] = truth["imbalance_cost_eur"] - truth[[c for c in truth if c.startswith("attr_")]].sum(axis=1)
    return {"cfg": cfg, "qh": qh, "local_day": local_day, "customers": cust, "devices": dev, "weather": wx, "forecasts": fc,
            "truth": truth, "imp": imp, "exp": exp_, "dev_kwh": {"ev": ev * 0.25, "heat_pump": hp * 0.25, "pv": pv * 0.25,
                                                                   "battery_c": batt_c * 0.25, "battery_d": batt_d * 0.25}}


# ------------------------------------------------------------------------------------------------- raw feeds

def write(sim: dict, root: Path) -> dict:
    """Writes the raw feeds under root/lake/raw and the truth under root/truth. Returns the planted faults."""
    raw = root / "lake" / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    for d in ("meters", "hems", "weather", "market", "trades", "desk_forecasts"):
        (raw / d).mkdir(parents=True, exist_ok=True)
    (root / "truth").mkdir(parents=True, exist_ok=True)
    planted = {"stuck_meters": [], "substitute_meter_days": 0, "offline_device_days": 0, "counter_resets": 0, "resent_files": 0}
    _meters(sim, raw / "meters", planted)
    _hems(sim, raw / "hems", planted)
    _weather(sim, raw / "weather")
    _market(sim, raw / "market")
    planted["resent_files"] += _trades(sim, raw / "trades")
    t = sim["truth"].copy()
    t.to_parquet(root / "truth" / "portfolio_qh.parquet", index=False)
    (root / "truth" / "planted.json").write_text(json.dumps(planted, indent=1))
    sim["weather"].to_parquet(root / "truth" / "weather_actual.parquet", index=False)
    return planted


def _meters(sim: dict, out: Path, planted: dict) -> None:
    cfg, qh, cust = sim["cfg"], sim["qh"], sim["customers"]
    mc = cfg["meters"]
    days = pd.unique(sim["local_day"])
    stuck = set(rng(cfg["seed"], "stuck").choice(len(cust), size=min(mc["stuck_meters"], len(cust)), replace=False).tolist())
    planted["stuck_meters"] = sorted(cust["meter"].iloc[list(stuck)].tolist())
    files: dict[tuple[str, str], list[pd.DataFrame]] = {}
    local = qh.tz_convert(TZ)
    for di, day in enumerate(days):
        idx = np.where(sim["local_day"] == day)[0]
        loc = local[idx]
        iso = loc.strftime("%Y-%m-%dT%H:%M:%S%z").str.replace(r"(\d{2})(\d{2})$", r"\1:\2", regex=True)
        if rng(cfg["seed"], "utc-day", day).random() < mc.get("utc_z_share", 0):
            iso = qh[idx].strftime("%Y-%m-%dT%H:%M:%SZ")       # this day's files from mdm_a come in UTC
        naive = loc.strftime("%Y-%m-%d %H:%M")
        for j, x in cust.iterrows():
            r = rng(cfg["seed"], "meter-day", x["meter"], day)
            u = r.random()
            lag = 1 if u < mc["arrival"]["d1"] else 2 if u < mc["arrival"]["d1"] + mc["arrival"]["d2"] else 3
            arrive = pd.Timestamp(day) + pd.Timedelta(days=lag)
            for obis, series in (("1-0:1.8.0", sim["imp"][idx, j]), ("1-0:2.8.0", sim["exp"][idx, j])):
                if obis.endswith("2.8.0") and not x["pv"]:
                    continue
                vals = series.copy()
                if j in stuck and di >= len(days) // 3 and obis.endswith("1.8.0"):
                    vals = np.full_like(vals, round(float(rng(cfg["seed"], "stuck-value", x["meter"]).uniform(0.05, 0.3)), 3))
                versions = [(1, "measured", vals, arrive)]
                if r.random() < mc["substitute_share"]:
                    est = np.full_like(vals, float(vals.mean())) * r.uniform(0.7, 1.3)
                    versions = [(1, "substitute", est, arrive), (2, "measured", vals, arrive + pd.Timedelta(days=int(r.integers(2, 6))))]
                    planted["substitute_meter_days"] += 1
                elif r.random() < mc["correction_share"]:
                    wrong = vals * r.uniform(0.5, 1.5)
                    versions = [(1, "measured", wrong, arrive), (2, "measured", vals, arrive + pd.Timedelta(days=int(r.integers(3, 8))))]
                for ver, status, v, when in versions:
                    if x["mdm"] == "mdm_a":
                        df = pd.DataFrame({"meter_id": x["meter"], "obis": obis, "ts": iso, "value": np.round(v, 4), "unit": "kWh",
                                           "status": status, "version": ver})
                    else:
                        df = pd.DataFrame({"meter_id": x["meter"], "obis": obis, "ts_local": naive, "seq": np.arange(1, len(idx) + 1),
                                           "value": np.round(v * 1000).astype(int), "unit": "Wh", "status": status, "version": ver})
                    files.setdefault((x["mdm"], when.strftime("%Y-%m-%d")), []).append(df)
    for (mdm, when), parts in files.items():
        df = pd.concat(parts, ignore_index=True)
        p = out / f"mdm={mdm}" / f"received={when}"
        p.mkdir(parents=True, exist_ok=True)
        df.to_csv(p / "batch-001.csv.gz", index=False)
        if rng(cfg["seed"], "resend", mdm, when).random() < mc["resend_share"] * 4:
            df.to_csv(p / "batch-002.csv.gz", index=False)          # the same delivery again, under a new file name
            planted["resent_files"] += 1


def _hems(sim: dict, out: Path, planted: dict) -> None:
    cfg, qh, cust, dev = sim["cfg"], sim["qh"], sim["customers"], sim["devices"]
    hc = cfg["hems"]
    t0 = qh[0].value // 10**9
    edges = np.arange(len(qh) + 1) * 900
    col = {c: i for i, c in enumerate(cust["customer"])}
    rows = []
    for _, d in dev.iterrows():
        j = col[d["customer"]]
        r = rng(cfg["seed"], "hems", d["device"])
        counters = {"ev": [sim["dev_kwh"]["ev"][:, j]], "heat_pump": [sim["dev_kwh"]["heat_pump"][:, j]],
                    "pv": [sim["dev_kwh"]["pv"][:, j]], "battery": [sim["dev_kwh"]["battery_c"][:, j], sim["dev_kwh"]["battery_d"][:, j]]}[d["kind"]]
        cum = [np.concatenate([[0.0], np.cumsum(c)]) + r.uniform(100, 5000) for c in counters]
        t, times = 0.0, []
        while t < edges[-1]:
            t += r.uniform(*hc["report_minutes"]) * 60
            times.append(t)
        times = np.array([x for x in times if x < edges[-1]])
        keep = np.ones(len(times), bool)
        for day_start in range(0, int(edges[-1]), 86400):
            if r.random() < hc["offline_share"]:
                a = day_start + r.uniform(0, 80000)
                keep &= ~((times > a) & (times < a + r.uniform(2, 12) * 3600))
                planted["offline_device_days"] += 1
        times = times[keep]
        vals = [np.interp(times, edges, c) for c in cum]
        if r.random() < hc["reset_share"] * len(qh) / 96 and len(times) > 10:
            k = int(r.integers(5, len(times) - 5))
            vals = [np.concatenate([v[:k], v[k:] - v[k] + r.uniform(0, 0.05)]) for v in vals]
            planted["counter_resets"] += 1
        for i, ts in enumerate(times):
            rec = {"device_id": d["device"], "customer_id": d["customer"], "kind": d["kind"], "ts_ms": int((t0 + ts) * 1000),
                   "energy_kwh": round(float(vals[0][i]), 4), "energy2_kwh": round(float(vals[1][i]), 4) if len(vals) > 1 else None}
            rows.append(rec)
            if r.random() < hc["duplicate_share"]:
                rows.append(dict(rec))
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True).dt.strftime("%Y-%m-%d")
    for day, part in df.groupby("day"):
        p = out / f"day={day}"
        p.mkdir(parents=True, exist_ok=True)
        part.drop(columns="day").sample(frac=1, random_state=0).to_csv(p / "telemetry.csv.gz", index=False)   # arrival order, not time order


def _weather(sim: dict, out: Path) -> None:
    fc = sim["forecasts"]
    for issue, part in fc.groupby("issue_time"):
        name = pd.Timestamp(issue).strftime("%Y%m%dT%H%M")
        recs = [{"valid_time": v.isoformat(), "temp_c": round(float(t), 2), "cloud": round(float(c), 3)}
                for v, t, c in zip(part["valid_time"], part["temp_c"], part["cloud"])]
        (out / f"run={name}-{part['run'].iloc[0]}.json").write_text(json.dumps({"issue_time": pd.Timestamp(issue).isoformat(),
                                                                                  "run": part["run"].iloc[0], "values": recs}))


def _market(sim: dict, out: Path) -> None:
    t = sim["truth"]
    cfg = sim["cfg"]
    for day, part in t.groupby("delivery_day"):
        (out / "day_ahead").mkdir(exist_ok=True)
        part[["qh_start_utc", "da_eur_mwh"]].rename(columns={"qh_start_utc": "delivery_start", "da_eur_mwh": "price_eur_mwh"}) \
            .assign(delivery_start=lambda x: x["delivery_start"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(out / "day_ahead" / f"{day}.csv", index=False)
        (out / "intraday").mkdir(exist_ok=True)
        part[["qh_start_utc", "id_eur_mwh"]].rename(columns={"qh_start_utc": "delivery_start", "id_eur_mwh": "id3_eur_mwh"}) \
            .assign(delivery_start=lambda x: x["delivery_start"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(out / "intraday" / f"{day}.csv", index=False)
        (out / "rebap").mkdir(exist_ok=True)
        pre = part[["qh_start_utc", "rebap_preliminary_eur_mwh"]].rename(columns={"rebap_preliminary_eur_mwh": "rebap_eur_mwh"})
        pre.assign(qh_start_utc=lambda x: x["qh_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"), status="preliminary",
                   published=(pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")).to_csv(out / "rebap" / f"{day}-preliminary.csv", index=False)
        final_day = pd.Timestamp(day) + pd.Timedelta(days=cfg["market"]["rebap_final_after_days"])
        last_day = pd.Timestamp(t["delivery_day"].max()) + pd.Timedelta(days=cfg["market"]["rebap_final_after_days"])
        if final_day <= last_day:
            fin = part[["qh_start_utc", "rebap_eur_mwh"]]
            fin.assign(qh_start_utc=lambda x: x["qh_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"), status="final",
                       published=final_day.strftime("%Y-%m-%d")).to_csv(out / "rebap" / f"{day}-final.csv", index=False)


def _trades(sim: dict, out: Path) -> int:
    """Trades as the trading system exports them: one row per trade version. An amendment repeats the trade id with a
    higher version; a cancellation is a version with status 'cancelled'; some exports are sent twice."""
    t, cfg = sim["truth"], sim["cfg"]
    tc = cfg["trades"]
    rows, tid = [], 0
    for _, x in t.iterrows():
        for product, mw, price in (("DA", x["da_mw"], x["da_eur_mwh"]), ("ID", x["id_mw"], x["id_eur_mwh"])):
            if abs(mw) < 1e-9:
                continue
            tid += 1
            r = rng(cfg["seed"], "trade", tid)
            base = {"trade_id": f"T{tid:07d}", "product": product, "delivery_start": x["qh_start_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "side": "buy" if mw > 0 else "sell", "price_eur_mwh": round(float(price), 2)}
            if r.random() < tc["cancel_share"]:
                wrong = round(float(abs(mw) * r.uniform(1.2, 2.0)), 3)
                rows.append({**base, "version": 1, "status": "active", "mw": wrong})
                rows.append({**base, "version": 2, "status": "cancelled", "mw": wrong})
                tid += 1
                rows.append({**base, "trade_id": f"T{tid:07d}", "version": 1, "status": "active", "mw": round(float(abs(mw)), 3)})
            elif r.random() < tc["amend_share"]:
                rows.append({**base, "version": 1, "status": "active", "mw": round(float(abs(mw) * r.uniform(0.6, 1.4)), 3)})
                rows.append({**base, "version": 2, "status": "active", "mw": round(float(abs(mw)), 3)})
            else:
                rows.append({**base, "version": 1, "status": "active", "mw": round(float(abs(mw)), 3)})
    df = pd.DataFrame(rows)
    df["export_day"] = df["delivery_start"].str[:10]
    resent = 0
    for day, part in df.groupby("export_day"):
        part = part.drop(columns="export_day")
        part.to_csv(out / f"trades-{day}.csv", index=False)
        if rng(cfg["seed"], "trade-resend", day).random() < tc["resend_share"] * 5:
            part.to_csv(out / f"trades-{day}-resent.csv", index=False)
            resent += 1
    desk = sim["truth"][["qh_start_utc", "delivery_day"] + [c for c in sim["truth"] if c.startswith("fc_") and c.endswith("_mwh")]]
    desk.assign(qh_start_utc=lambda x: x["qh_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")).to_csv(out.parent / "desk_forecasts" / "class_forecasts.csv", index=False)
    return resent
