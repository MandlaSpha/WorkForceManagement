"""How events change a forecast, worked by hand and with no database."""

from __future__ import annotations

from datetime import date

import pytest
from wfm_engine.forecast import SlotForecast

from wfm.forecasting.modeling import (
    BASELINE,
    Built,
    DayForecast,
    Uplift,
    apply_uplifts,
    day_factor,
)

MON, TUE, WED = date(2026, 5, 25), date(2026, 5, 26), date(2026, 5, 27)


def day(
    volume: float = 10.0, lower: float | None = None, upper: float | None = None
) -> DayForecast:
    return DayForecast([SlotForecast(20, volume, 180.0, 3)], lower, upper)


def event(pct: float, start: date = MON, end: date = MON, name: str = "e", id_: int = 1) -> Uplift:
    return Uplift(id_, name, start, end, pct)


class TestDayFactor:
    def test_no_event_means_no_change(self) -> None:
        assert day_factor(MON, []) == 1.0

    def test_an_event_covers_its_first_and_last_day_inclusive(self) -> None:
        e = event(20, MON, WED)
        assert [day_factor(d, [e]) for d in (MON, TUE, WED)] == [1.2, 1.2, 1.2]
        assert day_factor(date(2026, 5, 24), [e]) == 1.0
        assert day_factor(date(2026, 5, 28), [e]) == 1.0

    def test_overlapping_events_compound_rather_than_add(self) -> None:
        # A +20% campaign during a -50% outage is 1.2 x 0.5 = 0.6, not 1 + 0.2 - 0.5 = 0.7.
        assert day_factor(MON, [event(20), event(-50, id_=2)]) == pytest.approx(0.6)

    def test_minus_100_closes_the_queue(self) -> None:
        assert day_factor(MON, [event(-100)]) == 0.0


class TestApplyingEvents:
    def test_scales_volume_and_the_range_of_covered_days_only(self) -> None:
        built = Built(BASELINE, {MON: day(10, 8, 13), TUE: day(10, 8, 13)})
        apply_uplifts(built, [event(50)])

        assert built.days[MON].slots[0].volume == pytest.approx(15)
        assert built.days[MON].lower == pytest.approx(12)
        assert built.days[MON].upper == pytest.approx(19.5)
        assert built.days[TUE].slots[0].volume == 10  # not covered
        assert built.days[TUE].lower == 8

    def test_handling_time_and_evidence_are_left_alone(self) -> None:
        built = Built(BASELINE, {MON: day(10)})
        apply_uplifts(built, [event(50)])
        assert (built.days[MON].slots[0].aht_s, built.days[MON].slots[0].days_used) == (180.0, 3)

    def test_a_baseline_has_no_range_and_stays_without_one(self) -> None:
        built = Built(BASELINE, {MON: day(10)})
        apply_uplifts(built, [event(50)])
        assert (built.days[MON].lower, built.days[MON].upper) == (None, None)

    def test_a_closed_day_has_no_calls(self) -> None:
        built = Built(BASELINE, {MON: day(10, 8, 13)})
        apply_uplifts(built, [event(-100)])
        assert built.days[MON].slots[0].volume == 0
        assert (built.days[MON].lower, built.days[MON].upper) == (0, 0)

    def test_reports_what_was_applied_and_where(self) -> None:
        built = Built(BASELINE, {MON: day(), TUE: day()})
        applied = apply_uplifts(built, [event(20, MON, WED, name="Month-end", id_=7)])

        assert applied == [
            {
                "id": 7,
                "name": "Month-end",
                "dateFrom": "2026-05-25",
                "dateTo": "2026-05-27",
                "upliftPct": 20,
                "days": ["2026-05-25", "2026-05-26"],  # Wednesday has no forecast
            }
        ]
        assert built.params["events"] == applied

    def test_an_event_outside_the_forecast_days_is_neither_applied_nor_reported(self) -> None:
        built = Built(BASELINE, {MON: day()})
        applied = apply_uplifts(built, [event(99, WED, WED)])
        assert applied == []
        assert "events" not in built.params
        assert built.days[MON].slots[0].volume == 10
