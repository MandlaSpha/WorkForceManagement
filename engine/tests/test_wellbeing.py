from datetime import date, timedelta

from wfm_engine import wellbeing as w

TODAY = date(2026, 6, 15)


def back(*offsets: int) -> list[date]:
    return [TODAY - timedelta(days=n) for n in offsets]


def codes(
    shift_days: list[date] | None = None,
    overtime_days: list[date] | None = None,
    absence_days: list[date] | None = None,
) -> list[str]:
    flags = w.wellbeing_flags(
        shift_days=shift_days or [],
        overtime_days=overtime_days or [],
        absence_days=absence_days or [],
        today=TODAY,
    )
    return [f.code for f in flags]


def test_thresholds_are_pinned() -> None:
    assert (w.LONG_RUN_DAYS, w.MIN_REST_DAYS, w.REPEATED_OVERTIME_DAYS) == (7, 2, 4)
    assert (w.RISING_ABSENCE_MIN_DAYS, w.NO_REST_WINDOW_DAYS) == (3, 14)


def test_nothing_to_flag() -> None:
    assert codes(shift_days=back(0, 1, 2, 4, 5)) == []


def test_six_days_in_a_row_is_fine_seven_is_flagged() -> None:
    assert w.LONG_RUN not in codes(shift_days=back(*range(6)))
    flags = w.wellbeing_flags(
        shift_days=back(*range(7)), overtime_days=[], absence_days=[], today=TODAY
    )
    assert [(f.code, f.value) for f in flags if f.code == w.LONG_RUN] == [(w.LONG_RUN, 7)]


def test_a_run_up_to_yesterday_still_counts_when_today_is_not_rostered() -> None:
    assert w.LONG_RUN in codes(shift_days=back(*range(1, 8)))


def test_a_run_that_ended_before_yesterday_is_not_current() -> None:
    assert codes(shift_days=back(*range(3, 12))) == []


def test_overtime_days_extend_a_run() -> None:
    assert w.LONG_RUN in codes(shift_days=back(*range(4)), overtime_days=back(4, 5, 6))


def test_future_days_are_ignored() -> None:
    future = [TODAY + timedelta(days=n) for n in range(1, 15)]
    assert codes(shift_days=future, overtime_days=future) == []


def test_no_rest_needs_fewer_than_two_days_off_in_a_fortnight() -> None:
    thirteen = [d for d in back(*range(14)) if d != TODAY - timedelta(days=6)]
    assert w.NO_REST in codes(shift_days=thirteen)  # one day off
    twelve = [d for d in thirteen if d != TODAY - timedelta(days=3)]
    assert w.NO_REST not in codes(shift_days=twelve)  # a second day off clears it


def test_repeated_overtime_counts_distinct_days_in_four_weeks() -> None:
    assert w.REPEATED_OVERTIME not in codes(overtime_days=back(1, 8, 15))
    assert w.REPEATED_OVERTIME in codes(overtime_days=back(1, 8, 15, 27))
    assert w.REPEATED_OVERTIME not in codes(overtime_days=back(1, 8, 15, 28))  # outside the window
    assert w.REPEATED_OVERTIME not in codes(overtime_days=back(1, 1, 1, 1))  # one day


def test_absence_must_be_three_days_and_rising() -> None:
    assert w.RISING_ABSENCE not in codes(absence_days=back(1, 2))
    assert w.RISING_ABSENCE in codes(absence_days=back(1, 2, 3))
    # three before as well: not rising
    assert w.RISING_ABSENCE not in codes(absence_days=back(1, 2, 3, 30, 31, 32))
    assert w.RISING_ABSENCE in codes(absence_days=back(1, 2, 3, 4, 30, 31, 32))


def test_flags_carry_facts_not_scores() -> None:
    flags = w.wellbeing_flags(
        shift_days=back(*range(14)), overtime_days=back(0, 2, 4, 6), absence_days=[], today=TODAY
    )
    assert {f.code for f in flags} <= set(w.FLAG_CODES)
    assert all(isinstance(f.value, int) for f in flags)


def test_shortfalls_report_only_short_keys_and_zero_for_missing() -> None:
    found = w.skill_shortfalls(required=2, present={"a": 2, "b": 1}, expected=["a", "b", "c"])
    assert [(s.key, s.present, s.missing) for s in found] == [("b", 1, 1), ("c", 0, 2)]


def test_no_shortfall_when_nothing_expected() -> None:
    assert w.skill_shortfalls(required=1, present={}, expected=[]) == []
