"""Reading quality results. Everything starts from `Model.objects.for_user(user)`.

There is no ranking, no average across people and no "best" or "worst" anywhere: a summary is one
person's own results, and lists are in employee-number order.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q
from wfm_engine import quality as engine

from wfm.accounts.models import Role, User
from wfm.core.errors import ApiError, not_found
from wfm.scheduling.models import Employee

from .models import QualityResult
from .policy import MAX_DAYS, TEAM_ROLES


@dataclass(frozen=True, slots=True)
class PersonSummary:
    employee: Employee
    summary: engine.Summary


@dataclass(frozen=True, slots=True)
class PersonResults:
    employee: Employee
    summary: engine.Summary
    results: list[QualityResult]  # newest first


def check_days(days: int) -> int:
    if not 1 <= days <= MAX_DAYS:
        raise ApiError(
            422, "quality.days_invalid", "Invalid request", f"Ask for 1 to {MAX_DAYS} days."
        )
    return days


def _evaluation(row: QualityResult) -> engine.Evaluation:
    return engine.Evaluation(
        login="",  # the engine summary never uses it; the login is not read back out
        evaluated_on=row.evaluated_on,
        kind=row.kind,
        ref=row.ref,
        score_pct=float(row.score_pct),
        csat=row.csat,
        coaching_due=row.coaching_due,
    )


def team(user: User, today: date, days: int) -> list[PersonSummary]:
    """One summary per person the caller may review, in employee-number order (never ranked).
    A lead is shown their team, not themselves (their own results are on `mine`)."""
    rows = QualityResult.objects.for_user(user).filter(
        evaluated_on__gt=today - timedelta(days=check_days(days)), evaluated_on__lte=today
    )
    if user.role == Role.LEAD:
        rows = rows.exclude(employee__user=user)
    by_person: dict[int, list[QualityResult]] = defaultdict(list)
    for row in rows.select_related("employee"):
        by_person[row.employee_id].append(row)
    return [
        PersonSummary(found[0].employee, engine.summarise(map(_evaluation, found), today))
        for found in sorted(by_person.values(), key=lambda f: f[0].employee.emp_no)
    ]


def _own_scope(user: User, employee_id: int) -> Employee:
    people = Employee.objects.for_user(user).filter(pk=employee_id)
    if user.role in TEAM_ROLES:  # the roster scope is wider than a lead's team
        people = people.filter(Q(manager__user=user) | Q(user=user))
    found: Employee | None = people.first()
    if found is None:
        raise not_found("No such employee.")
    return found


def person(user: User, employee_id: int, today: date, days: int) -> PersonResults:
    employee = _own_scope(user, employee_id)
    rows = list(
        QualityResult.objects.for_user(user)
        .filter(
            employee=employee,
            evaluated_on__gt=today - timedelta(days=check_days(days)),
            evaluated_on__lte=today,
        )
        .order_by("-evaluated_on", "-id")
    )
    return PersonResults(employee, engine.summarise(map(_evaluation, rows), today), rows)


def own_employee(user: User) -> Employee | None:
    return Employee.objects.for_user(user).filter(user=user).first()
