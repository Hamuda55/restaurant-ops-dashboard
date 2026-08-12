"""Tests for load_square_data.py's business-name redaction."""

import pytest

from load_square_data import redact_business_name


@pytest.mark.parametrize("text,expected", [
    ("De Rada Breakfast", "Signature Breakfast"),
    ("de rada burger", "Signature burger"),
    ("DERADA", "Signature"),
    ("De  Rada", "Signature"),  # double space still matches (\s* in the regex)
    ("Classic Omelette", "Classic Omelette"),  # no match -> unchanged
])
def test_redact_business_name(text, expected):
    assert redact_business_name(text) == expected
