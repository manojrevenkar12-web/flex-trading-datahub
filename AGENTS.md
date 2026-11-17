# Working in flex-trading-datahub

Fast feedback first: `python -m pytest -q` simulates a four-day portfolio (24 to 27 October 2026, with the
100-quarter-hour day), lands it, runs `dbt build` and the first-version SQL on it, and checks the warehouse, the
invariants, the gate code and the dashboard in about 15 seconds. `ruff check .` for lint. After any change to the
world, the dbt models, the ingest, the forecast or the settings run

```bash
python -m ftd.eval.cli evaluate && python -m ftd.eval.cli gate && python -m ftd.eval.cli readme
```

and commit the regenerated `reports/dev.json`, `reports/marts/` and `README.md`. CI fails when they disagree.

## Layout

| path | what it is | may read |
|---|---|---|
| `ftd/world` | the simulated portfolio: customers, devices, weather, prices, the desk, the raw feeds it sends and the truth | `config/world.yaml` or `config/heldout.yaml`, `ftd/keyed.py` |
| `ftd/ingest.py` | raw files to bronze Parquet, once per file by content hash | the lake |
| `dbt/` | staging, intermediate and marts on DuckDB, with schema tests and singular tests | bronze |
| `ftd/forecast.py` | the day-ahead load model on `feat_load_qh` | the warehouse |
| `dags/` | the Airflow 3 DAG that runs ingest, dbt, data quality and the forecast | `ftd.ingest`, `ftd.pipeline`, `ftd.forecast` |
| `dashboard/` | the Dash app: `features/` per view, `theme.py` and `assets/theme.css` for every colour, size and duration | the warehouse or `reports/marts` |
| `ftd/eval` | simulates, builds both designs, scores them against the truth, writes reports, the gate and the README | everything |

## Invariants (checked in `tests/test_invariants.py` and the dbt tests)

1. **The truth stays in the world.** Nothing in `ftd/*.py`, `dbt/`, `dags/` or `dashboard/` imports `ftd.world` or
   reads `truth/`. Only `ftd/eval` compares with the truth.
2. **The world does not read the warehouse's settings.** `ftd/world` reads its world file, never `dbt/`,
   `config/gate.yaml` or the pipeline.
3. **Same luck for every design.** Every random draw is keyed by what it is about (`ftd/keyed.py`), so the warehouse
   and the first version see the same files.
4. **Delivery days are local.** A day has 92, 96 or 100 quarter hours. Times without an offset are placed by their
   position in the day, never by the wall clock (`stg_meter_readings`).
5. **A feature is what was known at the gate.** `feat_load_qh` uses forecast runs issued before 12:00 Berlin time the
   day before and meter values received by then (`assert_features_known_at_the_gate`).
6. **Landing is idempotent.** A file is landed once by its content hash; a second run changes no mart.
7. **Settings in config.** World rates in `config/*.yaml`, dbt variables in `dbt/dbt_project.yml`, the gate in
   `config/gate.yaml`, the dashboard's look in `dashboard/theme.py`.
8. **Generated reports.** Every number in the README comes from `reports/`.

## The held-out rule

`config/heldout.yaml` (March 2026: colder, the start of summer time, more heat pumps and EVs, twice the faults) is run
once with `python -m ftd.eval.cli heldout`, with the code and settings dev ended on. It writes `config/heldout.lock`
and `reports/heldout.json`; findings go into `docs/heldout.md`. Fixes are made and measured on dev. The held-out month
is not run again and `config/gate.yaml` is not moved.
