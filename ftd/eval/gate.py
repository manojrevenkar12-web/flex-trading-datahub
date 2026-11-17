"""The release gate: each line reads one number from a report and compares it with a value or another number."""
from __future__ import annotations

import operator
from pathlib import Path

import yaml

OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt, "==": operator.eq}


def get(d: dict, path: str):
    for k in path.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def check(report: dict, gate_file: Path) -> list[dict]:
    g = yaml.safe_load(gate_file.read_text())
    out = []
    for line in g["lines"]:
        value = get(report, line["metric"])
        target = get(report, line["ref"]) if "ref" in line else line["value"]
        ok = value is not None and target is not None and OPS[line["op"]](value, target)
        out.append({"name": line["name"], "metric": line["metric"], "op": line["op"], "value": value, "target": target, "pass": bool(ok)})
    return out
