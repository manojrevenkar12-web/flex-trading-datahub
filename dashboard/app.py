"""The trading desk's dashboard: run with `python -m dashboard.app` (FTD_DUCKDB=<warehouse> to read live marts)."""
from __future__ import annotations

import os

from dash import Dash, Input, Output, State, ctx, dcc, html, no_update

from dashboard import data as data_mod
from dashboard.components import empty_state, error_state, skeleton
from dashboard.features import attribution, comparison, day, quality
from dashboard.theme import css_variables


def body(source: str | None = None) -> tuple[list, str | None]:
    """The page's sections, or the reason they could not be built."""
    try:
        d = data_mod.load(source)
    except Exception as e:  # noqa: BLE001  (any failure to read becomes the error state, with its reason)
        return [], f"{type(e).__name__}: {e}. Check that FTD_DUCKDB points at the warehouse or that reports/marts exists."
    if not d.days:
        return [empty_state()], None
    return [day.view(d, d.days[-1]), attribution.view(d), quality.view(d), comparison.view(d)], None


def create_app(source: str | None = None) -> Dash:
    app = Dash(__name__, title="Flex trading data", assets_folder=os.path.join(os.path.dirname(__file__), "assets"), suppress_callback_exceptions=True)
    app.index_string = app.index_string.replace("{%css%}", "{%css%}<style>" + css_variables() + "</style>")
    app.layout = html.Main([
        html.Header([html.Strong("Flex trading data"), html.Span("Portfolio, positions, imbalance and data quality for a dynamic-tariff supplier's trading desk")], className="header"),
        dcc.Interval(id="loader", interval=1, max_intervals=1),
        html.Div(skeleton(6), id="body"),
        error_state(),
        html.Footer("Households, devices, prices and trades are simulated; the warehouse is built with dbt on DuckDB from the same "
                    "raw feeds a supplier receives.", className="footer"),
    ], className="page")

    @app.callback(Output("body", "children"), Output("error", "hidden"), Output("error-message", "children"),
                  Input("loader", "n_intervals"), Input("retry", "n_clicks"))
    def fill(_, __):
        children, problem = body(source)
        return children, problem is None, problem or ""

    @app.callback(Output("day", "value"), Input("prev-day", "n_clicks"), Input("next-day", "n_clicks"), State("day", "value"), State("day", "options"), prevent_initial_call=True)
    def step(_, __, current, options):
        days = [o["value"] for o in options]
        i = days.index(current) + (-1 if ctx.triggered_id == "prev-day" else 1)
        return days[max(0, min(len(days) - 1, i))]

    @app.callback(Output("day-chart", "figure"), Output("day-side", "children"), Input("day", "value"), prevent_initial_call=True)
    def show_day(value):
        d = data_mod.load(source)
        if value not in d.days:
            return no_update, no_update
        return day.figure(d, value), day.side(d, value)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", 8050)), debug=False)
