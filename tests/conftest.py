import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from ftd.eval.naive import build as build_naive
from ftd.pipeline import build
from ftd.world import portfolio

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def quick(tmp_path_factory):
    """The four-day quick world (24 to 27 October 2026, with the 100-quarter-hour day), landed and built once."""
    work = tmp_path_factory.mktemp("quick")
    sim = portfolio.simulate(portfolio.load(ROOT / "config/world.yaml", quick=True))
    planted = portfolio.write(sim, work)
    res = build(work / "lake", work / "warehouse.duckdb")
    build_naive(work / "lake", work / "naive.duckdb")
    truth = pd.read_parquet(work / "truth" / "portfolio_qh.parquet")
    truth["qh_start_utc"] = truth["qh_start_utc"].dt.tz_convert("UTC").dt.tz_localize(None)

    def sql(q: str, db: str = "warehouse") -> pd.DataFrame:
        con = duckdb.connect(str(work / f"{db}.duckdb"), read_only=True)
        try:
            return con.sql(q).df()
        finally:
            con.close()

    return {"work": work, "sim": sim, "planted": planted, "build": res, "truth": truth, "sql": sql,
            "planted_json": json.loads((work / "truth" / "planted.json").read_text())}
