"""Restaurant Operations Analytics Dashboard.

Two data sources, selected in the sidebar:
- Demo restaurant: this project's own real, anonymised Square POS export
  (see src/load_square_data.py). No real Timecards export exists for the
  demo yet, so the Staffing tab runs on a modelled, clearly labelled
  synthetic year instead, to demonstrate the analysis approach.
- Upload your own: a visitor's own Square exports (Item Sales,
  Transactions, and/or Timecards), parsed in-session via square_parser.py
  (same PII-stripping logic as the demo data — employee names/IDs are
  never read into the output). A real Timecards upload drives a real
  Staffing tab, not the synthetic model.
"""

import datetime as dt
import io
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import theme
from square_parser import (
    SquareFileError,
    clean_item_sales,
    clean_timecards,
    clean_transactions,
    read_square_csv,
)

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


@st.cache_data(show_spinner="Parsing uploaded files…")
def load_uploaded_data(item_bytes, item_name, txn_bytes, txn_name, labour_bytes, labour_name):
    """Cache key is the raw bytes + filename, so re-running with the same
    upload doesn't re-parse, but a new file does."""
    items = clean_item_sales(read_square_csv(io.BytesIO(item_bytes))) if item_bytes else None
    orders = clean_transactions(read_square_csv(io.BytesIO(txn_bytes))) if txn_bytes else None
    labour = clean_timecards(read_square_csv(io.BytesIO(labour_bytes))) if labour_bytes else None
    return orders, items, labour


if not (REAL_DIR / "real_orders.csv").exists():
    st.error("Demo data not found. Run `python src/load_square_data.py` first (needs the raw exports in data/raw/).")
    st.stop()

# ---------------------------------------------------------------------------
# Data source: bundled demo restaurant, or a visitor's own Square export
# ---------------------------------------------------------------------------
st.sidebar.title("🍽️ Restaurant Ops")

data_source = st.sidebar.radio(
    "Data source", ["Demo restaurant", "Upload your own"], key="data_source",
    help="Analyse this project's real (anonymised) demo data, or upload your own restaurant's Square exports."
)

orders = item_sales = labour = None
staffing = None
upload_error = None

if data_source == "Demo restaurant":
    st.sidebar.caption("Real Square POS data · anonymised")
    orders, item_sales = load_real_data()
    staffing = load_synthetic_staffing()
else:
    st.sidebar.caption("Your Square POS data · processed in this session only, never saved")
    with st.sidebar.expander("📤 Upload your Square exports", expanded=True):
        with st.expander("❓ Where do I get these files?"):
            st.markdown(
                "From **[squareup.com/dashboard](https://squareup.com/dashboard)** on desktop "
                "(exporting works better there than the mobile app):\n\n"
                "**Item Sales export** — unlocks the Menu Performance tab\n"
                "1. Go to **Reports → Sales**\n"
                "2. Filter the breakdown by **Item**\n"
                "3. Set the date range to as much history as you have (a full year "
                "if possible, to capture seasonality)\n"
                "4. Click **Export** → CSV\n\n"
                "**Transactions export** — unlocks Peak Trading Hours and Revenue by Day-part\n"
                "1. Go to the **Transactions** tab\n"
                "2. Set the same date range\n"
                "3. Click **Export** → CSV\n\n"
                "**Timecards export** — unlocks a real (not modelled) Staffing tab\n"
                "1. Go to **Team → Timecards** (or **Reports → Labor**, naming varies by account)\n"
                "2. Set the same date range\n"
                "3. Click **Export** → CSV\n\n"
                "All three are optional but complementary — upload whichever you have; "
                "more history gives more reliable patterns than a short window. Labour "
                "cost as a % of revenue needs both Timecards and Transactions uploaded."
            )
        item_file = st.file_uploader("Item Sales export (CSV)", type=["csv"], key="item_upload")
        txn_file = st.file_uploader("Transactions export (CSV)", type=["csv"], key="txn_upload")
        labour_file = st.file_uploader("Timecards / Labour export (CSV)", type=["csv"], key="labour_upload")

    if item_file or txn_file or labour_file:
        try:
            orders, item_sales, labour = load_uploaded_data(
                item_file.getvalue() if item_file else None, item_file.name if item_file else None,
                txn_file.getvalue() if txn_file else None, txn_file.name if txn_file else None,
                labour_file.getvalue() if labour_file else None, labour_file.name if labour_file else None,
            )
        except SquareFileError as e:
            upload_error = str(e)

    if upload_error:
        st.error(f"Couldn't process that upload: {upload_error}")
        st.stop()
    if orders is None and item_sales is None and labour is None:
        st.info(
            "⬆️ Upload at least one Square export in the sidebar to get started — an Item Sales "
            "export unlocks Menu Performance, a Transactions export unlocks Peak Trading Hours "
            "and Revenue by Day-part, and a Timecards export unlocks a real Staffing tab. "
            "Nothing you upload is saved or sent anywhere outside this browser session."
        )
        st.stop()

has_orders = orders is not None and not orders.empty
has_items = item_sales is not None and not item_sales.empty
has_labour = labour is not None and not labour.empty

# ---------------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------------
if has_orders:
    min_date, max_date = orders["date"].min().date(), orders["date"].max().date()
else:
    min_date = max_date = dt.date.today()

preset = st.sidebar.segmented_control(
    "Quick range", ["All data", "Last 7 days", "Custom"], default="All data", width="stretch",
    disabled=not has_orders,
)
if preset == "Last 7 days":
    preset_start = max(min_date, max_date - dt.timedelta(days=6))
else:
    preset_start = min_date

date_range = st.sidebar.date_input(
    "Date range", value=(preset_start, max_date), min_value=min_date, max_value=max_date,
    key=f"date_input_{preset}", disabled=not has_orders,
)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
else:
    start_date, end_date = min_date, max_date

dow_present_all = [d for d in DOW_ORDER if d in orders["dow_name"].unique()] if has_orders else []
dow_sel = st.sidebar.pills("Day of week", dow_present_all, selection_mode="multi",
                            default=dow_present_all, width="stretch", disabled=not has_orders)
part_sel = st.sidebar.pills("Day-part", DAY_PART_ORDER, selection_mode="multi",
                             default=DAY_PART_ORDER, width="stretch", disabled=not has_orders)
dow_sel = dow_sel or []
part_sel = part_sel or []

if has_orders:
    mask = (
        (orders["date"].dt.date >= start_date) & (orders["date"].dt.date <= end_date)
        & (orders["dow_name"].isin(dow_sel)) & (orders["day_part"].isin(part_sel))
    )
    f_orders = orders[mask].copy()
else:
    f_orders = pd.DataFrame(columns=["order_id", "date", "time", "hour", "dow_name", "day_part",
                                      "gross_sales", "net_sales", "tax", "tip", "table_number", "source"])
    f_orders["date"] = pd.to_datetime(f_orders["date"])

if has_labour:
    labour_mask = (labour["date"].dt.date >= start_date) & (labour["date"].dt.date <= end_date) \
        & (labour["dow_name"].isin(dow_sel))
    f_labour = labour[labour_mask].copy()
else:
    f_labour = pd.DataFrame(columns=["shift_id", "date", "dow_name", "day_part", "job", "hours", "labor_cost"])

st.sidebar.divider()
if data_source == "Demo restaurant":
    with st.sidebar.expander("ℹ️ About this project"):
        st.markdown(
            "Built on real, anonymised Square POS exports from an independent "
            "restaurant I help run (17–31 Jul 2026 — the export window available "
            "so far; the business name is intentionally left out). Staff names, "
            "customer details, card and device info are stripped at load time "
            "and never stored in this repo — see `src/load_square_data.py`.\n\n"
            "Staffing/labour isn't wired to real data yet (no Timecards export "
            "available) — that tab uses a clearly-marked illustrative model.\n\n"
            "Want to try this on your own restaurant's data? Switch **Data source** "
            "above to \"Upload your own\"."
        )
else:
    with st.sidebar.expander("ℹ️ About your data"):
        st.markdown(
            "Uploaded files are parsed in memory for this browser session only — "
            "nothing is written to disk or shared with anyone else using this app. "
            "Staff/employee names, customer details, card and device info are "
            "stripped at parse time, before anything is charted — including from "
            "a Timecards upload, where employee identity is dropped entirely and "
            "shifts are only ever shown in aggregate. See `src/square_parser.py`.\n\n"
            "Refreshing the page or closing this tab clears the upload; there's "
            "nothing to delete afterwards."
        )

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------
st.title("Restaurant Operations Analytics")

if has_orders:
    st.caption(
        f"{start_date:%d %b %Y} – {end_date:%d %b %Y}  ·  {len(dow_sel)} day(s) of week  ·  "
        f"{len(part_sel)} day-part(s)  ·  Source: Square POS exports"
    )

    total_revenue = f_orders["gross_sales"].sum()
    n_transactions = len(f_orders)
    avg_txn = total_revenue / n_transactions if n_transactions else 0
    n_days = f_orders["date"].dt.date.nunique()
    avg_daily_revenue = total_revenue / n_days if n_days else 0

    daily_kpi = f_orders.groupby(f_orders["date"].dt.date, as_index=False).agg(
        revenue=("gross_sales", "sum"), txns=("order_id", "count")
    ).sort_values("date")
    daily_kpi["avg_txn"] = (daily_kpi["revenue"] / daily_kpi["txns"]).replace([np.inf, -np.inf], np.nan)
    spark = len(daily_kpi) > 1  # a one-point sparkline isn't a trend

    k1, k2, k3 = st.columns(3)
    k1.metric("Revenue", f"£{total_revenue:,.0f}", icon="💷", border=True,
              help="Gross revenue across the selected filters",
              chart_data=daily_kpi["revenue"] if spark else None, chart_type="area")
    k2.metric("Transactions", f"{n_transactions:,}", icon="🧾", border=True,
              help="Completed POS transactions in range",
              chart_data=daily_kpi["txns"] if spark else None, chart_type="area")
    k3.metric("Avg txn value", f"£{avg_txn:,.2f}", icon="💳", border=True,
              help="Gross revenue ÷ transaction count. Square's export doesn't include "
                   "covers/party size, so this is per-transaction rather than per-cover — "
                   "a real constraint of POS-only data.",
              chart_data=daily_kpi["avg_txn"] if spark else None, chart_type="area")

    k4, k5 = st.columns(2)
    k4.metric("Avg daily revenue", f"£{avg_daily_revenue:,.0f}", icon="📈", border=True,
              help="Total revenue ÷ trading days in view")
    k5.metric("Trading days", f"{n_days}", icon="📅", border=True,
              help="Distinct calendar days with at least one transaction, in the current filter")
else:
    n_days = 0
    st.caption("No Transactions export uploaded yet — showing whichever tabs your other uploads unlock.")

st.divider()

staff_tab_label = "👥 Staffing (illustrative)" if data_source == "Demo restaurant" else "👥 Staffing"
tab_labels = ["⏰ Peak Trading Hours", "📅 Revenue by Day-part", "🍴 Menu Performance", staff_tab_label, "📋 Data"]
_tabs = st.tabs(tab_labels)
tab_peak, tab_daypart, tab_menu, tab_staff, tab_data = _tabs

# ---------------------------------------------------------------------------
# Peak Trading Hours
# ---------------------------------------------------------------------------
with tab_peak:
    st.subheader("When is the restaurant actually busy?", divider=True)

    if not has_orders:
        st.info("⬆️ Upload a Transactions export in the sidebar to see this.")
    else:
        st.caption(f"Transactions by hour, one panel per day of week — {n_days} trading days ({start_date:%d %b} – {end_date:%d %b %Y}).")

        heat = f_orders.groupby(["dow_name", "hour"], as_index=False).size()
        dow_present = [d for d in DOW_ORDER if d in heat["dow_name"].unique()]
        heat["dow_name"] = pd.Categorical(heat["dow_name"], categories=dow_present, ordered=True)
        heat = heat.sort_values(["dow_name", "hour"])

        fig = px.bar(heat, x="hour", y="size", facet_col="dow_name", facet_col_wrap=4,
                     color_discrete_sequence=[theme.CAT_BLUE], category_orders={"dow_name": dow_present})
        fig.update_layout(**theme.PLOTLY_LAYOUT, height=420, showlegend=False)
        fig.update_traces(hovertemplate="Hour %{x}:00<br>%{y} transactions<extra></extra>")
        fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1], font=dict(size=13)))
        fig.update_xaxes(title=None, dtick=4)
        fig.update_yaxes(title=None, matches="y")
        fig.add_annotation(text="Transactions", xref="paper", yref="paper", x=-0.06, y=0.5,
                            showarrow=False, textangle=-90, font=dict(color=theme.INK_MUTED, size=12))
        st.plotly_chart(fig, width='stretch')

        if len(heat) and heat["size"].mean() > 0:
            busiest = heat.loc[heat["size"].idxmax()]
            multiple = busiest["size"] / heat["size"].mean()
            st.info(
                f"**Reading it:** Your busiest slot is **{busiest['dow_name']} at {int(busiest['hour']):02d}:00**, "
                f"with {int(busiest['size'])} transactions — {multiple:.1f}x an average hour."
            )

        focus_dow = st.pills("Focus on a day", ["All days"] + dow_present, selection_mode="single",
                              default="All days", key="peak_focus_dow")
        focus_orders = f_orders if not focus_dow or focus_dow == "All days" else f_orders[f_orders["dow_name"] == focus_dow]

        if focus_dow and focus_dow != "All days":
            n_focus = len(focus_orders)
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric(f"{focus_dow} transactions", f"{n_focus:,}", border=True)
            fc2.metric(f"{focus_dow} revenue", f"£{focus_orders['gross_sales'].sum():,.0f}", border=True)
            fc3.metric(f"{focus_dow} avg txn value",
                       f"£{(focus_orders['gross_sales'].sum() / n_focus if n_focus else 0):,.2f}", border=True)

        c1, c2 = st.columns(2)
        with c1:
            by_hour = focus_orders.groupby("hour", as_index=False).size().sort_values("hour")
            fig2 = px.bar(by_hour, x="hour", y="size", color_discrete_sequence=[theme.CAT_BLUE])
            fig2.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title="Hour", yaxis_title="Transactions")
            fig2.update_traces(hovertemplate="Hour %{x}:00<br>%{y} transactions<extra></extra>")
            st.plotly_chart(fig2, width='stretch')
            st.caption(f"Total transactions by hour{'' if focus_dow in (None, 'All days') else f' — {focus_dow} only'}.")
        with c2:
            top_tables = focus_orders["table_number"].dropna().astype(str)
            top_tables = top_tables[top_tables != ""].value_counts().head(10).reset_index()
            top_tables.columns = ["table_number", "transactions"]
            if top_tables.empty:
                st.info("No table numbers in this export.")
            else:
                fig3 = px.bar(top_tables, x="table_number", y="transactions", color_discrete_sequence=[theme.CAT_ORANGE])
                fig3.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title="Table", yaxis_title="Transactions",
                                    xaxis_type="category")
                fig3.update_traces(hovertemplate="Table %{x}<br>%{y} transactions<extra></extra>")
                st.plotly_chart(fig3, width='stretch')
                st.caption(f"Busiest tables by transaction count (top 10){'' if focus_dow in (None, 'All days') else f' — {focus_dow} only'}.")

# ---------------------------------------------------------------------------
# Revenue by Day-part
# ---------------------------------------------------------------------------
with tab_daypart:
    st.subheader("Where does the revenue actually come from?", divider=True)

    if not has_orders:
        st.info("⬆️ Upload a Transactions export in the sidebar to see this.")
    else:
        part_present = [p for p in DAY_PART_ORDER if p in f_orders["day_part"].unique()]
        focus_part = st.pills("Focus on a day-part", ["All day-parts"] + part_present, selection_mode="single",
                               default="All day-parts", key="daypart_focus")
        part_orders = f_orders if not focus_part or focus_part == "All day-parts" else f_orders[f_orders["day_part"] == focus_part]

        if focus_part and focus_part != "All day-parts":
            total_rev = f_orders["gross_sales"].sum()
            part_rev = part_orders["gross_sales"].sum()
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric(f"{focus_part} revenue", f"£{part_rev:,.0f}", border=True)
            fc2.metric("Share of total", f"{(part_rev / total_rev if total_rev else 0):.1%}", border=True)
            fc3.metric(f"{focus_part} transactions", f"{len(part_orders):,}", border=True)

        c1, c2 = st.columns([1, 1])
        with c1:
            rev_part = f_orders.groupby("day_part", as_index=False)["gross_sales"].sum().set_index("day_part").reindex(
                part_present
            ).reset_index()
            fig = px.pie(rev_part, names="day_part", values="gross_sales", hole=0.55,
                         color="day_part", color_discrete_map=theme.DAY_PART_COLOR)
            fig.update_traces(hovertemplate="%{label}<br>£%{value:,.0f} (%{percent})<extra></extra>", textinfo="label+percent",
                               pull=[0.06 if p == focus_part else 0 for p in rev_part["day_part"]])
            fig.update_layout(**theme.PLOTLY_LAYOUT, height=340, showlegend=False)
            st.plotly_chart(fig, width='stretch')
            st.caption("Share of gross revenue by day-part (always shows all day-parts for context).")
        with c2:
            rev_dow_part = part_orders.groupby(["dow_name", "day_part"], as_index=False)["gross_sales"].sum()
            rev_dow_part["dow_name"] = pd.Categorical(rev_dow_part["dow_name"], categories=dow_present_all, ordered=True)
            fig2 = px.bar(rev_dow_part.sort_values("dow_name"), x="dow_name", y="gross_sales", color="day_part",
                          color_discrete_map=theme.DAY_PART_COLOR, category_orders={"day_part": DAY_PART_ORDER})
            fig2.update_layout(**theme.PLOTLY_LAYOUT, height=340, xaxis_title=None, yaxis_title="Revenue (£)", legend_title=None)
            fig2.update_traces(hovertemplate="%{x}, %{fullData.name}<br>£%{y:,.0f}<extra></extra>")
            st.plotly_chart(fig2, width='stretch')
            st.caption(f"Revenue by day of week{'' if focus_part in (None, 'All day-parts') else f' — {focus_part} only'}.")

        if len(rev_part) and rev_part["gross_sales"].sum() > 0:
            top_part = rev_part.loc[rev_part["gross_sales"].idxmax()]
            top_part_share = top_part["gross_sales"] / rev_part["gross_sales"].sum()
            by_day_total = f_orders.groupby("date")["gross_sales"].sum()
            best_day = by_day_total.idxmax()
            st.info(
                f"**Reading it:** **{top_part['day_part']}** brings in {top_part_share:.0%} of revenue — the "
                f"largest share. Your best single day was **{best_day:%a %d %b}** at £{by_day_total.max():,.0f}."
            )

        st.subheader(
            "Daily revenue trend", divider=True,
            help=f"Only {n_days} days of POS data are available so far ({start_date:%d %b} – "
                 f"{end_date:%d %b %Y}) — too short a window to read seasonality from. More "
                 "Square exports would extend this directly."
        )
        daily = part_orders.groupby("date", as_index=False)["gross_sales"].sum()
        fig3 = px.line(daily, x="date", y="gross_sales", color_discrete_sequence=[theme.CAT_BLUE], markers=True)
        fig3.update_traces(hovertemplate="%{x|%a %d %b}<br>£%{y:,.0f}<extra></extra>", line=dict(width=2))
        fig3.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title=None, yaxis_title="Revenue (£)")
        st.plotly_chart(fig3, width='stretch')
        if focus_part and focus_part != "All day-parts":
            st.caption(f"Revenue from {focus_part} only, by day.")

# ---------------------------------------------------------------------------
# Menu Performance
# ---------------------------------------------------------------------------
with tab_menu:
    st.subheader(
        "What sells — and what's actually worth selling", divider=True,
        help="Item Sales report covers the same window as the transactions above. Margin "
             "isn't in the Square export (no COGS) — the quadrant chart uses **estimated** "
             "cost-of-sales benchmarks by category (Food 30%, Drink 22%, Dessert 24%), not "
             "actual item cost."
    )

    if not has_items:
        st.info("⬆️ Upload an Item Sales export in the sidebar to see this.")
    else:
        with st.expander("⚙️ Adjust estimated cost-of-sales assumptions"):
            st.caption("Square doesn't export COGS — drag these to stress-test how sensitive the quadrant below is to the assumption.")
            sc1, sc2, sc3 = st.columns(3)
            food_cost_pct = sc1.slider("Food cost %", 15, 45, 30)
            drink_cost_pct = sc2.slider("Drink cost %", 10, 40, 22)
            dessert_cost_pct = sc3.slider("Dessert cost %", 10, 40, 24)
        cost_map = {"Food": food_cost_pct / 100, "Drink": drink_cost_pct / 100, "Dessert": dessert_cost_pct / 100}

        cat_sel = st.pills("Filter by category", CATEGORY_ORDER, selection_mode="multi",
                            default=CATEGORY_ORDER, key="menu_cat") or []
        item_f = item_sales[item_sales["category_group"].isin(cat_sel)].copy()
        # Square exports one row per item+variation (e.g. "Cappuccino / Regular" and
        # "Cappuccino / Large") but every chart/table/lookup below keys on item_name
        # alone — collapse variations into one row per name so "Cappuccino" means one
        # thing everywhere, instead of silently picking whichever variation sorts first.
        item_f = item_f.groupby("item_name", as_index=False).agg(
            raw_category=("raw_category", "first"), category_group=("category_group", "first"),
            units_sold=("units_sold", "sum"), revenue=("revenue", "sum"),
        )
        item_f["avg_unit_price"] = (item_f["revenue"] / item_f["units_sold"]).replace([np.inf, -np.inf], np.nan)
        item_f["margin_pct"] = 1 - item_f["category_group"].map(cost_map)

        c1, c2 = st.columns([1.1, 1])
        with c1:
            sort_mode = st.segmented_control("Show", ["Best sellers", "Worst sellers"],
                                              default="Best sellers", key="menu_sort_mode")
            worst = sort_mode == "Worst sellers"
            ranked15 = item_f.sort_values("units_sold", ascending=worst).head(15).sort_values("units_sold")
            fig = px.bar(ranked15, x="units_sold", y="item_name", orientation="h",
                         color=None if worst else "category_group",
                         color_discrete_sequence=[theme.CAT_RED] if worst else None,
                         color_discrete_map=None if worst else theme.CATEGORY_COLOR,
                         category_orders={"category_group": CATEGORY_ORDER})
            fig.update_layout(**theme.PLOTLY_LAYOUT, height=400, xaxis_title="Units sold", yaxis_title=None, legend_title=None)
            fig.update_traces(hovertemplate="%{y}<br>%{x:.0f} units<extra></extra>")
            st.plotly_chart(fig, width='stretch')
            st.caption(
                "Bottom 15 items by units sold — candidates to reconsider or discontinue."
                if worst else "Top 15 items by units sold."
            )

            lookup_options = ["—"] + sorted(item_f["item_name"].unique().tolist())
            selected_item = st.selectbox("🔍 Look up an item", lookup_options, key="item_lookup")
            if selected_item != "—":
                row = item_f[item_f["item_name"] == selected_item].iloc[0]
                ranked = item_f.sort_values("revenue", ascending=False).reset_index(drop=True)
                rank = int(ranked.index[ranked["item_name"] == selected_item][0]) + 1
                d1, d2 = st.columns(2)
                d1.metric("Units sold", f"{row['units_sold']:.0f}", border=True)
                d2.metric("Revenue", f"£{row['revenue']:,.0f}", border=True, help=f"Rank #{rank} by revenue in the current filter")
                d3, d4 = st.columns(2)
                d3.metric("Avg price", f"£{row['avg_unit_price']:,.2f}", border=True)
                d4.metric("Margin", f"{row['margin_pct']:.0%}", border=True, icon="⚙️",
                          help="Estimated — uses the adjustable cost-of-sales assumption above")
        with c2:
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

        if len(item_f):
            top_item = item_f.sort_values("units_sold", ascending=False).iloc[0]
            top_item_share = top_item["units_sold"] / item_f["units_sold"].sum() if item_f["units_sold"].sum() else 0
            n_dogs = len(item_f[(item_f["units_sold"] < avg_pop) & (item_f["margin_pct"] < avg_margin_pct)])
            dogs_msg = (
                f"{n_dogs} item(s) sit in the low-popularity, low-margin \"Dogs\" quadrant — worth a second look."
                if n_dogs else "No items currently sit in the low-popularity, low-margin \"Dogs\" quadrant."
            )
            st.info(
                f"**Reading it:** **{top_item['item_name']}** is your best seller — "
                f"{int(top_item['units_sold'])} units, {top_item_share:.0%} of everything sold in this filter. "
                f"{dogs_msg}"
            )

        st.subheader("Full item performance", divider=True)
        st.caption("Click a row for a detail card.")
        perf_display = item_f.sort_values("revenue", ascending=False)[
            ["item_name", "raw_category", "category_group", "units_sold", "revenue", "avg_unit_price"]
        ].rename(columns={"item_name": "Item", "raw_category": "Square category", "category_group": "Group",
                           "units_sold": "Units sold", "revenue": "Revenue (£)", "avg_unit_price": "Avg price (£)"})
        table_event = st.dataframe(
            perf_display, width='stretch', hide_index=True,
            on_select="rerun", selection_mode="single-row", key="item_perf_table",
        )
        selected_rows = table_event["selection"]["rows"] if table_event else []
        if selected_rows:
            clicked_name = perf_display.iloc[selected_rows[0]]["Item"]
            row = item_f[item_f["item_name"] == clicked_name].iloc[0]
            st.markdown(f"**{clicked_name}**")
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Units sold", f"{row['units_sold']:.0f}", border=True)
            e2.metric("Revenue", f"£{row['revenue']:,.0f}", border=True)
            e3.metric("Avg price", f"£{row['avg_unit_price']:,.2f}", border=True)
            e4.metric("Margin", f"{row['margin_pct']:.0%}", border=True, icon="⚙️",
                      help="Estimated — uses the adjustable cost-of-sales assumption above")

# ---------------------------------------------------------------------------
# Staffing — synthetic model for the demo dataset, real analysis when a
# Timecards file has been uploaded
# ---------------------------------------------------------------------------
def _render_synthetic_staffing_tab():
    st.warning(
        "⚠️ **Illustrative model, not real data.** Square Timecards haven't been exported yet, "
        "so this tab runs on a synthetic full year (see `src/generate_data.py`) to demonstrate "
        "the analysis. Swap in a real Timecards export and this becomes a live chart — the "
        "logic doesn't change."
    )
    st.subheader("Does the rota track actual demand? (modelled)", divider=True)
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


def _render_real_staffing_tab(f_labour, f_orders, has_orders):
    has_cost = f_labour["labor_cost"].notna().any()
    total_hours = f_labour["hours"].sum()
    n_shifts = len(f_labour)
    avg_hours = total_hours / n_shifts if n_shifts else 0

    k1, k2, k3 = st.columns(3)
    k1.metric("Total hours", f"{total_hours:,.1f}", icon="⏱️", border=True)
    k2.metric("Shifts", f"{n_shifts:,}", icon="🧑‍🍳", border=True,
              help="One row per clocked shift in the Timecards export")
    k3.metric("Avg hours / shift", f"{avg_hours:,.1f}", icon="📏", border=True)

    if has_cost:
        total_cost = f_labour["labor_cost"].sum()
        k4, k5 = st.columns(2)
        k4.metric("Total labour cost", f"£{total_cost:,.0f}", icon="💷", border=True)
        if has_orders and f_orders["gross_sales"].sum() > 0:
            pct = total_cost / f_orders["gross_sales"].sum()
            k5.metric("Labour cost (% of revenue)", f"{pct:.1%}", icon="📊", border=True,
                      help="Total labour cost ÷ total revenue across the current filters")
        else:
            k5.metric("Labour cost (% of revenue)", "—", icon="📊", border=True,
                      help="Upload a Transactions export too, to compute this")
    else:
        st.caption(
            "No hourly rate or total pay column found in your Timecards export — "
            "showing hours only, not £ cost."
        )

    st.subheader("When is labour scheduled?", divider=True)
    c1, c2 = st.columns(2)
    with c1:
        by_part = f_labour.groupby("day_part", as_index=False)["hours"].sum()
        part_order_present = [p for p in DAY_PART_ORDER + ["Unknown"] if p in by_part["day_part"].unique()]
        by_part = by_part.set_index("day_part").reindex(part_order_present).reset_index()
        color_map = {**theme.DAY_PART_COLOR, "Unknown": theme.INK_MUTED}
        fig = px.bar(by_part, x="day_part", y="hours", color="day_part", color_discrete_map=color_map)
        fig.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title=None, yaxis_title="Hours", showlegend=False)
        fig.update_traces(hovertemplate="%{x}<br>%{y:.1f} hours<extra></extra>")
        st.plotly_chart(fig, width='stretch')
        st.caption(
            "Total scheduled hours by day-part."
            + (" (\"Unknown\" = no clock-in time in the export.)" if "Unknown" in part_order_present else "")
        )
    with c2:
        by_dow = f_labour.groupby("dow_name", as_index=False)["hours"].sum()
        dow_order_present = [d for d in DOW_ORDER if d in by_dow["dow_name"].unique()]
        by_dow["dow_name"] = pd.Categorical(by_dow["dow_name"], categories=dow_order_present, ordered=True)
        fig2 = px.bar(by_dow.sort_values("dow_name"), x="dow_name", y="hours", color_discrete_sequence=[theme.CAT_VIOLET])
        fig2.update_layout(**theme.PLOTLY_LAYOUT, height=320, xaxis_title=None, yaxis_title="Hours")
        fig2.update_traces(hovertemplate="%{x}<br>%{y:.1f} hours<extra></extra>")
        st.plotly_chart(fig2, width='stretch')
        st.caption("Total scheduled hours by day of week.")

    if (f_labour["job"] != "Unspecified").any():
        st.subheader("Hours by role", divider=True)
        by_job = f_labour.groupby("job", as_index=False)["hours"].sum().sort_values("hours", ascending=False)
        fig3 = px.bar(by_job, x="hours", y="job", orientation="h", color_discrete_sequence=[theme.CAT_BLUE])
        fig3.update_layout(**theme.PLOTLY_LAYOUT, height=max(240, 40 * len(by_job)),
                            xaxis_title="Hours", yaxis_title=None)
        fig3.update_traces(hovertemplate="%{y}<br>%{x:.1f} hours<extra></extra>")
        st.plotly_chart(fig3, width='stretch')

    if not has_orders:
        st.info("⬆️ Upload a Transactions export too, to see labour cost as a % of revenue over time.")
    elif not has_cost:
        st.info("No pay/rate column in this Timecards export, so labour cost can't be compared to revenue.")
    else:
        st.subheader(
            "Labour cost vs revenue, by day", divider=True,
            help="Two panels sharing a date axis rather than one dual-axis chart — revenue and labour "
                 "% of revenue are on different scales, so overlaying them on a single axis would distort one of them."
        )
        daily_labour = f_labour.groupby("date", as_index=False)["labor_cost"].sum()
        daily_rev = f_orders.groupby("date", as_index=False)["gross_sales"].sum()
        merged = daily_rev.merge(daily_labour, on="date", how="outer").fillna(0).sort_values("date")
        merged["labor_pct"] = (merged["labor_cost"] / merged["gross_sales"]).replace([np.inf, -np.inf], np.nan)

        fig4 = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.5, 0.5], vertical_spacing=0.1,
                              subplot_titles=("Revenue", "Labour cost as % of revenue"))
        fig4.add_trace(go.Scatter(x=merged["date"], y=merged["gross_sales"], mode="lines+markers",
                                   line=dict(color=theme.CAT_BLUE, width=2),
                                   hovertemplate="%{x|%d %b}<br>£%{y:,.0f}<extra></extra>"), row=1, col=1)
        fig4.add_trace(go.Scatter(x=merged["date"], y=merged["labor_pct"] * 100, mode="lines+markers",
                                   line=dict(color=theme.CAT_ORANGE, width=2),
                                   hovertemplate="%{x|%d %b}<br>%{y:.1f}%% labour<extra></extra>"), row=2, col=1)
        fig4.add_hrect(y0=25, y1=32, line_width=0, fillcolor=theme.CAT_AQUA, opacity=0.10, row=2, col=1,
                       annotation_text="healthy range", annotation_position="top left", annotation_font_color=theme.INK_MUTED)
        fig4.update_layout(**{k: v for k, v in theme.PLOTLY_LAYOUT.items() if k not in ("xaxis", "yaxis")},
                            height=460, showlegend=False)
        fig4.update_xaxes(gridcolor=theme.GRIDLINE, linecolor=theme.BASELINE)
        fig4.update_yaxes(gridcolor=theme.GRIDLINE, linecolor=theme.BASELINE)
        st.plotly_chart(fig4, width='stretch')


with tab_staff:
    if data_source == "Demo restaurant":
        _render_synthetic_staffing_tab()
    elif has_labour:
        _render_real_staffing_tab(f_labour, f_orders, has_orders)
    else:
        st.info("⬆️ Upload a Timecards export in the sidebar to see this.")

# ---------------------------------------------------------------------------
# Data tab
# ---------------------------------------------------------------------------
with tab_data:
    st.subheader(
        "Underlying data", divider=True,
        help="Cleaned, anonymised Square POS data — see `src/square_parser.py` for the "
             "cleaning and anonymisation logic (staff names, customer IDs, card/device "
             "details are dropped at parse time and never shown here)."
    )
    d1, d2, d3 = st.columns(3)
    with d1:
        st.markdown("**Transactions (filtered)**")
        if has_orders:
            st.dataframe(f_orders, width='stretch', hide_index=True, height=300)
            st.download_button("Download filtered transactions (CSV)", f_orders.to_csv(index=False),
                                "transactions_filtered.csv", "text/csv")
        else:
            st.info("No Transactions export uploaded.")
    with d2:
        st.markdown("**Item sales (period total)**")
        if has_items:
            st.dataframe(item_sales, width='stretch', hide_index=True, height=300)
        else:
            st.info("No Item Sales export uploaded.")
    with d3:
        st.markdown("**Shifts (filtered)**")
        if has_labour:
            st.dataframe(f_labour, width='stretch', hide_index=True, height=300)
            st.download_button("Download filtered shifts (CSV)", f_labour.to_csv(index=False),
                                "shifts_filtered.csv", "text/csv")
        else:
            st.info("No Timecards export uploaded.")
