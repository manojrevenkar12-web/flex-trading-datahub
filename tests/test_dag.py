"""Runs where Airflow 3 is installed (the airflow CI job); skipped elsewhere."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_the_dag_imports_with_its_tasks_and_schedule():
    pytest.importorskip("airflow.sdk")
    from airflow.sdk import DAG
    spec = importlib.util.spec_from_file_location("flex_dag", ROOT / "dags/flex_trading_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    dag = mod.dag_object
    assert isinstance(dag, DAG)
    assert set(dag.task_ids) == {"land_raw", "dbt_build", "data_quality", "forecast"}
    assert dag.get_task("dbt_build").upstream_task_ids == {"land_raw"}
    assert dag.get_task("forecast").upstream_task_ids == {"dbt_build"}
    assert dag.max_active_runs == 1
