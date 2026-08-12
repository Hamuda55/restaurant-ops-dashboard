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
import re
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


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Case-insensitive match against a list of possible column names.
    Timecards exports aren't as standardised as the Sales/Transactions
    reports — Square's own naming has shifted over time and third-party
    time-tracking add-ons vary more, so this matches by intent rather than
    one fixed spelling."""
    lower_map = {str(c).strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]
    return None


TIMECARD_DATE_CANDIDATES = ["Date", "Clock-in Date", "Clock in Date", "Shift Date", "Work Date"]
TIMECARD_CLOCKIN_CANDIDATES = ["Clock-in Time", "Clock in Time", "Start Time", "Time In", "Clock In"]
TIMECARD_CLOCKOUT_CANDIDATES = ["Clock-out Time", "Clock out Time", "End Time", "Time Out", "Clock Out"]
TIMECARD_HOURS_CANDIDATES = ["Total Hours", "Hours Worked", "Hours", "Net Hours"]
TIMECARD_JOB_CANDIDATES = ["Job Title", "Job", "Role", "Team Member Job Title", "Position"]
TIMECARD_RATE_CANDIDATES = ["Hourly Rate", "Wage", "Rate", "Pay Rate"]
TIMECARD_PAY_CANDIDATES = ["Total Pay", "Gross Pay", "Pay", "Total Cost"]


def clean_timecards(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a Square Timecards/labour export. Column names vary more here
    than Sales/Transactions, so fields are matched by candidate name rather
    than a single required schema. Only date + (hours or clock-in/out) are
    truly required; job title and cost fields degrade gracefully if absent.

    Employee name/ID is never read into the output — whatever column
    identifies the person is simply not selected, replaced by an anonymous
    sequential shift_id, the same anonymisation approach as transactions."""
    date_col = _find_column(df, TIMECARD_DATE_CANDIDATES)
    if date_col is None:
        raise SquareFileError(
            "This doesn't look like a Timecards export — couldn't find a date column "
            f"(tried {', '.join(TIMECARD_DATE_CANDIDATES)}). Found: {', '.join(df.columns[:10])}"
            f"{', ...' if len(df.columns) > 10 else ''}."
        )

    df = df.copy()
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df[df["date"].notna()].copy()
    if df.empty:
        raise SquareFileError("No valid dates found in this Timecards export.")
    df["dow_name"] = df["date"].dt.day_name()

    hours_col = _find_column(df, TIMECARD_HOURS_CANDIDATES)
    clockin_col = _find_column(df, TIMECARD_CLOCKIN_CANDIDATES)
    clockout_col = _find_column(df, TIMECARD_CLOCKOUT_CANDIDATES)

    if hours_col is not None:
        df["hours"] = pd.to_numeric(df[hours_col], errors="coerce").fillna(0.0)
    elif clockin_col is not None and clockout_col is not None:
        clock_in = pd.to_datetime(df[date_col].astype(str) + " " + df[clockin_col].astype(str), errors="coerce")
        clock_out = pd.to_datetime(df[date_col].astype(str) + " " + df[clockout_col].astype(str), errors="coerce")
        overnight = (clock_out < clock_in).fillna(False)
        clock_out = clock_out + pd.to_timedelta(overnight.astype(int), unit="D")
        df["hours"] = ((clock_out - clock_in).dt.total_seconds() / 3600).clip(lower=0, upper=16).fillna(0.0)
    else:
        raise SquareFileError(
            "Couldn't find hours worked or clock-in/clock-out times in this file — is this a "
            f"Square Timecards export? Found: {', '.join(df.columns[:10])}{', ...' if len(df.columns) > 10 else ''}."
        )

    if clockin_col is not None:
        clock_in_dt = pd.to_datetime(df[date_col].astype(str) + " " + df[clockin_col].astype(str), errors="coerce")
        df["hour"] = clock_in_dt.dt.hour
        df["day_part"] = df["hour"].apply(lambda h: hour_to_day_part(h) if pd.notna(h) else "Unknown")
    else:
        df["day_part"] = "Unknown"

    job_col = _find_column(df, TIMECARD_JOB_CANDIDATES)
    df["job"] = df[job_col].astype(str).str.strip() if job_col is not None else "Unspecified"

    rate_col = _find_column(df, TIMECARD_RATE_CANDIDATES)
    pay_col = _find_column(df, TIMECARD_PAY_CANDIDATES)
    if pay_col is not None:
        df["labor_cost"] = money(df[pay_col])
    elif rate_col is not None:
        df["labor_cost"] = money(df[rate_col]) * df["hours"]
    else:
        df["labor_cost"] = np.nan  # hours still usable; cost charts will note it's unavailable

    df = df.sort_values("date").reset_index(drop=True)
    df["shift_id"] = df.index + 1  # anonymous — replaces whatever employee name/ID column existed

    return df[["shift_id", "date", "dow_name", "day_part", "job", "hours", "labor_cost"]]


# "Table info" is a free-text field in Square, meant for a table number but
# with nothing stopping staff from typing a note or a name into it instead.
# Only pass through values that actually look like a table identifier —
# plain numbers, split-bill format ("5 - 2"), or a takeaway label — and drop
# anything else rather than risk displaying a name that ended up there by
# accident. (This is exactly what happened in this project's own export.)
_VALID_TABLE_RE = re.compile(r"^\d+(\s*-\s*\d+)?$")


def sanitize_table_number(value) -> "str | float":
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return np.nan
    if _VALID_TABLE_RE.match(text) or text.lower().startswith("takeaw"):
        return text
    return np.nan


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
    else:
        df["Table info"] = df["Table info"].apply(sanitize_table_number)
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
