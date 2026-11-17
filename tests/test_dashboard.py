import shutil

import pytest

from dashboard import app as appmod
from dashboard.data import load
from dashboard.features import attribution, day


@pytest.fixture()
def marts(quick, tmp_path):
    out = tmp_path / "marts"
    out.mkdir()
    for t in ("fct_portfolio_qh", "fct_pnl_daily", "fct_data_quality_daily", "dq_stuck_meters"):
        quick["sql"](f"select * from {t}").to_parquet(out / f"{t}.parquet", index=False)
    return out


def test_every_section_renders_from_the_marts(marts):
    children, problem = appmod.body(str(marts))
    assert problem is None and len(children) >= 3
    d = load(str(marts))
    assert "2026-10-25" in d.days
    fig = day.figure(d, "2026-10-25")
    assert len(fig.data[0].x) == 100                       # the night summer time ends
    assert len(attribution.figure(d).data) == 8


def test_a_missing_warehouse_shows_the_error_with_its_reason(tmp_path):
    children, problem = appmod.body(str(tmp_path / "nowhere"))
    assert children == [] and "reports/marts" in problem


def test_no_days_shows_the_empty_state(marts):
    import pandas as pd
    for t in ("fct_portfolio_qh", "fct_pnl_daily", "fct_data_quality_daily"):
        df = pd.read_parquet(marts / f"{t}.parquet")
        df.iloc[0:0].to_parquet(marts / f"{t}.parquet", index=False)
    children, problem = appmod.body(str(marts))
    assert problem is None and "No delivery days yet." in str(children)


def test_the_app_builds(marts):
    a = appmod.create_app(str(marts))
    assert "--paper:" in a.index_string
    shutil.rmtree(marts)
