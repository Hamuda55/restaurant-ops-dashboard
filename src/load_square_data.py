"""
Load and clean real Square POS exports for a real restaurant (kept unnamed
throughout this project — see the redaction step below).

Reads raw exports from data/raw/ (Square exports as UTF-16, tab-delimited
CSV) and writes anonymised, analysis-ready CSVs to data/real/.

PII handling: Square's transaction export includes staff names/IDs, customer
names/IDs, card brand + PAN suffix, device names, and transaction/payment/
deposit IDs. None of that is needed for operations analytics, and this
project may end up published (GitHub, a deployed dashboard link on a CV) —
so those columns are dropped here, at load time, and never written to
data/real/. Only data/raw/ (gitignored, local-only) holds the original
export.

Business-name redaction: a handful of menu items/categories are named after
the restaurant itself (e.g. a signature dish sharing its name). Those are
rewritten to a generic "Signature" at load time so the restaurant's real
name never appears in data/real/, data/bi_export/, or the dashboard.

Run:
    python src/load_square_data.py
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ITEM_SUMMARY_FILE = RAW_DIR / "item-sales-summary-2026-07-01-2026-07-31.csv"
TRANSACTIONS_FILE = RAW_DIR / "transactions-2026-07-01-2026-08-01.csv"

# The restaurant's real name, as it appears in a few menu item/category
# names in the raw export — redacted on the way out. Update this if the
# raw export's naming changes.
_BUSINESS_NAME_RE = re.compile(r"de\s*rada", re.IGNORECASE)


def redact_business_name(text: str) -> str:
    return _BUSINESS_NAME_RE.sub("Signature", str(text)).strip()

# Raw Square category -> high-level group, for consistent chart coloring.
CATEGORY_GROUP = {
    "Hot Drinks": "Drink", "Soft Drinks": "Drink", "White Wines": "Drink",
    "Red Wines": "Drink", "Rosé Wines": "Drink", "Water": "Drink",
    "Cocktails": "Drink", "Kids Drinks": "Drink", "Beers & Ciders": "Drink",
    "Gin & Tonic": "Drink", "Aperitifs": "Drink", "Juices": "Drink",
    "Smoothies": "Drink", "Champagne / Sparkling": "Drink",
    "Liqueur Coffee": "Drink", "Rum": "Drink", "Spirit": "Drink",
    "Spirits": "Drink", "Vodka": "Drink", "Whiskey": "Drink",
    "Hand-Crafted": "Drink",
    "Desserts": "Dessert", "Gelato & Sorbet": "Dessert", "Kids Dessert": "Dessert",
    "Starters": "Food", "Pasta": "Food", "Sides": "Food", "Secondi": "Food",
    "Burford Browns Eggs": "Food", "Signature Breakfast": "Food", "Pizza": "Food",
    "Kids Mains": "Food", "Lunch Pasta": "Food", "Lunch Sandwiches": "Food",
    "Toast and Sandwiches": "Food", "Breakfast Menu": "Food", "Salads": "Food",
    "Kids Breakfast": "Food", "Nibbles": "Food", "Risotto": "Food",
    "Starters to Share": "Food", "Breakfast Extra": "Food", "Breakfast Sweets": "Food",
    "Uncategorised": "Food",
}

# Square doesn't export COGS, so there's no real margin figure. These are
# typical UK hospitality cost-of-sales benchmarks by group (food ~28-32%,
# drink ~20-30% depending on category) used only to give the menu-engineering
# chart a plausible margin axis — clearly labelled as estimated wherever shown.
ESTIMATED_COST_PCT = {"Food": 0.30, "Drink": 0.22, "Dessert": 0.24}


def money(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("£", "", regex=False)
        .str.replace(",", "", regex=False)
        .replace("", "0")
        .astype(float)
    )


def load_item_sales() -> pd.DataFrame:
    df = pd.read_csv(ITEM_SUMMARY_FILE, encoding="utf-16", sep="\t")
    for col in ["Product Sales", "Refunds", "Discounts & Comps", "Net Sales", "Tax", "Gross Sales"]:
        df[col] = money(df[col])
    df["Items Sold"] = pd.to_numeric(df["Items Sold"], errors="coerce").fillna(0)
    df = df[df["Item Name"] != "Custom Amount"].copy()  # not a real menu item
    df["Item Name"] = df["Item Name"].map(redact_business_name)
    df["Category"] = df["Category"].map(redact_business_name)
    df["category_group"] = df["Category"].map(CATEGORY_GROUP).fillna("Food")
    df["avg_unit_price"] = (df["Product Sales"] / df["Items Sold"]).replace([np.inf, -np.inf], np.nan)
    df["est_cost_pct"] = df["category_group"].map(ESTIMATED_COST_PCT)
    df["est_margin"] = df["avg_unit_price"] * (1 - df["est_cost_pct"])
    out = df.rename(columns={
        "Item Name": "item_name", "Item Variation": "variation", "Category": "raw_category",
        "Items Sold": "units_sold", "Product Sales": "revenue", "Net Sales": "net_sales",
        "Gross Sales": "gross_sales",
    })[[
        "item_name", "variation", "raw_category", "category_group", "units_sold",
        "revenue", "net_sales", "gross_sales", "avg_unit_price", "est_cost_pct", "est_margin",
    ]]
    return out


DAY_PART_BINS = [
    (8, 11, "Breakfast"), (11, 15, "Lunch"), (15, 17, "Afternoon"), (17, 23, "Dinner"),
]


def hour_to_day_part(hour: int) -> str:
    for start, end, name in DAY_PART_BINS:
        if start <= hour < end:
            return name
    return "Other"


def load_transactions() -> pd.DataFrame:
    df = pd.read_csv(TRANSACTIONS_FILE, encoding="utf-16", sep="\t")
    df = df[(df["Transaction Status"] == "Complete") & (df["Event Type"] == "Payment")].copy()

    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
    df["date"] = pd.to_datetime(df["Date"])
    df["hour"] = df["datetime"].dt.hour
    df["dow_name"] = df["datetime"].dt.day_name()
    df["day_part"] = df["hour"].apply(hour_to_day_part)

    for col in ["Gross Sales", "Net Sales", "Tax", "Tip", "Discounts", "Service Charges"]:
        df[col] = money(df[col])

    df = df.sort_values("datetime").reset_index(drop=True)
    df["order_id"] = df.index + 1  # anonymous sequential ID, replaces Transaction ID

    out = df.rename(columns={
        "Gross Sales": "gross_sales", "Net Sales": "net_sales", "Tax": "tax", "Tip": "tip",
        "Table info": "table_number", "Source": "source", "Time": "time",
    })[[
        "order_id", "date", "time", "hour", "dow_name", "day_part",
        "gross_sales", "net_sales", "tax", "tip", "table_number", "source",
    ]]
    return out


if __name__ == "__main__":
    item_sales = load_item_sales()
    orders = load_transactions()

    item_sales.to_csv(OUT_DIR / "real_item_sales.csv", index=False)
    orders.to_csv(OUT_DIR / "real_orders.csv", index=False)

    print(f"real_item_sales: {len(item_sales):,} rows  (£{item_sales['revenue'].sum():,.0f} product sales)")
    print(f"real_orders:     {len(orders):,} rows  (£{orders['gross_sales'].sum():,.0f} gross sales)")
    print(f"date range: {orders['date'].min().date()} to {orders['date'].max().date()}  ({orders['date'].dt.date.nunique()} trading days)")
    print(f"Wrote anonymised outputs to {OUT_DIR}")
