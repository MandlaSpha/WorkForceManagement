from datetime import date, datetime

import pytest

from wfm_engine.schedule import is_due, latest_slot, period

# Wednesday 12 March 2031, 09:30.
NOW = datetime(2031, 3, 12, 9, 30)


def test_daily_slot_is_today_at_the_hour_or_yesterday_if_it_has_not_come() -> None:
    assert latest_slot("daily", 7, 0, 1, NOW) == datetime(2031, 3, 12, 7, 0)
    assert latest_slot("daily", 18, 0, 1, NOW) == datetime(2031, 3, 11, 18, 0)


def test_weekly_slot_is_the_most_recent_such_weekday() -> None:
    # Monday 07:00 and Wednesday 09:00 have passed; Wednesday 12:00 has not.
    assert latest_slot("weekly", 7, 0, 1, NOW) == datetime(2031, 3, 10, 7, 0)
    assert latest_slot("weekly", 9, 2, 1, NOW) == datetime(2031, 3, 12, 9, 0)
    assert latest_slot("weekly", 12, 2, 1, NOW) == datetime(2031, 3, 5, 12, 0)
    assert latest_slot("weekly", 7, 4, 1, NOW) == datetime(2031, 3, 7, 7, 0)  # last Friday


def test_monthly_slot_steps_back_across_a_month_and_a_year() -> None:
    assert latest_slot("monthly", 7, 0, 5, NOW) == datetime(2031, 3, 5, 7, 0)
    assert latest_slot("monthly", 7, 0, 20, NOW) == datetime(2031, 2, 20, 7, 0)
    assert latest_slot("monthly", 7, 0, 20, datetime(2031, 1, 10, 9, 0)) == datetime(
        2030, 12, 20, 7, 0
    )


@pytest.mark.parametrize(
    ("frequency", "hour", "weekday", "day"),
    [("hourly", 7, 0, 1), ("daily", 24, 0, 1), ("weekly", 7, 7, 1), ("monthly", 7, 0, 29)],
)
def test_nonsense_is_refused_not_scheduled(
    frequency: str, hour: int, weekday: int, day: int
) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        latest_slot(frequency, hour, weekday, day, NOW)


def test_a_new_schedule_does_not_send_the_slot_that_has_just_passed() -> None:
    # Failure caught: making a 07:00 schedule at 09:30 mailing out at once.
    assert not is_due(
        "daily", 7, 0, 1, now=NOW, created_at=datetime(2031, 3, 12, 9, 0), last_sent=None
    )
    assert is_due("daily", 7, 0, 1, now=NOW, created_at=datetime(2031, 3, 11, 9, 0), last_sent=None)


def test_a_slot_is_sent_once() -> None:
    # Failure caught: a schedule mailing every time the check runs during its hour.
    created = datetime(2031, 3, 1, 9, 0)
    assert is_due(
        "daily", 7, 0, 1, now=NOW, created_at=created, last_sent=datetime(2031, 3, 11, 7, 1)
    )
    assert not is_due(
        "daily", 7, 0, 1, now=NOW, created_at=created, last_sent=datetime(2031, 3, 12, 7, 1)
    )


def test_a_missed_run_is_sent_once_not_once_per_missed_slot() -> None:
    # The worker was down for a week: one catch-up, and then the sent time silences the rest.
    created = datetime(2031, 3, 1, 9, 0)
    assert is_due(
        "daily", 7, 0, 1, now=NOW, created_at=created, last_sent=datetime(2031, 3, 5, 7, 1)
    )
    assert not is_due("daily", 7, 0, 1, now=NOW, created_at=created, last_sent=NOW)


def test_the_period_each_frequency_covers() -> None:
    wed = date(2031, 3, 12)
    assert period("daily", wed) == (date(2031, 3, 11), date(2031, 3, 11))
    assert period("weekly", wed) == (date(2031, 3, 5), date(2031, 3, 11))
    assert period("monthly", wed) == (date(2031, 2, 1), date(2031, 2, 28))
    assert period("monthly", date(2031, 1, 5)) == (date(2030, 12, 1), date(2030, 12, 31))
