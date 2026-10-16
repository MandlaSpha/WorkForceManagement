"""Filling a roster week automatically (SCH-05, PLN-04).

Applying never trusts a proposal the client saw: it is worked out again, and every shift goes in
through the same `assign` the planner's own clicks use, so each is checked by the roster rules and
audited one by one. Whatever the roster refuses (someone changed something in the meantime) is
skipped and counted, never forced. The summary audit event is the LAST write."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError

from .autoschedule_selectors import Proposal, propose
from .roster_services import assign


@dataclass(frozen=True, slots=True)
class Applied:
    proposal: Proposal
    placed: int
    skipped: dict[str, int] = field(default_factory=dict)  # refusal code -> how many


def apply(user: User, queue_id: int, week_start: date) -> Applied:
    proposal = propose(user, queue_id, week_start)
    placed = 0
    skipped: dict[str, int] = {}
    for employee_id, day, template_id in proposal.solution.placements:
        try:
            assign(
                user=user,
                queue_id=queue_id,
                employee_id=employee_id,
                day=day,
                template_id=template_id,
            )
            placed += 1
        except ApiError as refusal:
            skipped[refusal.code] = skipped.get(refusal.code, 0) + 1
    solution = proposal.solution
    with transaction.atomic():
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ROSTER_AUTO_SCHEDULED,
            entity_type="queue",
            entity_id=str(queue_id),
            changes=[
                audit.FieldChange(
                    "roster_week",
                    f"{queue_id}:{week_start}",
                    "shifts_added",
                    None,
                    f"{placed} placed, {sum(skipped.values())} skipped; "
                    f"half-hours short {solution.short_before} to {solution.short_after}",
                )
            ],
        )
    return Applied(proposal=proposal, placed=placed, skipped=skipped)
