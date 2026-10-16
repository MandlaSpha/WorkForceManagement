"""Compliance rules the roster is checked against (requirement CFG-06).

Pure functions: no Django, no clock, no I/O. A rule set is versioned by the day it takes effect;
the rules in force on a day are those of the latest version that started on or before it, or the
built-in defaults when none has.

The statutory floor is the line below which loosening a rule shows a warning. It is the customer's
responsibility to know what the law requires of them, so a rule may still be set below it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .roster import DEFAULT_MAX_CONSECUTIVE_DAYS, DEFAULT_MIN_REST_HOURS

MIN_REST_HOURS_LIMITS = (1, 24)
MAX_CONSECUTIVE_DAYS_LIMITS = (1, 14)
MAX_WEEKLY_HOURS_LIMITS = (1, 90)


@dataclass(frozen=True)
class Rules:
    min_rest_hours: int = DEFAULT_MIN_REST_HOURS
    max_consecutive_days: int = DEFAULT_MAX_CONSECUTIVE_DAYS
    max_weekly_hours: int | None = (
        None  # a cap for everybody, on top of each person's contract hours
    )


DEFAULT_RULES = Rules()
STATUTORY_FLOOR = Rules()  # no looser than the defaults, which are what the spec calls the law


def rules_in_force(versions: Iterable[tuple[date, Rules]], day: date) -> Rules:
    """The rules of the latest version taking effect on or before `day` (else the defaults)."""
    started = [
        (effective_from, rules) for effective_from, rules in versions if effective_from <= day
    ]
    return max(started, key=lambda pair: pair[0])[1] if started else DEFAULT_RULES


def invalid_reason(rules: Rules) -> str | None:
    """Why this rule set is not allowed at all (not merely loose), or None."""
    if not MIN_REST_HOURS_LIMITS[0] <= rules.min_rest_hours <= MIN_REST_HOURS_LIMITS[1]:
        return "Rest between shifts must be 1 to 24 hours."
    if (
        not MAX_CONSECUTIVE_DAYS_LIMITS[0]
        <= rules.max_consecutive_days
        <= MAX_CONSECUTIVE_DAYS_LIMITS[1]
    ):
        return "Days in a row must be 1 to 14."
    cap = rules.max_weekly_hours
    if cap is not None and not MAX_WEEKLY_HOURS_LIMITS[0] <= cap <= MAX_WEEKLY_HOURS_LIMITS[1]:
        return "The weekly hours cap must be 1 to 90."
    return None


def floor_warnings(rules: Rules) -> list[str]:
    """One plain sentence for each rule set looser than the statutory floor. Warnings only: the
    admin is responsible for what the law requires."""
    found: list[str] = []
    if rules.min_rest_hours < STATUTORY_FLOOR.min_rest_hours:
        found.append(
            f"Rest of {rules.min_rest_hours} hours is below the statutory "
            f"{STATUTORY_FLOOR.min_rest_hours}."
        )
    if rules.max_consecutive_days > STATUTORY_FLOOR.max_consecutive_days:
        found.append(
            f"{rules.max_consecutive_days} days in a row is above the statutory "
            f"{STATUTORY_FLOOR.max_consecutive_days}."
        )
    return found


def tightest(versions: Iterable[Rules]) -> Rules:
    """The strictest of several rule sets, field by field: the longest rest, the fewest days in a
    row, the lowest weekly cap. For planning across days that straddle a change of rules, so
    whatever is proposed is allowed under every one of them."""
    found = list(versions)
    if not found:
        return DEFAULT_RULES
    caps = [r.max_weekly_hours for r in found if r.max_weekly_hours is not None]
    return Rules(
        min_rest_hours=max(r.min_rest_hours for r in found),
        max_consecutive_days=min(r.max_consecutive_days for r in found),
        max_weekly_hours=min(caps) if caps else None,
    )
