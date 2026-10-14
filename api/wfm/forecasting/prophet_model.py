"""Prophet for day totals (ADR 0002). It forecasts how many calls a day brings; the intraday profile
in `wfm_engine.forecast.spread_day_total` then spreads that over the half-hours.

Only days that have data are given to the model: a day that was never imported is a gap, not a
quiet day (DAT-10). Nothing here touches the database or the clock, so it can be tested directly.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
from prophet import Prophet

# Prophet and its Stan back end are chatty at INFO and warn about an optional plotting library.
for _noisy in ("cmdstanpy", "prophet", "prophet.plot"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

MODEL = "prophet-v1"
MIN_TRAIN_DAYS = 14  # fewer observed days than this and no pattern can be told from noise
YEARLY_AFTER_DAYS = 730  # a yearly cycle needs two years to be told from a trend
MONTHLY_AFTER_DAYS = 90  # month-end and payment-cycle effects need a few months to show
MAX_ORIGINS = 6  # weekly refits in a backtest; each fit takes about a second
INTERVAL_WIDTH = 0.8
# Call volumes move in proportion: a quiet weekend is a fraction of the weekday level, so the dip
# grows as the queue grows. Additive seasonality under-forecast a growing queue by 7%.
SEASONALITY_MODE: Literal["additive", "multiplicative"] = "multiplicative"


@dataclass(frozen=True, slots=True)
class DayTotal:
    day: date
    expected: float  # calls expected in the day
    lower: float  # bottom of the 80% range
    upper: float


def predict_totals(
    totals: Mapping[date, float], targets: Collection[date]
) -> tuple[dict[date, DayTotal], dict[str, Any]] | None:
    """Fit on `totals` (calls per observed day) and forecast each of `targets`.

    Returns the forecasts and the settings used, or None when there are fewer than
    `MIN_TRAIN_DAYS` observed days to learn from.
    """
    if len(totals) < MIN_TRAIN_DAYS or not targets:
        return None
    days = sorted(totals)
    span = (days[-1] - days[0]).days + 1
    yearly = span >= YEARLY_AFTER_DAYS
    monthly = span >= MONTHLY_AFTER_DAYS
    settings = {
        "model": MODEL,
        "holidays": "ZA",
        "weeklySeasonality": True,
        "monthlySeasonality": monthly,
        "yearlySeasonality": yearly,
        "seasonalityMode": SEASONALITY_MODE,
        "intervalWidth": INTERVAL_WIDTH,
        "trainedOnDays": len(days),
        "trainedThrough": days[-1].isoformat(),
    }

    model = Prophet(
        yearly_seasonality=yearly,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=INTERVAL_WIDTH,
        seasonality_mode=SEASONALITY_MODE,
        uncertainty_samples=300,
    )
    model.add_country_holidays(country_name="ZA")
    if monthly:
        model.add_seasonality(name="monthly", period=30.5, fourier_order=3)
    model.fit(pd.DataFrame({"ds": pd.to_datetime(days), "y": [float(totals[d]) for d in days]}))

    wanted = sorted(targets)
    result = model.predict(pd.DataFrame({"ds": pd.to_datetime(wanted)}))
    yhat = result["yhat"].tolist()
    lower = result["yhat_lower"].tolist()
    upper = result["yhat_upper"].tolist()
    forecasts = {
        day: DayTotal(day, max(0.0, mid), max(0.0, low), max(0.0, high))
        for day, mid, low, high in zip(wanted, yhat, lower, upper, strict=True)
    }
    return forecasts, settings


def rolling_forecasts(
    totals: Mapping[date, float], score_days: Collection[date]
) -> dict[date, DayTotal]:
    """What Prophet WOULD have said for each of `score_days`, refitting once a week on only the
    days before that week (a rolling origin), so a score of it cannot peek at the future.

    Weeks are Monday to Sunday. A week with fewer than `MIN_TRAIN_DAYS` earlier observed days is
    skipped, and only the latest `MAX_ORIGINS` weeks are done.
    """
    weeks: dict[date, list[date]] = {}
    for day in sorted(score_days):
        weeks.setdefault(day - timedelta(days=day.weekday()), []).append(day)

    said: dict[date, DayTotal] = {}
    for monday in sorted(weeks)[-MAX_ORIGINS:]:
        before = {d: v for d, v in totals.items() if d < monday}
        fitted = predict_totals(before, weeks[monday])
        if fitted is not None:
            said.update(fitted[0])
    return said
