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
