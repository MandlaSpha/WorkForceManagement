"""South African public holidays, for counting leave days (the `holidays` package, MIT)."""

from __future__ import annotations

from datetime import date

import holidays


def public_holidays(first: date, last: date) -> set[date]:
    """The public holidays from `first` to `last` inclusive."""
    years = range(first.year, last.year + 1)
    return {day for day in holidays.country_holidays("ZA", years=years) if first <= day <= last}
