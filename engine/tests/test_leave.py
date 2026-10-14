from datetime import date
from decimal import Decimal

import pytest

from wfm_engine.leave import (
    Impact,
    Slot,
    balance,
    impact,
    overlaps,
    working_days,
    working_days_by_year,
)

D = date


class TestWorkingDays:
    def test_counts_monday_to_friday(self) -> None:
        assert working_days(D(2026, 5, 25), D(2026, 5, 29)) == 5  # Monday to Friday
        assert working_days(D(2026, 5, 25), D(2026, 6, 7)) == 10  # two weeks

    def test_weekends_alone_are_no_days(self) -> None:
        assert working_days(D(2026, 5, 30), D(2026, 5, 31)) == 0

    def test_a_single_day(self) -> None:
        assert working_days(D(2026, 5, 25), D(2026, 5, 25)) == 1
        assert working_days(D(2026, 5, 30), D(2026, 5, 30)) == 0

    def test_public_holidays_are_not_leave_days(self) -> None:
        # Freedom Day, Monday 27 April 2026, is a holiday: that week has four working days.
        assert working_days(D(2026, 4, 27), D(2026, 5, 1), holidays={D(2026, 4, 27)}) == 4

    def test_a_holiday_on_a_weekend_changes_nothing(self) -> None:
        assert working_days(D(2026, 5, 25), D(2026, 5, 31), holidays={D(2026, 5, 30)}) == 5

    def test_an_end_before_the_start_is_refused(self) -> None:
        with pytest.raises(ValueError, match="before"):
            working_days(D(2026, 5, 26), D(2026, 5, 25))

    def test_leave_across_new_year_is_split_between_the_years(self) -> None:
        # Mon 29 Dec 2025 to Fri 2 Jan 2026: 3 days in 2025 (Mon-Wed... Fri 2 Jan is 2026).
        # 29, 30, 31 Dec are Mon, Tue, Wed; 1 Jan is a holiday; 2 Jan is a Friday.
        by_year = working_days_by_year(D(2025, 12, 29), D(2026, 1, 2), holidays={D(2026, 1, 1)})
        assert by_year == {2025: 3, 2026: 1}


class TestOverlaps:
    def test_ranges_that_share_a_day_overlap_including_the_ends(self) -> None:
        assert overlaps((D(2026, 5, 1), D(2026, 5, 5)), (D(2026, 5, 5), D(2026, 5, 9)))
        assert overlaps((D(2026, 5, 1), D(2026, 5, 9)), (D(2026, 5, 3), D(2026, 5, 4)))

    def test_ranges_that_only_touch_in_time_do_not(self) -> None:
        assert not overlaps((D(2026, 5, 1), D(2026, 5, 4)), (D(2026, 5, 5), D(2026, 5, 9)))


class TestBalance:
    def test_available_is_the_entitlement_less_taken_and_pending(self) -> None:
        b = balance(Decimal(15), Decimal(5), Decimal(3))
        assert b.available == Decimal(7)
        assert not b.exceeded

    def test_using_exactly_the_entitlement_is_not_exceeding_it(self) -> None:
        assert not balance(Decimal(15), Decimal(10), Decimal(5)).exceeded

    def test_one_more_than_the_entitlement_is_exceeding_it(self) -> None:
        assert balance(Decimal(15), Decimal(10), Decimal(6)).exceeded

    def test_no_limit_means_nothing_to_exceed(self) -> None:
        b = balance(None, Decimal(40), Decimal(0))
        assert (b.available, b.exceeded) == (None, False)


class TestCoverageImpact:
    """Three half-hours of a shift on the leave days:
    A  4 scheduled, 4 required   covered with none to spare: would become short
    B  5 scheduled, 4 required   one to spare: stays covered
    C  2 scheduled, 4 required   already short: made shorter
    D  3 scheduled, no known requirement: counted, not judged
    """

    slots = (Slot(4, 4), Slot(5, 4), Slot(2, 4), Slot(3, None))

    def test_the_figures(self) -> None:
        assert impact(1, self.slots) == Impact(
            shifts=1, hours=2.0, intervals=4, newly_under=1, already_under=1, unknown=1
        )

    def test_a_spare_person_absorbs_the_leave(self) -> None:
        result = impact(1, [Slot(5, 4)])
        assert (result.newly_under, result.already_under) == (0, 0)

    def test_no_shifts_means_no_impact(self) -> None:
        assert impact(0, []) == Impact(0, 0.0, 0, 0, 0, 0)
