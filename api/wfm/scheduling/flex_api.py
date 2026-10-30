"""Cross-queue flexing: people to borrow from queues that can spare them (SCH-09)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import flex_services as services
from .policy import ROSTER_WRITE_ROLES

router = Router(tags=["scheduling"])
PLANNERS = RoleSessionAuth(*sorted(ROSTER_WRITE_ROLES), feature=Feature.OPTIMISATION)


class FlexApplyIn(Schema):
    queueId: int  # noqa: N815
    weekStart: date  # noqa: N815
    employeeId: int  # noqa: N815
    day: date


class FlexOut(Schema):
    employeeId: int  # noqa: N815
    employee: str
    fromQueue: str  # noqa: N815
    day: date
    shift: str  # the shift's code
    closes: int  # people-half-hours no longer short
    addsOver: int  # noqa: N815 - half-hours that would then have one person too many
    text: str


class FlexAppliedOut(Schema):
    applied: bool
    closes: int


@router.get("", auth=PLANNERS, response=list[FlexOut], summary="People to borrow across queues")
def list_flex(request: HttpRequest, queue_id: int, week_start: date) -> list[FlexOut]:
    found = services.suggestions(current_user(request), queue_id, week_start)
    out = []
    for f in found.items:
        name = found.employees[f.person_id].name
        shift = found.templates[f.template_id].code
        donor = found.queue_names[f.donor_queue_id]
        when = f"{f.day:%a} {f.day.day} {f.day:%b}"
        out.append(
            FlexOut(
                employeeId=f.person_id,
                employee=name,
                fromQueue=donor,
                day=f.day,
                shift=shift,
                closes=f.closes,
                addsOver=f.adds_over,
                text=(
                    f"Borrow {name} ({shift}) from {donor} on {when}: "
                    f"closes {f.closes} half-hours short."
                ),
            )
        )
    return out


@router.post("/apply", auth=PLANNERS, response=FlexAppliedOut, summary="Borrow one person")
def apply_flex(request: HttpRequest, body: FlexApplyIn) -> FlexAppliedOut:
    done = services.apply(
        user=current_user(request),
        queue_id=body.queueId,
        week_start=body.weekStart,
        employee_id=body.employeeId,
        day=body.day,
    )
    return FlexAppliedOut(applied=True, closes=done.closes)
