from datetime import datetime

import pytest

from wfm_engine.kpi import (
    Totals,
    interval_start,
    kpis,
    totals_for_call,
)


def add_all(calls: list[Totals]) -> Totals:
    total = Totals()
    for call in calls:
        total = total + call
    return total


def answered(wait: int, talk: int, wrap: int | None, call_type: str = "INBOUND") -> Totals:
    return totals_for_call(
        call_type=call_type,
        status="Agent",
        wait_s=wait,
        handle_s=talk + (wrap or 0),
    )


def abandoned(wait: int) -> Totals:
    return totals_for_call(call_type="INBOUND", status="Abandoned", wait_s=wait, handle_s=0)


class TestKpis:
    """Ten inbound calls, worked out by hand.

    answered (wait / talk / wrap): 0/100/20, 10/150/30, 20/200/10, 21/120/-, 30/60/40, 5/80/20,
    40/300/-, 15/90/10; abandoned after 7s and 60s. Plus noise that must not count.

    offered 10, answered 8, abandoned 2 -> abandon 20%.
    waits <= 20s: 0, 10, 20, 5, 15 = 5 calls -> SL = 5 / 10 offered = 50%.
    wait sum = 0+10+20+21+30+5+40+15 = 141 -> ASA = 141 / 8 = 17.625.
    handle = 120, 180, 210, 120, 100, 100, 300, 100 = 1230 -> AHT = 1230 / 8 = 153.75.
    """

    @pytest.fixture
    def totals(self) -> Totals:
        calls = [
            answered(0, 100, 20),
            answered(10, 150, 30),
            answered(20, 200, 10),  # exactly on the threshold counts as within it
            answered(21, 120, None),
            answered(30, 60, 40),
            answered(5, 80, 20),
            answered(40, 300, None),
            answered(15, 90, 10),
            abandoned(7),
            abandoned(60),
            # not inbound, so they add nothing
            answered(1, 500, 500, call_type="OUTBOUND"),
            answered(1, 500, 500, call_type="AGENT TRANSFER"),
            totals_for_call(call_type="OUTBOUND", status="Dial", wait_s=None, handle_s=None),
        ]
        return add_all(calls)

    def test_counts(self, totals: Totals) -> None:
        result = kpis(totals)
        assert (result.offered, result.answered, result.abandoned) == (10, 8, 2)

    def test_abandon_percentage(self, totals: Totals) -> None:
        assert kpis(totals).abandon_pct == pytest.approx(20.0)

    def test_service_level_is_over_offered_calls(self, totals: Totals) -> None:
        assert kpis(totals).service_level_pct == pytest.approx(50.0)  # not 5/8 = 62.5

    def test_asa_and_aht_average_the_answered_calls_only(self, totals: Totals) -> None:
        result = kpis(totals)
        assert result.asa_s == pytest.approx(17.625)
        assert result.aht_s == pytest.approx(153.75)

    def test_the_threshold_is_configurable(self) -> None:
        strict = totals_for_call(
            call_type="INBOUND", status="Agent", wait_s=11, handle_s=5, sl_threshold_s=10
        )
        assert strict.answered_in_sl == 0


class TestEdgeCases:
    def test_no_calls_means_no_figures_not_zeroes(self) -> None:
        result = kpis(Totals())
        assert result.offered == 0
        assert result.abandon_pct is None
        assert result.service_level_pct is None
        assert result.asa_s is None
        assert result.aht_s is None

    def test_all_abandoned_has_no_asa_or_aht(self) -> None:
        result = kpis(add_all([abandoned(5), abandoned(9)]))
        assert result.abandon_pct == pytest.approx(100.0)
        assert result.service_level_pct == pytest.approx(0.0)
        assert result.asa_s is None
        assert result.aht_s is None

    def test_an_inbound_call_that_is_neither_answered_nor_abandoned_is_still_offered(self) -> None:
        call = totals_for_call(call_type="INBOUND", status="Failover", wait_s=None, handle_s=None)
        assert call == Totals(offered=1)


class TestIntervals:
    @pytest.mark.parametrize(
        ("moment", "expected"),
        [
            (datetime(2026, 5, 1, 8, 0, 0), datetime(2026, 5, 1, 8, 0)),
            (datetime(2026, 5, 1, 8, 29, 59), datetime(2026, 5, 1, 8, 0)),
            (datetime(2026, 5, 1, 8, 30, 0), datetime(2026, 5, 1, 8, 30)),
            (datetime(2026, 5, 1, 23, 59, 59), datetime(2026, 5, 1, 23, 30)),
        ],
    )
    def test_buckets_into_thirty_minute_intervals(
        self, moment: datetime, expected: datetime
    ) -> None:
        assert interval_start(moment) == expected

    def test_other_lengths_must_divide_the_hour(self) -> None:
        assert interval_start(datetime(2026, 5, 1, 8, 14), 15) == datetime(2026, 5, 1, 8, 0)
        with pytest.raises(ValueError, match="divide an hour"):
            interval_start(datetime(2026, 5, 1, 8, 14), 25)
