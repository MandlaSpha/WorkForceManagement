"""The intraday view of one queue and one day (INT-01 to INT-03)."""

from __future__ import annotations

from datetime import date, timedelta

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from wfm.accounts.models import Role
from wfm.core.errors import ApiError, not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.telephony.models import Queue

from . import selectors, suggestions

router = Router(tags=["intraday"])
READ = RoleSessionAuth(Role.ADMIN, Role.PLANNER, Role.LEAD, feature=Feature.INTRADAY)
ACT = RoleSessionAuth(Role.ADMIN, Role.PLANNER, feature=Feature.INTRADAY)
DAYS_BACK, DAYS_AHEAD = 60, 14


class IntradaySlotOut(Schema):
    slot: int
    forecast: float | None
    actual: int | None
    reforecast: float | None
    scheduled: int
    required: int | None
    expectedRequired: int | None  # noqa: N815


class IntradayAlertOut(Schema):
    slot: int
    scheduled: int
    required: int
    short: int
    severity: str  # warning or critical


class IntradayOut(Schema):
    queue: str
    day: date
    elapsed: int
    hasForecast: bool  # noqa: N815
    ratio: float | None
    dataThrough: int | None  # noqa: N815
    serviceLevelPct: float | None  # noqa: N815
    slots: list[IntradaySlotOut]
    alerts: list[IntradayAlertOut]


class IntradayPersonOut(Schema):
    employeeId: int  # noqa: N815
    name: str
    weekMinutes: int  # noqa: N815


class IntradayBreakOut(Schema):
    activityId: int  # noqa: N815
    employee: str
    kind: str
    start: str
    end: str
    moveTo: str  # noqa: N815
    slots: int


class IntradaySuggestionsOut(Schema):
    overtimeStart: str  # noqa: N815 - the span an overtime request would cover, "HH:MM"
    overtimeEnd: str  # noqa: N815
    people: list[IntradayPersonOut]
    breaks: list[IntradayBreakOut]


@router.get(
    "",
    auth=READ,
    response=IntradayOut,
    summary="A queue day: forecast, calls so far, cover, re-forecast and shortfalls",
)
def get_intraday(request: HttpRequest, queue_id: int, day: date) -> IntradayOut:
    today = timezone.localdate()
    if not today - timedelta(days=DAYS_BACK) <= day <= today + timedelta(days=DAYS_AHEAD):
        raise ApiError(
            422,
            "intraday.date_out_of_range",
            "Day out of range",
            "That day is too far back or ahead.",
        )
    found = selectors.intraday(current_user(request), queue_id, day)
    return IntradayOut(
        queue=found.queue_name,
        day=found.day,
        elapsed=found.elapsed,
        hasForecast=found.has_forecast,
        ratio=found.ratio,
        dataThrough=found.data_through,
        serviceLevelPct=found.service_level_pct,
        slots=[
            IntradaySlotOut(
                slot=s.slot,
                forecast=s.forecast,
                actual=s.actual,
                reforecast=s.reforecast,
                scheduled=s.scheduled,
                required=s.required,
                expectedRequired=s.expected_required,
            )
            for s in found.slots
        ],
        alerts=[
            IntradayAlertOut(
                slot=a.slot,
                scheduled=a.scheduled,
                required=a.required,
                short=a.short,
                severity=a.severity,
            )
            for a in found.alerts
        ],
    )


@router.get(
    "/suggestions",
    auth=ACT,
    response=IntradaySuggestionsOut,
    summary="Who could be asked for overtime, and which breaks could move, for a short half-hour",
)
def get_suggestions(
    request: HttpRequest, queue_id: int, day: date, slot: int
) -> IntradaySuggestionsOut:
    user = current_user(request)
    if not Queue.objects.for_user(user).filter(pk=queue_id).exists():
        raise not_found("No such queue.")
    today = timezone.localdate()
    if not 0 <= slot < 48 or not (
        today - timedelta(days=DAYS_BACK) <= day <= today + timedelta(days=DAYS_AHEAD)
    ):
        raise ApiError(
            422, "intraday.date_out_of_range", "Day out of range", "Choose a day and half-hour."
        )
    found = suggestions.suggestions(user, queue_id, day, slot)
    start, end = suggestions.overtime_span(slot)
    return IntradaySuggestionsOut(
        overtimeStart=f"{start:%H:%M}",
        overtimeEnd=f"{end:%H:%M}",
        people=[
            IntradayPersonOut(employeeId=p.employee_id, name=p.name, weekMinutes=p.week_minutes)
            for p in found.people
        ],
        breaks=[
            IntradayBreakOut(
                activityId=b.activity_id,
                employee=b.employee,
                kind=b.kind,
                start=b.start,
                end=b.end,
                moveTo=b.move_to,
                slots=b.slots,
            )
            for b in found.breaks
        ],
    )
