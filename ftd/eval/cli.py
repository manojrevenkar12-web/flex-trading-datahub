"""python -m ftd.eval.cli evaluate [--quick] | gate | heldout | readme [--check]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

from ftd.eval import gate
from ftd.eval.run import ROOT, evaluate, write_report


def brief(rep: dict) -> None:
    for k, d in rep.get("designs", {}).items():
        print(f"{k:18} net error {d['net_abs_error_mwh']} MWh  within 0.5% {d['net_within_half_percent']}  "
              f"imbalance cost {d['imbalance_cost_built_eur']} (truth {d['imbalance_cost_truth_eur']})  attribution error {d['attribution_abs_error_eur']}")
    for ln in rep.get("gate", []):
        print(("PASS " if ln["pass"] else "FAIL ") + f"{ln['name']}: {ln['value']} {ln['op']} {ln['target']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ftd")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("evaluate")
    e.add_argument("--quick", action="store_true")
    sub.add_parser("gate")
    sub.add_parser("heldout")
    r = sub.add_parser("readme")
    r.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd == "evaluate":
        rep = evaluate(quick=args.quick)
        rep["gate"] = gate.check(rep, ROOT / "config/gate.yaml")
        write_report(rep, "quick" if args.quick else "dev")
        brief(rep)
        return 0
    if args.cmd == "gate":
        rep = json.loads((ROOT / "reports/dev.json").read_text())
        lines = gate.check(rep, ROOT / "config/gate.yaml")
        if rep.get("gate") != lines:
            rep["gate"] = lines
            write_report(rep, "dev")
        brief({"gate": lines})
        return 0 if all(x["pass"] for x in lines) else 1
    if args.cmd == "heldout":
        lock = ROOT / "config/heldout.lock"
        if lock.exists():
            print(f"the held-out world was run once already ({lock.read_text().strip()}); it is not run again")
            return 1
        rep = evaluate("config/heldout.yaml")
        rep["gate"] = gate.check(rep, ROOT / "config/gate.yaml")
        write_report(rep, "heldout")
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        lock.write_text(f"run once at commit {commit or 'unknown'}\n")
        brief(rep)
        return 0
    if args.cmd == "readme":
        from ftd.eval import readme
        text = readme.render()
        path = ROOT / "README.md"
        if args.check:
            if not path.exists() or path.read_text() != text:
                print("README.md does not match the reports: run python -m ftd.eval.cli readme")
                return 1
            return 0
        path.write_text(text)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
