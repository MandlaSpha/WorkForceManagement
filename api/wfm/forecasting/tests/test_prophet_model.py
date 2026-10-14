"""The Prophet wrapper on its own: no database, only the promises the rest relies on."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from wfm.forecasting import prophet_model as pm

START = date(2026, 3, 2)  # a Monday


def totals(weeks: int = 8) -> dict[date, float]:
    return {START + timedelta(days=n): 200.0 + 4 * n for n in range(weeks * 7)}


class TestNeedsEnoughHistory:
    def test_fewer_than_the_minimum_days_gives_no_forecast(self) -> None:
        few = {START + timedelta(days=n): 100.0 for n in range(pm.MIN_TRAIN_DAYS - 1)}
        assert pm.predict_totals(few, [date(2026, 4, 1)]) is None

    def test_nothing_to_forecast_gives_nothing(self) -> None:
        assert pm.predict_totals(totals(), []) is None


class TestNeverPeeks:
    """A backtest that let the model see the day it forecasts would look accurate and be worthless
    (the rule the baseline follows too). The week being scored must not change its own forecast."""

    last_week = tuple(START + timedelta(days=n) for n in range(49, 56))

    def test_changing_the_scored_week_changes_nothing_it_said_about_that_week(self) -> None:
        honest = pm.rolling_forecasts(totals(), self.last_week)
        future_changed = {d: (v * 50 if d in self.last_week else v) for d, v in totals().items()}
        again = pm.rolling_forecasts(future_changed, self.last_week)

        assert set(honest) == set(self.last_week)
        for day in self.last_week:
            assert again[day].expected == pytest.approx(honest[day].expected)

    def test_but_the_days_before_it_do_count(self) -> None:
        honest = pm.rolling_forecasts(totals(), self.last_week)
        before_changed = {d: (v * 3 if d < self.last_week[0] else v) for d, v in totals().items()}
        again = pm.rolling_forecasts(before_changed, self.last_week)
        assert again[self.last_week[0]].expected > honest[self.last_week[0]].expected * 2


class TestRollingOrigins:
    def test_a_week_with_too_little_before_it_is_skipped_not_guessed(self) -> None:
        first_week = [START + timedelta(days=n) for n in range(7)]
        assert pm.rolling_forecasts(totals(), first_week) == {}

    def test_only_the_latest_weeks_are_refitted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(pm, "MAX_ORIGINS", 2)
        many = totals(weeks=6)
        said = pm.rolling_forecasts(many, list(many))
        weeks = {d - timedelta(days=d.weekday()) for d in said}
        assert weeks == {START + timedelta(weeks=4), START + timedelta(weeks=5)}


class TestShapeOfAForecast:
    def test_a_forecast_is_never_negative_and_the_range_brackets_it(self) -> None:
        falling = {START + timedelta(days=n): max(1.0, 100.0 - 3 * n) for n in range(40)}
        fitted = pm.predict_totals(falling, [START + timedelta(days=n) for n in (60, 90)])
        assert fitted is not None
        for forecast in fitted[0].values():
            assert 0 <= forecast.lower <= forecast.expected <= forecast.upper

    def test_yearly_and_monthly_cycles_wait_for_enough_history(self) -> None:
        short = pm.predict_totals(totals(weeks=8), [date(2026, 5, 4)])
        assert short is not None
        assert (short[1]["monthlySeasonality"], short[1]["yearlySeasonality"]) == (False, False)
        assert short[1]["trainedOnDays"] == 56
        assert short[1]["trainedThrough"] == "2026-04-26"
