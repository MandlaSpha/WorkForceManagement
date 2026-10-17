"""Shifts, coverage, variance and roster rules (requirements SCH-01 to SCH-04, ENG-03, ENG-04).

Pure functions: no Django, no clock, no I/O. Times are local wall-clock times (naive); the caller
decides which zone they are in.

A shift is a start and an end time on the 30-minute grid, worked from a given day. When the end is
not after the start the shift runs overnight into the next day. Coverage counts, per half-hour, how
many people are rostered (`coverage`), and how many of those are really on the phones once the
breaks and activities inside their shifts (SCH-03) are taken off (`coverage_on_phone`, ENG-03).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

SLOTS_PER_DAY = 48
DEFAULT_MIN_REST_HOURS = 11
DEFAULT_MAX_CONSECUTIVE_DAYS = 6

SlotKey = tuple[date, int]  # (day, half-hour 0..47)


def on_grid(moment: time) -> bool:
    return moment.minute in (0, 30) and moment.second == 0 and moment.microsecond == 0


def _slot(moment: time) -> int:
    return moment.hour * 2 + moment.minute // 30


def _check(start: time, end: time) -> None:
    if not (on_grid(start) and on_grid(end)):
        raise ValueError("shift times must be on the half-hour")
    if start == end:
        raise ValueError("a shift must have a length")


def is_overnight(start: time, end: time) -> bool:
    return end <= start


def shift_kind(start: time, end: time) -> str:
    """The legend group of a shift: "night" if it runs overnight, otherwise "early" when it starts
    before 09:00, "day" from 09:00 up to 13:00, and "late" from 13:00 (UI spec, Roster)."""
    if is_overnight(start, end):
        return "night"
    if start < time(9, 0):
        return "early"
    return "day" if start < time(13, 0) else "late"


def shift_slots(day: date, start: time, end: time) -> list[SlotKey]:
    """The half-hours a shift worked from `day` covers, in order. An overnight shift continues
    into the next day."""
    _check(start, end)
    first, last = _slot(start), _slot(end)
    if last > first:
        return [(day, k) for k in range(first, last)]
    return [(day, k) for k in range(first, SLOTS_PER_DAY)] + [
        (day + timedelta(days=1), k) for k in range(0, last)
    ]


def shift_span(day: date, start: time, end: time) -> tuple[datetime, datetime]:
    """When the shift starts and ends as moments, the end falling on the next day if overnight."""
    _check(start, end)
    began = datetime.combine(day, start)
    finished = datetime.combine(day, end)
    if is_overnight(start, end):
        finished += timedelta(days=1)
    return began, finished


def shift_minutes(start: time, end: time) -> int:
    """Length of the shift on the clock, breaks not taken off."""
    _check(start, end)
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return minutes + 24 * 60 if minutes <= 0 else minutes


def coverage(shifts: Iterable[tuple[date, time, time]]) -> Counter[SlotKey]:
    """How many people are rostered in each half-hour, from (day, start, end) shifts."""
    counted: Counter[SlotKey] = Counter()
    for day, start, end in shifts:
        counted.update(shift_slots(day, start, end))
    return counted


Activity = tuple[int, int]  # (half-hours from the start of the shift, how many half-hours)


def shift_length_slots(start: time, end: time) -> int:
    """How many half-hours a shift covers."""
    return len(shift_slots(date(2000, 1, 3), start, end))


def check_activity(
    length: int, activity: Activity, others: Collection[Activity] = ()
) -> str | None:
    """Why an activity cannot go in a shift of `length` half-hours, or None when it can: it must
    have a length, sit wholly inside the shift, and not overlap another activity."""
    offset, slots = activity
    if slots < 1:
        return "length"
    if offset < 0 or offset + slots > length:
        return "outside"
    for other_offset, other_slots in others:
        if offset < other_offset + other_slots and other_offset < offset + slots:
            return "overlap"
    return None


def coverage_on_phone(
    shifts: Iterable[tuple[date, time, time, Iterable[Activity]]],
) -> tuple[Counter[SlotKey], Counter[SlotKey]]:
    """People on the phones in each half-hour, and people in an activity in each, from
    (day, start, end, activities) shifts. A half-hour in an activity is not on the phones."""
    on_phone: Counter[SlotKey] = Counter()
    off_phone: Counter[SlotKey] = Counter()
    for day, start, end, activities in shifts:
        slots = shift_slots(day, start, end)
        away = {i for offset, count in activities for i in range(offset, offset + count)}
        for index, key in enumerate(slots):
            (off_phone if index in away else on_phone)[key] += 1
    return on_phone, off_phone


# --- rules -------------------------------------------------------------------------------------


def rest_hours(previous_end: datetime, next_start: datetime) -> float:
    """Hours of rest between the end of one shift and the start of the next."""
    return (next_start - previous_end).total_seconds() / 3600


def breaks_rest_rule(
    spans: Collection[tuple[datetime, datetime]],
    candidate: tuple[datetime, datetime],
    *,
    min_hours: float = DEFAULT_MIN_REST_HOURS,
) -> bool:
    """True when adding `candidate` leaves less than `min_hours` of rest between it and any other
    shift of the same person (before or after it), or overlaps one."""
    began, finished = candidate
    for other_began, other_finished in spans:
        if other_began < finished and began < other_finished:
            return True  # overlap
        gap = rest_hours(other_finished, began) if other_finished <= began else None
        if gap is not None and gap < min_hours:
            return True
        gap = rest_hours(finished, other_began) if finished <= other_began else None
        if gap is not None and gap < min_hours:
            return True
    return False


def consecutive_run(worked: Collection[date], candidate: date) -> int:
    """How many days in a row would be worked if `candidate` were added, counting back and
    forward from it."""
    days = set(worked) | {candidate}
    run = 1
    day = candidate - timedelta(days=1)
    while day in days:
        run += 1
        day -= timedelta(days=1)
    day = candidate + timedelta(days=1)
    while day in days:
        run += 1
        day += timedelta(days=1)
    return run


def week_minutes(shifts: Iterable[tuple[time, time]]) -> int:
    return sum(shift_minutes(start, end) for start, end in shifts)


# --- variance ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class WeekSummary:
    intervals_known: int  # half-hours with a known requirement
    under_intervals: int  # of those, how many have fewer people than required
    gap: int  # total shortfall in people-half-hours (over-staffing does not offset it)
    required_total: int
    scheduled_total: int  # people-half-hours, over the half-hours with a known requirement
    worst: tuple[SlotKey, int] | None  # the half-hour furthest below requirement, and by how much


def variance(scheduled: int, required: int | None) -> int | None:
    """Scheduled minus required. None when the requirement is unknown: unknown is not zero."""
    return None if required is None else scheduled - required


def classify(scheduled: int, required: int | None) -> str | None:
    """ "under", "met" or "over". None when the requirement is unknown."""
    gap = variance(scheduled, required)
    if gap is None:
        return None
    return "under" if gap < 0 else "over" if gap > 0 else "met"


def summarise(
    scheduled: Mapping[SlotKey, int], required: Mapping[SlotKey, int | None]
) -> WeekSummary:
    """Roll the half-hours up to the numbers on the planner (PLN-03). Only half-hours with a known
    requirement take part: where the forecast does not reach, nothing is claimed."""
    known = {key: need for key, need in required.items() if need is not None}
    under = 0
    gap = 0
    worst: tuple[SlotKey, int] | None = None
    scheduled_total = 0
    for key in sorted(known):
        have = scheduled.get(key, 0)
        scheduled_total += have
        shortfall = known[key] - have
        if shortfall > 0:
            under += 1
            gap += shortfall
            if worst is None or shortfall > -worst[1]:
                worst = (key, -shortfall)
    return WeekSummary(
        intervals_known=len(known),
        under_intervals=under,
        gap=gap,
        required_total=sum(known.values()),
        scheduled_total=scheduled_total,
        worst=worst,
    )
