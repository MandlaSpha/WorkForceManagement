"""The week of a team at a glance. Everything starts from `Model.objects.for_user(user)`.

A lead sees their own team (the employees they manage, never themselves); a planner or admin sees
everyone and may narrow to one manager's team. Naming a manager outside the reader's scope is a
404. Nothing here reads pay, and a wellbeing prompt is reduced to a yes (the reason stays on the
Wellbeing screen). Adherence comes from the attendance module; a person with no agent-state data
has none, which is shown as "no data", never as zero.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from wfm_engine import team as engine
from wfm_engine.adherence import team_adherence_pct
from wfm_engine.leave import balance as leave_balance

from wfm.accounts.models import Role, User
from wfm.attendance import selectors as attendance
from wfm.core.errors import not_found
from wfm.scheduling.models import Employee, RosterStatus, ShiftAssignment
from wfm.skills import wellbeing_selectors

from .models import OPEN_SWAP_STATUSES, LeaveRequest, LeaveStatus, LeaveType, SwapRequest

CLOCK = "%H:%M"


@dataclass(frozen=True, slots=True)
class ShiftLine:
    day: date
    shift: str
    start_time: str
    end_time: str
    paid_hours: float
    adherence_pct: float | None


@dataclass(frozen=True, slots=True)
class BalanceLine:
    leave_type: str
    entitlement: Decimal | None
    taken: Decimal
    pending: Decimal
    available: Decimal | None


@dataclass(frozen=True, slots=True)
class PendingLine:
    leave_type: str
    start_date: date
    end_date: date
    days: int


@dataclass(frozen=True, slots=True)
class PersonCard:
    employee: Employee
    rostered_h: float
    adherence_pct: float | None
    on_track: bool | None
    pending_leave: int
    open_swaps: int
    check_in: bool
    shifts: list[ShiftLine]
    balances: list[BalanceLine]
    pending: list[PendingLine]


@dataclass(frozen=True, slots=True)
class TeamOverview:
    week_start: date
    week_end: date
    summary: engine.TeamSummary
    managers: list[Employee]
    people: list[PersonCard]


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _managers(user: User) -> list[Employee]:
    if user.role == Role.LEAD:
        return []  # a lead has one team; there is nothing to choose
    return list(
        Employee.objects.for_user(user).filter(reports__isnull=False).distinct().order_by("emp_no")
    )


def _members(user: User, first: date, last: date, manager_id: int | None) -> list[Employee]:
    people = Employee.objects.for_user(user).filter(
        Q(start_date__isnull=True) | Q(start_date__lte=last),
        Q(end_date__isnull=True) | Q(end_date__gte=first),
    )
    if user.role == Role.LEAD:
        own = Employee.objects.for_user(user).filter(user=user).first()
        if manager_id is not None and (own is None or own.pk != manager_id):
            raise not_found("No such team.")
        people = people.filter(manager__user=user).exclude(user=user)
    elif manager_id is not None:
        named = Employee.objects.for_user(user).filter(pk=manager_id, reports__isnull=False)
        if not named.exists():
            raise not_found("No such team.")
        people = people.filter(manager_id=manager_id)
    return list(people.order_by("emp_no"))


def _balances(user: User, ids: list[int], year: int) -> dict[int, list[BalanceLine]]:
    types = list(LeaveType.objects.for_user(user))
    counted: dict[tuple[int, int, str], Decimal] = defaultdict(Decimal)
    for emp_id, type_id, status, by_year in (
        LeaveRequest.objects.for_user(user)
        .filter(employee_id__in=ids, status__in=(LeaveStatus.APPROVED, LeaveStatus.PENDING))
        .values_list("employee_id", "leave_type_id", "status", "days_by_year")
    ):
        counted[(emp_id, type_id, status)] += Decimal(by_year.get(str(year), 0))
    out: dict[int, list[BalanceLine]] = {}
    for emp_id in ids:
        lines = []
        for t in types:
            approved = counted[(emp_id, t.pk, LeaveStatus.APPROVED)]
            pending = counted[(emp_id, t.pk, LeaveStatus.PENDING)]
            b = leave_balance(t.days_per_year, approved, pending)
            lines.append(BalanceLine(t.name, b.entitlement, b.taken, b.pending, b.available))
        out[emp_id] = lines
    return out


def overview(
    user: User, *, week_start: date | None = None, manager_id: int | None = None
) -> TeamOverview:
    first = monday_of(week_start or timezone.localdate())
    last = first + timedelta(days=6)
    members = _members(user, first, last, manager_id)
    ids = [m.pk for m in members]

    assignments = list(
        ShiftAssignment.objects.for_user(user)
        .filter(
            employee_id__in=ids,
            day__range=(first, last),
            roster_week__status=RosterStatus.PUBLISHED,
        )
        .select_related("template", "employee", "roster_week__queue")
        .prefetch_related("activities")
        .order_by("day")
    )
    days = attendance.person_days(user, assignments)
    shifts_of: dict[int, list[ShiftAssignment]] = defaultdict(list)
    for a in assignments:
        shifts_of[a.employee_id].append(a)

    pending_leave: dict[int, list[PendingLine]] = defaultdict(list)
    for req in (
        LeaveRequest.objects.for_user(user)
        .filter(employee_id__in=ids, status=LeaveStatus.PENDING)
        .select_related("leave_type")
        .order_by("start_date", "id")
    ):
        pending_leave[req.employee_id].append(
            PendingLine(req.leave_type.name, req.start_date, req.end_date, req.days)
        )

    open_swaps: dict[int, int] = defaultdict(int)
    for from_id, to_id in (
        SwapRequest.objects.for_user(user)
        .filter(status__in=OPEN_SWAP_STATUSES)
        .filter(Q(from_employee_id__in=ids) | Q(to_employee_id__in=ids))
        .values_list("from_employee_id", "to_employee_id")
    ):
        for emp_id in {from_id, to_id} & set(ids):
            open_swaps[emp_id] += 1

    # The reason behind a prompt never leaves the Wellbeing selector: only "there is one".
    prompted = wellbeing_selectors.prompts(user, today=timezone.localdate())
    check_in = {p.employee.pk for p in prompted}
    balances = _balances(user, ids, first.year)

    cards: list[PersonCard] = []
    parts: list[engine.PersonWeek] = []
    for m in members:
        mine = days.get(m.pk, [])
        week_pct = team_adherence_pct(d.result for d in mine if d.has_data)
        rostered = engine.hours(sum(a.template.paid_minutes for a in shifts_of[m.pk]))
        parts.append(engine.PersonWeek(rostered, float(m.weekly_hours), week_pct))
        lines = [
            ShiftLine(
                day=a.day,
                shift=a.template.code,
                start_time=a.template.start_time.strftime(CLOCK),
                end_time=a.template.end_time.strftime(CLOCK),
                paid_hours=engine.hours(a.template.paid_minutes),
                adherence_pct=d.result.adherence_pct if d.has_data else None,
            )
            for a, d in zip(shifts_of[m.pk], mine, strict=True)
        ]
        cards.append(
            PersonCard(
                employee=m,
                rostered_h=rostered,
                adherence_pct=week_pct,
                on_track=engine.is_on_track(week_pct),
                pending_leave=len(pending_leave[m.pk]),
                open_swaps=open_swaps[m.pk],
                check_in=m.pk in check_in,
                shifts=lines,
                balances=balances[m.pk],
                pending=pending_leave[m.pk],
            )
        )
    return TeamOverview(first, last, engine.summarise(parts), _managers(user), cards)
