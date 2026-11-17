"""Small pieces every section uses: sections, stats, flags, and the loading, error and empty states."""
from __future__ import annotations

from dash import html


def section(title: str, lede: str, *children, id_: str | None = None) -> html.Section:
    return html.Section([html.H2(title), html.P(lede, className="lede"), *children], className="section", id=id_ or "")


def stat(value: str, words: str) -> html.P:
    return html.P([html.B(value), html.Span(words)], className="stat")


def flag(text: str, bad: bool = False) -> html.Span:
    return html.Span(text, className="flag", **{"data-bad": "true" if bad else "false"})


def skeleton(rows: int = 4) -> html.Div:
    return html.Div([html.Div(className="bone") for _ in range(rows)], className="skeleton", **{"aria-busy": "true", "aria-label": "Loading"})


def error_state() -> html.Div:
    """Always in the layout and hidden until a load fails, so its button can always trigger a reload."""
    return html.Div([
        html.P("The trading data did not load.", className="state-title"),
        html.P(id="error-message"),
        html.Button("Load again", id="retry", n_clicks=0),
    ], id="error", className="state", role="alert", hidden=True)


def empty_state() -> html.Div:
    return html.Div([
        html.P("No delivery days yet.", className="state-title"),
        html.P("Run python -m ftd.eval.cli evaluate, or the Airflow DAG, and reload."),
    ], className="state")
