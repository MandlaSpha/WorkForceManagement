from decimal import Decimal

import pytest

from wfm_engine.payroll import hours, rands, safe_cell, to_csv


@pytest.mark.parametrize("text", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_a_cell_a_spreadsheet_would_run_as_a_formula_is_made_safe(text: str) -> None:
    # Failure caught: a name such as "=HYPERLINK(...)" executing when payroll opens the file.
    assert safe_cell(text) == "'" + text


def test_ordinary_text_is_left_alone() -> None:
    assert safe_cell("Pat O'Neil") == "Pat O'Neil"
    assert safe_cell("") == ""


def test_money_and_hours_have_two_decimals_and_a_point() -> None:
    assert rands(Decimal("300")) == "300.00"
    assert rands(Decimal("0.125")) == "0.13"  # half up
    assert hours(90) == "1.50"
    assert hours(0) == "0.00"


def test_the_file_has_crlf_ends_quotes_commas_and_safe_cells() -> None:
    text = to_csv(["No", "Name"], [["E1", "Smith, Pat"], ["E2", "=cmd"]])
    assert text == 'No,Name\r\nE1,"Smith, Pat"\r\nE2,\'=cmd\r\n'
