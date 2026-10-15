"""Availability windows, worked by hand. Monday 25 May 2026 is weekday 0."""

from datetime import date, time

import pytest

from wfm_engine.availability import Window, overlap, touches, window_of

MON = date(2026, 5, 25)


def test_a_window_is_a_run_of_half_hours_on_a_weekday() -> None:
    # 09:00-12:30 is slots 18 up to (not including) 25.
    assert window_of(0, time(9, 0), time(12, 30)) == Window(0, 18, 25)


def test_an_end_of_midnight_means_the_end_of_the_day() -> None:
    assert window_of(4, time(18, 0), time(0, 0)) == Window(4, 36, 48)


@pytest.mark.parametrize(
    ("weekday", "start", "end"),
    [
        (7, time(9, 0), time(10, 0)),  # no such weekday
        (0, time(9, 15), time(10, 0)),  # off the half-hour grid
        (0, time(10, 0), time(10, 0)),  # no length
        (0, time(10, 0), time(9, 0)),  # ends before it starts
    ],
)
def test_nonsense_windows_are_refused(weekday: int, start: time, end: time) -> None:
    with pytest.raises(ValueError, match=r"weekday|half-hour|end after"):
        window_of(weekday, start, end)


def test_windows_that_share_even_one_half_hour_overlap_but_touching_ones_do_not() -> None:
    morning = window_of(0, time(9, 0), time(12, 0))
    assert overlap(morning, window_of(0, time(11, 30), time(14, 0)))
    assert not overlap(morning, window_of(0, time(12, 0), time(14, 0)))  # starts where it ends
    assert not overlap(morning, window_of(1, time(9, 0), time(12, 0)))  # another weekday


def test_a_shift_is_blocked_only_when_it_covers_a_declared_half_hour() -> None:
    off = [window_of(0, time(12, 0), time(13, 0))]  # Monday 12:00-13:00
    assert touches(off, MON, time(9, 0), time(17, 30))  # works through the hour
    assert not touches(off, MON, time(13, 0), time(21, 0))  # starts when the window ends
    assert not touches(off, MON, time(7, 0), time(12, 0))  # ends when the window starts


def test_nothing_declared_blocks_nothing() -> None:
    assert not touches([], MON, time(9, 0), time(17, 0))


def test_an_overnight_shift_is_checked_against_the_next_days_windows_too() -> None:
    tuesday_early = [window_of(1, time(0, 0), time(2, 0))]
    # Monday 22:00 to Tuesday 06:00 covers Tuesday 00:00-02:00.
    assert touches(tuesday_early, MON, time(22, 0), time(6, 0))
    assert not touches(tuesday_early, MON, time(14, 0), time(22, 0))
