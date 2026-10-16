"""Reading everything the auto-scheduler needs, and asking it for a proposal (SCH-05).

Nothing is written here. The proposal is worked out afresh each time from what is in the database,
so a stale or tampered request can never put a shift in the roster: applying it recomputes it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Q
from wfm_engine import autoschedule as engine
from wfm_engine import availability as rules_availability
from wfm_engine.compliance import tightest

from wfm.accounts.models import User
from wfm.core.errors import ApiError
from wfm.people.models import Availability, AvailabilityKind, LeaveRequest, LeaveStatus

from .models import (
    Employee,
    RosterStatus,
    ShiftAssignment,
    ShiftTemplate,
)
from .selectors import rules_on, week_days, week_plan

CONTEXT_DAYS = 7  # shifts this far either side of the week matter to rest and days in a row


@dataclass(frozen=True, slots=True)
class Proposal:
    problem: engine.Problem
    solution: engine.Solution
    employees: dict[int, Employee]
    templates: dict[int, ShiftTemplate]


def _refuse(code: str, detail: str) -> ApiError:
    return ApiError(409, code, "Auto-schedule refused", detail)


def _windows(
    employee_ids: list[int], kind: str
) -> dict[int, tuple[rules_availability.Window, ...]]:
    found: dict[int, list[rules_availability.Window]] = {}
    for row in Availability.objects.filter(employee_id__in=employee_ids, kind=kind):
        found.setdefault(row.employee_id, []).append(
            rules_availability.window_of(row.weekday, row.start_time, row.end_time)
        )
    return {k: tuple(v) for k, v in found.items()}


def propose(user: User, queue_id: int, week_start: date) -> Proposal:
    """The shifts that would best fill this queue's week, given what is already rostered."""
    plan = week_plan(user, queue_id, week_start)  # refuses a bad queue or a non-Monday
    if plan.roster_status == RosterStatus.PUBLISHED:
        raise _refuse(
            "autoschedule.published",
            "This week is published. Return it to draft before filling it.",
        )
    days = week_days(week_start)
    required = {
        (day, cell.slot): cell.required
        for day, cells in plan.cells.items()
        for cell in cells
        if cell.required is not None
    }
    if not required:
        raise _refuse(
            "autoschedule.no_forecast",
            "There is no published forecast for this week, so nobody knows how many people "
            "are needed.",
        )

    templates = {t.pk: t for t in ShiftTemplate.objects.for_user(user)}
    if not templates:
        raise _refuse("autoschedule.no_shifts", "There are no shifts in the shift library.")

    first, last = days[0], days[-1]
    people = list(
        Employee.objects.for_user(user)
        .filter(skills__queue_id=queue_id)
        .filter(Q(start_date__isnull=True) | Q(start_date__lte=last))
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=first))
        .distinct()
    )
    ids = [p.pk for p in people]

    rules = tightest(rules_on(day) for day in days)
    cap_minutes = None if rules.max_weekly_hours is None else rules.max_weekly_hours * 60

    blocked: dict[int, set[date]] = {pk: set() for pk in ids}
    for person in people:
        for day in days:
            if (person.start_date and day < person.start_date) or (
                person.end_date and day > person.end_date
            ):
                blocked[person.pk].add(day)
    leave = LeaveRequest.objects.filter(
        employee_id__in=ids,
        status=LeaveStatus.APPROVED,
        start_date__lte=last,
        end_date__gte=first,
    )
    for row in leave:
        day = max(row.start_date, first)
        while day <= min(row.end_date, last):
            blocked[row.employee_id].add(day)
            day += timedelta(days=1)

    held: dict[int, list[engine.Held]] = {pk: [] for pk in ids}
    assignments = ShiftAssignment.objects.filter(
        employee_id__in=ids,
        day__gte=first - timedelta(days=CONTEXT_DAYS),
        day__lte=last + timedelta(days=CONTEXT_DAYS),
    ).select_related("roster_week")
    for a in assignments:
        held[a.employee_id].append(
            engine.Held(a.day, a.template_id, counts_here=a.roster_week.queue_id == queue_id)
        )

    cannot = _windows(ids, AvailabilityKind.UNAVAILABLE)
    rather = _windows(ids, AvailabilityKind.PREFERRED)
    problem = engine.Problem(
        week_start=week_start,
        templates=tuple(
            engine.Template(t.pk, t.start_time, t.end_time, t.paid_minutes)
            for t in templates.values()
        ),
        people=tuple(
            engine.Person(
                id=p.pk,
                max_week_minutes=min(
                    int(p.weekly_hours * 60), cap_minutes if cap_minutes is not None else 10**6
                ),
                blocked_days=frozenset(blocked[p.pk]),
                cannot_work=cannot.get(p.pk, ()),
                would_rather=rather.get(p.pk, ()),
                held=tuple(held[p.pk]),
            )
            for p in people
        ),
        required=required,
        rules=rules,
        max_time_s=float(settings.AUTOSCHEDULE_TIME_LIMIT_S),
    )
    return Proposal(
        problem=problem,
        solution=engine.solve(problem),
        employees={p.pk: p for p in people},
        templates=templates,
    )
