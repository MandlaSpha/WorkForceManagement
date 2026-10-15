"""Reading leave. Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, QuerySet
from wfm_engine import leave as rules
from wfm_engine.roster import shift_slots

from wfm.accounts.models import Role, User
from wfm.core.errors import not_found
from wfm.scheduling.models import Employee, ShiftAssignment
from wfm.scheduling.selectors import PlanCell, week_plan

from .models import LeaveRequest, LeaveStatus, LeaveType
from .policy import ALL_SCOPE_ROLES


def leave_types(user: User) -> list[LeaveType]:
    return list(LeaveType.objects.for_user(user))


def own_employee(user: User) -> Employee | None:
    return Employee.objects.filter(user=user).first()


def employee_in_scope(user: User, employee_id: int) -> Employee | None:
    """An employee the person may act on: anyone for a planner or admin, their team (and
    themselves) for a lead, only themselves for an agent. None when out of scope, which the
    caller answers as 'not found'."""
    found = Employee.objects.filter(pk=employee_id)
    if user.role in ALL_SCOPE_ROLES:
        return found.first()
    if user.role == Role.LEAD:
        return found.filter(Q(manager__user=user) | Q(user=user)).first()
    if user.role == Role.AGENT:
        return found.filter(user=user).first()
    return None


def requests(
    user: User, *, status: str | None = None, employee_id: int | None = None
) -> QuerySet[LeaveRequest]:
    found = LeaveRequest.objects.for_user(user).select_related("employee", "leave_type")
    if status:
        found = found.filter(status=status)
    if employee_id is not None:
        found = found.filter(employee_id=employee_id)
    return found.order_by("-start_date", "-id")


def request_for(user: User, request_id: int) -> LeaveRequest:
    found: LeaveRequest | None = (
        LeaveRequest.objects.for_user(user)
        .select_related("employee", "leave_type")
        .filter(pk=request_id)
        .first()
    )
    if found is None:
        raise not_found("No such leave request.")
    return found


def days_in_year(employee: Employee, leave_type: LeaveType, year: int, status: str) -> Decimal:
    """Days of a year already counted under `status` for this person and type."""
    total = Decimal(0)
    for by_year in LeaveRequest.objects.filter(
        employee=employee, leave_type=leave_type, status=status
    ).values_list("days_by_year", flat=True):
        total += Decimal(by_year.get(str(year), 0))
    return total


def balance(employee: Employee, leave_type: LeaveType, year: int) -> rules.Balance:
    return rules.balance(
        leave_type.days_per_year,
        days_in_year(employee, leave_type, year, LeaveStatus.APPROVED),
        days_in_year(employee, leave_type, year, LeaveStatus.PENDING),
    )


def impact(user: User, leave: LeaveRequest) -> rules.Impact:
    """What approving the request would do to coverage: every shift the person has on the leave
    days, and for each half-hour of it whether the queue stays covered without them."""
    assignments = list(
        ShiftAssignment.objects.for_user(user)
        .filter(employee=leave.employee, day__gte=leave.start_date, day__lte=leave.end_date)
        .select_related("template", "roster_week")
    )
    plans: dict[tuple[int, date], dict[date, list[PlanCell]]] = {}
    slots: list[rules.Slot] = []
    for assignment in assignments:
        queue_id = assignment.roster_week.queue_id
        for day, slot in shift_slots(
            assignment.day, assignment.template.start_time, assignment.template.end_time
        ):
            monday = day - timedelta(days=day.weekday())
            if (queue_id, monday) not in plans:
                plans[(queue_id, monday)] = week_plan(user, queue_id, monday).cells
            cell = plans[(queue_id, monday)][day][slot]
            slots.append(rules.Slot(cell.scheduled, cell.required))
    return rules.impact(len(assignments), slots)
