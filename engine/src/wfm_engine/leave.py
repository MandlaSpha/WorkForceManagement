"""Leave rules (requirements LV-01 to LV-03): working days, overlap, balances and what taking leave
does to coverage. Pure functions: no Django, no clock, no I/O. Public holidays are passed in.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

WORKING_WEEKDAYS = 5  # Monday to Friday
HOURS_PER_SLOT = 0.5


def working_days(start: date, end: date, holidays: Collection[date] = ()) -> int:
    """Monday-to-Friday days from `start` to `end` inclusive that are not public holidays."""
    return sum(working_days_by_year(start, end, holidays).values())


def working_days_by_year(start: date, end: date, holidays: Collection[date] = ()) -> dict[int, int]:
    """The same days, counted against the calendar year they fall in. Leave that crosses New Year
    is taken from two years' entitlements."""
    if end < start:
        raise ValueError("end is before start")
    counts: Counter[int] = Counter()
    day = start
    while day <= end:
        if day.weekday() < WORKING_WEEKDAYS and day not in holidays:
            counts[day.year] += 1
        day += timedelta(days=1)
    return dict(counts)


def overlaps(a: tuple[date, date], b: tuple[date, date]) -> bool:
    """Whether two date ranges (inclusive) share a day."""
    return a[0] <= b[1] and b[0] <= a[1]


@dataclass(frozen=True, slots=True)
class Balance:
    entitlement: Decimal | None  # days a year; None means no limit (unpaid, training)
    taken: Decimal  # approved days in the year
    pending: Decimal  # asked for and not decided yet
    available: Decimal | None  # entitlement - taken - pending; None for no limit

    @property
    def exceeded(self) -> bool:
        return self.available is not None and self.available < 0


def balance(entitlement: Decimal | None, taken: Decimal, pending: Decimal) -> Balance:
    """What is left of a year's entitlement once approved and pending leave is counted."""
    available = None if entitlement is None else entitlement - taken - pending
    return Balance(entitlement, taken, pending, available)


@dataclass(frozen=True, slots=True)
class Slot:
    """A half-hour the person is rostered for, with how many are scheduled on the queue and how
    many are required (None when no requirement is known)."""

    scheduled: int
    required: int | None


@dataclass(frozen=True, slots=True)
class Impact:
    shifts: int  # shifts that fall on the leave days
    hours: float  # rostered hours given up
    intervals: int  # half-hours affected
    newly_under: int  # half-hours that were covered and would no longer be
    already_under: int  # half-hours already short, made shorter
    unknown: int  # half-hours with no known requirement: nothing is claimed about them


def impact(shifts: int, slots: Iterable[Slot]) -> Impact:
    """What approving the leave does to coverage: the person leaves each of these half-hours, so
    one fewer is scheduled. A half-hour with no known requirement is counted, not judged."""
    intervals = newly = already = unknown = 0
    for slot in slots:
        intervals += 1
        if slot.required is None:
            unknown += 1
        elif slot.scheduled < slot.required:
            already += 1
        elif slot.scheduled - 1 < slot.required:
            newly += 1
    return Impact(shifts, intervals * HOURS_PER_SLOT, intervals, newly, already, unknown)
