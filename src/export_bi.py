"""
Export a clean star-schema for Power BI / Tableau import, from the real
(anonymised) Square data — same source the Streamlit app uses.

Power BI Desktop has no macOS build, and Tableau isn't installed in this
environment, so this produces the flat, import-ready CSVs instead of a
.pbix/.twbx directly. Follow BI_TOOL_GUIDE.md to build the actual workbook.

Run:
    python src/load_square_data.py   # if data/real/ doesn't exist yet
    python src/export_bi.py
Outputs (in ../data/bi_export/):
    fact_transactions.csv   (grain: one row per POS transaction)
    dim_item_sales.csv      (grain: one row per menu item, period totals)
    dim_date.csv
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
REAL_DIR = DATA_DIR / "real"
OUT_DIR = DATA_DIR / "bi_export"
OUT_DIR.mkdir(exist_ok=True)

if not (REAL_DIR / "real_orders.csv").exists():
    raise SystemExit("data/real/ not found — run `python src/load_square_data.py` first.")

orders = pd.read_csv(REAL_DIR / "real_orders.csv", parse_dates=["date"])
item_sales = pd.read_csv(REAL_DIR / "real_item_sales.csv")

orders.to_csv(OUT_DIR / "fact_transactions.csv", index=False)
item_sales.to_csv(OUT_DIR / "dim_item_sales.csv", index=False)

all_dates = pd.date_range(orders["date"].min(), orders["date"].max(), freq="D")
dim_date = pd.DataFrame({"date": all_dates})
dim_date["day_name"] = dim_date["date"].dt.day_name()
dim_date["is_weekend"] = dim_date["date"].dt.dayofweek >= 5
dim_date.to_csv(OUT_DIR / "dim_date.csv", index=False)

print(f"fact_transactions: {len(orders):,} rows  (£{orders['gross_sales'].sum():,.0f} gross)")
print(f"dim_item_sales:    {len(item_sales):,} rows")
print(f"dim_date:          {len(dim_date):,} rows")
print(f"Exported to {OUT_DIR}")
