"""Reading backup teams and the mobilise view (BCP-01).

The mobilise view answers one question for a queue and a day: if a site fails (or an outbreak
removes a share of the staff), who on the backup teams could cover, and what is left of the
roster? It uses what the system already knows: the published roster, approved leave, declared
availability and each person's work mode. Leave and availability are used only as yes or no.
An executive gets numbers and no names.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from wfm_engine import continuity as engine
from wfm_engine.availability import window_of

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.people.models import Availability, AvailabilityKind, LeaveRequest, LeaveStatus
from wfm.scheduling.models import Employee, RosterStatus, ShiftAssignment
from wfm.telephony.models import Queue

from .models import BackupMember, BackupTeam
from .policy import NAMED_READ_ROLES, READ_ROLES


@dataclass(frozen=True, slots=True)
class TeamView:
    team: BackupTeam
    queue_name: str
    member_count: int
    members: list[Employee]  # empty for a reader who may not see names


@dataclass(frozen=True, slots=True)
class CandidateView:
    employee: Employee
    status: str
    usable: bool


@dataclass(frozen=True, slots=True)
class TeamCover:
    team_id: int
    name: str
    member_count: int
    usable_count: int
    candidates: list[CandidateView]  # empty for a reader who may not see names


@dataclass(frozen=True, slots=True)
class Mobilise:
    queue_name: str
    day: date
    scenario: str
    lost_pct: int
    rostered_by_mode: dict[str, int]
    impact: engine.Impact
    by_status: dict[str, int]  # distinct backup people by why they can or cannot cover
    usable_distinct: int
    teams: list[TeamCover]


def _queue(user: User, queue_id: int) -> Queue:
    queue: Queue | None = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    return queue


def teams(user: User, *, queue_id: int | None = None, team_id: int | None = None) -> list[TeamView]:
    rows = BackupTeam.objects.for_user(user).select_related("queue")
    if queue_id is not None:
        rows = rows.filter(queue=_queue(user, queue_id))
    if team_id is not None:
        rows = rows.filter(pk=team_id)
    named = user.role in NAMED_READ_ROLES
    found = list(rows.order_by("queue__name", "name"))
    members: dict[int, list[Employee]] = {t.pk: [] for t in found}
    counts: Counter[int] = Counter()
    for m in BackupMember.objects.for_user(user).filter(team__in=found).select_related("employee"):
        counts[m.team_id] += 1
        if named:
            members[m.team_id].append(m.employee)
    return [
        TeamView(
            team=t,
            queue_name=t.queue.name,
            member_count=counts[t.pk],
            members=members[t.pk],
        )
        for t in found
    ]


def _unavailable_min(windows: list[Availability], day: date) -> int:
    total = 0
    for w in windows:
        if w.weekday == day.weekday():
            span = window_of(w.weekday, w.start_time, w.end_time)
            total += (span.end_slot - span.start_slot) * 30
    return total


def mobilise(user: User, queue_id: int, day: date, scenario: str, lost_pct: int) -> Mobilise:
    queue = _queue(user, queue_id)
    named = user.role in NAMED_READ_ROLES
    roles = READ_ROLES

    # The roster is read as counts (an executive may not see who is on it).
    roster = ShiftAssignment.objects.counts_for(user, roles).filter(
        day=day, roster_week__status=RosterStatus.PUBLISHED
    )
    here = {
        employee_id: mode
        for employee_id, mode in roster.filter(roster_week__queue=queue).values_list(
            "employee_id", "employee__work_mode"
        )
    }
    elsewhere = set(roster.exclude(roster_week__queue=queue).values_list("employee_id", flat=True))

    member_rows = list(
        BackupMember.objects.for_user(user)
        .filter(team__queue=queue)
        .select_related("employee")
        .order_by("employee__emp_no")
    )
    ids = {m.employee_id for m in member_rows}
    on_leave = set(
        LeaveRequest.objects.coverage_for(user, roles)
        .filter(
            employee_id__in=ids,
            status=LeaveStatus.APPROVED,
            start_date__lte=day,
            end_date__gte=day,
        )
        .values_list("employee_id", flat=True)
    )
    windows: dict[int, list[Availability]] = {}
    for w in Availability.objects.coverage_for(user, roles).filter(
        employee_id__in=ids, kind=AvailabilityKind.UNAVAILABLE, weekday=day.weekday()
    ):
        windows.setdefault(w.employee_id, []).append(w)

    status: dict[int, str] = {}
    for m in member_rows:
        e = m.employee
        status[e.pk] = engine.classify(
            engine.Candidate(
                work_mode=e.work_mode,
                on_leave=e.pk in on_leave,
                unavailable_min=_unavailable_min(windows.get(e.pk, []), day),
                rostered_here=e.pk in here,
                rostered_elsewhere=e.pk in elsewhere,
            ),
            scenario,
        )
    usable_ids = {pk for pk, s in status.items() if s in engine.USABLE}
    modes = list(here.values())
    impact = engine.roster_impact(modes, len(usable_ids), scenario, lost_pct)

    covers: list[TeamCover] = []
    for t in BackupTeam.objects.for_user(user).filter(queue=queue).order_by("name"):
        mine = [m for m in member_rows if m.team_id == t.pk]
        covers.append(
            TeamCover(
                team_id=t.pk,
                name=t.name,
                member_count=len(mine),
                usable_count=sum(1 for m in mine if m.employee_id in usable_ids),
                candidates=[
                    CandidateView(m.employee, status[m.employee_id], m.employee_id in usable_ids)
                    for m in mine
                ]
                if named
                else [],
            )
        )
    return Mobilise(
        queue_name=queue.name,
        day=day,
        scenario=scenario,
        lost_pct=lost_pct,
        rostered_by_mode=dict(Counter(modes)),
        impact=impact,
        by_status=dict(Counter(status.values())),
        usable_distinct=len(usable_ids),
        teams=covers,
    )
