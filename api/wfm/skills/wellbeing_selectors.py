"""Who has an early-warning prompt today (WEL-01).

Visible to planners and admins (everybody) and to a lead (their own team, never themselves).
Nobody else is served, and no peer ever is. The result is a list of prompts with the plain fact
behind each; there is no score and no ranking. Unplanned absence means approved leave of a type
that cannot wait (`restricted=False`: sick, family responsibility), weekdays only.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q
from wfm_engine.wellbeing import ABSENCE_WINDOW_DAYS, Flag, wellbeing_flags

from wfm.accounts.models import Role, User
from wfm.overtime.models import OvertimeRequest, OvertimeStatus
from wfm.people.models import LeaveRequest, LeaveStatus
from wfm.scheduling.models import Employee, ShiftAssignment

LOOKBACK_DAYS = 2 * ABSENCE_WINDOW_DAYS  # this window and the one before it
WEEKDAYS = 5


@dataclass(frozen=True, slots=True)
class WellbeingPerson:
    employee: Employee
    flags: list[Flag]


def _team(user: User, today: date) -> list[Employee]:
    people = Employee.objects.for_user(user).filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today)
    )
    if user.role == Role.LEAD:
        people = people.filter(manager__user=user).exclude(user=user)
    return list(people.order_by("emp_no"))


def prompts(user: User, *, today: date) -> list[WellbeingPerson]:
    people = _team(user, today)
    if not people:
        return []
    ids = [p.pk for p in people]
    first = today - timedelta(days=LOOKBACK_DAYS - 1)

    shifts: dict[int, set[date]] = defaultdict(set)
    for emp_id, day in (
        ShiftAssignment.objects.for_user(user)
        .filter(employee_id__in=ids, day__range=(first, today))
        .values_list("employee_id", "day")
    ):
        shifts[emp_id].add(day)

    overtime: dict[int, set[date]] = defaultdict(set)
    for emp_id, day in (
        OvertimeRequest.objects.for_user(user)
        .filter(employee_id__in=ids, status=OvertimeStatus.APPROVED, day__range=(first, today))
        .values_list("employee_id", "day")
    ):
        overtime[emp_id].add(day)

    absence: dict[int, set[date]] = defaultdict(set)
    for emp_id, start, end in (
        LeaveRequest.objects.for_user(user)
        .filter(
            employee_id__in=ids,
            status=LeaveStatus.APPROVED,
            leave_type__restricted=False,
            start_date__lte=today,
            end_date__gte=first,
        )
        .values_list("employee_id", "start_date", "end_date")
    ):
        day = max(start, first)
        while day <= min(end, today):
            if day.weekday() < WEEKDAYS:
                absence[emp_id].add(day)
            day += timedelta(days=1)

    found = []
    for person in people:
        flags = wellbeing_flags(
            shift_days=shifts[person.pk],
            overtime_days=overtime[person.pk],
            absence_days=absence[person.pk],
            today=today,
        )
        if flags:
            found.append(WellbeingPerson(person, flags))
    return found
