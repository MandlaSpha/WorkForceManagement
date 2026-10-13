"""Shared setup for forecasting tests: imported history built from synthetic workbooks."""

from __future__ import annotations

from datetime import date

from django.test import Client

from wfm.accounts.models import Role, User
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
