"""README from the reports: every number in it comes from reports/dev.json or reports/heldout.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def pct(x, d=1):
    return "–" if x is None else f"{100 * x:.{d}f}%"


def eur(x, d=0):
    return "–" if x is None else f"{'-' if x < 0 else ''}€{abs(x):,.{d}f}"


def n(x):
    return f"{x:,}"


def show(line: dict) -> str:
    v = line["value"]
    if isinstance(v, bool):
        return "yes" if v else "no"
    if v is None:
        return "–"
    if "share" in line["metric"] or "within" in line["metric"] or "vs_first" in line["metric"]:
        return pct(v)
    if "kwh" in line["metric"]:
        return f"{v} kWh"
    return n(v) if isinstance(v, int) else f"{v:.4g}"


def render() -> str:
    dev = json.loads((ROOT / "reports/dev.json").read_text())
    hp = ROOT / "reports/heldout.json"
    held = json.loads(hp.read_text()) if hp.exists() else None
    d, f = dev["designs"]["datahub"], dev["designs"]["first_version_sql"]
    hd = held["designs"]["datahub"] if held else None
    hf = held["designs"]["first_version_sql"] if held else None
    rows = [
        ("Portfolio energy off from the truth", f"{f['net_abs_error_mwh']:,.2f} MWh ({pct(dev['relative']['first_version_net_abs_error_share'], 2)})",
         f"{d['net_abs_error_mwh']:,.2f} MWh ({pct(dev['relative']['net_abs_error_share'], 2)})",
         f"{hd['net_abs_error_mwh']:,.2f} MWh vs {hf['net_abs_error_mwh']:,.2f}" if held else "–"),
        ("Quarter hours within 0.5% of the true net load", pct(f["net_within_half_percent"]), pct(d["net_within_half_percent"]),
         f"{pct(hd['net_within_half_percent'])} vs {pct(hf['net_within_half_percent'])}" if held else "–"),
        ("Imbalance cost for the month (truth)", f"{eur(f['imbalance_cost_built_eur'])} ({eur(f['imbalance_cost_truth_eur'])})",
         f"{eur(d['imbalance_cost_built_eur'])} ({eur(d['imbalance_cost_truth_eur'])})",
         f"{eur(hd['imbalance_cost_built_eur'])} vs {eur(hf['imbalance_cost_built_eur'])} ({eur(hd['imbalance_cost_truth_eur'])})" if held else "–"),
        ("Imbalance cost, sum of daily errors", eur(f["imbalance_cost_daily_abs_error_eur"]), eur(d["imbalance_cost_daily_abs_error_eur"]),
         f"{eur(hd['imbalance_cost_daily_abs_error_eur'])} vs {eur(hf['imbalance_cost_daily_abs_error_eur'])}" if held else "–"),
        ("Days with procurement cost within 1%", pct(f["days_procurement_within_1pct"], 0), pct(d["days_procurement_within_1pct"], 0),
         f"{pct(hd['days_procurement_within_1pct'], 0)} vs {pct(hf['days_procurement_within_1pct'], 0)}" if held else "–"),
        ("Imbalance cost attribution off from the truth", eur(f["attribution_abs_error_eur"]), eur(d["attribution_abs_error_eur"]),
         f"{eur(hd['attribution_abs_error_eur'])} vs {eur(hf['attribution_abs_error_eur'])}" if held else "–"),
    ]
    table = "\n".join(f"| {a} | {b} | {c} | {e} |" for a, b, c, e in rows)
    fa = dev["faults"]
    fc = dev.get("forecast", {})
    gate = []
    for i, ln in enumerate(dev["gate"]):
        h = held["gate"][i] if held else None
        gate.append(f"| {ln['name']} | {show(ln)} {'✅' if ln['pass'] else '❌'} | " + (f"{show(h)} {'✅' if h['pass'] else '❌'} |" if h else "– |"))
    passed = sum(x["pass"] for x in dev["gate"])
    hpassed = sum(x["pass"] for x in held["gate"]) if held else 0
    attr = d["attribution"]
    attr_rows = "\n".join(f"| {k.replace('_', ' ')} | {eur(v['truth_eur'])} | {eur(v['built_eur'])} | {eur(f['attribution'][k]['built_eur'])} |" for k, v in attr.items())
    held_line = (f"The held-out month passed {hpassed} of {len(held['gate'])}. [docs/heldout.md](docs/heldout.md) has what it "
                 "stressed and what came out." if held else "The held-out month has not been run yet.")
    dst = fa["dst_days"][0] if fa["dst_days"] else None
    return f"""# flex-trading-datahub

The data under a dynamic-tariff power supplier's trading desk. The desk buys on the day-ahead auction, corrects
intraday, pays the imbalance price for whatever is left, and runs a virtual power plant of EVs, heat pumps, solar and
home batteries. Its data comes from every direction, and none of it arrives clean:

- **smart-meter readings** from two metering operators. One sends kWh with UTC offsets. The other sends Wh in local
  wall-clock time without an offset, so the second 02:00 on the night summer time ends can only be placed by its
  position in the day. Files arrive one to three days late, sometimes twice. Values come first as substitutes, then
  as measured, and some are corrected later. A few registers get stuck;
- **device counters** from home energy management systems (EV chargers, heat pumps, PV, batteries). They report
  every few minutes, out of order and duplicated, go offline for hours, and restart at zero after firmware updates;
- **weather forecast runs**, each with its issue time. A forecast feature is only honest if it was issued before the
  day-ahead gate;
- **EPEX day-ahead (15-minute products) and intraday prices**, and the German imbalance price (reBAP), which is
  published preliminary and revised later;
- **trades** from the trading system, as versions: amended, cancelled, sometimes exported twice.

This repository lands those feeds in an S3-style bronze layer (Parquet, once per file by content hash) and builds
them with **dbt on DuckDB** into tested models:
- `fct_portfolio_qh`: one row per quarter hour, with metered load, each device class, positions, prices, the
  imbalance and its cost, and an attribution of that cost to the desk's forecast error per class that adds up exactly;
- `fct_pnl_daily`: procurement P&L per delivery day;
- `fct_data_quality_daily`: is each day complete and settled;
- `feat_load_qh`: forecasting features using only what was known at the gate.

An **Airflow** DAG runs it hourly, and a **Python dashboard** (Dash and Plotly) shows it to the desk. Everything is
measured against a simulated portfolio ({dev['customers']} households, {dev['devices']} devices, {dev['days']} days from
{dev['start']}) and a held-out month that was run once.

![dashboard](docs/dashboard.png)

## Against a first version of the same warehouse

Same bronze files. The first version is plain SQL that handles units and offsets but:
- keeps every version of a meter value and every version of a trade;
- reads local times without an offset as ordinary local times;
- settles on the first imbalance price published;
- differences device counters as they come.

| | first version | **this warehouse** | held-out month (this vs first) |
|---|---|---|---|
{table}

Dev month: {n(dev['raw']['meter_values'])} meter values, {n(dev['raw']['device_reports'])} device reports,
{n(dev['raw']['trade_versions'])} trade versions and {dev['raw']['weather_runs']} forecast runs. The portfolio is a few hundred
households, so the euro amounts are small. The ratios are the point.

**Where the month's imbalance cost came from**, against the truth:

| class | truth | this warehouse | first version |
|---|---|---|---|
{attr_rows}

## Faults that were planted, and what was found

| fault | planted | handled |
|---|---|---|
| stuck registers | {fa['stuck_meters_planted']} | {fa['stuck_meters_found']} found, {fa['stuck_meters_false_alarms']} false alarms; values estimated from the meter's own profile for analysis |
| register-days first sent as substitute values | {fa['substitute_register_days_planted']} | {fa['substitute_register_days_seen']} seen, {fa['substitute_values_left_after_versions']} substitute values left once the measured ones arrived |
| files delivered twice | {fa['duplicate_deliveries_skipped']} | all skipped at landing by content hash |
| device counters restarted at zero | {fa['counter_resets_planted']} | {fa['counter_resets_found']} stitched on |
| the night summer time ends | {dst['day'] if dst else '–'} | {dst['quarter_hours'] if dst else '–'} quarter hours, as expected |

A second landing and dbt run changes nothing: {'yes' if dev['idempotent']['marts_unchanged'] else 'no'}.

## Forecasting on features known at the gate

The same LightGBM model was trained on two feature sets: `feat_load_qh`, and the first version's features (the newest
weather run for each hour, and yesterday's metered load). It was then tested on the last {fc.get('test_days', '–')} days.

| features | backtest error | error in production | exposure at the imbalance price |
|---|---|---|---|
| known at the gate (`feat_load_qh`) | {fc['gate_features']['backtest_mae_kwh']} kWh | {fc['gate_features']['live_mae_kwh']} kWh | {eur(fc['gate_features']['live_exposure_eur'])} |
| leaking the future | {fc['leaky_features']['backtest_mae_kwh']} kWh | {fc['leaky_features']['live_mae_kwh']} kWh | {eur(fc['leaky_features']['live_exposure_eur'])} |
| the desk's own day-ahead position | – | {fc['desk_day_ahead']['live_mae_kwh']} kWh | {eur(fc['desk_day_ahead']['live_exposure_eur'])} |

- The leaking feature set looks {fc['leaky_features']['optimism_kwh']} kWh per quarter hour better in its backtest than it
  does in production. The honest one backtests at exactly what production gets.
- Neither model beats the desk's own class-by-class forecast. The model is here to show the features are safe to
  build on, not to replace the desk.

## Gate

The gate was written after the first dev results and before the held-out month was run (`config/gate.yaml`).

| line | dev | held-out H1 |
|---|---|---|
{chr(10).join(gate)}

Dev passes {passed} of {len(dev['gate'])} lines. {held_line}

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                          # a four-day world (with the 100-quarter-hour day) built and tested, about 15 s
python -m ftd.eval.cli evaluate              # the dev month: world, landing, dbt build, comparison, forecast, gate, about 2 min
cd dbt && FTD_DUCKDB=../warehouse/flex.duckdb dbt build --vars "{{lake: '../work/D1/lake'}}"   # dbt directly on a kept lake
python -m dashboard.app                      # the dashboard on :8050 (FTD_DUCKDB=<warehouse> for live marts)
```

Where things live:
- `ftd/world`: the simulated portfolio and its truth (nothing else imports it);
- `ftd/ingest.py`: raw to bronze;
- `dbt/`: staging, intermediate, marts and their tests;
- `dags/`: the Airflow DAG;
- `dashboard/`: the Dash app, feature-first, with theme tokens;
- `ftd/eval`: the comparison, scoring, gate and this README.

On AWS, bronze is an S3 prefix and the same models run with dbt-athena or on DuckDB reading S3. [docs/aws.md](docs/aws.md)
covers that, and [docs/agentic-workflow.md](docs/agentic-workflow.md) covers how a coding agent was used to build this.
"""
