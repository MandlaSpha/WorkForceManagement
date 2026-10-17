"""When a repeating report is due and which days it covers (requirement RPT-10). Pure: no Django,
no clock, no I/O: the caller passes the local time.

A schedule is daily at an hour, weekly on a weekday at an hour, or monthly on a day (1 to 28, so it
exists in every month) at an hour. Its latest slot is the most recent such moment that is not in the
future. It is due when that slot is after both the last time it was sent and the moment it was
created, so making a schedule never sends the slot that has just passed, and a missed run is sent
once, not once per missed slot.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

DAILY, WEEKLY, MONTHLY = "daily", "weekly", "monthly"
FREQUENCIES = (DAILY, WEEKLY, MONTHLY)
MAX_MONTH_DAY = 28


def latest_slot(
    frequency: str, hour: int, weekday: int, day_of_month: int, now: datetime
) -> datetime:
    """The most recent slot at or before `now`, in the same (local) time as `now`."""
    if frequency not in FREQUENCIES:
        raise ValueError("unknown frequency")
    if not 0 <= hour <= 23:
        raise ValueError("hour must be 0 to 23")
    today_slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if frequency == DAILY:
        return today_slot if today_slot <= now else today_slot - timedelta(days=1)
    if frequency == WEEKLY:
        if not 0 <= weekday <= 6:
            raise ValueError("weekday must be 0 (Monday) to 6")
        slot = today_slot - timedelta(days=(now.weekday() - weekday) % 7)
        return slot if slot <= now else slot - timedelta(days=7)
    if not 1 <= day_of_month <= MAX_MONTH_DAY:
        raise ValueError("day of month must be 1 to 28")
    slot = today_slot.replace(day=day_of_month)
    if slot <= now:
        return slot
    previous = (today_slot.replace(day=1) - timedelta(days=1)).replace(day=day_of_month)
    return previous


def is_due(
    frequency: str,
    hour: int,
    weekday: int,
    day_of_month: int,
    *,
    now: datetime,
    created_at: datetime,
    last_sent: datetime | None,
) -> bool:
    slot = latest_slot(frequency, hour, weekday, day_of_month, now)
    after = created_at if last_sent is None else max(created_at, last_sent)
    return slot > after


def period(frequency: str, on: date) -> tuple[date, date]:
    """The days a report sent on `on` covers: yesterday, the seven days before today, or the last
    whole calendar month."""
    if frequency == DAILY:
        yesterday = on - timedelta(days=1)
        return yesterday, yesterday
    if frequency == WEEKLY:
        return on - timedelta(days=7), on - timedelta(days=1)
    if frequency == MONTHLY:
        last = on.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    raise ValueError("unknown frequency")
