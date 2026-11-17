"""Runs the warehouse: land raw files in bronze, then dbt build (models and tests) into DuckDB."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from ftd.ingest import land

ROOT = Path(__file__).resolve().parents[1]
DBT = ROOT / "dbt"


def dbt(args: list[str], lake: Path, db: Path) -> dict:
    """Runs dbt in its own process, as the Airflow task does, so the warehouse file is closed when it returns."""
    env = {**os.environ, "FTD_DUCKDB": str(db), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false", "DO_NOT_TRACK": "1"}
    db.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which("dbt") or "dbt"
    proc = subprocess.run([exe, *args, "--project-dir", str(DBT), "--profiles-dir", str(DBT), "--vars", f"{{lake: '{lake}'}}"],
                          env=env, capture_output=True, text=True)
    results = DBT / "target" / "run_results.json"
    failed = []
    if results.exists():
        for res in json.loads(results.read_text())["results"]:
            if res["status"] in ("error", "fail"):
                failed.append(f"{res['unique_id']}: {(res.get('message') or '')[:300]}")
    return {"ok": proc.returncode == 0, "failed": failed, "log_tail": proc.stdout[-1500:] if proc.returncode else ""}


def build(lake: Path, db: Path) -> dict:
    landed = land(lake)
    out = dbt(["build"], lake, db)
    return {"landed": landed, **out}
