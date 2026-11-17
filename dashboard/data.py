"""Where the dashboard's numbers come from: the warehouse's marts in DuckDB when FTD_DUCKDB points at one, otherwise
the snapshot the evaluation writes to reports/marts. Either way the same tables, read-only."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TABLES = ("fct_portfolio_qh", "fct_pnl_daily", "fct_data_quality_daily", "dq_stuck_meters")


@dataclass
class Data:
    portfolio: pd.DataFrame
    pnl: pd.DataFrame
    quality: pd.DataFrame
    stuck: pd.DataFrame
    report: dict | None

    @property
    def days(self) -> list[str]:
        return sorted(self.pnl["delivery_day"].astype(str).str[:10].unique()) if len(self.pnl) else []


def load(source: str | None = None) -> Data:
    src = source or os.environ.get("FTD_DUCKDB")
    if src and Path(src).suffix == ".duckdb":
        import duckdb
        con = duckdb.connect(src, read_only=True)
        try:
            frames = {t: con.sql(f"select * from {t}").df() for t in TABLES}
        finally:
            con.close()
    else:
        base = Path(src) if src else ROOT / "reports" / "marts"
        frames = {t: pd.read_parquet(base / f"{t}.parquet") for t in TABLES}
    for k in ("fct_portfolio_qh", "fct_pnl_daily", "fct_data_quality_daily"):
        frames[k]["delivery_day"] = frames[k]["delivery_day"].astype(str).str[:10]
    rp = ROOT / "reports" / "dev.json"
    return Data(frames["fct_portfolio_qh"], frames["fct_pnl_daily"], frames["fct_data_quality_daily"], frames["dq_stuck_meters"],
                json.loads(rp.read_text()) if rp.exists() else None)
