"""Reading a person's own availability and schedule."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Q, QuerySet

from wfm.accounts.models import User
from wfm.scheduling.models import Employee, RosterStatus, ShiftAssignment

from .models import OPEN_SWAP_STATUSES, Availability, LeaveRequest, LeaveStatus, SwapRequest


def windows(user: User, employee: Employee) -> QuerySet[Availability]:
    return Availability.objects.for_user(user).filter(employee=employee).select_related("employee")


@dataclass(frozen=True, slots=True)
class MySchedule:
    shifts: list[ShiftAssignment]
    leave: list[LeaveRequest]
    unpublished: int
    open_swaps: int


def my_schedule(employee: Employee, first: date, last: date) -> MySchedule:
    """Published shifts, leave that is asked for or approved, and how many shifts are still in
    weeks that are not published (their number is shown, their content is not)."""
    mine = ShiftAssignment.objects.filter(employee=employee, day__gte=first, day__lte=last)
    published = (
        mine.filter(roster_week__status=RosterStatus.PUBLISHED)
        .select_related("template", "roster_week__queue")
        .prefetch_related("activities")
        .order_by("day")
    )
    leave = (
        LeaveRequest.objects.filter(
            employee=employee,
            status__in=(LeaveStatus.PENDING, LeaveStatus.APPROVED),
            start_date__lte=last,
            end_date__gte=first,
        )
        .select_related("leave_type")
        .order_by("start_date")
    )
    swaps = SwapRequest.objects.filter(status__in=OPEN_SWAP_STATUSES).filter(
        Q(from_employee=employee) | Q(to_employee=employee)
    )
    return MySchedule(
        shifts=list(published),
        leave=list(leave),
        unpublished=mine.exclude(roster_week__status=RosterStatus.PUBLISHED).count(),
        open_swaps=swaps.count(),
    )
