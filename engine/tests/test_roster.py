from datetime import date, datetime, time
from typing import ClassVar

import pytest

from wfm_engine.roster import (
    breaks_rest_rule,
    classify,
    consecutive_run,
    coverage,
    is_overnight,
    on_grid,
    rest_hours,
    shift_kind,
    shift_minutes,
    shift_slots,
    shift_span,
    summarise,
    variance,
    week_minutes,
)

MON, TUE, WED = date(2026, 5, 25), date(2026, 5, 26), date(2026, 5, 27)


class TestShiftSlots:
    def test_a_day_shift_covers_each_half_hour_it_spans(self) -> None:
        # 09:00 to 17:30 = 17 half-hours, slots 18 (09:00) to 34 (17:00-17:30).
        slots = shift_slots(MON, time(9, 0), time(17, 30))
        assert len(slots) == 17
        assert slots[0] == (MON, 18)
        assert slots[-1] == (MON, 34)

    def test_the_end_is_not_covered(self) -> None:
        assert (MON, 35) not in shift_slots(MON, time(9, 0), time(17, 30))

    def test_a_night_shift_continues_into_the_next_day(self) -> None:
        # 22:00 to 06:00: 4 half-hours before midnight (slots 44-47), 12 after (slots 0-11).
        slots = shift_slots(MON, time(22, 0), time(6, 0))
        assert [s for s in slots if s[0] == MON] == [(MON, k) for k in range(44, 48)]
        assert [s for s in slots if s[0] == TUE] == [(TUE, k) for k in range(0, 12)]
        assert len(slots) == 16

    def test_finishing_exactly_at_midnight_stays_on_the_same_day(self) -> None:
        # 20:00 to 00:00 is overnight by the rule (end is not after start) but covers no slot of
        # the next day: slots 40..47 on the day itself.
        slots = shift_slots(MON, time(20, 0), time(0, 0))
        assert slots == [(MON, k) for k in range(40, 48)]

    @pytest.mark.parametrize(
        ("start", "end"), [(time(9, 15), time(17, 0)), (time(9, 0), time(17, 10))]
    )
    def test_refuses_times_off_the_half_hour(self, start: time, end: time) -> None:
        with pytest.raises(ValueError, match="half-hour"):
            shift_slots(MON, start, end)

    def test_refuses_a_shift_with_no_length(self) -> None:
        with pytest.raises(ValueError, match="length"):
            shift_slots(MON, time(9, 0), time(9, 0))

    def test_grid_check(self) -> None:
        assert on_grid(time(9, 30))
        assert not on_grid(time(9, 45))


class TestSpansAndMinutes:
    def test_a_day_shift_ends_the_same_day(self) -> None:
        began, ended = shift_span(MON, time(9, 0), time(17, 30))
        assert (began, ended) == (datetime(2026, 5, 25, 9, 0), datetime(2026, 5, 25, 17, 30))

    def test_a_night_shift_ends_the_next_day(self) -> None:
        _, ended = shift_span(MON, time(22, 0), time(6, 0))
        assert ended == datetime(2026, 5, 26, 6, 0)
        assert is_overnight(time(22, 0), time(6, 0))
        assert not is_overnight(time(9, 0), time(17, 0))

    @pytest.mark.parametrize(
        ("start", "end", "minutes"),
        [
            (time(9, 0), time(17, 30), 510),
            (time(22, 0), time(6, 0), 480),
            (time(10, 0), time(14, 0), 240),
        ],
    )
    def test_minutes_on_the_clock(self, start: time, end: time, minutes: int) -> None:
        assert shift_minutes(start, end) == minutes

    def test_week_minutes_adds_up(self) -> None:
        assert week_minutes([(time(9, 0), time(17, 30)), (time(10, 0), time(14, 0))]) == 750


class TestCoverage:
    def test_counts_how_many_people_are_rostered_in_each_half_hour(self) -> None:
        # Two people overlap 10:00-10:30: A 09:00-10:30, B 10:00-11:00.
        counted = coverage([(MON, time(9, 0), time(10, 30)), (MON, time(10, 0), time(11, 0))])
        assert counted[(MON, 18)] == 1  # 09:00 only A
        assert counted[(MON, 20)] == 2  # 10:00 both
        assert counted[(MON, 21)] == 1  # 10:30 only B
        assert counted[(MON, 22)] == 0  # 11:00 nobody

    def test_a_night_shift_covers_the_next_morning(self) -> None:
        counted = coverage([(MON, time(22, 0), time(2, 0))])
        assert counted[(MON, 47)] == 1
        assert counted[(TUE, 0)] == 1
        assert counted[(TUE, 3)] == 1
        assert counted[(TUE, 4)] == 0


class TestRestRule:
    def test_rest_is_the_gap_between_the_end_of_one_shift_and_the_start_of_the_next(self) -> None:
        assert rest_hours(datetime(2026, 5, 25, 22, 0), datetime(2026, 5, 26, 7, 0)) == 9

    def test_a_late_then_an_early_shift_breaks_the_eleven_hour_rule(self) -> None:
        late = shift_span(MON, time(13, 0), time(22, 0))
        early = shift_span(TUE, time(7, 0), time(15, 0))  # only 9 hours after the late shift
        assert breaks_rest_rule([late], early) is True

    def test_exactly_eleven_hours_is_allowed(self) -> None:
        late = shift_span(MON, time(13, 0), time(22, 0))
        early = shift_span(TUE, time(9, 0), time(17, 0))  # exactly 11 hours
        assert breaks_rest_rule([late], early) is False

    def test_it_works_whichever_shift_comes_first(self) -> None:
        early = shift_span(TUE, time(7, 0), time(15, 0))
        late = shift_span(MON, time(13, 0), time(22, 0))
        assert breaks_rest_rule([early], late) is True

    def test_a_night_shift_followed_by_a_morning_shift_is_caught(self) -> None:
        night = shift_span(MON, time(22, 0), time(6, 0))  # ends 06:00 Tuesday
        morning = shift_span(TUE, time(9, 0), time(17, 0))  # only 3 hours later
        assert breaks_rest_rule([night], morning) is True

    def test_overlapping_shifts_are_refused(self) -> None:
        a = shift_span(MON, time(9, 0), time(17, 0))
        b = shift_span(MON, time(16, 0), time(20, 0))
        assert breaks_rest_rule([a], b) is True

    def test_shifts_a_week_apart_do_not_interact(self) -> None:
        a = shift_span(MON, time(9, 0), time(17, 0))
        b = shift_span(date(2026, 6, 1), time(9, 0), time(17, 0))
        assert breaks_rest_rule([a], b) is False


class TestConsecutiveDays:
    def test_counts_the_run_the_new_day_would_make(self) -> None:
        worked = [date(2026, 5, 25), date(2026, 5, 26), date(2026, 5, 28)]
        # Adding Wednesday 27 joins Mon, Tue and Thu into one run of four.
        assert consecutive_run(worked, date(2026, 5, 27)) == 4

    def test_a_day_on_its_own_is_a_run_of_one(self) -> None:
        assert consecutive_run([date(2026, 5, 25)], date(2026, 5, 29)) == 1

    def test_crosses_a_month_end(self) -> None:
        worked = [date(2026, 5, 30), date(2026, 5, 31)]
        assert consecutive_run(worked, date(2026, 6, 1)) == 3


class TestVariance:
    def test_unknown_is_not_zero(self) -> None:
        assert variance(3, None) is None
        assert classify(3, None) is None

    @pytest.mark.parametrize(
        ("scheduled", "required", "gap", "label"),
        [(3, 5, -2, "under"), (5, 5, 0, "met"), (7, 5, 2, "over"), (0, 0, 0, "met")],
    )
    def test_scheduled_minus_required(
        self, scheduled: int, required: int, gap: int, label: str
    ) -> None:
        assert variance(scheduled, required) == gap
        assert classify(scheduled, required) == label


class TestWeekSummary:
    """Four half-hours. Required 5, 5, 3, unknown. Scheduled 3, 6, 3, 9.

    known 3 (the unknown one takes no part, whatever is scheduled in it)
    under 1 (the first: 3 against 5, short by 2); the second is over by 1, which does not offset
    the shortfall; the third is met
    gap 2; required total 13; scheduled total 12 (3 + 6 + 3, not the 9)
    worst: the first half-hour, by -2
    """

    required: ClassVar[dict[tuple[date, int], int | None]] = {
        (MON, 20): 5,
        (MON, 21): 5,
        (MON, 22): 3,
        (MON, 23): None,
    }
    scheduled: ClassVar[dict[tuple[date, int], int]] = {
        (MON, 20): 3,
        (MON, 21): 6,
        (MON, 22): 3,
        (MON, 23): 9,
    }

    def test_numbers(self) -> None:
        s = summarise(self.scheduled, self.required)
        assert (s.intervals_known, s.under_intervals, s.gap) == (3, 1, 2)
        assert (s.required_total, s.scheduled_total) == (13, 12)
        assert s.worst == ((MON, 20), -2)

    def test_over_staffing_elsewhere_does_not_cover_a_shortfall(self) -> None:
        s = summarise({(MON, 20): 0, (MON, 21): 50}, {(MON, 20): 2, (MON, 21): 1})
        assert s.gap == 2
        assert s.under_intervals == 1

    def test_picks_the_worst_not_the_first(self) -> None:
        s = summarise({}, {(MON, 20): 1, (MON, 21): 4, (MON, 22): 2})
        assert s.worst == ((MON, 21), -4)

    def test_nothing_known_claims_nothing(self) -> None:
        s = summarise({(MON, 20): 5}, {(MON, 20): None})
        assert (s.intervals_known, s.under_intervals, s.gap, s.worst) == (0, 0, 0, None)

    def test_fully_staffed_has_no_worst(self) -> None:
        s = summarise({(MON, 20): 5}, {(MON, 20): 5})
        assert (s.under_intervals, s.gap, s.worst) == (0, 0, None)


class TestShiftKind:
    @pytest.mark.parametrize(
        ("start", "end", "kind"),
        [
            (time(7, 0), time(15, 30), "early"),
            (time(8, 30), time(17, 0), "early"),
            (time(9, 0), time(17, 30), "day"),
            (time(12, 30), time(21, 0), "day"),
            (time(13, 0), time(21, 30), "late"),
            (time(16, 0), time(20, 0), "late"),
            (time(22, 0), time(6, 0), "night"),
            (time(20, 0), time(0, 0), "night"),
        ],
    )
    def test_groups_a_shift_for_the_legend(self, start: time, end: time, kind: str) -> None:
        assert shift_kind(start, end) == kind
