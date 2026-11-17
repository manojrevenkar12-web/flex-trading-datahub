# SKILLS.md

## Add a source feed

1. Make the world send it: write the raw files in `ftd/world/portfolio.py` (`write`) in the shape the real source
   uses, with its faults and their rates in `config/world.yaml`. Record planted faults in `planted.json`.
2. Add its glob to `SOURCES` in `ftd/ingest.py`, so it lands in `bronze/<source>/` once per file.
3. Add `stg_<source>.sql` in `dbt/models/staging` (types, units, UTC) and its tests in `schema.yml`. Versions and
   corrections are resolved in `intermediate`, never in staging.
4. `python -m pytest -q`, then the evaluate line in AGENTS.md.

## Add a data-quality check

Write it as a model or a singular test in `dbt/tests`. A check that should stop the pipeline is a test (Airflow's
`dbt_build` fails on it); a check the desk should see is a column in `fct_data_quality_daily`, shown in the dashboard's
quality view. Plant the fault in the world first, and add a line to the README's fault table in `ftd/eval/readme.py`.

## Add a forecast feature

Add the column to `feat_load_qh` using only rows available before `gate_utc(delivery_day)`, extend
`assert_features_known_at_the_gate`, then add it to `FEATURES` in `ftd/forecast.py`. The gate line "the forecast
backtest is what production gets" fails if the feature leaks.

## Add a dashboard view

Create `dashboard/features/<view>.py` with a `view(data)` returning the section, using `components.section`, `stat`,
`flag`, `empty_state` and `theme.figure_layout`. Colours, sizes and durations come from `dashboard/theme.py`. Add it
to `body` in `dashboard/app.py` and a test in `tests/test_dashboard.py`.

## Run dbt by hand

```bash
python -c "from pathlib import Path; from ftd.world import portfolio as p; p.write(p.simulate(p.load(Path('config/world.yaml'), quick=True)), Path('work/q'))"
python -c "from pathlib import Path; from ftd.ingest import land; print(land(Path('work/q/lake')))"
cd dbt && FTD_DUCKDB=../work/q/flex.duckdb dbt build --vars "{lake: '../work/q/lake'}" && dbt docs generate --vars "{lake: '../work/q/lake'}"
```
