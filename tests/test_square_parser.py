"""
Tests for square_parser.py, focused on the guarantees this whole project
is built around: PII/identifier columns never survive into the cleaned
output, malformed input fails with a readable error instead of a crash or
silent garbage, and the encoding/format quirks across Square accounts are
actually handled rather than assumed.
"""

import io

import numpy as np
import pandas as pd
import pytest

from square_parser import (
    SquareFileError,
    clean_item_sales,
    clean_timecards,
    clean_transactions,
    guess_category_group,
    hour_to_day_part,
    money,
    read_square_csv,
    require_columns,
    sanitize_table_number,
)


# --- read_square_csv / encoding + delimiter sniffing ------------------------

def test_reads_utf16_tab_delimited_with_bom():
    text = "Item Name\tCategory\nCoffee\tDrinks\n"
    raw = text.encode("utf-16")  # includes a BOM
    df = read_square_csv(io.BytesIO(raw))
    assert list(df.columns) == ["Item Name", "Category"]
    assert df.iloc[0]["Item Name"] == "Coffee"


def test_reads_utf8_comma_delimited():
    raw = "Item Name,Category\nCoffee,Drinks\n".encode("utf-8")
    df = read_square_csv(io.BytesIO(raw))
    assert list(df.columns) == ["Item Name", "Category"]


def test_reads_utf8_sig_bom():
    raw = b"\xef\xbb\xbf" + "Item Name,Category\nCoffee,Drinks\n".encode("utf-8")
    df = read_square_csv(io.BytesIO(raw))
    assert list(df.columns) == ["Item Name", "Category"]


def test_empty_file_raises():
    with pytest.raises(SquareFileError, match="empty"):
        read_square_csv(io.BytesIO(b""))


def test_whitespace_only_file_raises():
    with pytest.raises(SquareFileError, match="empty"):
        read_square_csv(io.BytesIO(b"   \n  \n"))


def test_single_column_file_raises():
    raw = "just one column\nrow1\nrow2\n".encode("utf-8")
    with pytest.raises(SquareFileError, match="single column"):
        read_square_csv(io.BytesIO(raw))


def test_accepts_a_path(tmp_path):
    p = tmp_path / "sample.csv"
    p.write_text("Item Name,Category\nCoffee,Drinks\n", encoding="utf-8")
    df = read_square_csv(p)
    assert df.iloc[0]["Item Name"] == "Coffee"


# --- require_columns ---------------------------------------------------

def test_require_columns_passes_when_all_present():
    df = pd.DataFrame(columns=["A", "B", "C"])
    require_columns(df, ["A", "B"], "Test")  # should not raise


def test_require_columns_raises_with_missing_named():
    df = pd.DataFrame(columns=["A"])
    with pytest.raises(SquareFileError, match="B"):
        require_columns(df, ["A", "B"], "Test")


# --- money ---------------------------------------------------------------

def test_money_strips_currency_symbols_and_commas():
    s = pd.Series(["£1,234.50", "$99.99", "€0.00", ""])
    out = money(s)
    assert out.tolist() == [1234.50, 99.99, 0.0, 0.0]


def test_money_handles_already_numeric_input():
    s = pd.Series([1.5, 2.0])
    assert money(s).tolist() == [1.5, 2.0]


# --- guess_category_group -------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("Red Wine", "Drink"),
    ("craft beer", "Drink"),
    ("Hot Coffee", "Drink"),
    ("Chocolate Cake", "Dessert"),
    ("Gelato & Sorbet", "Dessert"),
    ("Grilled Chicken", "Food"),
    ("Burford Browns Eggs", "Food"),  # no drink/dessert keyword -> Food fallback
])
def test_guess_category_group(name, expected):
    assert guess_category_group(name) == expected


# --- hour_to_day_part ------------------------------------------------------

@pytest.mark.parametrize("hour,expected", [
    (7, "Late/Early"), (8, "Breakfast"), (10, "Breakfast"),
    (11, "Lunch"), (14, "Lunch"), (15, "Afternoon"), (16, "Afternoon"),
    (17, "Dinner"), (22, "Dinner"), (23, "Late/Early"),
])
def test_hour_to_day_part(hour, expected):
    assert hour_to_day_part(hour) == expected


# --- sanitize_table_number — this is the PII-leak fix ----------------------

@pytest.mark.parametrize("value,expected", [
    ("46", "46"),
    ("5 - 2", "5 - 2"),
    ("28 - 2", "28 - 2"),
    ("Takeaway1", "Takeaway1"),
    ("Takeawya", "Takeawya"),  # real typo seen in this project's own export
    ("takeaway", "takeaway"),
])
def test_sanitize_table_number_accepts_real_identifiers(value, expected):
    assert sanitize_table_number(value) == expected


@pytest.mark.parametrize("value", [
    "46 Agor dennis",  # the actual name that leaked through in production
    "Table 5",
    "John Smith",
    "",
    None,
    float("nan"),
])
def test_sanitize_table_number_rejects_free_text(value):
    result = sanitize_table_number(value)
    assert result is np.nan or (isinstance(result, float) and np.isnan(result))


# --- clean_item_sales ------------------------------------------------------

def _item_sales_df(**overrides):
    base = pd.DataFrame({
        "Item Name": ["Latte", "Custom Amount", "Zero Sales Item"],
        "Category": ["Hot Drinks", "Uncategorised", "Mystery Category"],
        "Items Sold": [10, 5, 0],
        "Product Sales": ["£25.00", "£50.00", "£0.00"],
    })
    for k, v in overrides.items():
        base[k] = v
    return base


def test_clean_item_sales_requires_columns():
    with pytest.raises(SquareFileError):
        clean_item_sales(pd.DataFrame({"foo": [1]}))


def test_clean_item_sales_drops_custom_amount_and_zero_sales_rows():
    out = clean_item_sales(_item_sales_df())
    assert "Custom Amount" not in out["item_name"].tolist()
    assert len(out) == 1
    assert out.iloc[0]["item_name"] == "Latte"


def test_clean_item_sales_computes_avg_price_and_category_group():
    out = clean_item_sales(_item_sales_df())
    row = out.iloc[0]
    assert row["category_group"] == "Drink"  # "Hot Drinks" in CATEGORY_GROUP dict
    assert row["avg_unit_price"] == pytest.approx(2.5)
    assert row["units_sold"] == 10
    assert row["revenue"] == pytest.approx(25.0)


def test_clean_item_sales_only_expected_columns_survive():
    out = clean_item_sales(_item_sales_df())
    assert set(out.columns) == {
        "item_name", "variation", "raw_category", "category_group", "units_sold",
        "revenue", "net_sales", "gross_sales", "avg_unit_price", "est_cost_pct", "est_margin",
    }


# --- clean_transactions — the core PII-stripping guarantee -----------------

def _transactions_df(**overrides):
    base = pd.DataFrame({
        "Date": ["2026-07-17", "2026-07-17", "2026-07-18"],
        "Time": ["12:30:00", "19:00:00", "10:00:00"],
        "Gross Sales": ["£25.00", "£40.00", "£10.00"],
        "Transaction Status": ["Complete", "Complete", "Voided"],
        "Event Type": ["Payment", "Payment", "Payment"],
        "Table info": ["Takeaway1", "46 Agor dennis", "12"],
        "Staff Name": ["Alex Doe", "Jamie Smith", "Alex Doe"],
        "Staff ID": ["staff_1", "staff_2", "staff_1"],
        "Customer Name": ["Pat Jones", "", ""],
        "Customer ID": ["cust_9", "", ""],
        "Card Brand": ["Visa", "Mastercard", ""],
        "PAN Suffix": ["1234", "5678", ""],
        "Transaction ID": ["txn_abc", "txn_def", "txn_ghi"],
        "Payment ID": ["pay_abc", "pay_def", "pay_ghi"],
    })
    for k, v in overrides.items():
        base[k] = v
    return base


def test_clean_transactions_requires_columns():
    with pytest.raises(SquareFileError):
        clean_transactions(pd.DataFrame({"foo": [1]}))


def test_clean_transactions_filters_to_complete_payments():
    out = clean_transactions(_transactions_df())
    assert len(out) == 2  # the "Voided" row is dropped
    assert out["gross_sales"].sum() == pytest.approx(65.0)


def test_clean_transactions_never_leaks_pii_columns():
    out = clean_transactions(_transactions_df())
    leaked = {
        "Staff Name", "Staff ID", "Customer Name", "Customer ID",
        "Card Brand", "PAN Suffix", "Transaction ID", "Payment ID",
    }
    assert not (leaked & set(out.columns))
    # belt and braces: the actual PII values shouldn't appear anywhere in the
    # serialised output either, not just as column names
    csv_text = out.to_csv(index=False)
    for name in ["Alex Doe", "Jamie Smith", "Pat Jones", "txn_abc", "staff_1", "cust_9"]:
        assert name not in csv_text


def test_clean_transactions_sanitizes_table_number():
    out = clean_transactions(_transactions_df())
    tables = out["table_number"].tolist()
    assert "Takeaway1" in tables  # valid identifier passes through
    assert not any(isinstance(t, str) and "Agor" in t for t in tables)  # free text dropped


def test_clean_transactions_order_id_is_anonymous_sequential():
    out = clean_transactions(_transactions_df())
    assert out["order_id"].tolist() == list(range(1, len(out) + 1))
    assert "txn_abc" not in out["order_id"].astype(str).tolist()


def test_clean_transactions_derives_hour_dow_daypart():
    out = clean_transactions(_transactions_df())
    row = out[out["time"] == "12:30:00"].iloc[0]
    assert row["hour"] == 12
    assert row["dow_name"] == "Friday"  # 2026-07-17 is a Friday
    assert row["day_part"] == "Lunch"


def test_clean_transactions_empty_after_filter_raises():
    df = _transactions_df(**{"Transaction Status": ["Voided", "Voided", "Voided"]})
    with pytest.raises(SquareFileError, match="No completed payment"):
        clean_transactions(df)


# --- clean_timecards ---------------------------------------------------

def test_clean_timecards_requires_date_column():
    with pytest.raises(SquareFileError, match="date column"):
        clean_timecards(pd.DataFrame({"Hours": [5]}))


def test_clean_timecards_requires_hours_or_clockinout():
    df = pd.DataFrame({"Date": ["2026-07-17"], "Employee Name": ["Alex Doe"]})
    with pytest.raises(SquareFileError, match="hours worked or clock-in"):
        clean_timecards(df)


def test_clean_timecards_never_leaks_employee_identity():
    df = pd.DataFrame({
        "Employee Name": ["Alex Doe", "Jamie Smith"],
        "Job Title": ["Server", "Chef"],
        "Date": ["2026-07-17", "2026-07-17"],
        "Total Hours": [6.0, 8.0],
        "Hourly Rate": [12.5, 15.0],
    })
    out = clean_timecards(df)
    assert "Employee Name" not in out.columns
    csv_text = out.to_csv(index=False)
    assert "Alex Doe" not in csv_text
    assert "Jamie Smith" not in csv_text
    assert out["shift_id"].tolist() == [1, 2]


def test_clean_timecards_computes_hours_from_clock_in_out():
    df = pd.DataFrame({
        "Date": ["2026-07-17"],
        "Clock-in Time": ["17:00"],
        "Clock-out Time": ["23:00"],
    })
    out = clean_timecards(df)
    assert out.iloc[0]["hours"] == pytest.approx(6.0)
    assert out.iloc[0]["day_part"] == "Dinner"


def test_clean_timecards_case_insensitive_column_matching():
    df = pd.DataFrame({
        "work date": ["2026-07-17"], "total hours": [5.5], "total pay": [88.0],
    })
    out = clean_timecards(df)
    assert out.iloc[0]["hours"] == 5.5
    assert out.iloc[0]["labor_cost"] == 88.0


def test_clean_timecards_labor_cost_nan_when_no_pay_or_rate():
    df = pd.DataFrame({"Date": ["2026-07-17"], "Total Hours": [5.0]})
    out = clean_timecards(df)
    assert out.iloc[0]["hours"] == 5.0
    assert pd.isna(out.iloc[0]["labor_cost"])


def test_clean_timecards_job_defaults_to_unspecified():
    df = pd.DataFrame({"Date": ["2026-07-17"], "Total Hours": [5.0]})
    out = clean_timecards(df)
    assert out.iloc[0]["job"] == "Unspecified"
