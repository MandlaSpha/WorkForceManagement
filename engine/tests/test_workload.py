from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

from wfm_engine.workload import Demand, OpenItem, arrival_rate_per_working_day, demand, working_days

MON = date(2026, 5, 25)
AS_OF = datetime(2026, 5, 25, 9, 0, tzinfo=UTC)  # Monday 09:00
END = datetime(2026, 5, 29, 23, 59, tzinfo=UTC)  # end of Friday: 5 working days


def at(day: int, hour: int = 12) -> datetime:
    """`day` days after Monday 25 May, at `hour`."""
    return datetime(2026, 5, 25, hour, 0, tzinfo=UTC) + timedelta(days=day)


class TestWorkingDays:
    def test_counts_monday_to_friday_only(self) -> None:
        assert working_days(MON, 7) == 5  # a full week
        assert working_days(MON, 5) == 5
        assert working_days(date(2026, 5, 30), 2) == 0  # Saturday and Sunday
        assert working_days(date(2026, 5, 29), 4) == 2  # Fri, Sat, Sun, Mon

    def test_no_days_is_no_working_days(self) -> None:
        assert working_days(MON, 0) == 0


class TestArrivalRate:
    def test_is_the_effort_opened_per_working_day_of_the_window(self) -> None:
        # 3600 minutes opened over a 28-day window (20 working days) is 180 a working day.
        opened = [(date(2026, 4, 28), 1800), (date(2026, 5, 5), 1200), (date(2026, 5, 12), 600)]
        assert arrival_rate_per_working_day(opened, date(2026, 4, 27), 28) == pytest.approx(180)

    def test_nothing_opened_is_unknown_not_zero(self) -> None:
        # A quiet month and a missing import look the same, so no rate is claimed.
        assert arrival_rate_per_working_day([], date(2026, 4, 27), 28) is None

    def test_unestimated_items_add_nothing_to_the_effort(self) -> None:
        assert arrival_rate_per_working_day(
            [(date(2026, 4, 28), None), (date(2026, 4, 29), 100)], date(2026, 4, 27), 28
        ) == pytest.approx(5)  # 100 over 20 working days

    def test_a_window_with_no_working_days_has_no_rate(self) -> None:
        assert arrival_rate_per_working_day([(date(2026, 5, 30), 60)], date(2026, 5, 30), 2) is None


class TestDemandByHand:
    """Five open items, productive time 360 minutes a day, 5 working days: one person does 1800.

      A  480 min due Tuesday          in the horizon
      B  240 min due Monday 08:00     already breached, still has to be done
      C  600 min due next Wednesday   outside the horizon
      D  no estimate, due Thursday    in the horizon but unknown effort
      E  120 min, no deadline         in the backlog, not in the requirement
    backlog   480 + 240 + 600 + 120 = 1440; due in horizon 480 + 240 = 720
    arriving  180 a working day * 5 = 900
    required  (720 + 900) / 1800 = 0.9 people
    """

    items = (
        OpenItem(480, at(1)),
        OpenItem(240, datetime(2026, 5, 25, 8, 0, tzinfo=UTC)),
        OpenItem(600, at(9)),
        OpenItem(None, at(3)),
        OpenItem(120, None),
    )

    def run(self, **over: Any) -> Demand:
        args: dict[str, Any] = {
            "as_of": AS_OF,
            "horizon_end": END,
            "horizon_working_days": 5,
            "productive_min_per_day": 360,
            "arrival_per_working_day": 180.0,
            **over,
        }
        return demand(self.items, **args)

    def test_the_figures(self) -> None:
        d = self.run()
        assert (d.open_count, d.breached) == (5, 1)
        assert d.backlog_min == 1440
        assert d.due_min == 720
        assert d.arriving_min == pytest.approx(900)
        assert d.required_fte == pytest.approx(0.9)

    def test_what_is_missing_is_counted_and_makes_the_figure_a_minimum(self) -> None:
        d = self.run()
        assert d.unestimated == 1
        assert d.no_deadline == 1
        assert d.complete is False

    def test_an_unknown_arrival_rate_is_not_zero_arrivals(self) -> None:
        d = self.run(arrival_per_working_day=None)
        assert d.arriving_min is None
        assert d.required_fte == pytest.approx(720 / 1800)
        assert d.complete is False

    def test_work_due_beyond_the_horizon_is_not_needed_yet(self) -> None:
        # Pull the horizon in to Tuesday: B (breached) and A (Tuesday noon) only.
        d = self.run(horizon_end=at(1, 23), horizon_working_days=2)
        assert d.due_min == 720
        assert d.required_fte == pytest.approx((720 + 360) / 720)

    def test_effort_not_the_sla_window_decides(self) -> None:
        # Four hours to resolve, twenty minutes of work: it needs 20 minutes of someone's time.
        d = demand(
            [OpenItem(20, AS_OF + timedelta(hours=4))],
            as_of=AS_OF,
            horizon_end=END,
            horizon_working_days=5,
            productive_min_per_day=360,
            arrival_per_working_day=0.0,
        )
        assert d.due_min == 20
        assert d.required_fte == pytest.approx(20 / 1800)
        assert d.complete is True

    def test_no_work_needs_nobody(self) -> None:
        d = demand(
            [],
            as_of=AS_OF,
            horizon_end=END,
            horizon_working_days=5,
            productive_min_per_day=360,
            arrival_per_working_day=0.0,
        )
        assert (d.open_count, d.required_fte) == (0, 0.0)

    def test_a_horizon_with_no_working_days_has_no_requirement(self) -> None:
        d = self.run(horizon_working_days=0)
        assert d.required_fte is None

    def test_productive_time_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            self.run(productive_min_per_day=0)
