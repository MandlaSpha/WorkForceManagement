"""Reading utilisation, cost and workload balance. Everything starts from
`Model.objects.for_user(user)` (or the named aggregate scope of the roster).

Worked time is the paid time of shifts on PUBLISHED rosters. Billable time is the part of it on a
queue held by an active contract, less the time inside the shift given to activities other than
customer work (lunch is left alone: it is not paid time). That is a MODEL of billing, not a
timesheet, so every figure here is marked as modelled (DAT-10)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine import balance as balancing
from wfm_engine import overtime as pricing
from wfm_engine import utilisation as util
from wfm_engine.roster import shift_length_slots

from wfm.accounts.models import Role, User
from wfm.contracts.models import Contract, ContractQueue
from wfm.core.errors import ApiError
from wfm.overtime.models import EmployeePay, OvertimeRequest, OvertimeStatus
from wfm.scheduling.models import (
    ActivityKind,
    Employee,
    EmployeeSkill,
    RosterStatus,
    ShiftAssignment,
)
from wfm.scheduling.selectors import week_plan
from wfm.servicedesk.models import ServicePool, WorkItem
from wfm.telephony.models import Queue

from .models import ContractTerms
from .policy import BALANCE_ROLES, COST_ROLES, DEFAULT_TARGET_PCT, GROUP_ROLES, PERSON_ROLES

SLOT_MIN = 30
NO_TEAM = "No team"


def month_start(value: date) -> date:
    return value.replace(day=1)


def month_end(first: date) -> date:
    return (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)


@dataclass(frozen=True, slots=True)
class Shift:
    employee: Employee
    queue_id: int
    worked_min: int
    billable_min: int
    contract: Contract | None
    target_pct: Decimal | None


def _targets(user: User) -> dict[int, ContractTerms]:
    return {t.contract_id: t for t in ContractTerms.objects.for_user(user)}


def _shifts(user: User, first: date, *, roles: frozenset[Role]) -> list[Shift]:
    """Every published shift of the month the caller may sum, with its contract (if any)."""
    last = month_end(first)
    found = (
        ShiftAssignment.objects.aggregate_for(user, roles)
        .filter(day__gte=first, day__lte=last, roster_week__status=RosterStatus.PUBLISHED)
        .select_related("employee", "template", "roster_week")
        .prefetch_related("activities")
    )
    if user.role == Role.LEAD:  # their own team, never a colleague lead's
        found = found.filter(employee__manager__user=user)
    held = {
        link.queue_id: link.contract
        for link in ContractQueue.objects.for_user(user)
        .filter(contract__active=True)
        .select_related("contract__customer")
    }
    terms = _targets(user)
    rows: list[Shift] = []
    for a in found.order_by("employee__emp_no", "day"):
        contract = held.get(a.roster_week.queue_id)
        worked = a.template.paid_minutes
        away = sum(x.slots for x in a.activities.all() if x.kind != ActivityKind.LUNCH) * SLOT_MIN
        billable = util.billable_minutes(
            worked, on_contract=contract is not None, non_billable_min=away
        )
        target: Decimal | None = None
        if contract is not None:
            row = terms.get(contract.pk)
            target = row.utilisation_target_pct if row else Decimal(DEFAULT_TARGET_PCT)
        rows.append(Shift(a.employee, a.roster_week.queue_id, worked, billable, contract, target))
    return rows


# --- UTL-01: utilisation and billability --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroupRow:
    key: str
    name: str
    figures: util.Utilisation
    target_is_default: bool = False
    contract_id: int | None = None
    customer: str | None = None


@dataclass(frozen=True, slots=True)
class PersonRow:
    employee: Employee
    figures: util.Utilisation


@dataclass(frozen=True, slots=True)
class UtilisationReport:
    month: date
    teams: list[GroupRow]
    customers: list[GroupRow]
    contracts: list[GroupRow]
    people: list[PersonRow] = field(default_factory=list)


def _blocks(rows: list[Shift]) -> list[util.Block]:
    return [util.Block(r.worked_min, r.billable_min, r.target_pct) for r in rows]


def utilisation(user: User, month: date) -> UtilisationReport:
    first = month_start(month)
    shifts = _shifts(user, first, roles=GROUP_ROLES)
    terms = _targets(user)

    by_team: dict[int | None, list[Shift]] = defaultdict(list)
    by_customer: dict[int, list[Shift]] = defaultdict(list)
    by_contract: dict[int, list[Shift]] = defaultdict(list)
    by_person: dict[int, list[Shift]] = defaultdict(list)
    for s in shifts:
        by_team[s.employee.manager_id].append(s)
        by_person[s.employee.pk].append(s)
        if s.contract is not None:
            by_customer[s.contract.customer_id].append(s)
            by_contract[s.contract.pk].append(s)

    managers = {
        e.pk: e.emp_no
        for e in Employee.objects.headcount_for(user, GROUP_ROLES).filter(
            pk__in=[k for k in by_team if k]
        )
    }
    teams = [
        GroupRow(
            key=str(k or 0),
            name=f"Team {managers[k]}" if k and k in managers else NO_TEAM,
            figures=util.utilisation(_blocks(rows)),
        )
        for k, rows in by_team.items()
    ]
    teams.sort(key=lambda g: (g.name == NO_TEAM, g.name))

    customers = [
        GroupRow(
            key=str(cid),
            name=rows[0].contract.customer.name,  # type: ignore[union-attr]
            figures=util.utilisation(_blocks(rows)),
        )
        for cid, rows in by_customer.items()
    ]
    customers.sort(key=lambda g: g.name)

    contracts = [
        GroupRow(
            key=str(cid),
            name=rows[0].contract.name,  # type: ignore[union-attr]
            figures=util.utilisation(_blocks(rows)),
            target_is_default=cid not in terms,
            contract_id=cid,
            customer=rows[0].contract.customer.name,  # type: ignore[union-attr]
        )
        for cid, rows in by_contract.items()
    ]
    contracts.sort(key=lambda g: (g.customer or "", g.name))

    people: list[PersonRow] = []
    if user.role in PERSON_ROLES:  # in employee-number order: there is no ranking anywhere
        by_emp = {s.employee.pk: s.employee for s in shifts}
        people = [
            PersonRow(by_emp[pk], util.utilisation(_blocks(rows)))
            for pk, rows in sorted(by_person.items(), key=lambda kv: by_emp[kv[0]].emp_no)
        ]
    return UtilisationReport(first, teams, customers, contracts, people)


# --- UTL-02: cost -------------------------------------------------------------------------------


@dataclass(slots=True)
class EngineerCost:
    employee: Employee
    worked_min: int = 0
    ordinary: Decimal | None = None  # None: no salary on file
    overtime: Decimal = Decimal("0.00")
    overtime_missing: int = 0  # approved overtime with no price on file

    @property
    def total(self) -> Decimal | None:
        return None if self.ordinary is None else self.ordinary + self.overtime


@dataclass(slots=True)
class ContractCost:
    contract: Contract | None  # None: time on queues that no contract holds
    worked_min: int = 0
    ordinary: Decimal = Decimal("0.00")
    overtime: Decimal = Decimal("0.00")
    revenue: Decimal | None = None
    incomplete: bool = False  # somebody who worked on it has no salary or price on file

    @property
    def total(self) -> Decimal:
        return self.ordinary + self.overtime


@dataclass(frozen=True, slots=True)
class PoolCost:
    pool: ServicePool
    ticket: util.TicketCost


@dataclass(frozen=True, slots=True)
class CostReport:
    month: date
    engineers: list[EngineerCost]
    contracts: list[ContractCost]
    pools: list[PoolCost]
    blended_hourly_rate: Decimal | None
    engineers_without_salary: int


def costs(user: User, month: date) -> CostReport:
    if user.role not in COST_ROLES:
        raise PermissionError("pay figures are for the roles that approve overtime")
    first = month_start(month)
    last = month_end(first)
    shifts = _shifts(user, first, roles=COST_ROLES)
    pay = {p.employee_id: p for p in EmployeePay.objects.for_pricing(user)}
    terms = _targets(user)

    rate_of: dict[int, Decimal] = {}
    people: dict[int, EngineerCost] = {}
    minutes_by: dict[int, dict[int | None, int]] = defaultdict(lambda: defaultdict(int))
    contracts: dict[int | None, ContractCost] = {}
    for s in shifts:
        e = s.employee
        person = people.setdefault(e.pk, EngineerCost(e))
        person.worked_min += s.worked_min
        cid = s.contract.pk if s.contract else None
        minutes_by[e.pk][cid] += s.worked_min
        if cid not in contracts:
            row = ContractCost(s.contract)
            if cid is not None and cid in terms:
                row.revenue = terms[cid].monthly_revenue_zar
            contracts[cid] = row
        contracts[cid].worked_min += s.worked_min
        p = pay.get(e.pk)
        if p is not None and e.pk not in rate_of:
            rate_of[e.pk] = pricing.hourly_rate(p.monthly_salary, e.weekly_hours)

    overtime = OvertimeRequest.objects.for_user(user).filter(
        status=OvertimeStatus.APPROVED, day__gte=first, day__lte=last, employee__in=people.keys()
    )
    ot_cost: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for r in overtime:
        amount = r.worked_cost if r.worked_minutes is not None else r.approved_cost
        if amount is None:
            people[r.employee_id].overtime_missing += 1
        else:
            ot_cost[r.employee_id] += amount

    for pk, person in people.items():
        rate = rate_of.get(pk)
        person.overtime = ot_cost[pk]
        if rate is not None:
            person.ordinary = util.cost_of(rate, person.worked_min)
        shares = dict(minutes_by[pk])
        ordinary_parts = util.allocate(person.ordinary or Decimal(0), shares)
        overtime_parts = util.allocate(person.overtime, shares)
        for cid in shares:
            row = contracts[cid]
            row.ordinary += ordinary_parts[cid]
            row.overtime += overtime_parts[cid]
            if person.ordinary is None or person.overtime_missing:
                row.incomplete = True

    blended = util.blended_hourly_rate(rate_of.values())
    return CostReport(
        month=first,
        engineers=sorted(people.values(), key=lambda p: p.employee.emp_no),
        contracts=sorted(
            contracts.values(),
            key=lambda c: (
                c.contract is None,
                c.contract.customer.name if c.contract else "",
                c.contract.name if c.contract else "",
            ),
        ),
        pools=_pool_costs(user, first, last, blended),
        blended_hourly_rate=blended,
        engineers_without_salary=sum(1 for p in people.values() if p.ordinary is None),
    )


def _pool_costs(user: User, first: date, last: date, rate: Decimal | None) -> list[PoolCost]:
    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(first, time.min, tzinfo=zone)
    end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone)
    closed: dict[int, list[int | None]] = defaultdict(list)
    for pool_id, effort in (
        WorkItem.objects.for_user(user)
        .filter(closed_at__gte=start, closed_at__lt=end)
        .values_list("pool_id", "effort_minutes")
    ):
        closed[pool_id].append(effort)
    return [
        PoolCost(pool, util.ticket_cost(closed.get(pool.pk, []), rate))
        for pool in ServicePool.objects.for_user(user)
    ]


# --- WLB-01: workload balance -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class QueueBalance:
    queue: Queue
    load: balancing.QueueLoad
    ratio: float | None
    state: str


@dataclass(frozen=True, slots=True)
class MoveSuggestion:
    employee: Employee
    from_queue: Queue
    to_queue: Queue
    slots: int


@dataclass(frozen=True, slots=True)
class Balance:
    day: date
    queues: list[QueueBalance]
    suggestions: list[MoveSuggestion]


def balance(user: User, day: date) -> Balance:
    if user.role not in BALANCE_ROLES:
        raise PermissionError("balance is for planners, admins and team leads")
    monday = day - timedelta(days=day.weekday())
    queues = list(Queue.objects.for_user(user).order_by("name"))
    loads: list[balancing.QueueLoad] = []
    for q in queues:
        cells = week_plan(user, q.pk, monday).cells[day]
        known = [c for c in cells if c.required is not None]
        loads.append(
            balancing.QueueLoad(
                q.pk, q.name, sum(c.required or 0 for c in known), sum(c.scheduled for c in known)
            )
        )
    by_id = {q.pk: q for q in queues}
    rows = [
        QueueBalance(by_id[ld.queue_id], ld, balancing.load_ratio(ld), balancing.classify(ld))
        for ld in loads
    ]
    rows.sort(key=lambda r: (r.ratio is None, -(r.ratio or 0), r.queue.name))

    assigned = (
        ShiftAssignment.objects.for_user(user)
        .filter(day=day)
        .select_related("employee", "template", "roster_week")
        .prefetch_related("activities")
    )
    if user.role == Role.LEAD:  # a lead moves only their own team
        assigned = assigned.filter(employee__manager__user=user)
    skills: dict[int, set[int]] = defaultdict(set)
    for emp_id, queue_id in EmployeeSkill.objects.filter(
        employee__in=[a.employee_id for a in assigned]
    ).values_list("employee_id", "queue_id"):
        skills[emp_id].add(queue_id)
    employees = {a.employee_id: a.employee for a in assigned}
    movers = [
        balancing.Mover(
            a.employee_id,
            a.roster_week.queue_id,
            frozenset(skills[a.employee_id]),
            shift_length_slots(a.template.start_time, a.template.end_time)
            - sum(x.slots for x in a.activities.all()),
        )
        for a in assigned
    ]
    moves = [
        MoveSuggestion(
            employees[s.person_id], by_id[s.from_queue_id], by_id[s.to_queue_id], s.slots
        )
        for s in balancing.suggest_moves(loads, movers)
        if s.from_queue_id in by_id and s.to_queue_id in by_id
    ]
    return Balance(day, rows, moves)


def check_month(value: date) -> date:
    if value.day != 1:
        raise ApiError(
            422, "utilisation.not_a_month", "Invalid request", "A month starts on its 1st."
        )
    return value
