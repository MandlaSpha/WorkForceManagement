"""Planned shrinkage measured from approved leave, by team (SHR-01).

A team is the people who share a lead (`Employee.manager`); people with no lead are one group of
their own. Everything starts from `Employee.objects.for_user(user)`; a lead is limited to their own
team. Unplanned shrinkage is not measured here: it needs an attendance feed.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from wfm_engine import leave as leave_rules
from wfm_engine import shrinkage as rules

from wfm.accounts.models import Role, User
from wfm.scheduling.models import Employee

from .calendar import public_holidays
from .models import LeaveRequest, LeaveStatus
from .policy import ALL_SCOPE_ROLES


@dataclass(frozen=True, slots=True)
class TeamShrinkage:
    team: str  # the lead's name, or "No lead"
    summary: rules.Summary
    assumed_pct: Decimal | None  # the planning assumption of the queues the team is skilled on


def _scope(user: User) -> list[Employee]:
    people = (
        Employee.objects.for_user(user).select_related("manager").prefetch_related("skills__queue")
    )
    if user.role in ALL_SCOPE_ROLES:
        return list(people)
    if user.role == Role.LEAD:
        return list(people.filter(manager__user=user))
    return []


def _clip(first: date, last: date, person: Employee) -> tuple[date, date] | None:
    start = max(first, person.start_date) if person.start_date else first
    end = min(last, person.end_date) if person.end_date else last
    return (start, end) if start <= end else None


def monthly(user: User, month: date) -> list[TeamShrinkage]:
    first = month.replace(day=1)
    last = first.replace(day=monthrange(first.year, first.month)[1])
    holidays = public_holidays(first, last)
    people = _scope(user)
    leaves: dict[int, list[LeaveRequest]] = {}
    for leave in LeaveRequest.objects.for_user(user).filter(
        status=LeaveStatus.APPROVED,
        start_date__lte=last,
        end_date__gte=first,
        employee__in=people,
    ):
        leaves.setdefault(leave.employee_id, []).append(leave)

    teams: dict[str, list[rules.Person]] = {}
    skilled: dict[str, dict[int, Decimal]] = {}  # per team: queue id to its assumption
    for person in people:
        window = _clip(first, last, person)
        if window is None:
            continue
        employed = set(leave_rules.working_day_list(*window, holidays))
        away: set[date] = set()
        for leave in leaves.get(person.pk, []):
            span = (max(first, leave.start_date), min(last, leave.end_date))
            away |= set(leave_rules.working_day_list(*span, holidays))
        team = person.manager.name if person.manager else "No lead"
        teams.setdefault(team, []).append(
            rules.Person(person.weekly_hours, len(employed), len(away & employed))
        )
        skilled.setdefault(team, {}).update(
            {skill.queue_id: skill.queue.shrinkage_pct for skill in person.skills.all()}
        )

    result = []
    for team, members in sorted(teams.items()):
        targets = list(skilled.get(team, {}).values())
        assumed = sum(targets, Decimal(0)) / len(targets) if targets else None
        result.append(TeamShrinkage(team, rules.summarise(members), assumed))
    return result
