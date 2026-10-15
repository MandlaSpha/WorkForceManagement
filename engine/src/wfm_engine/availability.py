"""Declared availability: weekly windows in which a person says they cannot work (or would rather).

A window is a weekday and a run of half-hours on the day. "Nothing declared" is not the same as
"available": this module only answers whether a shift touches a window that WAS declared.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, time

from wfm_engine.roster import SLOTS_PER_DAY, on_grid, shift_slots


@dataclass(frozen=True, slots=True)
class Window:
    weekday: int  # Monday is 0
    start_slot: int  # first half-hour covered, 0-47
    end_slot: int  # first half-hour NOT covered, 1-48


def window_of(weekday: int, start: time, end: time) -> Window:
    """A window from clock times. The end may be 00:00, meaning the end of the day."""
    if not 0 <= weekday <= 6:
        raise ValueError("weekday must be 0 (Monday) to 6 (Sunday)")
    if not (on_grid(start) and on_grid(end)):
        raise ValueError("times must be on the hour or half-hour")
    first = start.hour * 2 + start.minute // 30
    last = SLOTS_PER_DAY if end == time(0, 0) else end.hour * 2 + end.minute // 30
    if last <= first:
        raise ValueError("a window must end after it starts")
    return Window(weekday, first, last)


def overlap(a: Window, b: Window) -> bool:
    return a.weekday == b.weekday and a.start_slot < b.end_slot and b.start_slot < a.end_slot


def touches(windows: Iterable[Window], day: date, start: time, end: time) -> bool:
    """Does a shift worked from `day` cover any half-hour inside one of the windows? An overnight
    shift's second half falls on the next weekday and is checked against that day's windows."""
    wanted: Sequence[tuple[date, int]] = shift_slots(day, start, end)
    return any(
        w.weekday == d.weekday() and w.start_slot <= k < w.end_slot
        for w in windows
        for d, k in wanted
    )
