"""Adding a forecast up over a range of days, for the week and month views (FC-01, DAT-10).

Pure functions: no Django, no clock, no I/O. Input is the half-hours of a forecast already in local
time; output is one line per asked-for day. A day with no forecast is reported as such, never as
zero calls, and a figure that cannot be worked out in full is None, never a partial total.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

SLOTS_PER_DAY = 48
HOURS_PER_SLOT = 0.5


@dataclass(frozen=True, slots=True)
class Slot:
    """One half-hour as forecast. `slot` is 0 (00:00) to 47 (23:30)."""

    day: date
    slot: int
    volume: float
    aht_s: float | None
    required: int | None  # agents to roster; None when it could not be worked out


@dataclass(frozen=True, slots=True)
class DayRange:
    day: date
    has_forecast: bool
    calls: float  # 0.0 only means "no calls expected" when has_forecast
    aht_s: float | None  # call-weighted; None when no call has a handling time
    peak_required: int | None  # None when unknown (see `complete`) or no forecast
    hours_required: float | None  # agent-hours to roster over the day; None like the peak
    busiest_slot: int | None  # half-hour with the most calls (earlier on a tie)
    complete: bool  # False: some half-hour with calls has no requirement
    required_by_slot: tuple[int | None, ...]  # 48 entries; empty when no forecast


@dataclass(frozen=True, slots=True)
class RangeSummary:
    days: tuple[DayRange, ...]
    busiest_day: date | None  # most calls among days with a forecast and calls
    quietest_day: date | None  # fewest calls among days with a forecast (ties: earlier day)


def summarise(slots: Iterable[Slot], days: Sequence[date]) -> RangeSummary:
    """One line per day in `days`, in that order, for the slots given.

    A day with no slots at all has no forecast. Busiest and quietest are named only when at least
    two days have a forecast and they differ, so a single day is not crowned both."""
    by_day: dict[date, list[Slot]] = defaultdict(list)
    for s in slots:
        by_day[s.day].append(s)
    lines = tuple(_day(d, by_day.get(d, [])) for d in days)

    forecast = [d for d in lines if d.has_forecast]
    busiest: date | None = None
    quietest: date | None = None
    if len(forecast) >= 2 and len({d.calls for d in forecast}) > 1:
        busiest = min(forecast, key=lambda d: (-d.calls, d.day)).day
        quietest = min(forecast, key=lambda d: (d.calls, d.day)).day
    return RangeSummary(lines, busiest, quietest)


def _day(day: date, slots: list[Slot]) -> DayRange:
    if not slots:
        return DayRange(day, False, 0.0, None, None, None, None, True, ())
    grid: list[int | None] = [0] * SLOTS_PER_DAY
    calls = 0.0
    handle_s = 0.0
    handled_calls = 0.0
    busiest: Slot | None = None
    complete = True
    for s in slots:
        calls += s.volume
        if s.aht_s is not None and s.volume > 0:
            handle_s += s.aht_s * s.volume
            handled_calls += s.volume
        if s.volume > 0 and (busiest is None or s.volume > busiest.volume):
            busiest = s
        # A half-hour with no calls needs nobody even if its requirement was not stored.
        need = s.required if s.volume > 0 else 0
        if need is None:
            complete = False
        grid[s.slot] = need
    known = [n for n in grid if n is not None]
    return DayRange(
        day=day,
        has_forecast=True,
        calls=calls,
        aht_s=handle_s / handled_calls if handled_calls > 0 else None,
        peak_required=max(known, default=0) if complete else None,
        hours_required=sum(known) * HOURS_PER_SLOT if complete else None,
        busiest_slot=None if busiest is None else busiest.slot,
        complete=complete,
        required_by_slot=tuple(grid),
    )
