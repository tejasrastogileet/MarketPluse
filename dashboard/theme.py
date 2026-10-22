"""
Shared Plotly styling so every chart in the dashboard reads as one system
instead of each using Plotly's default rainbow template.

Palette source: the project's dataviz skill reference palette (validated for
colorblind-safe adjacent contrast). Values are the LIGHT-mode set since the
dashboard runs in Streamlit's default light theme; swap in the dark-mode
steps from the same reference if you enable Streamlit's dark theme.
"""
import plotly.graph_objects as go
import plotly.io as pio

# --- Chrome & ink ---
SURFACE = "#fcfcfb"
PAGE_PLANE = "#f9f9f7"
TEXT_PRIMARY = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
TEXT_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"

# --- Categorical (fixed order - never cycle the assignment within one chart) ---
CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#1baf7a",  # 2 aqua
    "#eda100",  # 3 yellow
    "#008300",  # 4 green
    "#4a3aa7",  # 5 violet
    "#e34948",  # 6 red
    "#e87ba4",  # 7 magenta
    "#eb6834",  # 8 orange
]

# --- Sequential (single hue, light -> dark; magnitude only) ---
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#5598e7", "#2a78d6", "#1c5cab", "#0d366b"]

# --- Status (state, never reused as a categorical series color) ---
STATUS = {
    "good": "#0ca30c",     # LOW risk
    "warning": "#fab219",  # MEDIUM risk
    "critical": "#d03b3b", # HIGH risk
}

# Fixed sector -> categorical slot mapping (8 sectors, 8 slots - by design,
# so "Technology" is always the same color regardless of which tickers a
# user has filtered to; color follows the entity, not chart-local rank).
SECTOR_COLOR = {
    "Technology": CATEGORICAL[0],
    "Consumer Discretionary": CATEGORICAL[1],
    "Financials": CATEGORICAL[2],
    "Consumer Staples": CATEGORICAL[3],
    "Energy": CATEGORICAL[4],
    "Healthcare": CATEGORICAL[5],
    "Industrials": CATEGORICAL[6],
    "Communication Services": CATEGORICAL[7],
}

RISK_TIER_COLOR = {
    "LOW": STATUS["good"],
    "MEDIUM": STATUS["warning"],
    "HIGH": STATUS["critical"],
}


def build_template() -> go.layout.Template:
    template = go.layout.Template()
    template.layout = go.Layout(
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family="system-ui, -apple-system, 'Segoe UI', sans-serif", color=TEXT_PRIMARY, size=13),
        colorway=CATEGORICAL,
        xaxis=dict(gridcolor=GRIDLINE, linecolor=BASELINE, zerolinecolor=BASELINE, tickfont=dict(color=TEXT_MUTED)),
        yaxis=dict(gridcolor=GRIDLINE, linecolor=BASELINE, zerolinecolor=BASELINE, tickfont=dict(color=TEXT_MUTED)),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_SECONDARY)),
        margin=dict(l=40, r=20, t=40, b=40),
    )
    return template


def apply_theme() -> None:
    pio.templates["market_data_platform"] = build_template()
    pio.templates.default = "market_data_platform"
