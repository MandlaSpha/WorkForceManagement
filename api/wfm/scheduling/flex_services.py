"""Borrowing people across queues, and doing it (SCH-09).

Reading changes nothing. Applying never trusts what the client saw: the suggestions are worked out
again and the request must match one still on the list, otherwise it is refused as stale. The move
itself goes through `roster_services.move_to_queue`, which checks the roster rules and audits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from wfm_engine import flex as engine
from wfm_engine.roster import SlotKey

from wfm.accounts.models import User
from wfm.core.errors import ApiError

from .models import Employee, ShiftAssignment, ShiftTemplate
from .roster_services import move_to_queue
from .selectors import Plan, week_days, week_plan

SHOWN = 10
CHECKED = 500


@dataclass(frozen=True, slots=True)
class Flexing:
    queue_name: str
    items: list[engine.Flex]
    employees: dict[int, Employee]
    templates: dict[int, ShiftTemplate]
    queue_names: dict[int, str]


def _maps(plan: Plan) -> tuple[dict[SlotKey, int | None], dict[SlotKey, int]]:
    required: dict[SlotKey, int | None] = {}
    covered: dict[SlotKey, int] = {}
    for day, cells in plan.cells.items():
        for cell in cells:
            required[(day, cell.slot)] = cell.required
            covered[(day, cell.slot)] = cell.scheduled
    return required, covered


def suggestions(user: User, queue_id: int, week_start: date, limit: int = SHOWN) -> Flexing:
    plan = week_plan(user, queue_id, week_start)  # refuses a bad queue or a non-Monday
    required, covered = _maps(plan)
    days = week_days(week_start)

    rows = list(
        ShiftAssignment.objects.for_user(user)
        .filter(
            day__gte=days[0],
            day__lte=days[-1],
            employee__skills__queue_id=queue_id,
            roster_week__status="draft",
        )
        .exclude(roster_week__queue_id=queue_id)
        .select_related("employee", "template", "roster_week__queue")
        .distinct()
    )
    # A week already published cannot lend anyone, so those queues are not donors.
    donor_ids = {r.roster_week.queue_id for r in rows}
    donors: dict[int, engine.Donor] = {}
    for donor_id in donor_ids:
        donor_plan = week_plan(user, donor_id, week_start)
        donor_required, donor_covered = _maps(donor_plan)
        donors[donor_id] = engine.Donor(donor_required, donor_covered)

    candidates = [
        engine.Candidate(
            r.employee_id,
            r.roster_week.queue_id,
            r.day,
            r.template_id,
            r.template.start_time,
            r.template.end_time,
        )
        for r in rows
    ]
    items = engine.suggest(required, covered, donors, candidates, limit=limit)
    return Flexing(
        queue_name=plan.queue.name,
        items=items,
        employees={r.employee_id: r.employee for r in rows},
        templates={r.template_id: r.template for r in rows},
        queue_names={r.roster_week.queue_id: r.roster_week.queue.name for r in rows},
    )


def apply(
    *, user: User, queue_id: int, week_start: date, employee_id: int, day: date
) -> engine.Flex:
    found = suggestions(user, queue_id, week_start, limit=CHECKED)
    match = next(
        (f for f in found.items if (f.person_id, f.day) == (employee_id, day)),
        None,
    )
    if match is None:
        raise ApiError(
            409,
            "flex.stale",
            "Suggestion refused",
            "That suggestion no longer applies: the rosters have changed. Look at the list again.",
        )
    move_to_queue(user=user, queue_id=queue_id, employee_id=employee_id, day=day)
    return match
