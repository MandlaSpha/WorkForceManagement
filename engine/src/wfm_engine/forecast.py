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
from collections.abc import Callable, Collection, Iterable
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
    bias_pct: float | None = None  # over all days, forecast total vs actual: + ran high, - ran low


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


def spread_day_total(
    history: Iterable[SlotHistory],
    observed_days: Collection[date],
    target: date,
    total: float,
    *,
    weeks: int = DEFAULT_WEEKS,
    decay: float = DEFAULT_DECAY,
) -> list[SlotForecast] | None:
    """A day's forecast total spread over its half-hours in the shape of the recent same-weekday
    days (the intraday profile), so a model that forecasts day totals can drive the whole day.

    None when the shape is unknown: no earlier same-weekday day, or those days had no calls, so
    there is nothing to say where in the day the calls fall. Handling times come from the profile.
    """
    if total < 0:
        raise ValueError("total must not be negative")
    profile = baseline_day(history, observed_days, target, weeks=weeks, decay=decay)
    if profile is None:
        return None
    shape = sum(s.volume for s in profile)
    if shape == 0:
        return None
    factor = total / shape
    return [SlotForecast(s.slot, s.volume * factor, s.aht_s, s.days_used) for s in profile]


DEFAULT_LEVEL_DAYS = 20  # recent days of the same kind that set the day's usual level
DEFAULT_LEVEL_DECAY = 0.9
DEFAULT_LEVEL_WEIGHT = 0.5  # how much of the day's total comes from that level
DEFAULT_SHAPE_WEEKS = 8  # weeks of same-kind days whose intraday shape is pooled
DEFAULT_SHAPE_DECAY = 0.9


def _day_kind(day: date) -> int:
    """Monday to Friday are one kind of day; Saturday and Sunday each stand alone."""
    return 0 if day.weekday() < 5 else day.weekday()


def smoothed_day(
    history: Iterable[SlotHistory],
    observed_days: Collection[date],
    target: date,
    *,
    weeks: int = DEFAULT_WEEKS,
    decay: float = DEFAULT_DECAY,
    level_days: int = DEFAULT_LEVEL_DAYS,
    level_decay: float = DEFAULT_LEVEL_DECAY,
    level_weight: float = DEFAULT_LEVEL_WEIGHT,
    shape_weeks: int = DEFAULT_SHAPE_WEEKS,
) -> list[SlotForecast] | None:
    """A steadier forecast than `baseline_day`, for queues with few calls per half-hour (FC-02).

    The baseline averages only the last few days with the same weekday, so on a small queue one odd
    day moves the whole forecast and a half-hour holds a call or two of noise. This model does two
    things differently:

    - **The day's total** blends the baseline's total with the usual level of the recent days of
      the same kind (Monday to Friday, or that Saturday or Sunday), taking `level_weight` from the
      level. A weekday pattern is kept (half of the total still follows the same weekday); a
      single odd day is diluted by the others.
    - **The shape of the day** (where in the day the calls fall) is pooled over `shape_weeks`
      weeks of days of the same kind instead of four same-weekday days, so a half-hour is judged
      on many days, not four.

    Handling times are the baseline's. Same honesty rules: only days BEFORE `target` and only
    observed days count, and None when no earlier day with the same weekday has data, or when the
    days that set the shape had no calls (nothing says where in the day the calls fall).
    """
    if not 0 <= level_weight <= 1:
        raise ValueError("level_weight must be between 0 and 1")
    if level_days < 1 or shape_weeks < 1:
        raise ValueError("level_days and shape_weeks must be at least 1")
    if not 0 < level_decay <= 1:
        raise ValueError("level_decay must be in (0, 1]")

    base = baseline_day(history, observed_days, target, weeks=weeks, decay=decay)
    if base is None:
        return None
    baseline_total = sum(s.volume for s in base)

    kind = _day_kind(target)
    same_kind = sorted(
        (d for d in observed_days if d < target and _day_kind(d) == kind), reverse=True
    )
    by_day: dict[date, dict[int, int]] = defaultdict(dict)
    for r in history:
        by_day[r.day][r.slot] = r.offered
    totals = {day: float(sum(by_day[day].values())) for day in same_kind}

    level_pool = same_kind[:level_days]
    level_weights = [level_decay**age for age in range(len(level_pool))]
    level = sum(w * totals[d] for w, d in zip(level_weights, level_pool, strict=True)) / sum(
        level_weights
    )
    total = (1 - level_weight) * baseline_total + level_weight * level

    # Weekdays are five days a week, so the pool of weekday days is five times as deep.
    shape_pool = same_kind[: shape_weeks * (5 if kind == 0 else 1)]
    shape = [0.0] * SLOTS_PER_DAY
    shape_weight = 0.0
    for age, day in enumerate(shape_pool):
        if totals[day] <= 0:
            continue
        w = DEFAULT_SHAPE_DECAY**age
        shape_weight += w
        for slot, offered in by_day[day].items():
            shape[slot] += w * offered / totals[day]
    if shape_weight == 0:
        return None
    return [
        SlotForecast(s.slot, total * shape[s.slot] / shape_weight, s.aht_s, s.days_used)
        for s in base
    ]


def bias_pct(pairs: Iterable[tuple[float, float]]) -> float | None:
    """How far the forecasts ran from what happened, in total: +10 means 10% too many calls
    forecast, -10 means 10% too few. Unlike accuracy it keeps the sign, because a forecast that is
    always high and one that is always low are wrong in different ways and are fixed differently.
    None when nothing was actually offered."""
    forecast = actual = 0.0
    for f, a in pairs:
        forecast += f
        actual += a
    return None if actual == 0 else 100.0 * (forecast - actual) / actual


def backtest(
    history: Collection[SlotHistory],
    observed_days: Collection[date],
    *,
    weeks: int = DEFAULT_WEEKS,
    decay: float = DEFAULT_DECAY,
) -> Backtest:
    """The baseline forecast scored against what happened (see `backtest_with`)."""
    return backtest_with(
        history,
        observed_days,
        lambda day: baseline_day(history, observed_days, day, weeks=weeks, decay=decay),
    )


def backtest_with(
    history: Collection[SlotHistory],
    observed_days: Collection[date],
    forecast_day: Callable[[date], list[SlotForecast] | None],
    *,
    only_days: Collection[date] | None = None,
) -> Backtest:
    """Forecast every observed day with `forecast_day` and score it against what happened.

    `forecast_day` must use only the days BEFORE the one it forecasts; that is the caller's
    promise and the reason a score here can be trusted. `only_days` restricts the scoring, so two
    models can be compared on exactly the same days.

    Two scores, because they answer different questions (FC-05). The half-hour score asks how well
    each interval was predicted; it is low for small queues, where a half-hour holds a call or two
    and chance variation swamps any forecast. The daily score asks how well the day's TOTAL was
    predicted, which is what planning a day's staffing level leans on.

    Days the model could not forecast (it returns None) are skipped.
    """
    actual: dict[date, dict[int, int]] = defaultdict(dict)
    for row in history:
        actual[row.day][row.slot] = row.offered

    days: list[DayAccuracy] = []
    pooled_intervals: list[tuple[float, float]] = []
    pooled_days: list[tuple[float, float]] = []
    for day in sorted(observed_days):
        if only_days is not None and day not in only_days:
            continue
        forecast = forecast_day(day)
        if forecast is None:
            continue
        pairs = [(f.volume, float(actual[day].get(f.slot, 0))) for f in forecast]
        total = (sum(f.volume for f in forecast), float(sum(actual[day].values())))
        days.append(
            DayAccuracy(day, accuracy_pct(pairs), accuracy_pct([total]), forecast[0].days_used)
        )
        pooled_intervals.extend(pairs)
        pooled_days.append(total)
    return Backtest(
        days, accuracy_pct(pooled_intervals), accuracy_pct(pooled_days), bias_pct(pooled_days)
    )
