"""Auto-schedule a roster week: preview what it would do, then apply it (SCH-05, PLN-04)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema, Status

from wfm.core.errors import not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.jobs import services as jobs
from wfm.jobs.api import JobOut, job_out
from wfm.jobs.runners import AUTO_SCHEDULE
from wfm.telephony.models import Queue

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


@router.post(
    "/jobs",
    auth=ROSTER_WRITE,
    response={202: JobOut},
    summary="Fill the week automatically in the background",
)
def apply_in_background(request: HttpRequest, body: AutoIn) -> Status[JobOut]:
    """Answers at once with a job to ask about. The worker does the same as the call below, as
    this person, so their scope, the roster rules and the audit trail apply."""
    user = current_user(request)
    if not Queue.objects.for_user(user).filter(pk=body.queueId).exists():
        raise not_found("No such queue.")
    job = jobs.start(
        user=user,
        kind=AUTO_SCHEDULE,
        params={"queue_id": body.queueId, "week_start": body.weekStart.isoformat()},
    )
    return Status(202, job_out(job))


@router.post("", auth=ROSTER_WRITE, response=AppliedOut, summary="Fill the week automatically")
def apply(request: HttpRequest, body: AutoIn) -> AppliedOut:
    applied = services.apply(current_user(request), body.queueId, body.weekStart)
    shown = _proposal(applied.proposal)
    return AppliedOut(**shown.dict(), placed=applied.placed, skipped=applied.skipped)
