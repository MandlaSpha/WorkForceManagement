"""Choosing and running a forecast model for a set of days (ADR 0002).

No database and no clock here: it takes the queue's history and returns forecasts and the facts
that explain them, so the choice between Prophet and the baseline can be tested on its own.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Collection, Iterable
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from wfm_engine.forecast import (
    DEFAULT_DECAY,
    DEFAULT_WEEKS,
    Backtest,
    SlotForecast,
    SlotHistory,
    backtest_with,
    baseline_day,
    smoothed_day,
    spread_day_total,
)

from wfm.core.errors import ApiError

from . import prophet_model

BASELINE = "baseline-v1"
SMOOTHED = "smoothed-v1"
MIN_SCORED_DAYS = 7  # fewer compared days and "Prophet is better" would be a guess

METHODS = ("baseline", "smoothed", "prophet")


@dataclass(frozen=True, slots=True)
class DayForecast:
    slots: list[SlotForecast]
    lower: float | None = None  # bottom of the range for the day's total; None for the baseline
    upper: float | None = None


@dataclass(slots=True)
class Built:
    method: str  # the model that really produced the forecast
    days: dict[date, DayForecast]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Tuning:
    """How a queue's forecast is tuned (requirement RPT-07). The defaults are what the baseline
    always did; a queue keeps its own only once someone has saved one."""

    weeks: int = DEFAULT_WEEKS  # how many earlier same-weekday days the forecast looks back over
    decay: float = DEFAULT_DECAY  # how much less each older day counts (1 = all alike)
    volume_multiplier: float = 1.0  # corrects a forecast that runs high or low
    aht_multiplier: float = 1.0  # corrects the handling time

    def scaled(self, slots: list[SlotForecast]) -> list[SlotForecast]:
        """The forecast with the multipliers applied; unchanged when both are 1."""
        if self.volume_multiplier == 1.0 and self.aht_multiplier == 1.0:
            return slots
        return [
            replace(
                s,
                volume=s.volume * self.volume_multiplier,
                aht_s=None if s.aht_s is None else s.aht_s * self.aht_multiplier,
            )
            for s in slots
        ]

    def as_params(self) -> dict[str, float | int]:
        return {
            "weeks": self.weeks,
            "decay": self.decay,
            "volumeMultiplier": self.volume_multiplier,
            "ahtMultiplier": self.aht_multiplier,
        }


DEFAULT_TUNING = Tuning()

MIN_WEEKS, MAX_WEEKS = 1, 12
MIN_DECAY, MAX_DECAY = 0.1, 1.0
MIN_MULTIPLIER, MAX_MULTIPLIER = 0.5, 2.0


def check_tuning(tuning: Tuning) -> None:
    def refuse(code: str, detail: str) -> ApiError:
        return ApiError(422, code, "Invalid tuning", detail)

    if not MIN_WEEKS <= tuning.weeks <= MAX_WEEKS:
        raise refuse("tuning.weeks_invalid", f"Look back over {MIN_WEEKS} to {MAX_WEEKS} weeks.")
    if not MIN_DECAY <= tuning.decay <= MAX_DECAY:
        raise refuse("tuning.decay_invalid", f"Recency weight is {MIN_DECAY} to {MAX_DECAY}.")
    for name, value in (
        ("volume", tuning.volume_multiplier),
        ("aht", tuning.aht_multiplier),
    ):
        if not MIN_MULTIPLIER <= value <= MAX_MULTIPLIER:
            raise refuse(
                f"tuning.{name}_multiplier_invalid",
                f"The {name} multiplier is {MIN_MULTIPLIER} to {MAX_MULTIPLIER}.",
            )


def daily_totals(history: Iterable[SlotHistory]) -> dict[date, float]:
    totals: dict[date, float] = defaultdict(float)
    for row in history:
        totals[row.day] += row.offered
    return dict(totals)


def baseline_forecaster(
    history: list[SlotHistory], observed: Collection[date], tuning: Tuning
) -> Callable[[date], list[SlotForecast] | None]:
    """The tuned baseline as a function of the day, for forecasting and for scoring."""

    def forecast(day: date) -> list[SlotForecast] | None:
        slots = baseline_day(history, observed, day, weeks=tuning.weeks, decay=tuning.decay)
        return None if slots is None else tuning.scaled(slots)

    return forecast


def smoothed_forecaster(
    history: list[SlotHistory], observed: Collection[date], tuning: Tuning
) -> Callable[[date], list[SlotForecast] | None]:
    """The smoothed model (day-level level and a pooled intraday shape) as a function of the day,
    with the queue's tuning applied. Same looking-back settings as the baseline."""

    def forecast(day: date) -> list[SlotForecast] | None:
        slots = smoothed_day(history, observed, day, weeks=tuning.weeks, decay=tuning.decay)
        return None if slots is None else tuning.scaled(slots)

    return forecast


def baseline_days(
    history: list[SlotHistory],
    observed: Collection[date],
    days: Iterable[date],
    tuning: Tuning = DEFAULT_TUNING,
) -> dict[date, DayForecast]:
    forecast = baseline_forecaster(history, observed, tuning)
    forecasts = ((day, forecast(day)) for day in days)
    return {day: DayForecast(slots) for day, slots in forecasts if slots is not None}


def baseline_backtest(
    history: list[SlotHistory], observed: Collection[date], tuning: Tuning = DEFAULT_TUNING
) -> Backtest:
    """The tuned baseline scored on every past day it could have forecast."""
    return backtest_with(history, observed, baseline_forecaster(history, observed, tuning))


def smoothed_backtest(
    history: list[SlotHistory], observed: Collection[date], tuning: Tuning = DEFAULT_TUNING
) -> Backtest:
    """The smoothed model scored on every past day it could have forecast."""
    return backtest_with(history, observed, smoothed_forecaster(history, observed, tuning))


def prophet_backtest(
    history: list[SlotHistory], observed: Collection[date], tuning: Tuning = DEFAULT_TUNING
) -> tuple[Backtest, Backtest]:
    """Prophet and the baseline, each forecasting the same past days from only the days before
    them. Returns (prophet, baseline). Days Prophet could not forecast are in neither."""
    totals = daily_totals(history)
    said = prophet_model.rolling_forecasts(totals, observed)

    def prophet_day(day: date) -> list[SlotForecast] | None:
        if day not in said:
            return None
        slots = spread_day_total(
            history, observed, day, said[day].expected, weeks=tuning.weeks, decay=tuning.decay
        )
        return None if slots is None else tuning.scaled(slots)

    scored = set(said)
    prophet = backtest_with(history, observed, prophet_day, only_days=scored)
    baseline = backtest_with(
        history, observed, baseline_forecaster(history, observed, tuning), only_days=scored
    )
    return prophet, baseline


def build(
    history: list[SlotHistory],
    observed: set[date],
    days: list[date],
    method: str,
    tuning: Tuning = DEFAULT_TUNING,
) -> Built:
    """Forecast `days` with the requested model, or with the baseline when Prophet cannot show
    that it does better (recorded in `params["fallback"]`, never silent). The queue's tuning
    shapes both, and is recorded with the forecast so it can be explained later."""
    baseline = Built(
        BASELINE,
        baseline_days(history, observed, days, tuning),
        {"tuning": tuning.as_params()},
    )
    if method == "smoothed":
        forecast = smoothed_forecaster(history, observed, tuning)
        days_forecast = ((day, forecast(day)) for day in days)
        return Built(
            SMOOTHED,
            {day: DayForecast(slots) for day, slots in days_forecast if slots is not None},
            {"tuning": tuning.as_params()},
        )
    if method != "prophet":
        return baseline

    totals = daily_totals(history)
    fitted = prophet_model.predict_totals(totals, days)
    if fitted is None:
        return _fell_back(
            baseline,
            "too_little_history",
            f"Prophet needs at least {prophet_model.MIN_TRAIN_DAYS} days of call data.",
        )

    prophet_bt, baseline_bt = prophet_backtest(history, observed, tuning)
    evidence = {
        "prophetDailyPct": prophet_bt.daily_pct,
        "baselineDailyPct": baseline_bt.daily_pct,
        "daysScored": len(prophet_bt.days),
    }
    if len(prophet_bt.days) < MIN_SCORED_DAYS or prophet_bt.daily_pct is None:
        return _fell_back(
            baseline,
            "too_little_to_compare",
            f"Fewer than {MIN_SCORED_DAYS} past days could be used to check Prophet against the "
            "baseline.",
            evidence,
        )
    if baseline_bt.daily_pct is not None and prophet_bt.daily_pct <= baseline_bt.daily_pct:
        return _fell_back(
            baseline, "not_better", "Prophet did not beat the baseline on past days.", evidence
        )

    totals_by_day, settings = fitted
    spread: dict[date, DayForecast] = {}
    for day, total in totals_by_day.items():
        slots = spread_day_total(
            history, observed, day, total.expected, weeks=tuning.weeks, decay=tuning.decay
        )
        if slots is not None:
            spread[day] = DayForecast(
                tuning.scaled(slots),
                total.lower * tuning.volume_multiplier,
                total.upper * tuning.volume_multiplier,
            )
    return Built(
        prophet_model.MODEL,
        spread,
        {"model": settings, "backtest": evidence, "tuning": tuning.as_params()},
    )


def _fell_back(
    baseline: Built, reason: str, message: str, evidence: dict[str, Any] | None = None
) -> Built:
    baseline.params["fallback"] = {
        "requested": "prophet",
        "reason": reason,
        "message": message,
        **(evidence or {}),
    }
    return baseline


@dataclass(frozen=True, slots=True)
class Uplift:
    """An event's effect on demand: `pct` per cent more (or less) calls on each day of the range."""

    event_id: int
    name: str
    date_from: date
    date_to: date
    pct: float

    def covers(self, day: date) -> bool:
        return self.date_from <= day <= self.date_to


def day_factor(day: date, uplifts: Iterable[Uplift]) -> float:
    """What the model's forecast for `day` is multiplied by. Events that overlap compound, so a
    +20% campaign during a -50% outage is 1.2 x 0.5 = 0.6."""
    factor = 1.0
    for uplift in uplifts:
        if uplift.covers(day):
            factor *= 1 + uplift.pct / 100
    return factor


def apply_uplifts(built: Built, uplifts: list[Uplift]) -> list[dict[str, Any]]:
    """Scale the forecast days the events cover, in place, and describe what was applied so the
    version can show it (params["events"]). Events outside the forecast days change nothing and
    are not reported."""
    applied: list[dict[str, Any]] = []
    for uplift in uplifts:
        days = sorted(d for d in built.days if uplift.covers(d))
        if days:
            applied.append(
                {
                    "id": uplift.event_id,
                    "name": uplift.name,
                    "dateFrom": uplift.date_from.isoformat(),
                    "dateTo": uplift.date_to.isoformat(),
                    "upliftPct": uplift.pct,
                    "days": [d.isoformat() for d in days],
                }
            )
    for day, forecast in list(built.days.items()):
        factor = day_factor(day, uplifts)
        if factor != 1.0:
            built.days[day] = DayForecast(
                [replace(s, volume=s.volume * factor) for s in forecast.slots],
                None if forecast.lower is None else forecast.lower * factor,
                None if forecast.upper is None else forecast.upper * factor,
            )
    if applied:
        built.params["events"] = applied
    return applied
