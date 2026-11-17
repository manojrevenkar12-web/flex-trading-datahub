"""Every colour, size and duration the dashboard uses. Components and charts read these, never literals.
The palette is a control room's: ink for what was metered, green for what was bought, rust when the portfolio was
short and blue when it was long, ochre for the imbalance price."""
from __future__ import annotations

COLOURS = {
    "paper": "#eef2f1",
    "paper_raised": "#f9fbfa",
    "ink": "#13201d",
    "ink_soft": "#586663",
    "rule": "#cdd6d3",
    "focus": "#2f6f9f",
    "metered": "#13201d",
    "position": "#3c7a6b",
    "short": "#c4572e",
    "long": "#3f6fb0",
    "price": "#9a7a1c",
    "good": "#3c7a6b",
    "bad": "#c4572e",
}
CLASS_COLOURS = {
    "base": "#7d8a87", "heat_pump": "#c4572e", "ev": "#3f6fb0", "pv": "#d9a21b", "battery": "#6b4fa0",
    "intraday": "#3c7a6b", "rounding": "#cdd6d3",
}
CLASS_WORDS = {
    "base": "Household base load", "heat_pump": "Heat pumps", "ev": "EV charging", "pv": "Solar", "battery": "Home batteries",
    "intraday": "Intraday trades", "rounding": "Lot rounding",
}
TYPE = {
    "display": "'Lora', Georgia, serif",
    "body": "Inter, 'Liberation Sans', system-ui, sans-serif",
    "xs": "0.75rem", "sm": "0.875rem", "md": "1rem", "lg": "1.375rem", "xl": "2rem", "hero": "clamp(2rem, 4.2vw, 3.25rem)",
    "leading": "1.5", "leading_tight": "1.08",
}
SPACE = {"1": "0.25rem", "2": "0.5rem", "3": "0.75rem", "4": "1rem", "6": "1.5rem", "8": "2rem", "12": "3rem", "16": "4rem"}
LAYOUT = {"page": "78rem", "measure": "66ch", "side": "18rem", "radius": "4px", "chart_height": 380, "bars_height": 320}
MOTION = {"fade": "200ms"}


def css_variables() -> str:
    """The tokens as CSS custom properties, so the stylesheet and the charts share one source."""
    lines = [f"--{k.replace('_', '-')}: {v};" for k, v in COLOURS.items()]
    lines += [f"--font-{k}: {v};" for k, v in TYPE.items() if k in ("display", "body")]
    lines += [f"--text-{k}: {v};" for k, v in TYPE.items() if k not in ("display", "body", "leading", "leading_tight")]
    lines += [f"--leading: {TYPE['leading']};", f"--leading-tight: {TYPE['leading_tight']};"]
    lines += [f"--space-{k}: {v};" for k, v in SPACE.items()]
    lines += [f"--page: {LAYOUT['page']};", f"--measure: {LAYOUT['measure']};", f"--side: {LAYOUT['side']};", f"--radius: {LAYOUT['radius']};"]
    lines += [f"--fade: {MOTION['fade']};"]
    return ":root {" + "".join(lines) + "}"


def figure_layout(height: int) -> dict:
    return {
        "height": height, "margin": {"l": 48, "r": 16, "t": 8, "b": 36},
        "paper_bgcolor": COLOURS["paper_raised"], "plot_bgcolor": COLOURS["paper_raised"],
        "font": {"family": TYPE["body"], "color": COLOURS["ink_soft"], "size": 12},
        "xaxis": {"gridcolor": COLOURS["rule"], "zeroline": False}, "yaxis": {"gridcolor": COLOURS["rule"], "zerolinecolor": COLOURS["rule"]},
        "legend": {"orientation": "h", "y": -0.15, "x": 0}, "hovermode": "x unified",
    }


def eur(x: float, decimals: int = 0) -> str:
    """Euros with the sign in front of the symbol: -€14.94, not €-14.94."""
    return f"{'-' if x < 0 else ''}€{abs(x):,.{decimals}f}"
