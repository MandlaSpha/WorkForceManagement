"""Report schedules: who gets which report, how often (RPT-04, RPT-10)."""

from __future__ import annotations

from datetime import datetime

from django.http import HttpRequest
from ninja import Router, Schema, Status

from wfm.accounts.models import Role
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import services
from .models import ReportSchedule

router = Router(tags=["reports"])
SCHEDULERS = (Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE, Role.CUSTOMER_OPS)
AUTH = RoleSessionAuth(*SCHEDULERS, feature=Feature.INSIGHT)
ADMIN = RoleSessionAuth(Role.ADMIN, feature=Feature.INSIGHT)


class ScheduleIn(Schema):
    report: str
    queueId: int | None = None  # noqa: N815 - the queue a peaks report is about
    recipients: list[str]
    frequency: str
    hour: int
    weekday: int = 0
    dayOfMonth: int = 1  # noqa: N815


class SchedulePatch(Schema):
    recipients: list[str] | None = None
    frequency: str | None = None
    hour: int | None = None
    weekday: int | None = None
    dayOfMonth: int | None = None  # noqa: N815
    paused: bool | None = None


class ScheduleOut(Schema):
    id: int
    report: str
    queueId: int | None  # noqa: N815
    queue: str
    recipients: list[str]
    frequency: str
    hour: int
    weekday: int
    dayOfMonth: int  # noqa: N815
    paused: bool
    lastSentAt: datetime | None  # noqa: N815
    lastOutcome: str  # noqa: N815
    mine: bool
    owner: str  # the owner's name, shown to the admin only


class SettingsOut(Schema):
    allowedDomains: list[str]  # noqa: N815


class SettingsIn(Schema):
    allowedDomains: list[str]  # noqa: N815


def _out(s: ReportSchedule, user_id: int, as_admin: bool) -> ScheduleOut:
    return ScheduleOut(
        id=s.pk,
        report=s.report,
        queueId=s.queue_id,
        queue=s.queue.name if s.queue else "",
        recipients=list(s.recipients),
        frequency=s.frequency,
        hour=s.hour,
        weekday=s.weekday,
        dayOfMonth=s.day_of_month,
        paused=s.paused,
        lastSentAt=s.last_sent_at,
        lastOutcome=s.last_outcome,
        mine=s.owner_id == user_id,
        owner=s.owner.get_full_name() or s.owner.username if as_admin else "",
    )


def _one(request: HttpRequest, schedule_id: int) -> ScheduleOut:
    user = current_user(request)
    found = (
        ReportSchedule.objects.for_user(user).select_related("owner", "queue").get(pk=schedule_id)
    )
    return _out(found, user.pk, user.role == Role.ADMIN)


@router.get("/schedules", auth=AUTH, response=list[ScheduleOut], summary="Report schedules")
def list_schedules(request: HttpRequest) -> list[ScheduleOut]:
    user = current_user(request)
    found = ReportSchedule.objects.for_user(user).select_related("owner", "queue")
    return [_out(s, user.pk, user.role == Role.ADMIN) for s in found]


@router.post("/schedules", auth=AUTH, response={201: ScheduleOut}, summary="Schedule a report")
def create(request: HttpRequest, body: ScheduleIn) -> Status[ScheduleOut]:
    made = services.create(
        user=current_user(request),
        report=body.report,
        queue_id=body.queueId,
        recipients=body.recipients,
        frequency=body.frequency,
        hour=body.hour,
        weekday=body.weekday,
        day_of_month=body.dayOfMonth,
    )
    return Status(201, _one(request, made.pk))


@router.patch(
    "/schedules/{schedule_id}",
    auth=AUTH,
    response=ScheduleOut,
    summary="Change or pause a schedule",
)
def change(request: HttpRequest, schedule_id: int, body: SchedulePatch) -> ScheduleOut:
    services.update(
        user=current_user(request),
        schedule_id=schedule_id,
        recipients=body.recipients,
        frequency=body.frequency,
        hour=body.hour,
        weekday=body.weekday,
        day_of_month=body.dayOfMonth,
        paused=body.paused,
    )
    return _one(request, schedule_id)


@router.delete("/schedules/{schedule_id}", auth=AUTH, response={204: None}, summary="Delete one")
def remove(request: HttpRequest, schedule_id: int) -> Status[None]:
    services.delete(user=current_user(request), schedule_id=schedule_id)
    return Status(204, None)


@router.get("/settings", auth=AUTH, response=SettingsOut, summary="Email domains reports may use")
def get_settings(request: HttpRequest) -> SettingsOut:
    return SettingsOut(allowedDomains=services.allowed_domains())


@router.put("/settings", auth=ADMIN, response=SettingsOut, summary="Set the allowed email domains")
def put_settings(request: HttpRequest, body: SettingsIn) -> SettingsOut:
    return SettingsOut(
        allowedDomains=services.set_allowed_domains(
            user=current_user(request), domains=body.allowedDomains
        )
    )
