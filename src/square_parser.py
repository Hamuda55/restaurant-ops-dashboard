"""
Shared parsing/cleaning logic for Square POS exports.

Used by both src/load_square_data.py (the bundled demo dataset, read from
disk) and src/app.py (user-uploaded files, read from memory) — so the same
column validation, PII stripping, and category logic applies everywhere,
regardless of source.

Square's exports vary a bit by account/region: most are UTF-16 tab-delimited
(what this project's own exports look like), but UTF-8 comma-delimited
exports exist too. read_square_csv() sniffs both rather than assuming.
"""

from __future__ import annotations

import io
from typing import BinaryIO

import numpy as np
import pandas as pd

# --- Reading -----------------------------------------------------------


class SquareFileError(ValueError):
    """Raised when an uploaded/loaded file doesn't look like a Square export."""


def _decode(raw: bytes) -> str:
    """Decode CSV bytes to text. UTF-16 (what this project's own Square
    exports use) always carries a BOM, so check for that explicitly rather
    than guessing — blindly trying `.decode("utf-16")` on arbitrary bytes
    rarely raises an error, it just silently produces garbage, so encoding
    order matters here and can't be a plain try-each-in-turn loop."""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("utf-16")  # no BOM, but maybe still UTF-16
    except UnicodeDecodeError:
        return raw.decode("latin-1")  # always succeeds — last resort


def read_square_csv(file_obj_or_path) -> pd.DataFrame:
    """Read a Square CSV export, sniffing encoding (UTF-16 or UTF-8) and
    delimiter (tab or comma). Accepts a path, an open binary file, or a
    Streamlit UploadedFile."""
    if hasattr(file_obj_or_path, "read"):
        raw = file_obj_or_path.read()
        if hasattr(file_obj_or_path, "seek"):
            file_obj_or_path.seek(0)
    else:
        with open(file_obj_or_path, "rb") as f:
            raw = f.read()

    if not raw.strip():
        raise SquareFileError("This file is empty.")

    text = _decode(raw)
    first_line = text.splitlines()[0] if text.splitlines() else ""
    sep = "\t" if first_line.count("\t") > first_line.count(",") else ","

    try:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception as e:
        raise SquareFileError(f"Couldn't parse this as a CSV: {e}") from e

    if df.shape[1] <= 1:
        raise SquareFileError(
            "This file only parsed as a single column — is it really a CSV export from Square? "
            "(tab and comma delimiters were both tried)"
        )
    return df


def require_columns(df: pd.DataFrame, required: list[str], file_kind: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SquareFileError(
            f"This doesn't look like a Square {file_kind} export — missing column(s): "
            f"{', '.join(missing)}. Found: {', '.join(df.columns[:8])}"
            f"{', ...' if len(df.columns) > 8 else ''}."
        )


# --- Cleaning ------------------------------------------------------------

ITEM_SALES_REQUIRED = ["Item Name", "Category", "Items Sold", "Product Sales"]
TRANSACTIONS_REQUIRED = ["Date", "Time", "Gross Sales", "Transaction Status", "Event Type"]

# Raw Square category -> high-level group, for consistent chart coloring.
# Covers standard/common Square category names; anything else (including
# venue-specific ones, from this project's own data or an upload) falls
# back to guess_category_group() below.
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
    "Pizza": "Food", "Kids Mains": "Food", "Lunch Pasta": "Food",
    "Lunch Sandwiches": "Food", "Breakfast Menu": "Food", "Salads": "Food",
    "Kids Breakfast": "Food", "Nibbles": "Food", "Risotto": "Food",
    "Starters to Share": "Food", "Breakfast Extra": "Food", "Breakfast Sweets": "Food",
    "Uncategorised": "Food",
}

_DRINK_KEYWORDS = ["wine", "beer", "cider", "cocktail", "coffee", "tea", "latte", "juice",
                   "soda", "spirit", "vodka", "rum", "gin", "whisk", "liqueur", "drink",
                   "water", "smoothie", "champagne", "prosecco", "lager", "ale"]
_DESSERT_KEYWORDS = ["dessert", "cake", "ice cream", "gelato", "sorbet", "sweet", "pudding",
                      "pastry", "tart", "cookie", "brownie"]


def guess_category_group(raw_category: str) -> str:
    """Fallback for categories not in CATEGORY_GROUP — used for uploaded
    files whose category names won't match this project's own export."""
    name = str(raw_category).lower()
    if any(k in name for k in _DRINK_KEYWORDS):
        return "Drink"
    if any(k in name for k in _DESSERT_KEYWORDS):
        return "Dessert"
    return "Food"


# Square doesn't export COGS, so there's no real margin figure. These are
# typical UK hospitality cost-of-sales benchmarks by group (food ~28-32%,
# drink ~20-30% depending on category) used only to give the menu-engineering
# chart a plausible margin axis — clearly labelled as estimated wherever shown.
ESTIMATED_COST_PCT = {"Food": 0.30, "Drink": 0.22, "Dessert": 0.24}

DAY_PART_BINS = [
    (8, 11, "Breakfast"), (11, 15, "Lunch"), (15, 17, "Afternoon"), (17, 23, "Dinner"),
]


def hour_to_day_part(hour: int) -> str:
    for start, end, name in DAY_PART_BINS:
        if start <= hour < end:
            return name
    return "Late/Early"


def money(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"[£$€]", "", regex=True)
        .str.replace(",", "", regex=False)
        .replace("", "0")
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0.0)
    )


def clean_item_sales(df: pd.DataFrame) -> pd.DataFrame:
    require_columns(df, ITEM_SALES_REQUIRED, "Item Sales")
    df = df.copy()
    for col in ["Product Sales", "Refunds", "Discounts & Comps", "Net Sales", "Tax", "Gross Sales"]:
        if col in df.columns:
            df[col] = money(df[col])
        else:
            df[col] = 0.0
    df["Items Sold"] = pd.to_numeric(df["Items Sold"], errors="coerce").fillna(0)
    df = df[(df["Item Name"] != "Custom Amount") & (df["Items Sold"] > 0)].copy()
    df["category_group"] = df["Category"].map(CATEGORY_GROUP)
    df["category_group"] = df["category_group"].fillna(df["Category"].map(guess_category_group))
    df["avg_unit_price"] = (df["Product Sales"] / df["Items Sold"]).replace([np.inf, -np.inf], np.nan)
    df["est_cost_pct"] = df["category_group"].map(ESTIMATED_COST_PCT)
    df["est_margin"] = df["avg_unit_price"] * (1 - df["est_cost_pct"])
    if "Item Variation" not in df.columns:
        df["Item Variation"] = ""
    out = df.rename(columns={
        "Item Name": "item_name", "Item Variation": "variation", "Category": "raw_category",
        "Items Sold": "units_sold", "Product Sales": "revenue", "Net Sales": "net_sales",
        "Gross Sales": "gross_sales",
    })[[
        "item_name", "variation", "raw_category", "category_group", "units_sold",
        "revenue", "net_sales", "gross_sales", "avg_unit_price", "est_cost_pct", "est_margin",
    ]]
    return out


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    require_columns(df, TRANSACTIONS_REQUIRED, "Transactions")
    df = df.copy()
    if "Transaction Status" in df.columns:
        df = df[df["Transaction Status"] == "Complete"]
    if "Event Type" in df.columns:
        df = df[df["Event Type"] == "Payment"]
    df = df.copy()
    if df.empty:
        raise SquareFileError("No completed payment transactions found in this file after filtering.")

    df["datetime"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"].astype(str), errors="coerce")
    df = df[df["datetime"].notna()].copy()
    df["date"] = pd.to_datetime(df["Date"])
    df["hour"] = df["datetime"].dt.hour
    df["dow_name"] = df["datetime"].dt.day_name()
    df["day_part"] = df["hour"].apply(hour_to_day_part)

    for col in ["Gross Sales", "Net Sales", "Tax", "Tip", "Discounts", "Service Charges"]:
        df[col] = money(df[col]) if col in df.columns else 0.0

    df = df.sort_values("datetime").reset_index(drop=True)
    df["order_id"] = df.index + 1  # anonymous sequential ID — never the original Transaction ID

    if "Table info" not in df.columns:
        df["Table info"] = np.nan
    if "Source" not in df.columns:
        df["Source"] = "Unknown"

    out = df.rename(columns={
        "Gross Sales": "gross_sales", "Net Sales": "net_sales", "Tax": "tax", "Tip": "tip",
        "Table info": "table_number", "Source": "source", "Time": "time",
    })[[
        "order_id", "date", "time", "hour", "dow_name", "day_part",
        "gross_sales", "net_sales", "tax", "tip", "table_number", "source",
    ]]
    return out
