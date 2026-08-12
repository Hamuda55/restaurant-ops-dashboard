"""
Regression tests tied to specific incidents, not general behaviour. Each of
these encodes something that actually went wrong once, so it can't happen
silently again — e.g. `data/real/real_orders.csv` briefly contained a real
name ("46 Agor dennis") in its table_number field before the sanitizer in
square_parser.py was added.

These read the actual tracked data files, not synthetic fixtures, so they
also catch a bad regeneration (e.g. someone re-running the loader against a
raw export before a future fix is in place).
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REAL_DIR = ROOT / "data" / "real"

# Strings that must never appear again in the tracked, published data —
# add to this list whenever a similar leak is found and fixed.
_FORBIDDEN_STRINGS = ["Agor", "dennis", "Dennis"]


@pytest.mark.parametrize("csv_name", ["real_orders.csv", "real_item_sales.csv"])
def test_real_data_has_no_known_leaked_strings(csv_name):
    path = REAL_DIR / csv_name
    if not path.exists():
        pytest.skip(f"{csv_name} not generated in this environment")
    text = path.read_text(encoding="utf-8")
    for bad in _FORBIDDEN_STRINGS:
        assert bad not in text, f"{bad!r} found in {csv_name} — a name leaked through again"


def test_real_orders_table_numbers_all_look_like_table_identifiers():
    """Every non-null table_number in the tracked data should pass the same
    sanitizer real uploads go through — if this fails, the committed CSV is
    stale relative to square_parser.py and needs regenerating."""
    import pandas as pd

    from square_parser import sanitize_table_number

    path = REAL_DIR / "real_orders.csv"
    if not path.exists():
        pytest.skip("real_orders.csv not generated in this environment")
    df = pd.read_csv(path)
    for value in df["table_number"].dropna():
        assert sanitize_table_number(value) == str(value), (
            f"{value!r} in the tracked CSV wouldn't pass sanitize_table_number today"
        )
