"""Peaks and troughs of measured demand (RPT-03). Pure functions: no Django, no clock, no I/O.

Input is one queue's offered calls per half-hour, already in local time. Ties are broken by the
earlier time so the same data always gives the same report.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

TOP = 5
_TENTH = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class DayTotal:
    day: date
    offered: int


@dataclass(frozen=True, slots=True)
class IntervalTotal:
    start: datetime
    offered: int


@dataclass(frozen=True, slots=True)
class SlotAverage:
    slot: time  # the half-hour of the day
    average_offered: Decimal  # per day on which the queue had any calls in that slot's day
    days: int


@dataclass(frozen=True, slots=True)
class Report:
    busiest_days: list[DayTotal]
    quietest_days: list[DayTotal]
    busiest_intervals: list[IntervalTotal]
    busiest_slots: list[SlotAverage]
    quietest_slots: list[SlotAverage]  # among slots that ever saw a call: the queue is open then


def analyse(intervals: Iterable[tuple[datetime, int]], top: int = TOP) -> Report:
    """`intervals` are (local start of the half-hour, offered calls). Days with no rows are not
    counted as quiet: nothing was measured, which is not the same as nobody calling."""
    per_day: dict[date, int] = defaultdict(int)
    slot_sum: dict[time, int] = defaultdict(int)
    slot_days: dict[time, set[date]] = defaultdict(set)
    rows = sorted(intervals)
    for start, offered in rows:
        per_day[start.date()] += offered
        slot_sum[start.time()] += offered
        slot_days[start.time()].add(start.date())

    days = [DayTotal(d, n) for d, n in per_day.items()]
    slots = [
        SlotAverage(
            slot,
            (Decimal(total) / len(slot_days[slot])).quantize(_TENTH, ROUND_HALF_UP),
            len(slot_days[slot]),
        )
        for slot, total in slot_sum.items()
        if total > 0
    ]
    return Report(
        busiest_days=sorted(days, key=lambda d: (-d.offered, d.day))[:top],
        quietest_days=sorted(days, key=lambda d: (d.offered, d.day))[:top],
        busiest_intervals=sorted(
            (IntervalTotal(s, n) for s, n in rows), key=lambda i: (-i.offered, i.start)
        )[:top],
        busiest_slots=sorted(slots, key=lambda s: (-s.average_offered, s.slot))[:top],
        quietest_slots=sorted(slots, key=lambda s: (s.average_offered, s.slot))[:top],
    )
