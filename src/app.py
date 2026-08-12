"""Restaurant Operations Analytics Dashboard.

Built on real, anonymised Square POS exports (see src/load_square_data.py):
15 trading days, 17-31 Jul 2026. Staffing/labour is not yet wired to real
data (Square Timecards not exported) — that tab runs on a modelled, clearly
labelled synthetic year instead, to demonstrate the analysis approach.
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import theme

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REAL_DIR = DATA_DIR / "real"
SYNTHETIC_DIR = DATA_DIR / "synthetic"

st.set_page_config(page_title="Restaurant Ops Analytics", page_icon="🍽️", layout="wide")

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_PART_ORDER = ["Breakfast", "Lunch", "Afternoon", "Dinner"]
CATEGORY_ORDER = ["Food", "Drink", "Dessert"]


@st.cache_data
def load_real_data():
    orders = pd.read_csv(REAL_DIR / "real_orders.csv", parse_dates=["date"])
    items = pd.read_csv(REAL_DIR / "real_item_sales.csv")
    return orders, items


@st.cache_data
def load_synthetic_staffing():
    staffing = pd.read_csv(SYNTHETIC_DIR / "staffing.csv", parse_dates=["date"])
    staffing["month"] = staffing["date"].dt.to_period("M").dt.to_timestamp()
    return staffing


if not (REAL_DIR / "real_orders.csv").exists():
    st.error("Real data not found. Run `python src/load_square_data.py` first (needs the raw exports in data/raw/).")
    st.stop()

orders, item_sales = load_real_data()
staffing = load_synthetic_staffing()

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
st.sidebar.title("🍽️ Restaurant Ops")
st.sidebar.caption("Restaurant Operations Analytics — real Square POS data")

min_date, max_date = orders["date"].min().date(), orders["date"].max().date()
date_range = st.sidebar.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

dow_present_all = [d for d in DOW_ORDER if d in orders["dow_name"].unique()]
dow_sel = st.sidebar.multiselect("Day of week", dow_present_all, default=dow_present_all)
part_sel = st.sidebar.multiselect("Day-part", DAY_PART_ORDER, default=DAY_PART_ORDER)

mask = (
    (orders["date"].dt.date >= start_date) & (orders["date"].dt.date <= end_date)
    & (orders["dow_name"].isin(dow_sel)) & (orders["day_part"].isin(part_sel))
)
f_orders = orders[mask].copy()

st.sidebar.divider()
st.sidebar.markdown(
    "**About this project**\n\n"
    "Built on real, anonymised Square POS exports from an independent "
    "restaurant I help run (17–31 Jul 2026 — the export window available so "
    "far; the business name is intentionally left out). Staff names, "
    "customer details, card and device info are stripped at load time and "
    "never stored in this repo — see `src/load_square_data.py`.\n\n"
    "Staffing/labour isn't wired to real data yet (no Timecards export "
    "available) — that tab uses a clearly-marked illustrative model."
)

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------
st.title("Restaurant Operations Analytics")
st.caption(
    f"{start_date:%d %b %Y} – {end_date:%d %b %Y}  ·  {len(dow_sel)} day(s) of week  ·  "
    f"{len(part_sel)} day-part(s)  ·  Source: Square POS exports"
)

total_revenue = f_orders["gross_sales"].sum()
n_transactions = len(f_orders)
avg_txn = total_revenue / n_transactions if n_transactions else 0
n_days = f_orders["date"].dt.date.nunique()
avg_daily_revenue = total_revenue / n_days if n_days else 0
total_tips = f_orders["tip"].sum()

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Revenue (gross)", f"£{total_revenue:,.0f}")
k2.metric("Transactions", f"{n_transactions:,}")
k3.metric("Avg transaction value", f"£{avg_txn:,.2f}")
k4.metric("Avg daily revenue", f"£{avg_daily_revenue:,.0f}")
k5.metric("Trading days in view", f"{n_days}")

st.caption(
    "Note: Square's export doesn't include covers/party size, so metrics here are "
    "per-transaction rather than per-cover — a real constraint of POS-only data."
)

st.divider()

tab_peak, tab_daypart, tab_menu, tab_staff, tab_data = st.tabs(
    ["⏰ Peak Trading Hours", "📅 Revenue by Day-part", "🍴 Menu Performance",
     "👥 Staffing (illustrative)", "📋 Data"]
)

# ---------------------------------------------------------------------------
# Peak Trading Hours
# ---------------------------------------------------------------------------
with tab_peak:
    st.subheader("When is the restaurant actually busy?")
    st.caption(f"Transaction count by hour and day of week — {n_days} real trading days ({start_date:%d %b} – {end_date:%d %b %Y}).")

    heat = f_orders.groupby(["dow_name", "hour"], as_index=False).size()
    dow_present = [d for d in DOW_ORDER if d in heat["dow_name"].unique()]
    pivot = heat.pivot(index="dow_name", columns="hour", values="size").reindex(dow_present)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values, x=[f"{h:02d}:00" for h in pivot.columns], y=pivot.index,
            colorscale=[[i / (len(theme.SEQUENTIAL_BLUE) - 1), c] for i, c in enumerate(theme.SEQUENTIAL_BLUE)],
            hovertemplate="%{y}, %{x}<br>%{z:.0f} transactions<extra></extra>",
            colorbar=dict(title="Txns"),
        )
    )
    fig.update_layout(**theme.PLOTLY_LAYOUT, height=340, xaxis_title="Hour", yaxis_title=None)
    st.plotly_chart(fig, width='stretch')

    c1, c2 = st.columns(2)
    with c1:
        by_hour = f_orders.groupby("hour", as_index=False).size().sort_values("hour")
        fig2 = px.bar(by_hour, x="hour", y="size", color_discrete_sequence=[theme.CAT_BLUE])
        fig2.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title="Hour", yaxis_title="Transactions")
        fig2.update_traces(hovertemplate="Hour %{x}:00<br>%{y} transactions<extra></extra>")
        st.plotly_chart(fig2, width='stretch')
        st.caption("Total transactions by hour, across the selected range.")
    with c2:
        top_tables = f_orders["table_number"].dropna().astype(str)
        top_tables = top_tables[top_tables != ""].value_counts().head(10).reset_index()
        top_tables.columns = ["table_number", "transactions"]
        fig3 = px.bar(top_tables, x="table_number", y="transactions", color_discrete_sequence=[theme.CAT_ORANGE])
        fig3.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title="Table", yaxis_title="Transactions",
                            xaxis_type="category")
        fig3.update_traces(hovertemplate="Table %{x}<br>%{y} transactions<extra></extra>")
        st.plotly_chart(fig3, width='stretch')
        st.caption("Busiest tables by transaction count (top 10).")

# ---------------------------------------------------------------------------
# Revenue by Day-part
# ---------------------------------------------------------------------------
with tab_daypart:
    st.subheader("Where does the revenue actually come from?")

    c1, c2 = st.columns([1, 1])
    with c1:
        rev_part = f_orders.groupby("day_part", as_index=False)["gross_sales"].sum().set_index("day_part").reindex(
            [p for p in DAY_PART_ORDER if p in f_orders["day_part"].unique()]
        ).reset_index()
        fig = px.pie(rev_part, names="day_part", values="gross_sales", hole=0.55,
                     color="day_part", color_discrete_map=theme.DAY_PART_COLOR)
        fig.update_traces(hovertemplate="%{label}<br>£%{value:,.0f} (%{percent})<extra></extra>", textinfo="label+percent")
        fig.update_layout(**theme.PLOTLY_LAYOUT, height=340, showlegend=False)
        st.plotly_chart(fig, width='stretch')
        st.caption("Share of gross revenue by day-part.")
    with c2:
        rev_dow_part = f_orders.groupby(["dow_name", "day_part"], as_index=False)["gross_sales"].sum()
        rev_dow_part["dow_name"] = pd.Categorical(rev_dow_part["dow_name"], categories=dow_present_all, ordered=True)
        fig2 = px.bar(rev_dow_part.sort_values("dow_name"), x="dow_name", y="gross_sales", color="day_part",
                      color_discrete_map=theme.DAY_PART_COLOR, category_orders={"day_part": DAY_PART_ORDER})
        fig2.update_layout(**theme.PLOTLY_LAYOUT, height=340, xaxis_title=None, yaxis_title="Revenue (£)", legend_title=None)
        fig2.update_traces(hovertemplate="%{x}, %{fullData.name}<br>£%{y:,.0f}<extra></extra>")
        st.plotly_chart(fig2, width='stretch')
        st.caption("Revenue by day of week, split by day-part.")

    st.markdown("##### Daily revenue trend")
    daily = f_orders.groupby("date", as_index=False)["gross_sales"].sum()
    fig3 = px.line(daily, x="date", y="gross_sales", color_discrete_sequence=[theme.CAT_BLUE], markers=True)
    fig3.update_traces(hovertemplate="%{x|%a %d %b}<br>£%{y:,.0f}<extra></extra>", line=dict(width=2))
    fig3.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title=None, yaxis_title="Revenue (£)")
    st.plotly_chart(fig3, width='stretch')
    st.caption(f"Only {n_days} days of POS data are available so far ({start_date:%d %b} – {end_date:%d %b %Y}) — too short a window to read seasonality from; more exports would extend this.")

# ---------------------------------------------------------------------------
# Menu Performance
# ---------------------------------------------------------------------------
with tab_menu:
    st.subheader("What sells — and what's actually worth selling")
    st.caption(
        "Item Sales report covers the same window as the transactions above. "
        "Margin isn't in the Square export (no COGS) — the quadrant chart uses "
        "**estimated** cost-of-sales benchmarks by category (Food 30%, Drink 22%, "
        "Dessert 24%), not actual item cost."
    )

    cat_sel = st.multiselect("Filter by category", CATEGORY_ORDER, default=CATEGORY_ORDER, key="menu_cat")
    item_f = item_sales[item_sales["category_group"].isin(cat_sel)].copy()

    c1, c2 = st.columns([1.1, 1])
    with c1:
        top15 = item_f.sort_values("units_sold", ascending=False).head(15).sort_values("units_sold")
        fig = px.bar(top15, x="units_sold", y="item_name", color="category_group", orientation="h",
                     color_discrete_map=theme.CATEGORY_COLOR, category_orders={"category_group": CATEGORY_ORDER})
        fig.update_layout(**theme.PLOTLY_LAYOUT, height=460, xaxis_title="Units sold", yaxis_title=None, legend_title=None)
        fig.update_traces(hovertemplate="%{y}<br>%{x:.0f} units<extra></extra>")
        st.plotly_chart(fig, width='stretch')
        st.caption("Top 15 items by units sold.")
    with c2:
        item_f = item_f.assign(margin_pct=item_f["est_margin"] / item_f["avg_unit_price"])
        avg_pop = item_f["units_sold"].median()
        avg_margin_pct = item_f["margin_pct"].median()
        fig2 = px.scatter(item_f, x="units_sold", y="margin_pct", color="category_group", size="revenue",
                           hover_name="item_name", color_discrete_map=theme.CATEGORY_COLOR,
                           category_orders={"category_group": CATEGORY_ORDER})
        fig2.add_vline(x=avg_pop, line_dash="dash", line_color=theme.INK_MUTED)
        fig2.add_hline(y=avg_margin_pct, line_dash="dash", line_color=theme.INK_MUTED)
        fig2.update_traces(hovertemplate="%{hovertext}<br>%{x:.0f} units, %{y:.0%} est. margin<extra></extra>")
        fig2.update_layout(**theme.PLOTLY_LAYOUT, height=460, xaxis_title="Units sold (popularity)",
                            yaxis_title="Estimated margin %", yaxis_tickformat=".0%", legend_title=None)
        st.plotly_chart(fig2, width='stretch')
        st.caption(
            "Menu engineering quadrant (estimated margin) — top-right = **Stars**, "
            "bottom-right = **Plowhorses**, top-left = **Puzzles**, bottom-left = **Dogs**."
        )

    st.markdown("##### Full item performance")
    st.dataframe(
        item_f.sort_values("revenue", ascending=False)[
            ["item_name", "raw_category", "category_group", "units_sold", "revenue", "avg_unit_price"]
        ].rename(columns={"item_name": "Item", "raw_category": "Square category", "category_group": "Group",
                           "units_sold": "Units sold", "revenue": "Revenue (£)", "avg_unit_price": "Avg price (£)"}),
        width='stretch', hide_index=True,
    )

# ---------------------------------------------------------------------------
# Staffing (illustrative)
# ---------------------------------------------------------------------------
with tab_staff:
    st.warning(
        "⚠️ **Illustrative model, not real data.** Square Timecards haven't been exported yet, "
        "so this tab runs on a synthetic full year (see `src/generate_data.py`) to demonstrate "
        "the analysis. Swap in a real Timecards export and this becomes a live chart — the "
        "logic doesn't change."
    )
    st.subheader("Does the rota track actual demand? (modelled)")
    st.caption(
        "Staff are scheduled off a trailing 4-week average for that weekday/day-part in this "
        "model — so the rota structurally lags fast ramps and drop-offs."
    )

    monthly = staffing.groupby("month", as_index=False).agg(
        covers=("covers", "sum"), labor_cost=("labor_cost", "sum"), revenue=("revenue", "sum")
    )
    monthly["labor_pct"] = monthly["labor_cost"] / monthly["revenue"]

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.5, 0.5], vertical_spacing=0.08,
                         subplot_titles=("Covers served (modelled demand)", "Labour cost as % of revenue (modelled)"))
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["covers"], mode="lines+markers",
                              line=dict(color=theme.CAT_BLUE, width=2), marker=dict(size=8),
                              hovertemplate="%{x|%b %Y}<br>%{y:.0f} covers<extra></extra>", name="Covers"), row=1, col=1)
    fig.add_trace(go.Scatter(x=monthly["month"], y=monthly["labor_pct"] * 100, mode="lines+markers",
                              line=dict(color=theme.CAT_ORANGE, width=2), marker=dict(size=8),
                              hovertemplate="%{x|%b %Y}<br>%{y:.1f}%% labour<extra></extra>", name="Labour %"), row=2, col=1)
    fig.add_hrect(y0=25, y1=32, line_width=0, fillcolor=theme.CAT_AQUA, opacity=0.10, row=2, col=1,
                  annotation_text="healthy range", annotation_position="top left", annotation_font_color=theme.INK_MUTED)
    fig.update_layout(**{k: v for k, v in theme.PLOTLY_LAYOUT.items() if k not in ("xaxis", "yaxis")},
                       height=480, showlegend=False)
    fig.update_xaxes(gridcolor=theme.GRIDLINE, linecolor=theme.BASELINE)
    fig.update_yaxes(gridcolor=theme.GRIDLINE, linecolor=theme.BASELINE)
    st.plotly_chart(fig, width='stretch')

    peak_month = monthly.loc[monthly["labor_pct"].idxmax()]
    lean_month = monthly.loc[monthly["labor_pct"].idxmin()]
    st.info(
        f"**Reading it (modelled data):** {lean_month['month']:%B %Y} runs leanest on labour "
        f"({lean_month['labor_pct']*100:.1f}%) — right as demand climbs into the festive peak, "
        f"a real understaffing risk. {peak_month['month']:%B %Y} then overshoots to "
        f"{peak_month['labor_pct']*100:.1f}% once the schedule catches up but demand has already "
        f"dropped. This is the shape a lagging trailing-average rota produces — the same check "
        f"applies once real Timecards data is connected."
    )

# ---------------------------------------------------------------------------
# Data tab
# ---------------------------------------------------------------------------
with tab_data:
    st.subheader("Underlying data")
    st.caption(
        "Real, anonymised Square POS exports — see `src/load_square_data.py` for the cleaning "
        "and anonymisation logic (staff names, customer IDs, card/device details are dropped "
        "at load time and never written here)."
    )
    d1, d2 = st.columns(2)
    with d1:
        st.markdown("**Transactions (filtered)**")
        st.dataframe(f_orders, width='stretch', hide_index=True, height=300)
    with d2:
        st.markdown("**Item sales (period total)**")
        st.dataframe(item_sales, width='stretch', hide_index=True, height=300)
    st.download_button("Download filtered transactions (CSV)", f_orders.to_csv(index=False), "transactions_filtered.csv", "text/csv")
