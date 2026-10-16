"""Auto-schedule a roster week: preview what it would do, then apply it (SCH-05, PLN-04)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import autoschedule_selectors as selectors
from . import autoschedule_services as services
from .policy import ROSTER_WRITE_ROLES

router = Router(tags=["scheduling"])
ROSTER_WRITE = RoleSessionAuth(*sorted(ROSTER_WRITE_ROLES), feature=Feature.OPTIMISATION)


class AutoIn(Schema):
    queueId: int  # noqa: N815
    weekStart: date  # noqa: N815


class PlacementOut(Schema):
    employeeId: int  # noqa: N815
    employee: str
    day: date
    shift: str  # the shift's code


class ProposalOut(Schema):
    status: str  # optimal, feasible, or none (no answer found)
    placements: list[PlacementOut]
    shortBefore: int  # noqa: N815 - people-half-hours short with nothing added
    shortAfter: int  # noqa: N815
    overAfter: int  # noqa: N815
    kept: int  # shifts already on this queue, left as they are


class AppliedOut(ProposalOut):
    placed: int
    skipped: dict[str, int]  # refusal code -> how many the roster refused when applying


def _proposal(found: selectors.Proposal) -> ProposalOut:
    solution = found.solution
    return ProposalOut(
        status=solution.status,
        placements=[
            PlacementOut(
                employeeId=employee_id,
                employee=found.employees[employee_id].name,
                day=day,
                shift=found.templates[template_id].code,
            )
            for employee_id, day, template_id in solution.placements
        ],
        shortBefore=solution.short_before,
        shortAfter=solution.short_after,
        overAfter=solution.over_after,
        kept=solution.kept,
    )


@router.post(
    "/preview", auth=ROSTER_WRITE, response=ProposalOut, summary="What auto-schedule would add"
)
def preview(request: HttpRequest, body: AutoIn) -> ProposalOut:
    return _proposal(selectors.propose(current_user(request), body.queueId, body.weekStart))


@router.post("", auth=ROSTER_WRITE, response=AppliedOut, summary="Fill the week automatically")
def apply(request: HttpRequest, body: AutoIn) -> AppliedOut:
    applied = services.apply(current_user(request), body.queueId, body.weekStart)
    shown = _proposal(applied.proposal)
    return AppliedOut(**shown.dict(), placed=applied.placed, skipped=applied.skipped)
