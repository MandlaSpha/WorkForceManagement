"""Invented call history for the demo: a believable contact centre, with no real data in it.

Everything is derived from a fixed random seed, so two runs make the same history. The shapes are
the ones a planner meets in real life: a morning and an afternoon peak, a busy Monday and a quiet
Friday, a thin weekend, public holidays, month-end pressure, one outage day and one day the
recorder was down (no rows at all, which is different from a quiet day).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import holidays

from wfm.telephony.models import IntervalActual, Queue

# Monday first. Calls on a typical day relative to a Wednesday.
WEEKDAY_FACTOR = (1.25, 1.05, 1.0, 0.98, 0.85, 0.35, 0.10)
HISTORY_WEEKS = 12
OUTAGE_DAY_FACTOR = 1.9
HOLIDAY_FACTOR = 0.25
WEEKLY_GROWTH = 0.004


@dataclass(frozen=True, slots=True)
class QueueShape:
    name: str
    day_total: int  # calls on a typical Wednesday
    aht_s: float
    open_slots: tuple[int, ...]  # half-hours from local midnight in which the queue is open
    open_days: tuple[int, ...]  # weekdays, Monday = 0
    month_end_boost: float = 0.0  # extra volume in the last 3 and first 2 days of the month
    peaks: tuple[tuple[float, float, float], ...] = ((20.0, 2.5, 0.55), (29.0, 3.0, 0.45))


SHAPES = (
    QueueShape("Demo Support", 650, 360.0, tuple(range(14, 38)), (0, 1, 2, 3, 4, 5, 6)),
    QueueShape(
        "Demo Billing",
        380,
        480.0,
        tuple(range(16, 34)),
        (0, 1, 2, 3, 4),
        month_end_boost=0.35,
        peaks=((21.0, 2.5, 0.6), (28.0, 2.5, 0.4)),
    ),
    QueueShape(
        "Demo Night Desk",
        120,
        420.0,
        tuple(range(36, 48)) + tuple(range(0, 12)),
        (0, 1, 2, 3, 4, 5, 6),
        peaks=((40.0, 3.0, 0.5), (4.0, 3.0, 0.5)),
    ),
)


def _weights(shape: QueueShape) -> dict[int, float]:
    raw = {}
    for slot in shape.open_slots:
        value = 0.15
        for centre, spread, height in shape.peaks:
            distance = min(abs(slot - centre), 48 - abs(slot - centre))
            value += height * math.exp(-((distance / spread) ** 2) / 2)
        raw[slot] = value
    total = sum(raw.values())
    return {slot: value / total for slot, value in raw.items()}


def _month_end(day: date) -> bool:
    next_day = day + timedelta(days=1)
    in_last_days = (day + timedelta(days=3)).month != day.month
    return in_last_days or day.day <= 2 or next_day.day == 1


def history_days(today: date) -> list[date]:
    return [today - timedelta(days=n) for n in range(HISTORY_WEEKS * 7, 0, -1)]


def outage_day(today: date) -> date:
    """A weekday about a third of the way back: a system fault doubles the calls and many drop."""
    day = today - timedelta(days=HISTORY_WEEKS * 7 // 3 * 2)
    while day.weekday() > 3:
        day -= timedelta(days=1)
    return day


def recorder_gap_day(today: date) -> date:
    """A weekday with no rows at all: the phone system's recorder was down."""
    day = today - timedelta(days=HISTORY_WEEKS * 7 // 5 * 2 + 3)
    while day.weekday() > 3:
        day -= timedelta(days=1)
    return day


def build_history(
    queue: Queue, shape: QueueShape, today: date, zone: ZoneInfo
) -> list[IntervalActual]:
    rng = random.Random(f"wfm-demo-{shape.name}")
    holiday_dates = holidays.country_holidays("ZA", years=range(today.year - 1, today.year + 2))
    weights = _weights(shape)
    days = history_days(today)
    outage, gap = outage_day(today), recorder_gap_day(today)
    rows: list[IntervalActual] = []
    for day in days:
        if day == gap or day.weekday() not in shape.open_days:
            continue
        weeks_back = (today - day).days / 7
        total = shape.day_total * WEEKDAY_FACTOR[day.weekday()] * (1 - WEEKLY_GROWTH * weeks_back)
        if shape.month_end_boost and _month_end(day):
            total *= 1 + shape.month_end_boost
        if day in holiday_dates:
            total *= HOLIDAY_FACTOR
        stressed = day == outage
        if stressed:
            total *= OUTAGE_DAY_FACTOR
        for slot in shape.open_slots:
            expected = total * weights[slot]
            offered = max(0, round(rng.gauss(expected, math.sqrt(max(expected, 1.0)))))
            if offered == 0:
                continue
            # How well staffed the half-hour was drives how many callers waited and gave up. The
            # peaks run tighter than the quiet hours, and the outage day is chaos.
            peak_pressure = expected / (total * max(weights.values()) + 1e-9)
            cover = rng.uniform(0.85, 1.08) - 0.12 * peak_pressure
            if stressed:
                cover -= 0.35
            abandon_rate = min(0.6, max(0.0, (1 - cover) * 0.45))
            abandoned = round(offered * abandon_rate)
            answered = offered - abandoned
            in_sl_rate = min(0.98, max(0.15, 0.9 - (1 - cover) * 1.6))
            answered_in_sl = round(answered * in_sl_rate)
            handle = shape.aht_s * rng.uniform(0.93, 1.07) * (1.15 if stressed else 1.0)
            local = datetime(day.year, day.month, day.day, slot // 2, 30 * (slot % 2), tzinfo=zone)
            rows.append(
                IntervalActual(
                    queue=queue,
                    interval_start=local,
                    offered=offered,
                    answered=answered,
                    abandoned=abandoned,
                    answered_in_sl=answered_in_sl,
                    sum_wait_s=round(answered * (60 * (1 - in_sl_rate) + 8)),
                    sum_handle_s=round(answered * handle),
                )
            )
    return rows
