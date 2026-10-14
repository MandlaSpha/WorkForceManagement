"""Shared setup for scheduling tests: queues, shifts, people and a published forecast."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.test import Client

from wfm.accounts.models import Role, User
from wfm.forecasting.models import ForecastInterval, ForecastStatus, ForecastVersion
from wfm.scheduling.models import Employee, EmployeeSkill, ShiftTemplate
from wfm.telephony.models import Queue

SAST = ZoneInfo("Africa/Johannesburg")

# Monday 25 May 2026 and the days around it.
SUN_24, MON, TUE, WED, THU, FRI, SAT, SUN = (
    date(2026, 5, 24) + timedelta(days=n) for n in range(8)
)
NEXT_MON = date(2026, 6, 1)

ROSTER = "/api/v1/scheduling/roster"
ASSIGN = "/api/v1/scheduling/roster/assignments"
SHIFTS = "/api/v1/scheduling/shifts"
EMPLOYEES = "/api/v1/scheduling/employees"
PLAN = "/api/v1/scheduling/plan"


def login(role: Role = Role.PLANNER) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def params(q: Queue, day: date) -> dict[str, str | int]:
    """The query string of the roster and plan endpoints."""
    return {"queue_id": q.pk, "week_start": str(day)}


def queue(name: str = "QueueA") -> Queue:
    return Queue.objects.get_or_create(name=name)[0]


def shift(code: str, start: str, end: str, paid: int) -> ShiftTemplate:
    """A shift template made directly, so tests of the roster do not depend on the shift API."""
    return ShiftTemplate.objects.create(
        code=code,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        paid_minutes=paid,
    )


def standard_shifts() -> dict[str, ShiftTemplate]:
    return {
        "E1": shift("E1", "07:00", "15:30", 480),
        "D1": shift("D1", "09:00", "17:30", 480),
        "L1": shift("L1", "13:00", "22:00", 480),
        "N1": shift("N1", "22:00", "06:00", 480),
        "P1": shift("P1", "10:00", "14:00", 240),
    }


def person(
    emp_no: str = "E001",
    *,
    queues: tuple[str, ...] = ("QueueA",),
    hours: float = 40,
    name: str | None = None,
    **fields: Any,
) -> Employee:
    employee = Employee.objects.create(
        emp_no=emp_no,
        name=name or f"Person {emp_no}",
        weekly_hours=hours,
        weekly_hours_is_default=False,
        **fields,
    )
    for q in queues:
        EmployeeSkill.objects.create(employee=employee, queue=queue(q))
    return employee


def assign(
    client: Client, q: Queue, employee: Employee, day: date, template: ShiftTemplate | None
) -> Any:
    return client.put(
        ASSIGN,
        {
            "queueId": q.pk,
            "employeeId": employee.pk,
            "day": str(day),
            "templateId": template.pk if template else None,
        },
        content_type="application/json",
    )


def publish_forecast(q: Queue, required: dict[tuple[date, int], int | None]) -> ForecastVersion:
    """A PUBLISHED forecast with a chosen requirement per half-hour. Written directly so plan
    tests state exactly what is required instead of depending on the forecast engine. Days that
    appear in `required` get all 48 half-hours (zero where not named); other days get none."""
    user, _ = User.objects.get_or_create(username="forecaster", defaults={"role": Role.PLANNER})
    days = sorted({d for d, _ in required})
    version = ForecastVersion.objects.create(
        queue=q,
        label="published",
        status=ForecastStatus.PUBLISHED,
        method="test",
        params={"assumptionsConfirmed": True},
        date_from=days[0],
        date_to=days[-1],
        created_by=user,
    )
    ForecastInterval.objects.bulk_create(
        ForecastInterval(
            version=version,
            interval_start=datetime.combine(day, time(slot // 2, 30 * (slot % 2)), tzinfo=SAST),
            volume=1.0,
            aht_s=180.0,
            required_raw=0,
            required=required.get((day, slot), 0),
            days_used=1,
        )
        for day in days
        for slot in range(48)
    )
    return version
