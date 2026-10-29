from datetime import date, datetime, time
from decimal import Decimal

from wfm_engine.peaks import analyse


def at(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2031, 3, day, hh, mm)


def test_busiest_and_quietest_days_are_ranked_with_the_earlier_day_first_on_ties() -> None:
    # Failure caught: unstable ordering, so the same data gives a different report each run.
    r = analyse([(at(4, 9), 5), (at(3, 9), 5), (at(5, 9), 1)], top=2)
    assert [(d.day, d.offered) for d in r.busiest_days] == [
        (date(2031, 3, 3), 5),
        (date(2031, 3, 4), 5),
    ]
    assert [d.day for d in r.quietest_days] == [date(2031, 3, 5), date(2031, 3, 3)]


def test_the_busiest_half_hour_is_found() -> None:
    r = analyse([(at(3, 9), 4), (at(3, 9, 30), 9), (at(4, 9, 30), 2)])
    assert (r.busiest_intervals[0].start, r.busiest_intervals[0].offered) == (at(3, 9, 30), 9)


def test_slot_average_is_per_day_that_slot_was_measured() -> None:
    # Failure caught: dividing by every day in the range, so a slot open on two days looks quiet.
    r = analyse([(at(3, 9), 10), (at(4, 9), 20), (at(3, 12), 1)])
    nine = next(s for s in r.busiest_slots if s.slot == time(9))
    assert (nine.average_offered, nine.days) == (Decimal("15.0"), 2)
    assert r.busiest_slots[0].slot == time(9)


def test_a_slot_that_never_saw_a_call_is_closed_not_a_trough() -> None:
    # Failure caught: the dead of night reported as the quietest time to be open.
    r = analyse([(at(3, 2), 0), (at(3, 9), 3), (at(3, 12), 7)])
    assert [s.slot for s in r.quietest_slots] == [time(9), time(12)]


def test_no_data_is_an_empty_report() -> None:
    r = analyse([])
    assert r.busiest_days == []
    assert r.quietest_slots == []


def test_daily_lists_every_measured_day_oldest_first_and_gaps_are_missing() -> None:
    # Failure caught: a day with no rows drawn as a zero-call day in the daily chart.
    r = analyse([(at(5, 9), 4), (at(3, 9), 10), (at(3, 9, 30), 2)])
    assert [(d.day, d.offered) for d in r.daily] == [(date(2031, 3, 3), 12), (date(2031, 3, 5), 4)]


def test_profile_has_every_open_half_hour_by_time_of_day() -> None:
    # Failure caught: only the top five slots returned, so the 48-slot chart is mostly empty.
    r = analyse([(at(3, 12), 6), (at(3, 9), 3), (at(4, 9), 4), (at(3, 2), 0)], top=1)
    assert [(s.slot, s.average_offered, s.days) for s in r.profile] == [
        (time(9), Decimal("3.5"), 2),
        (time(12), Decimal("6.0"), 1),
    ]


def test_heat_averages_per_weekday_and_half_hour() -> None:
    # Failure caught: Mondays and Tuesdays pooled, hiding the weekday pattern.
    # 3, 10 March 2031 are Mondays; 4 March is a Tuesday.
    r = analyse([(at(3, 9), 10), (at(10, 9), 20), (at(4, 9), 7), (at(4, 9, 30), 0)])
    assert [(c.weekday, c.slot, c.average_offered, c.days) for c in r.heat] == [
        (0, time(9), Decimal("15.0"), 2),
        (1, time(9), Decimal("7.0"), 1),
    ]


def test_heat_is_bounded_by_a_week_of_half_hours() -> None:
    rows = [
        (datetime(2031, 3, 3 + d, h, m), 1) for d in range(14) for h in range(24) for m in (0, 30)
    ]
    assert len(analyse(rows).heat) == 7 * 48


def test_single_day_and_empty_range() -> None:
    one = analyse([(at(3, 9), 5)])
    assert len(one.daily) == 1
    assert len(one.profile) == 1
    assert len(one.heat) == 1
    empty = analyse([])
    assert (empty.daily, empty.profile, empty.heat) == ([], [], [])
