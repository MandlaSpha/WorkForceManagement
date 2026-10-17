"""Adherence of a queue's day, and of one person's own day (ATT-01, RTA-01).

The plan is the PUBLISHED roster: the shift less its breaks and activities. The actual is the
imported agent-state intervals. A person with no state rows near their shift has NO DATA, which is
not the same as not turning up: the feed may simply not have been loaded yet, so no percentage is
claimed for them. A night shift belongs to the day it starts on.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine import adherence as engine
from wfm_engine.adherence import Adherence, Span, StateSpan

from wfm.accounts.models import Role, User
from wfm.core.errors import not_found
from wfm.scheduling.models import Employee, RosterStatus, ShiftAssignment
from wfm.telephony.models import Queue

from .models import AgentStateInterval

MARGIN = timedelta(hours=1)  # states shown either side of the shift


@dataclass(frozen=True, slots=True)
class PersonDay:
    employee_id: int
    emp_no: str
    name: str
    shift_code: str
    queue_name: str
    planned: list[Span]
    actual: list[StateSpan]  # clipped to the shift and an hour either side
    has_data: bool
    result: Adherence


@dataclass(frozen=True, slots=True)
class QueueDay:
    queue_name: str
    day: date
    people: list[PersonDay]
    team_adherence_pct: float | None  # over the people who have data


def _window(assignment: ShiftAssignment) -> Span:
    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(assignment.day, assignment.template.start_time, tzinfo=zone)
    end = datetime.combine(assignment.day, assignment.template.end_time, tzinfo=zone)
    if end <= start:
        end += timedelta(days=1)  # overnight
    return start, end


def _person_day(assignment: ShiftAssignment, states: list[AgentStateInterval]) -> PersonDay:
    start, end = _window(assignment)
    planned = engine.scheduled_spans(
        start, end, [(x.offset_slots, x.slots) for x in assignment.activities.all()]
    )
    lo, hi = start - MARGIN, end + MARGIN
    actual: list[StateSpan] = [
        (s.state, max(s.start_at, lo), min(s.end_at, hi))
        for s in states
        if s.start_at < hi and s.end_at > lo
    ]
    employee = assignment.employee
    return PersonDay(
        employee_id=employee.pk,
        emp_no=employee.emp_no,
        name=employee.name,
        shift_code=assignment.template.code,
        queue_name=assignment.roster_week.queue.name,
        planned=planned,
        actual=sorted(actual, key=lambda a: a[1]),
        has_data=bool(actual),
        result=engine.adherence(planned, actual),
    )


def _states_by_person(
    user: User, employee_ids: list[int], assignments: list[ShiftAssignment]
) -> dict[int, list[AgentStateInterval]]:
    out: dict[int, list[AgentStateInterval]] = defaultdict(list)
    if not assignments:
        return out
    windows = [_window(a) for a in assignments]
    lo, hi = min(w[0] for w in windows) - MARGIN, max(w[1] for w in windows) + MARGIN
    for s in AgentStateInterval.objects.for_user(user).filter(
        employee_id__in=employee_ids, start_at__lt=hi, end_at__gt=lo
    ):
        out[s.employee_id].append(s)
    return out


def queue_day(user: User, queue_id: int, day: date) -> QueueDay:
    """Every person rostered (published) on the queue that day, within the reader's scope: a lead
    sees their own team only. An unreadable queue is a 404."""
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    rows = (
        ShiftAssignment.objects.for_user(user)
        .filter(day=day, roster_week__queue=queue, roster_week__status=RosterStatus.PUBLISHED)
        .select_related("template", "employee", "roster_week__queue")
        .prefetch_related("activities")
        .order_by("employee__emp_no")
    )
    if user.role == Role.LEAD:
        rows = rows.filter(employee__manager__user=user)
    assignments = list(rows)
    states = _states_by_person(user, [a.employee_id for a in assignments], assignments)
    people = [_person_day(a, states.get(a.employee_id, [])) for a in assignments]
    return QueueDay(
        queue_name=queue.name,
        day=day,
        people=people,
        team_adherence_pct=engine.team_adherence_pct(p.result for p in people if p.has_data),
    )


def own_employee(user: User) -> Employee | None:
    return Employee.objects.for_user(user).filter(user=user).first()


def my_day(user: User, employee: Employee, day: date) -> PersonDay | None:
    """The signed-in person's own published shift and states for a day; None with no shift.
    Nothing here can name a colleague: both lookups are pinned to this one employee."""
    assignment = (
        # Not `.for_user`: shifts are scoped to the roster-reading roles, while an agent may read
        # their own published shift (as on their schedule). The filter pins it to one person.
        ShiftAssignment.objects.filter(
            employee=employee, day=day, roster_week__status=RosterStatus.PUBLISHED
        )
        .select_related("template", "employee", "roster_week__queue")
        .prefetch_related("activities")
        .first()
    )
    if assignment is None:
        return None
    start, end = _window(assignment)
    near = AgentStateInterval.objects.for_user(user).filter(
        employee=employee, start_at__lt=end + MARGIN, end_at__gt=start - MARGIN
    )
    return _person_day(assignment, list(near))
