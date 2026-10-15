"""Employee self-service: your declared availability and your own schedule (ESS-01, SCH-08)."""

from __future__ import annotations

from datetime import date, timedelta

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Status

from wfm.core.errors import ApiError, not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.scheduling.models import Employee

from . import availability_services as services
from . import ess_selectors as selectors
from . import selectors as people_selectors
from .ess_schemas import (
    AvailabilityIn,
    AvailabilityOut,
    MyLeaveOut,
    MyScheduleOut,
    MyShiftOut,
)
from .models import Availability
from .policy import SELF_ROLES

router = Router(tags=["people"])
SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=Feature.PEOPLE)

DEFAULT_DAYS = 28
MAX_DAYS = 62


def _employee(request: HttpRequest, employee_id: int | None, area: str) -> Employee:
    user = current_user(request)
    if employee_id is None:
        own = people_selectors.own_employee(user)
        if own is None:
            raise ApiError(
                422,
                f"{area}.no_employee_record",
                "Not on the employee list",
                "You are not on the employee list yet, so there is nothing to show. "
                "A planner adds you.",
            )
        return own
    found = people_selectors.employee_in_scope(user, employee_id)
    if found is None:
        raise not_found("No such employee.")
    return found


@router.get(
    "/availability",
    auth=SELF,
    response=list[AvailabilityOut],
    summary="Declared availability: your own, or anyone's for leads, planners and admins",
)
def list_availability(
    request: HttpRequest, employee_id: int | None = None
) -> list[AvailabilityOut]:
    employee = _employee(request, employee_id, "availability")
    return [_out(w) for w in selectors.windows(current_user(request), employee)]


@router.post(
    "/availability",
    auth=SELF,
    response={201: AvailabilityOut},
    summary="Declare a weekly window you cannot work, or would rather work",
)
def add_availability(request: HttpRequest, body: AvailabilityIn) -> Status[AvailabilityOut]:
    window = services.add_window(
        user=current_user(request),
        weekday=body.weekday,
        start=body.startTime,
        end=body.endTime,
        kind=body.kind,
        employee_id=body.employeeId,
    )
    return Status(201, _out(window))


@router.delete(
    "/availability/{window_id}",
    auth=SELF,
    response=dict[str, bool],
    summary="Remove a window",
)
def remove_availability(request: HttpRequest, window_id: int) -> dict[str, bool]:
    services.remove_window(user=current_user(request), window_id=window_id)
    return {"ok": True}


@router.get(
    "/my-schedule",
    auth=SELF,
    response=MyScheduleOut,
    summary="Your published shifts and leave for the coming weeks",
)
def my_schedule(
    request: HttpRequest, from_date: date | None = None, to_date: date | None = None
) -> MyScheduleOut:
    employee = _employee(request, None, "schedule")
    first = from_date or timezone.localdate()
    last = to_date or first + timedelta(days=DEFAULT_DAYS - 1)
    if last < first or (last - first).days + 1 > MAX_DAYS:
        raise ApiError(
            422, "schedule.range_invalid", "Schedule refused", f"Ask for 1 to {MAX_DAYS} days."
        )
    found = selectors.my_schedule(employee, first, last)
    return MyScheduleOut(
        employee=employee.name,
        fromDate=first,
        toDate=last,
        shifts=[
            MyShiftOut(
                day=a.day,
                shift=a.template.code,
                startTime=a.template.start_time,
                endTime=a.template.end_time,
                queue=a.roster_week.queue.name,
            )
            for a in found.shifts
        ],
        leave=[
            MyLeaveOut(
                startDate=r.start_date,
                endDate=r.end_date,
                leaveType=r.leave_type.name,
                status=r.status,
            )
            for r in found.leave
        ],
        unpublishedShifts=found.unpublished,
        openSwaps=found.open_swaps,
    )


def _out(w: Availability) -> AvailabilityOut:
    return AvailabilityOut(
        id=w.pk,
        employeeId=w.employee_id,
        employee=w.employee.name,
        weekday=w.weekday,
        startTime=w.start_time,
        endTime=w.end_time,
        kind=w.kind,
    )
