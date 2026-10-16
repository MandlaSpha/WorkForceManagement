"""Shrinkage from actuals (SHR-01): the share of contracted hours people were away for approved
leave. Pure functions: no Django, no clock, no I/O. Working days are counted by the caller.

Only planned shrinkage is measured; unplanned (absence, lateness) needs an attendance feed and is
never guessed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

WORKING_DAYS_PER_WEEK = Decimal(5)
_TENTH = Decimal("0.1")


@dataclass(frozen=True)
class Person:
    weekly_hours: Decimal
    employed_days: int  # working days in the period on which they were employed
    away_days: int  # of those, working days on approved leave


@dataclass(frozen=True)
class Summary:
    people: int
    contracted_hours: Decimal
    away_hours: Decimal
    planned_pct: Decimal | None  # None: nobody had any contracted hours, so there is no share


def summarise(people: Iterable[Person]) -> Summary:
    contracted = Decimal(0)
    away = Decimal(0)
    count = 0
    for person in people:
        if person.away_days > person.employed_days:
            raise ValueError("away days exceed employed days")
        per_day = person.weekly_hours / WORKING_DAYS_PER_WEEK
        contracted += per_day * person.employed_days
        away += per_day * person.away_days
        count += 1
    pct = (away * 100 / contracted).quantize(_TENTH, ROUND_HALF_UP) if contracted > 0 else None
    return Summary(count, contracted, away, pct)
