"""Is each delivery day complete and settled enough to trade and report on?"""
from __future__ import annotations

from dash import html

from dashboard.components import section
from dashboard.data import Data

COLUMNS = [
    ("delivery_day", "Day", lambda v: v),
    ("quarter_hours", "Quarter hours", lambda v: f"{int(v)}"),
    ("min_meter_coverage", "Meters in", lambda v: f"{v * 100:.1f}%"),
    ("substitute_values", "Substitutes left", lambda v: f"{int(v)}"),
    ("estimated_values", "Stuck values estimated", lambda v: f"{int(v)}"),
    ("counter_resets", "Counter restarts", lambda v: f"{int(v)}"),
    ("cancelled_trades", "Cancelled trades", lambda v: f"{int(v)}"),
    ("rebap_final_share", "Final prices", lambda v: f"{v * 100:.0f}%"),
    ("ready_to_settle", "Ready", lambda v: "yes" if v else "no"),
]


def view(data: Data):
    q = data.quality.sort_values("delivery_day")
    rows = []
    for _, r in q.iterrows():
        cells = []
        for col, _, fmt in COLUMNS:
            bad = (col == "ready_to_settle" and not r[col]) or (col == "quarter_hours" and not r["calendar_ok"]) or (col == "estimated_values" and r[col] > 0)
            good = col == "ready_to_settle" and bool(r[col])
            cells.append(html.Td(fmt(r[col]), **{"data-bad": "true" if bad else "false", "data-good": "true" if good else "false"}))
        rows.append(html.Tr(cells))
    stuck = ", ".join(data.stuck["meter_id"].astype(str)) if len(data.stuck) else "none"
    return section(
        "Data quality, day by day",
        f"Late, repeated and corrected meter files, device counters that restart, and trades that were amended or cancelled are all "
        f"handled before these numbers reach the desk. Stuck registers found: {stuck}.",
        html.Div(html.Table([html.Thead(html.Tr([html.Th(h) for _, h, _ in COLUMNS])), html.Tbody(rows)], className="data"), className="scroll"),
    )
