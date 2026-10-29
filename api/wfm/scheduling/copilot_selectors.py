"""Small, plain-data reads for the Copilot (tech spec section 8.2). Each starts from
`Model.objects.for_user(user)` or from the named-roles variant meant for aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, Q

from wfm.accounts.models import Role, User

from .models import Employee, ShiftAssignment

# Roles that may be told HOW MANY people are rostered or employed, never who.
COUNT_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE})


@dataclass(frozen=True, slots=True)
class OnShift:
    name: str
    shift: str
    start: str
    end: str
    queue: str


def team_on_shift(user: User, day: date) -> list[OnShift]:
    """Who of the lead's own team is rostered on `day`. The roster itself is readable by every
    lead, so the team limit is applied here, in the query, and not left to the caller."""
    found = (
        ShiftAssignment.objects.for_user(user)
        .filter(day=day, employee__manager__user=user)
        .select_related("employee", "template", "roster_week__queue")
        .order_by("template__start_time", "employee__name")
    )
    return [
        OnShift(
            name=a.employee.name,
            shift=a.template.code,
            start=f"{a.template.start_time:%H:%M}",
            end=f"{a.template.end_time:%H:%M}",
            queue=a.roster_week.queue.name,
        )
        for a in found
    ]


@dataclass(frozen=True, slots=True)
class DayCount:
    day: date
    on_shift: int


@dataclass(frozen=True, slots=True)
class CoverageCounts:
    week_start: date
    headcount: int
    days: list[DayCount]


def coverage_counts(user: User, week_start: date) -> CoverageCounts:
    """People rostered per day and people employed, as numbers only (no names)."""
    last = week_start + timedelta(days=6)
    rows = dict(
        ShiftAssignment.objects.counts_for(user, COUNT_ROLES)
        .filter(day__gte=week_start, day__lte=last)
        .values_list("day")
        .annotate(n=Count("employee", distinct=True))
        .order_by("day")
    )
    headcount = (
        Employee.objects.headcount_for(user, COUNT_ROLES)
        .filter(Q(start_date__isnull=True) | Q(start_date__lte=last))
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=week_start))
        .count()
    )
    return CoverageCounts(
        week_start,
        headcount,
        [DayCount(d, rows.get(d, 0)) for d in (week_start + timedelta(days=n) for n in range(7))],
    )
