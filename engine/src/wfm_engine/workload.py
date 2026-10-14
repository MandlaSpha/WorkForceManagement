"""Effort-based staffing for ticket work (requirement SD-01; reference UI: the Service desk screen).

This is not Erlang. A caller who is not answered abandons; a ticket that is not picked up is still
there tomorrow. So the people needed are the EFFORT that must be finished by a deadline, divided by
the productive time one person has before it. Effort is engineer time, never the SLA window: a
four-hour P1 can hold twenty minutes of work.

Pure functions: no Django, no clock, no I/O. Times are passed in, already timezone-aware.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta

WORKING_WEEKDAYS = 5  # Monday to Friday


@dataclass(frozen=True, slots=True)
class OpenItem:
    """A ticket or task that is not finished yet."""

    effort_min: int | None  # engineer time still needed; None when nobody has estimated it
    due: datetime | None  # when it must be finished; None when it has no deadline


@dataclass(frozen=True, slots=True)
class Demand:
    open_count: int
    breached: int  # open and already past its deadline
    backlog_min: int  # estimated effort of everything open, with or without a deadline
    due_min: int  # estimated effort that must be finished by the end of the horizon
    arriving_min: float | None  # expected new effort over the horizon; None when unknown
    unestimated: int  # open items with no effort estimate: the figures are minimums
    no_deadline: int  # open items with no deadline: in the backlog, not in the requirement
    required_fte: float | None  # None when there are no working days to do it in
    complete: bool  # False when an estimate or the arrival rate is missing


def working_days(first: date, days: int) -> int:
    """Monday-to-Friday days among `days` days starting on `first`. Public holidays are not taken
    off: the planner adjusts the productive time instead."""
    return sum(1 for n in range(days) if (first + timedelta(days=n)).weekday() < WORKING_WEEKDAYS)


def arrival_rate_per_working_day(
    opened: Iterable[tuple[date, int | None]], window_first: date, window_days: int
) -> float | None:
    """Estimated effort arriving per working day, from the items opened in the window just gone.

    None when nothing was opened in it (that could be a quiet month or a missing import, and the
    data cannot tell which), or the window has no working days. Items with no estimate add
    nothing; they are counted by the caller so the figure is marked a minimum."""
    days = working_days(window_first, window_days)
    items = list(opened)
    if days == 0 or not items:
        return None
    return sum(effort or 0 for _day, effort in items) / days


def demand(
    items: Iterable[OpenItem],
    *,
    as_of: datetime,
    horizon_end: datetime,
    horizon_working_days: int,
    productive_min_per_day: int,
    arrival_per_working_day: float | None,
) -> Demand:
    """What a pool needs over the horizon: its open work due by then, plus what is expected to
    arrive, divided by what one person can productively do in the horizon's working days."""
    if productive_min_per_day <= 0:
        raise ValueError("productive minutes per day must be positive")
    open_count = breached = backlog = due_min = unestimated = no_deadline = 0
    for item in items:
        open_count += 1
        if item.effort_min is None:
            unestimated += 1
        else:
            backlog += item.effort_min
        if item.due is None:
            no_deadline += 1
            continue
        if item.due < as_of:
            breached += 1
        if item.due <= horizon_end and item.effort_min is not None:
            due_min += item.effort_min

    arriving = (
        None if arrival_per_working_day is None else arrival_per_working_day * horizon_working_days
    )
    capacity_per_fte = productive_min_per_day * horizon_working_days
    required = None if capacity_per_fte == 0 else (due_min + (arriving or 0.0)) / capacity_per_fte
    return Demand(
        open_count=open_count,
        breached=breached,
        backlog_min=backlog,
        due_min=due_min,
        arriving_min=arriving,
        unestimated=unestimated,
        no_deadline=no_deadline,
        required_fte=required,
        complete=unestimated == 0 and arriving is not None,
    )
