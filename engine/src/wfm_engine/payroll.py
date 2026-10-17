"""Building payroll export files (requirement RPT-08). Pure: no Django, no clock, no I/O.

A spreadsheet runs any cell that starts with =, +, - or @ as a formula, so text that came from a
person (a name) is made safe before it goes in a file somebody opens in Excel.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from decimal import ROUND_HALF_UP, Decimal

_FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")
CENT = Decimal("0.01")


def safe_cell(text: str) -> str:
    """Text with a leading apostrophe when a spreadsheet would read it as a formula."""
    return "'" + text if text.startswith(_FORMULA_STARTS) else text


def rands(amount: Decimal) -> str:
    """Rands to the cent with a point, as payroll systems read it."""
    return str(amount.quantize(CENT, rounding=ROUND_HALF_UP))


def hours(minutes: int) -> str:
    """Minutes as hours with two decimals."""
    return str((Decimal(minutes) / 60).quantize(CENT, rounding=ROUND_HALF_UP))


def to_csv(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """A CSV with CRLF line ends and every text cell made formula-safe."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([safe_cell(cell) for cell in row])
    return out.getvalue()
