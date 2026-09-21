"""Tests for how a document's date is decided.

Written after finding that the extractor was reporting zero disagreements
between the extracted dates and the years in the symbols, while A/RES/50/11
carried an adoption date of 1946-02-01. The check was resolving a year for only
28% of symbols and, where it did disagree, it printed a line and wrote the date
anyway.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "extract"))
import extract_date  # noqa: E402


def test_a_year_in_the_symbol_is_used():
    assert extract_date.symbol_year("S/RES/2728 (2024)") == 2024
    assert extract_date.symbol_year("S/2021/558") == 2021


def test_a_general_assembly_session_gives_its_year():
    """Session N opens in September of 1945 + N."""
    assert extract_date.symbol_year("A/RES/50/11") == 1995
    assert extract_date.symbol_year("A/RES/71/76") == 2016
    assert extract_date.symbol_year("A/74/PV.14") == 2019
    assert extract_date.symbol_year("A/RES/1/1") == 1946


def test_a_roman_session_gives_its_year():
    assert extract_date.symbol_year("A/RES/981(X)") == 1955


def test_a_symbol_with_nothing_to_go_on_gives_nothing():
    assert extract_date.symbol_year("S/PV.6231") is None
    assert extract_date.symbol_year("S/PRST/2009/1") == 2009


def test_a_date_far_from_the_symbol_year_is_rejected():
    """A/RES/50/11 is a 1995 resolution; 1946 came from a citation in its text.

    Reporting that and writing it anyway left 1946-02-01 in the data.
    """
    assert extract_date.plausible("1995-11-15", 1995)
    assert extract_date.plausible("1996-01-20", 1995)   # adopted Dec, distributed Jan
    assert not extract_date.plausible("1946-02-01", 1995)
    assert not extract_date.plausible("2009-08-21", 2016)
    assert extract_date.plausible("1946-02-01", None)   # nothing to check against
