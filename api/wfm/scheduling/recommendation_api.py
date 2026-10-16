"""Recommendations: ranked fixes for a roster week's gaps, applied one at a time (REC-01)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import recommendation_services as services
from .policy import ROSTER_WRITE_ROLES

router = Router(tags=["scheduling"])
PLANNERS = RoleSessionAuth(*sorted(ROSTER_WRITE_ROLES), feature=Feature.OPTIMISATION)


class ApplyIn(Schema):
    queueId: int  # noqa: N815
    weekStart: date  # noqa: N815
    employeeId: int  # noqa: N815
    day: date
    templateId: int  # noqa: N815


class RecommendationOut(Schema):
    kind: str  # "add" a person to a shift, or "change" the shift they have
    employeeId: int  # noqa: N815
    employee: str
    day: date
    templateId: int  # noqa: N815
    shift: str  # the shift's code
    replaces: str | None  # the code of the shift being changed
    closes: int  # people-half-hours no longer short
    addsOver: int  # noqa: N815 - half-hours that would then have one person too many
    text: str


class RecommendationAppliedOut(Schema):
    applied: bool
    closes: int


def _text(
    kind: str, employee: str, shift: str, replaces: str | None, day: date, closes: int
) -> str:
    when = f"{day:%a} {day.day} {day:%b}"
    what = (
        f"Change {employee} from {replaces} to {shift}"
        if kind == "change"
        else f"Add {employee} to {shift}"
    )
    return f"{what} on {when}: closes {closes} half-hours short."


@router.get(
    "",
    auth=PLANNERS,
    response=list[RecommendationOut],
    summary="Ranked fixes for the week's gaps",
)
def list_recommendations(
    request: HttpRequest, queue_id: int, week_start: date
) -> list[RecommendationOut]:
    found = services.recommendations(current_user(request), queue_id, week_start)
    people, shifts = found.context.employees, found.context.templates
    return [
        RecommendationOut(
            kind=r.kind,
            employeeId=r.person_id,
            employee=people[r.person_id].name,
            day=r.day,
            templateId=r.template_id,
            shift=shifts[r.template_id].code,
            replaces=shifts[r.replaces].code if r.replaces is not None else None,
            closes=r.closes,
            addsOver=r.adds_over,
            text=_text(
                r.kind,
                people[r.person_id].name,
                shifts[r.template_id].code,
                shifts[r.replaces].code if r.replaces is not None else None,
                r.day,
                r.closes,
            ),
        )
        for r in found.items
    ]


@router.post(
    "/apply", auth=PLANNERS, response=RecommendationAppliedOut, summary="Apply one suggestion"
)
def apply_recommendation(request: HttpRequest, body: ApplyIn) -> RecommendationAppliedOut:
    done = services.apply(
        user=current_user(request),
        queue_id=body.queueId,
        week_start=body.weekStart,
        employee_id=body.employeeId,
        day=body.day,
        template_id=body.templateId,
    )
    return RecommendationAppliedOut(applied=True, closes=done.closes)
