"""Shared setup for forecasting tests: imported history built from synthetic workbooks."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.test import Client

from wfm.accounts.models import Role, User
from wfm.telephony.models import IntervalActual, Queue
from wfm.telephony.tests.workbooks import Call, upload, workbook_bytes

# Mondays before the target Monday 25 May 2026, most recent first.
MON_4, MON_11, MON_18, MON_25 = (
    date(2026, 5, 4),
    date(2026, 5, 11),
    date(2026, 5, 18),
    date(2026, 5, 25),
)


def login(role: Role = Role.PLANNER) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def calls_at_ten(day: date, volume: int, first_id: int, queue: str = "QueueA") -> list[Call]:
    """`volume` answered inbound calls between 10:00 and 10:29 (the 10:00 half-hour), each handled
    for exactly 180 s (150 s talk + 30 s wrap-up)."""
    return [
        Call(
            first_id + i,
            queue,
            "Agent",
            f"{day.isoformat()} 10:{i // 2:02d}:{(i % 2) * 30:02d}",
            wait=0,
            talk=150,
            wrap=30,
        )
        for i in range(volume)
    ]


def import_mondays(volumes: dict[date, int], queue: str = "QueueA") -> None:
    """Import one report per day, each with `volume` calls in the 10:00 half-hour."""
    planner = login(Role.PLANNER)
    for index, (day, volume) in enumerate(sorted(volumes.items())):
        calls = calls_at_ten(day, volume, first_id=(index + 1) * 1000, queue=queue)
        response = planner.post(
            "/api/v1/telephony/imports", {"file": upload(workbook_bytes(calls), f"{day}.xlsx")}
        )
        assert response.status_code == 201, response.content


SLOTS_WITH_CALLS = (18, 19, 20, 21, 22)  # 09:00 to 11:30, so every day has the same shape


def add_days(queue_name: str, daily: dict[date, int]) -> Queue:
    """Give a queue `daily[day]` answered calls on each day, spread evenly over five half-hours
    (the first takes the remainder), each handled for 180 s. Straight into the interval table, so
    weeks of history cost milliseconds instead of one workbook import per day."""
    zone = ZoneInfo("Africa/Johannesburg")
    queue, _ = Queue.objects.get_or_create(name=queue_name)
    rows = []
    for day, total in daily.items():
        each, extra = divmod(total, len(SLOTS_WITH_CALLS))
        for n, slot in enumerate(SLOTS_WITH_CALLS):
            calls = each + (extra if n == 0 else 0)
            start = datetime(day.year, day.month, day.day, slot // 2, 30 * (slot % 2), tzinfo=zone)
            rows.append(
                IntervalActual(
                    queue=queue,
                    interval_start=start,
                    offered=calls,
                    answered=calls,
                    abandoned=0,
                    answered_in_sl=calls,
                    sum_wait_s=0,
                    sum_handle_s=180 * calls,
                )
            )
    IntervalActual.objects.bulk_create(rows)
    return queue
