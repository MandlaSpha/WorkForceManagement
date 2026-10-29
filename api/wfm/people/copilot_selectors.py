"""Small, plain-data reads for the Copilot (tech spec section 8.2). Each starts from
`Model.objects.for_user(user)` or from the named-roles variant meant for yes/no and counts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from wfm.accounts.models import Role, User
from wfm.scheduling.models import Employee

from . import selectors
from .models import LeaveRequest, LeaveStatus

# Roles told HOW MANY people are away, never who.
ABSENCE_COUNT_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.EXECUTIVE})


@dataclass(frozen=True, slots=True)
class OwnBalance:
    leave_type: str
    entitlement: float | None
    taken: float
    pending: float
    available: float | None


def own_balances(user: User, year: int) -> list[OwnBalance]:
    """The signed-in person's leave balances. There is no employee parameter on purpose."""
    employee = selectors.own_employee(user)
    if employee is None:
        return []
    out = []
    for leave_type in selectors.leave_types(user):
        b = selectors.balance(employee, leave_type, year)
        out.append(
            OwnBalance(
                leave_type.name,
                None if b.entitlement is None else float(b.entitlement),
                float(b.taken),
                float(b.pending),
                None if b.available is None else float(b.available),
            )
        )
    return out


def leave_count_on(user: User, queue_id: int, day: date) -> int:
    """How many people skilled on the queue are on approved leave that day (a number only)."""
    return (
        LeaveRequest.objects.for_user(user)
        .filter(
            status=LeaveStatus.APPROVED,
            start_date__lte=day,
            end_date__gte=day,
            employee__skills__queue_id=queue_id,
        )
        .values("employee_id")
        .distinct()
        .count()
    )


@dataclass(frozen=True, slots=True)
class AbsenceRate:
    first: date
    last: date
    headcount: int
    away_person_days: int
    rate_pct: float


def absence_rate(user: User, first: date, last: date) -> AbsenceRate:
    """Approved leave as a share of employed person-days over the range. Counts only."""
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    headcount = Employee.objects.headcount_for(user, ABSENCE_COUNT_ROLES).count()
    away = 0
    for day in days:
        away += (
            LeaveRequest.objects.coverage_for(user, ABSENCE_COUNT_ROLES)
            .filter(status=LeaveStatus.APPROVED, start_date__lte=day, end_date__gte=day)
            .values("employee_id")
            .distinct()
            .count()
        )
    possible = headcount * len(days)
    return AbsenceRate(
        first, last, headcount, away, round(100 * away / possible, 1) if possible else 0.0
    )
