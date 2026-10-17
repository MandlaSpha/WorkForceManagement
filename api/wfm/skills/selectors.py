"""Reading credentials and requirements, and finding the shifts where a required skill is short
(SKL-01, WEL-02). Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q
from wfm_engine.wellbeing import skill_shortfalls

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.scheduling.models import Employee, ShiftAssignment
from wfm.telephony.models import Queue

from .models import EmployeeCredential, QueueRequirement
from .policy import TEAM_ROLES


@dataclass(frozen=True, slots=True)
class SkillGap:
    queue: Queue
    kind: str
    name: str
    day: date
    shift_code: str
    required: int
    present: int


def credentials(user: User, employee_id: int | None = None) -> list[EmployeeCredential]:
    if employee_id is not None:
        people = Employee.objects.for_user(user).filter(pk=employee_id)
        if user.role in TEAM_ROLES:  # the roster scope is wider than a lead's team
            people = people.filter(Q(manager__user=user) | Q(user=user))
        if not people.exists():
            raise not_found("No such employee.")
    found = EmployeeCredential.objects.for_user(user).select_related("employee")
    if employee_id is not None:
        found = found.filter(employee_id=employee_id)
    return list(found.order_by("employee__emp_no", "kind", "name"))


def requirements(user: User, queue_id: int | None = None) -> list[QueueRequirement]:
    found = QueueRequirement.objects.for_user(user).select_related("queue")
    if queue_id is not None:
        if not Queue.objects.for_user(user).filter(pk=queue_id).exists():
            raise not_found("No such queue.")
        found = found.filter(queue_id=queue_id)
    return list(found.order_by("queue__name", "kind", "name"))


def skill_gaps(user: User, *, start: date, days: int) -> list[SkillGap]:
    """For each requirement, every shift rostered on its queue in the window (draft or published)
    where fewer than the required number of people hold the credential on that day."""
    last = start + timedelta(days=days - 1)
    gaps: list[SkillGap] = []
    for req in requirements(user):
        assigned = list(
            ShiftAssignment.objects.for_user(user)
            .filter(roster_week__queue=req.queue, day__range=(start, last))
            .select_related("template")
        )
        if not assigned:
            continue
        held: dict[int, list[date | None]] = defaultdict(list)
        for cred in EmployeeCredential.objects.filter(
            kind=req.kind,
            name__iexact=req.name,
            employee_id__in={a.employee_id for a in assigned},
        ):
            held[cred.employee_id].append(cred.expires_on)
        present: dict[tuple[date, str], int] = defaultdict(int)
        expected: set[tuple[date, str]] = set()
        for a in assigned:
            key = (a.day, a.template.code)
            expected.add(key)
            if any(e is None or e >= a.day for e in held.get(a.employee_id, ())):
                present[key] += 1
        gaps.extend(
            SkillGap(req.queue, req.kind, req.name, s.key[0], s.key[1], s.required, s.present)
            for s in skill_shortfalls(
                required=req.min_people, present=present, expected=sorted(expected)
            )
        )
    return sorted(gaps, key=lambda g: (g.day, g.queue.name, g.shift_code, g.name))
