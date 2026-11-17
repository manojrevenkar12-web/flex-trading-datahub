import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_nothing_that_serves_reads_the_truth():
    files = list((ROOT / "ftd").glob("*.py")) + list((ROOT / "dbt/models").rglob("*.sql")) + list((ROOT / "dashboard").rglob("*.py")) + list((ROOT / "dags").glob("*.py"))
    for f in files:
        text = f.read_text()
        assert not re.search(r"ftd\.world|truth/|portfolio_qh\.parquet", text), f


def test_the_world_does_not_read_the_warehouse_settings():
    for f in (ROOT / "ftd/world").glob("*.py"):
        text = f.read_text()
        assert "dbt/" not in text and "gate.yaml" not in text and "ftd.pipeline" not in text, f
