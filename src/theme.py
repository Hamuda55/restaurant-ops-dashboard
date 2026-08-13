"""Shared color palette (validated categorical/sequential/status roles)."""

# Fixed categorical order — never cycled, assigned by entity identity.
CAT_BLUE = "#2a78d6"
CAT_ORANGE = "#eb6834"
CAT_AQUA = "#1baf7a"
CAT_YELLOW = "#eda100"
CAT_MAGENTA = "#e87ba4"
CAT_GREEN = "#008300"
CAT_VIOLET = "#4a3aa7"
CAT_RED = "#e34948"

CATEGORICAL = [CAT_BLUE, CAT_ORANGE, CAT_AQUA, CAT_YELLOW, CAT_MAGENTA, CAT_GREEN, CAT_VIOLET, CAT_RED]

# Sequential (blue), light -> dark, for heatmaps / magnitude
SEQUENTIAL_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

# Status (fixed, never reused as a series color)
STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_SERIOUS = "#ec835a"
STATUS_CRITICAL = "#d03b3b"

# Chart chrome
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

# Fixed entity -> color maps (identity, not rank)
DAY_PART_COLOR = {"Breakfast": CAT_BLUE, "Lunch": CAT_ORANGE, "Afternoon": CAT_AQUA, "Dinner": CAT_YELLOW}
# Blue/Orange/Aqua, not Blue/Orange/Magenta: validated with the dataviz
# skill's contrast script (node scripts/validate_palette.js --pairs all).
# Orange<->Magenta measured ΔE 12.9 for normal vision — below the 15 floor,
# i.e. hard to tell apart even with full colour vision, not just CVD. Aqua
# is the documented "first three slots" combination that actually passes
# all-pairs (worst pair ΔE 24.0 normal-vision, 9.2 CVD).
CATEGORY_COLOR = {"Food": CAT_BLUE, "Drink": CAT_ORANGE, "Dessert": CAT_AQUA}

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color=INK_PRIMARY, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
    xaxis=dict(gridcolor=GRIDLINE, linecolor=BASELINE, zerolinecolor=BASELINE),
    yaxis=dict(gridcolor=GRIDLINE, linecolor=BASELINE, zerolinecolor=BASELINE),
    legend=dict(bgcolor="rgba(0,0,0,0)"),
    margin=dict(l=10, r=10, t=40, b=10),
)
