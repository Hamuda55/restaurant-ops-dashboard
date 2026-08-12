"""
Load and clean this project's own real Square POS exports (kept unnamed
throughout — see the redaction step below).

Reads raw exports from data/raw/ and writes anonymised, analysis-ready CSVs
to data/real/. Parsing/cleaning logic lives in square_parser.py, shared with
the "upload your own data" path in the Streamlit app.

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
name never appears in data/real/, data/bi_export/, or the dashboard. This
step is specific to this project's own demo data — uploaded files in the
app aren't redacted this way, since there's no way to know a third party's
business name in advance (and no need to hide it from themselves).

Run:
    python src/load_square_data.py
"""

import re
from pathlib import Path

from square_parser import clean_item_sales, clean_transactions, read_square_csv

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "real"
OUT_DIR.mkdir(parents=True, exist_ok=True)

ITEM_SUMMARY_FILE = RAW_DIR / "item-sales-summary-2026-07-01-2026-07-31.csv"
TRANSACTIONS_FILE = RAW_DIR / "transactions-2026-07-01-2026-08-01.csv"

_BUSINESS_NAME_RE = re.compile(r"de\s*rada", re.IGNORECASE)


def redact_business_name(text: str) -> str:
    return _BUSINESS_NAME_RE.sub("Signature", str(text)).strip()


if __name__ == "__main__":
    item_sales = clean_item_sales(read_square_csv(ITEM_SUMMARY_FILE))
    item_sales["item_name"] = item_sales["item_name"].map(redact_business_name)
    item_sales["raw_category"] = item_sales["raw_category"].map(redact_business_name)

    orders = clean_transactions(read_square_csv(TRANSACTIONS_FILE))

    item_sales.to_csv(OUT_DIR / "real_item_sales.csv", index=False)
    orders.to_csv(OUT_DIR / "real_orders.csv", index=False)

    print(f"real_item_sales: {len(item_sales):,} rows  (£{item_sales['revenue'].sum():,.0f} product sales)")
    print(f"real_orders:     {len(orders):,} rows  (£{orders['gross_sales'].sum():,.0f} gross sales)")
    print(f"date range: {orders['date'].min().date()} to {orders['date'].max().date()}  ({orders['date'].dt.date.nunique()} trading days)")
    print(f"Wrote anonymised outputs to {OUT_DIR}")
