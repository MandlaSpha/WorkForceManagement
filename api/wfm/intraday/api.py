"""The intraday view of one queue and one day (INT-01 to INT-03)."""

from __future__ import annotations

from datetime import date, timedelta

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from wfm.accounts.models import Role
from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors

router = Router(tags=["intraday"])
READ = RoleSessionAuth(Role.ADMIN, Role.PLANNER, Role.LEAD, feature=Feature.INTRADAY)
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
