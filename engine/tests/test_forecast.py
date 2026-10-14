from datetime import date

import pytest

from wfm_engine.forecast import (
    SLOTS_PER_DAY,
    Backtest,
    SlotForecast,
    SlotHistory,
    accuracy_pct,
    backtest,
    backtest_with,
    baseline_day,
    bias_pct,
    spread_day_total,
)

# Mondays in May 2026: 4, 11, 18, 25. The target is Monday 25 May.
MON_4, MON_11, MON_18, MON_25 = (
    date(2026, 5, 4),
    date(2026, 5, 11),
    date(2026, 5, 18),
    date(2026, 5, 25),
)
SLOT = 20  # 10:00-10:30


def row(
    day: date, offered: int, *, slot: int = SLOT, answered: int | None = None, aht: int = 180
) -> SlotHistory:
    answered = offered if answered is None else answered
    return SlotHistory(day, slot, offered, answered, answered * aht)


def slot_of(forecast: list, slot: int = SLOT):
    return forecast[slot]


class TestBaselineByHand:
    """Slot 10:00 on the three Mondays before 25 May, most recent first: 10, 20 and 40 calls with
    handle times of 180, 240 and 300 s. Decay 0.5 gives weights 1, 0.5, 0.25 (sum 1.75).

    volume = (10 + 0.5*20 + 0.25*40) / 1.75 = 30 / 1.75 = 17.142857
    AHT    = (10*180 + 0.5*20*240 + 0.25*40*300) / (10 + 0.5*20 + 0.25*40) = 7200 / 30 = 240
    """

    history = (row(MON_18, 10, aht=180), row(MON_11, 20, aht=240), row(MON_4, 40, aht=300))
    observed = (MON_4, MON_11, MON_18)

    def test_recent_days_count_more(self) -> None:
        forecast = baseline_day(self.history, self.observed, MON_25, weeks=3, decay=0.5)
        assert forecast is not None
        assert slot_of(forecast).volume == pytest.approx(30 / 1.75)
        assert slot_of(forecast).aht_s == pytest.approx(240.0)

    def test_says_how_many_days_it_rests_on(self) -> None:
        forecast = baseline_day(self.history, self.observed, MON_25, weeks=3, decay=0.5)
        assert forecast is not None
        assert {f.days_used for f in forecast} == {3}

    def test_only_the_most_recent_weeks_are_used(self) -> None:
        forecast = baseline_day(self.history, self.observed, MON_25, weeks=2, decay=0.5)
        assert forecast is not None
        assert slot_of(forecast).volume == pytest.approx((10 + 0.5 * 20) / 1.5)

    def test_covers_every_half_hour_of_the_day(self) -> None:
        forecast = baseline_day(self.history, self.observed, MON_25)
        assert forecast is not None
        assert [f.slot for f in forecast] == list(range(SLOTS_PER_DAY))
        assert slot_of(forecast, 3).volume == 0  # a quiet half-hour on days that had data


class TestMissingDaysAreNotQuietDays:
    def test_a_day_without_data_is_skipped_not_counted_as_zero_calls(self) -> None:
        # 11 May was never imported (not in observed_days). Treating it as zero calls would drag
        # the forecast down. Using 18 May and 4 May: (10 + 0.5*40) / 1.5 = 20.
        history = [row(MON_18, 10), row(MON_4, 40)]
        forecast = baseline_day(history, [MON_4, MON_18], MON_25, weeks=3, decay=0.5)
        assert forecast is not None
        assert slot_of(forecast).volume == pytest.approx(20.0)

    def test_on_a_day_that_has_data_a_slot_with_no_row_really_had_no_calls(self) -> None:
        # Both Mondays were observed, but only 18 May had calls at 10:00: (6 + 0.5*0) / 1.5 = 4.
        forecast = baseline_day([row(MON_18, 6)], [MON_11, MON_18], MON_25, weeks=2, decay=0.5)
        assert forecast is not None
        assert slot_of(forecast).volume == pytest.approx(4.0)

    def test_no_history_means_no_forecast_not_a_forecast_of_zero(self) -> None:
        assert baseline_day([], [], MON_25) is None

    def test_other_weekdays_do_not_count(self) -> None:
        tuesday = date(2026, 5, 19)
        assert baseline_day([row(tuesday, 50)], [tuesday], MON_25) is None


class TestNoPeekingAtTheFuture:
    def test_the_target_day_and_later_days_are_ignored(self) -> None:
        past = [row(MON_18, 10), row(MON_11, 20)]
        with_future = [*past, row(MON_25, 999), row(date(2026, 6, 1), 999)]
        observed = [MON_11, MON_18]
        with_future_observed = [*observed, MON_25, date(2026, 6, 1)]

        clean = baseline_day(past, observed, MON_25)
        peeking = baseline_day(with_future, with_future_observed, MON_25)

        assert clean == peeking


class TestHandlingTime:
    def test_a_slot_where_nothing_was_answered_falls_back_to_the_overall_handling_time(
        self,
    ) -> None:
        history = [
            row(MON_18, 8, slot=4, aht=200),  # answered, 200 s
            row(MON_18, 5, slot=30, answered=0),  # five calls, all abandoned
        ]
        forecast = baseline_day(history, [MON_18], MON_25)
        assert forecast is not None
        assert forecast[30].volume == pytest.approx(5.0)
        assert forecast[30].aht_s == pytest.approx(200.0)

    def test_no_answered_call_anywhere_means_no_handling_time(self) -> None:
        forecast = baseline_day([row(MON_18, 5, answered=0)], [MON_18], MON_25)
        assert forecast is not None
        assert forecast[SLOT].aht_s is None

    @pytest.mark.parametrize(("weeks", "decay"), [(0, 0.5), (1, 0.0), (1, 1.5)])
    def test_rejects_nonsense_settings(self, weeks: int, decay: float) -> None:
        with pytest.raises(ValueError, match="must"):
            baseline_day([], [], MON_25, weeks=weeks, decay=decay)


class TestAccuracy:
    def test_perfect(self) -> None:
        assert accuracy_pct([(10, 10), (4, 4)]) == pytest.approx(100.0)

    def test_pools_the_error_over_the_actual_volume(self) -> None:
        # |10-5| + |10-15| = 10 over 20 actual calls: 50%.
        assert accuracy_pct([(10, 5), (10, 15)]) == pytest.approx(50.0)

    def test_quiet_half_hours_do_not_blow_it_up(self) -> None:
        # MAPE would divide by the zero actual; the pooled error does not.
        assert accuracy_pct([(0, 0), (1, 0), (9, 10)]) == pytest.approx(100 * (1 - 2 / 10))

    def test_is_never_negative(self) -> None:
        assert accuracy_pct([(100, 1)]) == 0.0

    def test_has_no_value_when_nothing_was_offered(self) -> None:
        assert accuracy_pct([(5, 0)]) is None


class TestBacktest:
    @staticmethod
    def steady(volume_on_18th: int = 10) -> tuple[list[SlotHistory], list[date]]:
        history = [row(MON_4, 10), row(MON_11, 10), row(MON_18, volume_on_18th)]
        return history, [MON_4, MON_11, MON_18]

    def test_scores_each_day_against_only_the_days_before_it(self) -> None:
        history, observed = self.steady()
        result = backtest(history, observed, weeks=4, decay=0.7)
        days, overall = result.days, result.interval_pct
        # 4 May has nothing before it, so it cannot be forecast and is skipped.
        assert [d.day for d in days] == [MON_11, MON_18]
        assert [d.days_used for d in days] == [1, 2]
        assert [d.accuracy_pct for d in days] == [pytest.approx(100.0)] * 2
        assert overall == pytest.approx(100.0)

    def test_a_spike_the_forecast_could_not_know_about_costs_accuracy(self) -> None:
        # 18 May has 20 calls at 10:00 but both earlier Mondays had 10: forecast 10, actual 20,
        # so the error is 10 over 20 actual calls = 50%.
        history, observed = self.steady(volume_on_18th=20)
        days = backtest(history, observed, weeks=4, decay=0.7).days
        assert days[-1].accuracy_pct == pytest.approx(50.0)

    def test_a_later_day_never_changes_an_earlier_days_score(self) -> None:
        calm, observed = self.steady(10)
        spiky, _ = self.steady(500)
        calm_days = backtest(calm, observed).days
        spiky_days = backtest(spiky, observed).days
        assert calm_days[0] == spiky_days[0]  # 11 May is scored the same whatever 18 May did

    def test_nothing_to_score_gives_nothing(self) -> None:
        assert backtest([row(MON_4, 10)], [MON_4]) == Backtest([], None, None)


class TestTheDailyScore:
    """Why there are two numbers. Earlier Monday: 10 calls at 10:00 and 10 at 10:30. The Monday
    scored: 5 at 10:00 and 15 at 10:30. The forecast is 10 and 10.

    per half-hour: errors 5 + 5 = 10 over 20 actual calls -> 50%
    per day:       forecast total 20, actual total 20      -> 100%
    """

    history = (
        row(MON_4, 10, slot=20),
        row(MON_4, 10, slot=21),
        row(MON_11, 5, slot=20),
        row(MON_11, 15, slot=21),
    )
    observed = (MON_4, MON_11)

    def test_a_day_can_be_wrong_by_the_half_hour_but_right_in_total(self) -> None:
        result = backtest(self.history, self.observed)
        (day,) = result.days
        assert day.accuracy_pct == pytest.approx(50.0)
        assert day.daily_pct == pytest.approx(100.0)

    def test_the_overall_scores_pool_every_scored_day(self) -> None:
        result = backtest(self.history, self.observed)
        assert result.interval_pct == pytest.approx(50.0)
        assert result.daily_pct == pytest.approx(100.0)

    def test_a_day_that_is_off_in_total_is_scored_down(self) -> None:
        # Forecast total 20 against an actual total of 40: error 20 over 40 actual -> 50%.
        history = (*self.history[:2], row(MON_11, 20, slot=20), row(MON_11, 20, slot=21))
        (day,) = backtest(history, self.observed).days
        assert day.daily_pct == pytest.approx(50.0)

    def test_a_day_with_no_calls_has_no_daily_score(self) -> None:
        history = (row(MON_4, 10, slot=20), row(MON_11, 0, slot=20))
        (day,) = backtest(history, self.observed).days
        assert day.daily_pct is None


class TestSpreadingADayTotal:
    """Monday 18 May had 30 calls at 10:00 and 10 at 11:00 (shape 3 : 1). A day total of 80 for
    25 May is therefore 60 at 10:00 and 20 at 11:00, and the handling time stays 180 s."""

    history = (row(MON_18, 30), row(MON_18, 10, slot=22))
    observed = (MON_18,)

    def test_follows_the_recent_shape_and_adds_up_to_the_total(self) -> None:
        forecast = spread_day_total(self.history, self.observed, MON_25, 80)
        assert forecast is not None
        assert forecast[20].volume == pytest.approx(60)
        assert forecast[22].volume == pytest.approx(20)
        assert forecast[20].aht_s == pytest.approx(180)
        assert sum(s.volume for s in forecast) == pytest.approx(80)

    def test_a_total_of_zero_is_a_quiet_day_not_a_missing_one(self) -> None:
        forecast = spread_day_total(self.history, self.observed, MON_25, 0)
        assert forecast is not None
        assert sum(s.volume for s in forecast) == 0

    def test_no_same_weekday_means_no_shape_so_no_forecast(self) -> None:
        assert spread_day_total(self.history, self.observed, date(2026, 5, 26), 80) is None

    def test_a_day_with_no_calls_gives_no_shape_so_no_forecast(self) -> None:
        # Observed and quiet all day: there is nothing to say where 80 calls would fall.
        assert spread_day_total((), (MON_18,), MON_25, 80) is None

    def test_a_negative_total_is_refused(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            spread_day_total(self.history, self.observed, MON_25, -1)


class TestScoringAnyModel:
    """A model that always says 10 calls at 10:00 is scored against 10, 20 and 10 actual calls
    on three Mondays: errors 0, 10, 0 over 40 actual calls, so 75%."""

    history = (row(MON_4, 10), row(MON_11, 20), row(MON_18, 10))
    observed = (MON_4, MON_11, MON_18)

    @staticmethod
    def always_ten(_day: date) -> list[SlotForecast]:
        return [SlotForecast(s, 10.0 if s == SLOT else 0.0, 180.0, 1) for s in range(SLOTS_PER_DAY)]

    def test_scores_the_forecast_it_is_given(self) -> None:
        result = backtest_with(self.history, self.observed, self.always_ten)
        assert result.daily_pct == pytest.approx(75.0)
        assert [d.day for d in result.days] == [MON_4, MON_11, MON_18]

    def test_only_days_limits_both_the_scoring_and_what_the_model_is_asked(self) -> None:
        asked: list[date] = []

        def spy(day: date) -> list[SlotForecast]:
            asked.append(day)
            return self.always_ten(day)

        result = backtest_with(self.history, self.observed, spy, only_days={MON_11, MON_18})
        assert asked == [MON_11, MON_18]
        assert result.daily_pct == pytest.approx(100 * (1 - 10 / 30))

    def test_days_the_model_cannot_forecast_are_skipped_not_scored_as_zero(self) -> None:
        result = backtest_with(
            self.history, self.observed, lambda d: None if d == MON_11 else self.always_ten(d)
        )
        assert [d.day for d in result.days] == [MON_4, MON_18]
        assert result.daily_pct == pytest.approx(100.0)


class TestBias:
    """Over 40 actual calls the forecasts said 10, 30 and 20 against 10, 20 and 10:
    forecast 60, actual 40 -> 50% too high."""

    def test_keeps_the_sign_so_high_and_low_are_told_apart(self) -> None:
        assert bias_pct([(10, 10), (30, 20), (20, 10)]) == pytest.approx(50.0)
        assert bias_pct([(5, 10), (10, 20)]) == pytest.approx(-50.0)

    def test_errors_in_opposite_directions_cancel_where_accuracy_would_not(self) -> None:
        # +10 and -10 on a day of 20 each: no net bias, but accuracy would be 50%.
        assert bias_pct([(30, 20), (10, 20)]) == pytest.approx(0.0)
        assert accuracy_pct([(30, 20), (10, 20)]) == pytest.approx(50.0)

    def test_nothing_actually_offered_gives_no_bias(self) -> None:
        assert bias_pct([(5, 0)]) is None
        assert bias_pct([]) is None

    def test_a_backtest_reports_it(self) -> None:
        history = (row(MON_4, 10), row(MON_11, 20), row(MON_18, 10))
        observed = (MON_4, MON_11, MON_18)
        always_ten = lambda _d: [  # noqa: E731
            SlotForecast(s, 10.0 if s == SLOT else 0.0, 180.0, 1) for s in range(SLOTS_PER_DAY)
        ]
        result = backtest_with(history, observed, always_ten)
        # forecast 30, actual 40 -> 25% too low
        assert result.bias_pct == pytest.approx(-25.0)
