from pathlib import Path

import yaml

from ftd.eval.gate import check

ROOT = Path(__file__).resolve().parents[1]


def test_every_gate_line_reads_a_number_the_report_has():
    rep = {"dbt": {"ok": True}, "relative": {"calendar_ok_share": 1.0, "net_abs_error_share": 0.003, "imbalance_error_vs_first_version": 0.02,
                                             "attribution_error_vs_first_version": 0.02, "duplicates_skipped_share": 1.0},
           "designs": {"datahub": {"net_within_half_percent": 0.8, "days_procurement_within_1pct": 1.0}},
           "faults": {"stuck_meters_found": 3, "stuck_meters_planted": 3, "stuck_meters_false_alarms": 0, "substitute_values_left_after_versions": 0},
           "idempotent": {"marts_unchanged": True}, "forecast": {"gate_features": {"optimism_kwh": 0.0}}}
    lines = check(rep, ROOT / "config/gate.yaml")
    assert len(lines) == len(yaml.safe_load((ROOT / "config/gate.yaml").read_text())["lines"])
    assert all(x["pass"] for x in lines), [x for x in lines if not x["pass"]]
