"""The delivery day: what the portfolio drew each quarter hour against what the desk had bought, the imbalance left
between them, and the price it was settled at."""
from __future__ import annotations

import plotly.graph_objects as go
from dash import dcc, html

from dashboard.components import flag, stat
from dashboard.data import Data
from dashboard.theme import COLOURS, LAYOUT, eur, figure_layout


def figure(data: Data, day: str) -> go.Figure:
    d = data.portfolio[data.portfolio["delivery_day"] == day].sort_values("qh_start_utc")
    t = d["qh_start_utc"]
    pos = (d["da_mw"] + d["id_mw"]) / 4 * 1000
    net = d["net_mwh"] * 1000
    imb = d["imbalance_mwh"] * 1000
    fig = go.Figure()
    fig.add_bar(x=t, y=imb, name="Imbalance (kWh)", marker_color=[COLOURS["short"] if v > 0 else COLOURS["long"] for v in imb], opacity=0.55)
    fig.add_scatter(x=t, y=pos, name="Bought, day-ahead and intraday (kWh)", mode="lines", line={"shape": "hv", "color": COLOURS["position"], "width": 2})
    fig.add_scatter(x=t, y=net, name="Metered net load (kWh)", mode="lines", line={"color": COLOURS["metered"], "width": 2})
    fig.add_scatter(x=t, y=d["rebap_eur_mwh"], name="Imbalance price (€/MWh)", yaxis="y2", mode="lines",
                    line={"color": COLOURS["price"], "width": 1, "dash": "dot"})
    lay = figure_layout(LAYOUT["chart_height"])
    lay["yaxis2"] = {"overlaying": "y", "side": "right", "showgrid": False, "title": {"text": "€/MWh"}, "tickformat": ".0f", "nticks": 6}
    lay["yaxis"]["title"] = {"text": "kWh per quarter hour"}
    lay["bargap"] = 0.1
    fig.update_layout(**lay)
    return fig


def side(data: Data, day: str) -> list:
    p = data.pnl[data.pnl["delivery_day"] == day].iloc[0]
    q = data.quality[data.quality["delivery_day"] == day].iloc[0]
    flags = [
        flag(f"{int(q['quarter_hours'])} quarter hours", bad=not bool(q["calendar_ok"])),
        flag("final imbalance prices" if bool(p["settled_on_final_prices"]) else "preliminary prices", bad=not bool(p["settled_on_final_prices"])),
        flag(f"meters {q['min_meter_coverage'] * 100:.0f}% complete", bad=q["min_meter_coverage"] < 0.98),
    ]
    if q["stuck_meters"]:
        flags.append(flag(f"{int(q['stuck_meters'])} stuck registers estimated", bad=True))
    if q["counter_resets"]:
        flags.append(flag(f"{int(q['counter_resets'])} device counters restarted"))
    return [
        stat(eur(p["procurement_cost_eur"]), "procurement cost: day-ahead, intraday and imbalance"),
        stat(eur(p["imbalance_cost_eur"], 2), f"imbalance cost on {p['abs_imbalance_mwh'] * 1000:,.0f} kWh off position"),
        stat(f"{p['net_mwh']:,.2f} MWh", "metered net load"),
        html.Div(flags),
    ]


def view(data: Data, day: str) -> html.Section:
    return html.Section([
        html.H1("What the portfolio drew, what the desk bought, and what the gap cost.", className="title"),
        html.P(f"{len(data.days)} delivery days in Europe/Berlin, quarter hour by quarter hour. Bars are the imbalance the transmission "
               "operator settles: rust when the portfolio was short, blue when it was long. Pick a day; the night summer time ends "
               "has 100 quarter hours.", className="lede"),
        html.Div([
            html.Button("Previous day", id="prev-day", n_clicks=0),
            dcc.Dropdown(id="day", options=[{"label": x, "value": x} for x in data.days], value=day, clearable=False, className="day-picker"),
            html.Button("Next day", id="next-day", n_clicks=0),
        ], className="controls"),
        html.Div([
            dcc.Loading(dcc.Graph(id="day-chart", figure=figure(data, day), config={"displayModeBar": False}), type="dot", color=COLOURS["ink_soft"]),
            html.Aside(side(data, day), id="day-side", className="side", **{"aria-live": "polite"}),
        ], className="split"),
    ], className="hero")
