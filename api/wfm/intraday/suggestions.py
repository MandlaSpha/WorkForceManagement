"""What a planner can do about a short half-hour (INT-04): people who could be asked for overtime
and breaks that could move. Read only; applying either goes through the overtime and activity
services. Names appear only for planner and admin."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Sum
from wfm_engine.intraday import break_targets
from wfm_engine.roster import shift_slots

from wfm.accounts.models import Role, User
from wfm.overtime.models import OvertimeRequest, OvertimeStatus
from wfm.overtime.services import refusal_for
from wfm.scheduling.models import Employee, ShiftActivity, ShiftAssignment
from wfm.scheduling.selectors import Plan, week_plan

MAX_PEOPLE = 5
SUGGEST_ROLES = frozenset({Role.ADMIN, Role.PLANNER})


@dataclass(frozen=True, slots=True)
class Person:
    employee_id: int
    name: str
    week_minutes: int  # rostered paid minutes plus waiting or approved overtime that week


@dataclass(frozen=True, slots=True)
class BreakMove:
    activity_id: int
    employee: str
    kind: str
    start: str  # "HH:MM", where it is now
    end: str
    move_to: str  # "HH:MM", the nearest half-hour that keeps cover
    slots: int


@dataclass(frozen=True, slots=True)
class Suggestions:
    people: list[Person]
    breaks: list[BreakMove]


def overtime_span(slot: int) -> tuple[time, time]:
    """The overtime span that covers one half-hour (the last one ends a minute before midnight,
    because an overtime request stays inside one day)."""
    start = time(slot // 2, 30 * (slot % 2))
    nxt = slot + 1
    return start, (time(nxt // 2, 30 * (nxt % 2)) if nxt < 48 else time(23, 59))


def _week_minutes(ids: list[int], day: date) -> dict[int, int]:
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    load = dict.fromkeys(ids, 0)
    for row in (
        ShiftAssignment.objects.filter(employee_id__in=ids, day__gte=monday, day__lte=sunday)
        .values("employee_id")
        .annotate(total=Sum("template__paid_minutes"))
    ):
        load[row["employee_id"]] += row["total"] or 0
    for row in (
        OvertimeRequest.objects.filter(
            employee_id__in=ids,
            day__gte=monday,
            day__lte=sunday,
            status__in=(OvertimeStatus.PENDING, OvertimeStatus.APPROVED),
        )
        .values("employee_id")
        .annotate(total=Sum("minutes"))
    ):
        load[row["employee_id"]] += row["total"] or 0
    return load


def people_for(user: User, queue_id: int, day: date, slot: int) -> list[Person]:
    """Up to five people skilled on the queue who could cover the half-hour as overtime: not
    already working that day, and passing every overtime rule (leave, rest, days in a row, the
    weekly limit) for a span covering the half-hour. Lightest week first."""
    if user.role not in SUGGEST_ROLES:
        return []
    start, end = overtime_span(slot)
    working = ShiftAssignment.objects.filter(day=day).values_list("employee_id", flat=True)
    candidates = list(
        Employee.objects.for_user(user)
        .filter(skills__queue_id=queue_id)
        .exclude(pk__in=working)
        .distinct()
    )
    load = _week_minutes([e.pk for e in candidates], day)
    candidates.sort(key=lambda e: (load[e.pk], e.name, e.pk))
    found: list[Person] = []
    for employee in candidates:
        if refusal_for(employee, day, start, end) is None:
            found.append(Person(employee.pk, employee.name, load[employee.pk]))
            if len(found) == MAX_PEOPLE:
                break
    return found


def _clock(template_start: time, offset: int) -> str:
    moment = datetime.combine(date(2000, 1, 3), template_start) + timedelta(minutes=30 * offset)
    return f"{moment:%H:%M}"


def breaks_for(user: User, queue_id: int, day: date, slot: int) -> list[BreakMove]:
    """Breaks and activities that overlap the half-hour and could move to a place where the
    person's absence leaves the phones covered (`wfm_engine.intraday.break_targets`)."""
    if user.role not in SUGGEST_ROLES:
        return []
    plans: dict[date, Plan] = {}

    def cell(key: tuple[date, int]) -> Any:
        monday = key[0] - timedelta(days=key[0].weekday())
        if monday not in plans:
            plans[monday] = week_plan(user, queue_id, monday)
        return plans[monday].cells[key[0]][key[1]]

    shifts = (
        ShiftAssignment.objects.for_user(user)
        .filter(roster_week__queue_id=queue_id, day__gte=day - timedelta(days=1), day__lte=day)
        .select_related("template", "employee")
        .prefetch_related("activities")
    )
    moves: list[BreakMove] = []
    for shift in shifts:
        keys = shift_slots(shift.day, shift.template.start_time, shift.template.end_time)
        if (day, slot) not in keys:
            continue
        here = keys.index((day, slot))
        acts: list[ShiftActivity] = list(shift.activities.all())
        for act in acts:
            if not act.offset_slots <= here < act.offset_slots + act.slots:
                continue
            others = [(a.offset_slots, a.slots) for a in acts if a.pk != act.pk]
            scheduled = {k: cell(k).scheduled for k in keys}
            required = {k: cell(k).required for k in keys}
            targets = break_targets(
                keys, (act.offset_slots, act.slots), others, scheduled, required
            )
            if targets:
                start = shift.template.start_time
                moves.append(
                    BreakMove(
                        activity_id=act.pk,
                        employee=shift.employee.name,
                        kind=act.kind,
                        start=_clock(start, act.offset_slots),
                        end=_clock(start, act.offset_slots + act.slots),
                        move_to=_clock(start, targets[0]),
                        slots=act.slots,
                    )
                )
    return moves


def suggestions(user: User, queue_id: int, day: date, slot: int) -> Suggestions:
    return Suggestions(
        people=people_for(user, queue_id, day, slot), breaks=breaks_for(user, queue_id, day, slot)
    )
