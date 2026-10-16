"""Pricing overtime in rands (requirement OT-01), under the BCEA rates in the compliance rules.

Pure: no Django, no clock, no I/O. Money is Decimal throughout and rounded half up to the cent only
at the end. The hourly rate is the monthly salary over the hours in an average month: the contract
hours of a week times 4.333 weeks.

The rate paid depends on the kind of day: a public holiday pays the holiday multiplier, a Sunday the
Sunday multiplier (the ordinary overtime multiplier for a person who ordinarily works Sundays), any
other day the ordinary overtime multiplier. A Sunday that is also a public holiday is a holiday.
"""

from __future__ import annotations

from collections.abc import Container
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from .compliance import Rules

WEEKS_PER_MONTH = Decimal("4.333")
CENT = Decimal("0.01")
SUNDAY = 6  # date.weekday()

WEEKDAY, SUNDAY_KIND, HOLIDAY = "weekday", "sunday", "holiday"


def day_kind(day: date, public_holidays: Container[date]) -> str:
    if day in public_holidays:
        return HOLIDAY
    return SUNDAY_KIND if day.weekday() == SUNDAY else WEEKDAY


def hourly_rate(monthly_salary: Decimal, weekly_hours: Decimal) -> Decimal:
    if monthly_salary < 0 or weekly_hours <= 0:
        raise ValueError("salary cannot be negative and weekly hours must be above zero")
    return monthly_salary / (weekly_hours * WEEKS_PER_MONTH)


def multiplier(kind: str, *, ordinarily_works_sundays: bool, rules: Rules) -> Decimal:
    if kind == HOLIDAY:
        return rules.holiday_multiplier
    if kind == SUNDAY_KIND and not ordinarily_works_sundays:
        return rules.sunday_multiplier
    return rules.overtime_multiplier


def price(
    *,
    minutes: int,
    monthly_salary: Decimal,
    weekly_hours: Decimal,
    kind: str,
    ordinarily_works_sundays: bool,
    rules: Rules,
) -> Decimal:
    """What `minutes` of overtime on this kind of day costs, in rands to the cent."""
    if minutes <= 0:
        raise ValueError("overtime must be above zero minutes")
    rate = hourly_rate(monthly_salary, weekly_hours)
    factor = multiplier(kind, ordinarily_works_sundays=ordinarily_works_sundays, rules=rules)
    return (rate * factor * Decimal(minutes) / Decimal(60)).quantize(CENT, rounding=ROUND_HALF_UP)
