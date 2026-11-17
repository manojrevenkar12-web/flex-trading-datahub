"""How far a plausible first version of the same warehouse lands from the truth, next to this one."""
from __future__ import annotations

from dash import html

from dashboard.components import section
from dashboard.data import Data
from dashboard.theme import eur

ROWS = [
    ("Portfolio energy off from the truth", lambda d: f"{d['net_abs_error_mwh']:,.2f} MWh"),
    ("Quarter hours within 0.5% of the true load", lambda d: f"{d['net_within_half_percent'] * 100:.1f}%"),
    ("Imbalance cost, built vs truth", lambda d: f"{eur(d['imbalance_cost_built_eur'])} vs {eur(d['imbalance_cost_truth_eur'])}"),
    ("Days with procurement cost within 1%", lambda d: f"{d['days_procurement_within_1pct'] * 100:.0f}%"),
    ("Attribution off from the truth", lambda d: eur(d["attribution_abs_error_eur"])),
]


def view(data: Data):
    if not data.report:
        return html.Div()
    d = data.report["designs"]
    return section(
        "Against a first version of the same warehouse",
        "Same bronze files, plain SQL: units and offsets handled, but every version of a meter value and trade kept, local times "
        "without an offset read as ordinary local times, the first imbalance price used, device counters differenced as they come.",
        html.Div(html.Table([
            html.Thead(html.Tr([html.Th(""), html.Th("First version"), html.Th("This warehouse")])),
            html.Tbody([html.Tr([html.Th(name), html.Td(f(d["first_version_sql"])), html.Td(f(d["datahub"]), **{"data-good": "true"})]) for name, f in ROWS]),
        ], className="data"), className="scroll"),
    )
