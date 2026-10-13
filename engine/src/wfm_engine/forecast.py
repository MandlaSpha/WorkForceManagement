"""Baseline forecast and its accuracy (requirements FC-01, FC-02, FC-05; tech spec section 4.3).

Pure functions: no Django, no clock, no I/O.

Idea: for a target day, look at the most recent days with the SAME weekday that have data, and
take a weighted average per half-hour slot, recent days counting more. Two rules keep it honest:

- A day with no imported data is NOT a day with no calls. Only days the caller says were
  observed count; on an observed day a slot with no row really had zero calls.
- Only days BEFORE the target are used. A forecast that peeks at the day it predicts would look
  accurate and be worthless.

Not in this version (so not claimed): the monthly trend factor, event uplifts (FC-04) and
machine-learning models (FC-07).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import date

SLOTS_PER_DAY = 48  # 30-minute intervals
DEFAULT_WEEKS = 4
DEFAULT_DECAY = 0.7


@dataclass(frozen=True, slots=True)
class SlotHistory:
    """What happened in one half-hour slot that had at least one inbound call."""

    day: date
    slot: int  # 0 = 00:00-00:30 ... 47 = 23:30-24:00, in the display time zone
    offered: int
    answered: int
    handle_s: int  # talk + wrap-up of the answered calls, summed


@dataclass(frozen=True, slots=True)
class SlotForecast:
    slot: int
    volume: float  # expected inbound calls in the slot
    aht_s: float | None  # expected handling time; None when no call was ever answered
    days_used: int  # how many past days this rests on (DAT-10)


@dataclass(frozen=True, slots=True)
class DayAccuracy:
    day: date
    accuracy_pct: float | None  # per half-hour, pooled over the day
    daily_pct: float | None  # the day's total calls, forecast against actual
    days_used: int


@dataclass(frozen=True, slots=True)
class Backtest:
    days: list[DayAccuracy]
    interval_pct: float | None  # how well each half-hour was predicted, over all days
    daily_pct: float | None  # how well each day's total was predicted, over all days


def baseline_day(
    history: Iterable[SlotHistory],
    observed_days: Collection[date],
    target: date,
    *,
    weeks: int = DEFAULT_WEEKS,
    decay: float = DEFAULT_DECAY,
) -> list[SlotForecast] | None:
    """The forecast for `target`, or None when no earlier day with the same weekday has data."""
    if weeks < 1:
        raise ValueError("weeks must be at least 1")
    if not 0 < decay <= 1:
        raise ValueError("decay must be in (0, 1]")

    same_weekday = sorted(
        (d for d in observed_days if d < target and d.weekday() == target.weekday()),
        reverse=True,
    )[:weeks]
    if not same_weekday:
        return None
    weights = {day: decay**age for age, day in enumerate(same_weekday)}
    total_weight = sum(weights.values())

    by_slot: dict[int, dict[date, SlotHistory]] = defaultdict(dict)
    for row in history:
        if row.day in weights:
            by_slot[row.slot][row.day] = row

    all_handle = sum(
        weights[r.day] * r.handle_s for rows in by_slot.values() for r in rows.values()
    )
    all_answered = sum(
        weights[r.day] * r.answered for rows in by_slot.values() for r in rows.values()
    )
    overall_aht = all_handle / all_answered if all_answered else None

    forecast: list[SlotForecast] = []
    for slot in range(SLOTS_PER_DAY):
        rows = by_slot.get(slot, {})
        volume = sum(weights[day] * row.offered for day, row in rows.items()) / total_weight
        answered = sum(weights[day] * row.answered for day, row in rows.items())
        handle = sum(weights[day] * row.handle_s for day, row in rows.items())
        aht = handle / answered if answered else overall_aht
        forecast.append(SlotForecast(slot, volume, aht, len(same_weekday)))
    return forecast


def accuracy_pct(pairs: Iterable[tuple[float, float]]) -> float | None:
    """100 minus the weighted absolute percentage error, over (forecast, actual) pairs.

    The classic MAPE divides by each interval's actual, which is zero in quiet half-hours and
    explodes, so the error is pooled instead: total absolute error over total actual volume.
    None when nothing was actually offered; never below 0.
    """
    forecast_error = 0.0
    actual_total = 0.0
    for forecast, actual in pairs:
        forecast_error += abs(forecast - actual)
        actual_total += actual
    if actual_total == 0:
        return None
    return max(0.0, 100.0 * (1.0 - forecast_error / actual_total))


def backtest(
    history: Collection[SlotHistory],
    observed_days: Collection[date],
    *,
    weeks: int = DEFAULT_WEEKS,
    decay: float = DEFAULT_DECAY,
) -> Backtest:
    """Forecast every observed day from the days before it and score it against what happened.

    Two scores, because they answer different questions (FC-05). The half-hour score asks how well
    each interval was predicted; it is low for small queues, where a half-hour holds a call or two
    and chance variation swamps any forecast. The daily score asks how well the day's TOTAL was
    predicted, which is what planning a day's staffing level leans on.

    Days with no earlier same-weekday data are skipped: they cannot be forecast.
    """
    actual: dict[date, dict[int, int]] = defaultdict(dict)
    for row in history:
        actual[row.day][row.slot] = row.offered

    days: list[DayAccuracy] = []
    pooled_intervals: list[tuple[float, float]] = []
    pooled_days: list[tuple[float, float]] = []
    for day in sorted(observed_days):
        forecast = baseline_day(history, observed_days, day, weeks=weeks, decay=decay)
        if forecast is None:
            continue
        pairs = [(f.volume, float(actual[day].get(f.slot, 0))) for f in forecast]
        total = (sum(f.volume for f in forecast), float(sum(actual[day].values())))
        days.append(
            DayAccuracy(day, accuracy_pct(pairs), accuracy_pct([total]), forecast[0].days_used)
        )
        pooled_intervals.extend(pairs)
        pooled_days.append(total)
    return Backtest(days, accuracy_pct(pooled_intervals), accuracy_pct(pooled_days))
