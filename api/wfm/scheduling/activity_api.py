"""Breaks and activities inside a week's shifts (SCH-03)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from django.http import HttpRequest
from ninja import Router, Schema, Status

from wfm.core.errors import not_found
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.telephony.models import Queue

from . import activity_services as services
from .api import FEATURE
from .models import ShiftActivity, ShiftAssignment
from .policy import READ_ROLES, ROSTER_WRITE_ROLES

router = Router(tags=["scheduling"])
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
WRITE = RoleSessionAuth(*sorted(ROSTER_WRITE_ROLES), feature=FEATURE)


class ActivityIn(Schema):
    queueId: int  # noqa: N815
    employeeId: int  # noqa: N815
    day: date
    kind: str
    startTime: time  # noqa: N815 - on the hour or half-hour, inside the shift
    minutes: int  # a whole number of half-hours


class ActivityOut(Schema):
    id: int
    assignmentId: int  # noqa: N815
    employeeId: int  # noqa: N815
    employee: str
    day: date
    shift: str  # the shift's code
    kind: str
    startTime: str  # noqa: N815 - "HH:MM", from the start of the shift
    endTime: str  # noqa: N815
    slots: int
    offsetSlots: int  # noqa: N815


def _out(a: ShiftActivity) -> ActivityOut:
    shift = a.assignment
    began = datetime.combine(shift.day, shift.template.start_time) + timedelta(
        minutes=30 * a.offset_slots
    )
    finished = began + timedelta(minutes=30 * a.slots)
    return ActivityOut(
        id=a.pk,
        assignmentId=shift.pk,
        employeeId=shift.employee_id,
        employee=shift.employee.name,
        day=shift.day,
        shift=shift.template.code,
        kind=a.kind,
        startTime=f"{began:%H:%M}",
        endTime=f"{finished:%H:%M}",
        slots=a.slots,
        offsetSlots=a.offset_slots,
    )


@router.get(
    "",
    auth=READ,
    response=list[ActivityOut],
    summary="The breaks and activities in one queue's shifts for a week",
)
def list_activities(request: HttpRequest, queue_id: int, week_start: date) -> list[ActivityOut]:
    user = current_user(request)
    if not Queue.objects.for_user(user).filter(pk=queue_id).exists():
        raise not_found("No such queue.")
    found = (
        ShiftActivity.objects.filter(
            assignment__in=ShiftAssignment.objects.for_user(user).filter(
                roster_week__queue_id=queue_id,
                day__gte=week_start,
                day__lte=week_start + timedelta(days=6),
            )
        )
        .select_related("assignment__employee", "assignment__template")
        .order_by("assignment__day", "assignment__employee__name", "offset_slots")
    )
    return [_out(a) for a in found]


@router.post("", auth=WRITE, response={201: ActivityOut}, summary="Add a break or activity")
def add_activity(request: HttpRequest, body: ActivityIn) -> Status[ActivityOut]:
    made = services.add(
        user=current_user(request),
        queue_id=body.queueId,
        employee_id=body.employeeId,
        day=body.day,
        kind=body.kind,
        start_time=body.startTime,
        minutes=body.minutes,
    )
    made = ShiftActivity.objects.select_related("assignment__employee", "assignment__template").get(
        pk=made.pk
    )
    return Status(201, _out(made))


class ActivityMoveIn(Schema):
    startTime: time  # noqa: N815 - the new start, on the hour or half-hour


@router.post(
    "/{activity_id}/move",
    auth=WRITE,
    response=ActivityOut,
    summary="Move a break or activity to another start inside its shift",
)
def move_activity(request: HttpRequest, activity_id: int, body: ActivityMoveIn) -> ActivityOut:
    made = services.move(
        user=current_user(request), activity_id=activity_id, start_time=body.startTime
    )
    made = ShiftActivity.objects.select_related("assignment__employee", "assignment__template").get(
        pk=made.pk
    )
    return _out(made)


@router.delete(
    "/{activity_id}", auth=WRITE, response={204: None}, summary="Remove a break or activity"
)
def remove_activity(request: HttpRequest, activity_id: int) -> Status[None]:
    services.remove(user=current_user(request), activity_id=activity_id)
    return Status(204, None)
