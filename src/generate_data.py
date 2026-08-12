"""
Synthetic staffing/demand model for a restaurant (kept unnamed throughout
this project).

Used only by the dashboard's "Staffing (illustrative)" tab, since there's no
real Timecards export yet (see src/load_square_data.py for the real data,
which drives every other tab). Produces a full year of realistic but
fabricated restaurant transaction, staffing, and menu data. No real business
figures are used anywhere in this script — day-of-week trading shape,
seasonality, menu composition, and the staffing-lag dynamic are modelled
from general UK independent-restaurant operating patterns.

Run:
    python src/generate_data.py
Outputs (in ../data/synthetic/):
    menu_items.csv
    orders.csv
    order_items.csv
    staffing.csv
    daily_summary.csv
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "synthetic"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
START_DATE = dt.date(2025, 8, 12)
END_DATE = dt.date(2026, 8, 11)  # full year, ending "yesterday"
ALL_DATES = pd.date_range(START_DATE, END_DATE, freq="D")

CLOSED_WEEKDAY = 0  # Monday closed (common independent-restaurant pattern)

FIXED_CLOSURES = {dt.date(2025, 12, 25), dt.date(2025, 12, 26), dt.date(2026, 1, 1)}

SPECIAL_EVENTS = {
    dt.date(2025, 12, 24): ("Christmas Eve", 1.35, 1.15),
    dt.date(2025, 12, 31): ("New Year's Eve", 1.9, 1.35),
    dt.date(2026, 2, 14): ("Valentine's Day", 1.5, 1.25),
    dt.date(2026, 3, 15): ("Mother's Day", 1.6, 1.10),
    dt.date(2026, 4, 5): ("Easter Sunday", 1.3, 1.10),
    dt.date(2026, 6, 21): ("Father's Day", 1.35, 1.05),
}

MONTH_MULTIPLIER = {
    1: 0.72, 2: 0.85, 3: 0.92, 4: 0.97, 5: 1.00, 6: 1.07,
    7: 1.12, 8: 1.05, 9: 1.00, 10: 1.00, 11: 0.97, 12: 1.22,
}

# Day-of-week multiplier: Mon=0 ... Sun=6 (Monday unused, restaurant closed)
DOW_MULTIPLIER = {0: 0.0, 1: 0.72, 2: 0.80, 3: 0.90, 4: 1.20, 5: 1.35, 6: 1.10}

DAY_PARTS = {
    # name: (start_hour, end_hour(exclusive, fractional ok), which weekdays open, base capacity/hr)
    "Lunch": (12.0, 15.0, {1, 2, 3, 4, 5, 6}, 9.0),
    "Dinner": (17.5, 22.0, {1, 2, 3, 4, 5, 6}, 13.0),
    "Late": (22.0, 23.5, {4, 5}, 5.0),
}

SEATS = 68

# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
# Mediterranean/grill-leaning brasserie menu — flavoured by ingredients seen
# in the user's real supplier lists (lamb, ox cheek, whole fish, octopus,
# Greek dairy) but with fabricated names, prices and popularity.
MENU = [
    # category, name, price, food_cost_pct, popularity_weight
    ("Starter", "Whipped Feta & Hot Honey", 8.5, 0.26, 9),
    ("Starter", "Grilled Octopus, Salsa Verde", 12.5, 0.34, 8),
    ("Starter", "King Prawn Saganaki", 11.0, 0.36, 7),
    ("Starter", "Ox Cheek Croquettes", 9.5, 0.28, 6),
    ("Starter", "Burrata, Heritage Tomato", 10.5, 0.32, 6),
    ("Starter", "Soupe de Poisson, Rouille", 8.0, 0.24, 3),
    ("Starter", "Charred Flatbread, Tzatziki", 6.5, 0.20, 5),
    ("Main", "Lamb Chops, Salsa Verde", 24.0, 0.34, 10),
    ("Main", "Slow-Cooked Ox Cheek, Celeriac", 22.0, 0.30, 9),
    ("Main", "Cote de Boeuf (for two)", 62.0, 0.36, 4),
    ("Main", "Whole Grilled Sea Bass", 26.0, 0.38, 8),
    ("Main", "Pan-Seared Dover Sole", 29.0, 0.40, 4),
    ("Main", "Corn-Fed Chicken Supreme", 19.5, 0.30, 9),
    ("Main", "Grilled Squid Linguine", 18.0, 0.28, 6),
    ("Main", "Wild Mushroom Risotto (v)", 16.5, 0.24, 5),
    ("Main", "Brasserie Moussaka", 17.5, 0.27, 5),
    ("Main", "Signature Burger, Aged Cheddar", 16.0, 0.30, 8),
    ("Side", "Triple-Cooked Chips", 5.5, 0.22, 10),
    ("Side", "Greek Salad", 5.5, 0.24, 6),
    ("Side", "Charred Tenderstem Broccoli", 5.5, 0.26, 5),
    ("Side", "Sauteed Spinach, Garlic", 5.0, 0.24, 3),
    ("Dessert", "Baklava Cheesecake", 8.5, 0.22, 9),
    ("Dessert", "Dark Chocolate Fondant", 9.0, 0.24, 8),
    ("Dessert", "Citrus Olive Oil Cake", 7.5, 0.20, 5),
    ("Dessert", "Affogato", 6.5, 0.18, 4),
    ("Drink", "House Red / White (glass)", 8.0, 0.24, 10),
    ("Drink", "Negroni", 11.0, 0.20, 6),
    ("Drink", "Aperol Spritz", 10.5, 0.20, 7),
    ("Drink", "Craft Beer", 6.5, 0.26, 7),
    ("Drink", "Espresso Martini", 11.5, 0.20, 5),
    ("Drink", "Soft Drink / Juice", 3.5, 0.30, 6),
    ("Drink", "Coffee", 3.5, 0.28, 8),
]

menu_df = pd.DataFrame(MENU, columns=["category", "item_name", "price", "food_cost_pct", "popularity_weight"])
menu_df.insert(0, "item_id", [f"M{i:03d}" for i in range(1, len(menu_df) + 1)])
menu_df["cost"] = (menu_df["price"] * menu_df["food_cost_pct"]).round(2)
menu_df["margin"] = (menu_df["price"] - menu_df["cost"]).round(2)
menu_df.drop(columns=["food_cost_pct"], inplace=True)

CATEGORY_ATTACH_RATE = {
    "Starter": 0.55, "Main": 0.97, "Side": 0.45, "Dessert": 0.35, "Drink": 1.30,
}

# ---------------------------------------------------------------------------
# Build the trading calendar (date x day_part rows)
# ---------------------------------------------------------------------------
calendar_rows = []
for d in ALL_DATES:
    date = d.date()
    dow = d.dayofweek  # Mon=0
    if dow == CLOSED_WEEKDAY or date in FIXED_CLOSURES:
        continue
    for part, (start_h, end_h, open_days, base_cap) in DAY_PARTS.items():
        if dow not in open_days:
            continue
        event_name, cover_mult, spend_mult = SPECIAL_EVENTS.get(date, (None, 1.0, 1.0))
        calendar_rows.append({
            "date": date, "dow": dow, "day_part": part,
            "start_hour": start_h, "end_hour": end_h,
            "base_capacity_per_hr": base_cap,
            "event_name": event_name, "event_cover_mult": cover_mult, "event_spend_mult": spend_mult,
        })

cal = pd.DataFrame(calendar_rows)
cal["month"] = pd.to_datetime(cal["date"]).dt.month
cal["dow_mult"] = cal["dow"].map(DOW_MULTIPLIER)
cal["month_mult"] = cal["month"].map(MONTH_MULTIPLIER)

hours_open = cal["end_hour"] - cal["start_hour"]
expected_covers = (
    cal["base_capacity_per_hr"] * hours_open * cal["dow_mult"] * cal["month_mult"] * cal["event_cover_mult"]
)
noise = RNG.normal(1.0, 0.10, size=len(cal))
cal["covers"] = np.clip((expected_covers * noise).round().astype(int), 0, SEATS * 2)

# ---------------------------------------------------------------------------
# Staffing: scheduled a week ahead off a trailing 4-occurrence average for
# the same (dow, day_part) — deliberately laggy, so it under-reacts to fast
# ramps (e.g. the Nov -> Dec build-up) and over-reacts once demand cools.
# Known calendar events get a manual bump because managers plan for those.
# ---------------------------------------------------------------------------
cal = cal.sort_values(["dow", "day_part", "date"]).reset_index(drop=True)
cal["trailing_avg_covers"] = (
    cal.groupby(["dow", "day_part"])["covers"]
    .transform(lambda s: s.shift(1).rolling(4, min_periods=1).mean())
)
cal["trailing_avg_covers"] = cal["trailing_avg_covers"].fillna(cal["covers"])

COVERS_PER_FOH = 10.0
COVERS_PER_BOH = 13.0
MIN_FOH, MIN_BOH = 2, 2

planned_covers = cal["trailing_avg_covers"] * np.where(cal["event_name"].notna(), cal["event_cover_mult"], 1.0)
cal["staff_foh"] = np.maximum(MIN_FOH, np.ceil(planned_covers / COVERS_PER_FOH)).astype(int)
cal["staff_boh"] = np.maximum(MIN_BOH, np.ceil(planned_covers / COVERS_PER_BOH)).astype(int)

# Rates are "fully loaded" (wage + employer NI/pension on-costs), as a
# manager budgeting labour would actually use.
RATE_FOH, RATE_BOH = 14.50, 17.50
cal["labor_cost"] = (cal["staff_foh"] * RATE_FOH * hours_open + cal["staff_boh"] * RATE_BOH * hours_open).round(2)

cal = cal.sort_values(["date", "day_part"]).reset_index(drop=True)

# ---------------------------------------------------------------------------
# Explode covers into orders (tables) and order_items (line items)
# ---------------------------------------------------------------------------
order_rows = []
item_rows = []
order_id = 1

items_by_cat = {c: menu_df[menu_df.category == c] for c in CATEGORY_ATTACH_RATE}

for _, row in cal.iterrows():
    covers_remaining = row["covers"]
    if covers_remaining <= 0:
        continue
    start_h, end_h = row["start_hour"], row["end_hour"]
    while covers_remaining > 0:
        party_size = int(min(covers_remaining, RNG.choice([1, 2, 3, 4, 5, 6], p=[0.10, 0.46, 0.14, 0.16, 0.10, 0.04])))
        covers_remaining -= party_size
        order_time_frac = RNG.uniform(start_h, max(start_h + 0.05, end_h - 0.25))
        hour = int(order_time_frac)
        minute = int((order_time_frac - hour) * 60)
        service_type = RNG.choice(["Dine-in", "Takeaway"], p=[0.86, 0.14])

        order_total = 0.0
        for cat, attach_rate in CATEGORY_ATTACH_RATE.items():
            n_lines = RNG.poisson(attach_rate * party_size)
            if n_lines <= 0:
                continue
            pool = items_by_cat[cat]
            weights = pool["popularity_weight"].to_numpy(dtype=float)
            weights = weights / weights.sum()
            chosen = RNG.choice(pool["item_id"].to_numpy(), size=n_lines, p=weights)
            for item_id, qty in pd.Series(chosen).value_counts().items():
                item = pool[pool.item_id == item_id].iloc[0]
                line_total = round(float(item["price"]) * int(qty) * row["event_spend_mult"], 2)
                order_total += line_total
                item_rows.append({
                    "order_id": order_id, "item_id": item_id, "item_name": item["item_name"],
                    "category": cat, "quantity": int(qty), "unit_price": item["price"], "line_total": line_total,
                })

        order_rows.append({
            "order_id": order_id, "date": row["date"], "day_part": row["day_part"],
            "hour": hour, "time": f"{hour:02d}:{minute:02d}", "party_size": party_size,
            "service_type": service_type, "event_name": row["event_name"], "revenue": round(order_total, 2),
        })
        order_id += 1

orders_df = pd.DataFrame(order_rows)
order_items_df = pd.DataFrame(item_rows)

# ---------------------------------------------------------------------------
# Staffing / daily summary outputs
# ---------------------------------------------------------------------------
shift_revenue = orders_df.groupby(["date", "day_part"], as_index=False)["revenue"].sum()
staffing_df = cal.merge(shift_revenue, on=["date", "day_part"], how="left")
staffing_df["revenue"] = staffing_df["revenue"].fillna(0.0)
staffing_df["labor_pct"] = (staffing_df["labor_cost"] / staffing_df["revenue"].replace(0, np.nan)).round(3)
staffing_df["covers_per_foh"] = (staffing_df["covers"] / staffing_df["staff_foh"]).round(2)
staffing_df = staffing_df[[
    "date", "dow", "day_part", "event_name", "covers", "staff_foh", "staff_boh",
    "labor_cost", "revenue", "labor_pct", "covers_per_foh",
]]

orders_df["date"] = pd.to_datetime(orders_df["date"])
orders_df["dow_name"] = orders_df["date"].dt.day_name()
orders_df["month"] = orders_df["date"].dt.to_period("M").astype(str)

daily_summary = (
    orders_df.groupby(["date", "dow_name"], as_index=False)
    .agg(covers=("party_size", "sum"), revenue=("revenue", "sum"), orders=("order_id", "count"))
)
daily_summary["avg_spend_per_cover"] = (daily_summary["revenue"] / daily_summary["covers"]).round(2)

# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------
menu_df.to_csv(DATA_DIR / "menu_items.csv", index=False)
orders_df.drop(columns=["dow_name", "month"]).to_csv(DATA_DIR / "orders.csv", index=False)
order_items_df.to_csv(DATA_DIR / "order_items.csv", index=False)
staffing_df.to_csv(DATA_DIR / "staffing.csv", index=False)
daily_summary.to_csv(DATA_DIR / "daily_summary.csv", index=False)

print(f"menu_items:   {len(menu_df):>7,} rows")
print(f"orders:       {len(orders_df):>7,} rows")
print(f"order_items:  {len(order_items_df):>7,} rows")
print(f"staffing:     {len(staffing_df):>7,} rows")
print(f"daily_summary:{len(daily_summary):>7,} rows")
print(f"Total revenue: £{orders_df['revenue'].sum():,.0f} over {daily_summary.shape[0]} trading days")
