"""Reading the per-call detail sheets as aggregates (DAT-01 screens, tech spec section 4.31).

Who sees what:
- admin and planner: everything, including each agent login (mapped to the employee when known)
  and the incident numbers;
- a team lead: queue figures, and agent rows ONLY for logins mapped to people in their own team
  (an unmapped login, or a colleague lead's agent, is never shown to them); no incident numbers;
- an executive: queue figures only, no per-agent rows and no incident numbers.
Every other role gets nothing (the API refuses first). All reads start from the queues the role may
see. Nothing is ranked and no team average is returned next to a person.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine import call_detail as detail
from wfm_engine.cdr_details import (
    SHEET_DISPOSITION,
    SHEET_HOLD,
    SHEET_IVR,
    SHEET_MUTE,
    SHEET_OFFERED,
    SHEET_TRANSFER,
)

from wfm.accounts.models import Role, User
from wfm.scheduling.models import AgentLogin, Employee

from .models import (
    AgentOffer,
    CallDisposition,
    CallIvrStep,
    CallPause,
    CallRecord,
    CallTransfer,
    ImportBatch,
)
from .policy import AGGREGATE_ROLES

AGENT_ROLES = frozenset({Role.ADMIN, Role.PLANNER, Role.LEAD})
INCIDENT_ROLES = frozenset({Role.ADMIN, Role.PLANNER})
STATUS_ABANDONED = "Abandoned"


@dataclass(frozen=True, slots=True)
class AgentLine:
    login: str
    employee_number: str | None
    employee_name: str | None
    ring: detail.AgentRing


@dataclass(frozen=True, slots=True)
class CallDetail:
    month: str
    sheets: dict[str, bool]  # which sheets an import in this month actually held
    agents_allowed: bool
    incidents_allowed: bool
    scope: str  # "all", "team" or "aggregate": whose agents the rows cover
    agents: list[AgentLine] | None
    ivr: list[detail.IvrQueue] | None
    events_by_queue: dict[str, list[detail.EventRow]] | None
    events_by_day: dict[str, list[detail.EventRow]] | None
    incidents: list[detail.IncidentQueue] | None


def month_bounds(month: date) -> tuple[datetime, datetime]:
    zone = ZoneInfo(settings.TIME_ZONE)
    first = month.replace(day=1)
    following = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
    return datetime.combine(first, time.min, tzinfo=zone), datetime.combine(
        following, time.min, tzinfo=zone
    )


def _sheets_read(user: User, start: datetime, end: datetime) -> dict[str, bool]:
    """A sheet counts as present when an import overlapping the month read it. A sheet that was
    not in the file is NO DATA, which is different from a real zero."""
    names = {
        "ring": SHEET_OFFERED,
        "ivr": SHEET_IVR,
        "transfers": SHEET_TRANSFER,
        "holds": SHEET_HOLD,
        "mutes": SHEET_MUTE,
        "incidents": SHEET_DISPOSITION,
    }
    read: set[str] = set()
    for batch in ImportBatch.objects.aggregate_for(user, AGGREGATE_ROLES).filter(
        period_start__lt=end, period_end__gte=start
    ):
        read |= {r["sheet"] for r in batch.sheets_report if r.get("read")}
    return {key: name in read for key, name in names.items()}


def _agents(user: User, start: datetime, end: datetime) -> list[AgentLine]:
    mapping = AgentLogin.objects.filter(employee__in=Employee.objects.for_user(user))
    if user.role == Role.LEAD:  # their own team only, never a colleague lead's
        mapping = mapping.filter(employee__manager__user=user)
    people = {m.login: m.employee for m in mapping.select_related("employee")}
    offers = AgentOffer.objects.aggregate_for(user, AGENT_ROLES).filter(
        call__start_at__gte=start, call__start_at__lt=end
    )
    if user.role == Role.LEAD:
        offers = offers.filter(agent_login__in=list(people))
    rings = detail.ring_by_agent(
        detail.Offer(login, answered, ring_s)
        for login, answered, ring_s in offers.values_list("agent_login", "answered", "ring_s")
    )
    lines = [
        AgentLine(
            r.login,
            people[r.login].emp_no if r.login in people else None,
            people[r.login].name if r.login in people else None,
            r,
        )
        for r in rings
    ]
    # Employee-number order, unmapped logins last by login: an order of identity, not of merit.
    lines.sort(key=lambda a: (a.employee_number is None, a.employee_number or "", a.login))
    return lines


def _ivr(user: User, start: datetime, end: datetime) -> list[detail.IvrQueue]:
    rows = (
        CallIvrStep.objects.aggregate_for(user, AGGREGATE_ROLES)
        .filter(call__start_at__gte=start, call__start_at__lt=end)
        .order_by("call_id", "step")
        .values_list(
            "call_id",
            "step",
            "digit",
            "activity",
            "call__queue__name",
            "call__queue_at",
            "call__status",
        )
    )
    by_call: dict[int, tuple[str, bool, bool, list[detail.IvrStep]]] = {}
    for call_id, step, digit, activity, queue, queue_at, status in rows:
        if call_id not in by_call:
            by_call[call_id] = (queue, queue_at is not None, status == STATUS_ABANDONED, [])
        by_call[call_id][3].append(detail.IvrStep(step, digit, activity))
    return detail.ivr_by_queue(
        detail.IvrCall(queue, tuple(steps), reached, abandoned)
        for queue, reached, abandoned, steps in by_call.values()
    )


def _events(
    user: User, start: datetime, end: datetime, zone: ZoneInfo, sheets: dict[str, bool]
) -> list[detail.EventFact]:
    facts: list[detail.EventFact] = []
    if sheets["transfers"]:
        for queue, at, answer_s, duration_s in (
            CallTransfer.objects.aggregate_for(user, AGGREGATE_ROLES)
            .filter(call__start_at__gte=start, call__start_at__lt=end)
            .values_list("call__queue__name", "call__start_at", "answer_s", "duration_s")
        ):
            facts.append(
                detail.EventFact(
                    queue, at.astimezone(zone).date(), detail.KIND_TRANSFER, duration_s, answer_s
                )
            )
    wanted = [k for k, key in ((CallPause.HOLD, "holds"), (CallPause.MUTE, "mutes")) if sheets[key]]
    for kind, queue, at, duration_s in (
        CallPause.objects.aggregate_for(user, AGGREGATE_ROLES)
        .filter(kind__in=wanted, call__start_at__gte=start, call__start_at__lt=end)
        .values_list("kind", "call__queue__name", "call__start_at", "duration_s")
    ):
        facts.append(
            detail.EventFact(
                queue,
                at.astimezone(zone).date(),
                detail.KIND_HOLD if kind == CallPause.HOLD else detail.KIND_MUTE,
                duration_s,
            )
        )
    return facts


def _incidents(user: User, start: datetime, end: datetime) -> list[detail.IncidentQueue]:
    return detail.incident_links(
        detail.IncidentFact(queue, call_id, ref)
        for call_id, queue, ref in CallDisposition.objects.aggregate_for(user, INCIDENT_ROLES)
        .filter(call__start_at__gte=start, call__start_at__lt=end)
        .exclude(incident_ref="")
        .values_list("call_id", "call__queue__name", "incident_ref")
    )


def call_detail(user: User, month: date) -> CallDetail:
    zone = ZoneInfo(settings.TIME_ZONE)
    start, end = month_bounds(month)
    sheets = _sheets_read(user, start, end)
    agents_allowed = user.role in AGENT_ROLES
    incidents_allowed = user.role in INCIDENT_ROLES

    facts = _events(user, start, end, zone, sheets)
    queues = sorted(
        CallRecord.objects.aggregate_for(user, AGGREGATE_ROLES)
        .filter(start_at__gte=start, start_at__lt=end)
        .values_list("queue__name", flat=True)
        .distinct()
    )
    event_sheets = sheets["transfers"] or sheets["holds"] or sheets["mutes"]
    by_queue = detail.event_summary(facts, by_day=False, queues=queues) if event_sheets else []
    by_day = detail.event_summary(facts, by_day=True) if event_sheets else []

    return CallDetail(
        month=f"{month.year:04d}-{month.month:02d}",
        sheets=sheets,
        agents_allowed=agents_allowed,
        incidents_allowed=incidents_allowed,
        scope="all" if user.role in INCIDENT_ROLES else "team" if agents_allowed else "aggregate",
        agents=_agents(user, start, end) if agents_allowed and sheets["ring"] else None,
        ivr=_ivr(user, start, end) if sheets["ivr"] else None,
        events_by_queue=_group(by_queue) if event_sheets else None,
        events_by_day=_group(by_day) if event_sheets else None,
        incidents=_incidents(user, start, end)
        if incidents_allowed and sheets["incidents"]
        else None,
    )


def _group(rows: list[detail.EventRow]) -> dict[str, list[detail.EventRow]]:
    grouped: dict[str, list[detail.EventRow]] = {}
    for r in rows:
        grouped.setdefault(r.queue, []).append(r)
    return grouped
