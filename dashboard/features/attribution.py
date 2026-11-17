"""Where each day's imbalance cost came from: the desk's forecast error by device class, the intraday trades that
closed part of the gap, and lot rounding. The parts add up to the imbalance cost exactly."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc

from dashboard.components import section
from dashboard.data import Data
from dashboard.theme import CLASS_COLOURS, CLASS_WORDS, COLOURS, LAYOUT, eur, figure_layout

PARTS = ["base", "heat_pump", "ev", "pv", "battery", "intraday", "rounding"]


def figure(data: Data) -> go.Figure:
    p = data.pnl.sort_values("delivery_day")
    fig = go.Figure()
    for k in PARTS:
        fig.add_bar(x=p["delivery_day"], y=p[f"attr_{k}_eur"], name=CLASS_WORDS[k], marker_color=CLASS_COLOURS[k])
    fig.add_scatter(x=p["delivery_day"], y=p["imbalance_cost_eur"], name="Imbalance cost", mode="markers",
                    marker={"color": COLOURS["ink"], "size": 7, "symbol": "line-ew-open", "line": {"width": 3}})
    lay = figure_layout(LAYOUT["bars_height"])
    lay["barmode"] = "relative"
    lay["yaxis"]["title"] = {"text": "€ per delivery day"}
    fig.update_layout(**lay)
    return fig


def view(data: Data):
    total = data.pnl[[f"attr_{k}_eur" for k in PARTS]].sum()
    worst = max(PARTS[:5], key=lambda k: abs(total[f"attr_{k}_eur"]))
    return section(
        "Where the imbalance cost came from",
        f"Each bar splits a day's imbalance cost by cause. Over the run the largest driver was {CLASS_WORDS[worst].lower()} "
        f"({eur(total[f'attr_{worst}_eur'])}). Positive costs money, negative earned it back.",
        dcc.Graph(figure=figure(data), config={"displayModeBar": False}),
    )
