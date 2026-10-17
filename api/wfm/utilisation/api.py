"""Utilisation and billability, cost of engineer time, and workload balance (UTL-01, UTL-02,
WLB-01). Reads only, apart from a contract's utilisation target and revenue."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.http import HttpRequest
from ninja import Router, Schema
from wfm_engine import utilisation as util

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .policy import BALANCE_ROLES, COST_ROLES, GROUP_ROLES, TERMS_WRITE_ROLES

router = Router(tags=["utilisation"])
READ = RoleSessionAuth(*sorted(GROUP_ROLES), feature=Feature.INSIGHT)
COST = RoleSessionAuth(*sorted(COST_ROLES), feature=Feature.INSIGHT)
TERMS = RoleSessionAuth(*sorted(TERMS_WRITE_ROLES), feature=Feature.INSIGHT)
BALANCE = RoleSessionAuth(*sorted(BALANCE_ROLES), feature=Feature.SCHEDULING)


class UtilFigures(Schema):
    workedMin: int  # noqa: N815
    billableMin: int  # noqa: N815
    utilisationPct: float | None  # noqa: N815
    targetPct: float | None  # noqa: N815
    gapPct: float | None  # noqa: N815 - percentage points; negative is short of target


class UtilGroupOut(UtilFigures):
    key: str
    name: str
    customer: str | None = None
    contractId: int | None = None  # noqa: N815
    targetIsDefault: bool = False  # noqa: N815 - an assumption until an admin sets the target


class UtilPersonOut(UtilFigures):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str


class UtilReportOut(Schema):
    month: date
    basis: str  # always "modelled": the roster, not a timesheet
    teams: list[UtilGroupOut]
    customers: list[UtilGroupOut]
    contracts: list[UtilGroupOut]
    people: list[UtilPersonOut]  # empty unless the role plans or leads the people; never ranked


class UtilTermsIn(Schema):
    utilisationTargetPct: float  # noqa: N815
    monthlyRevenueRands: float | None = None  # noqa: N815


class UtilTermsOut(Schema):
    contractId: int  # noqa: N815
    utilisationTargetPct: float  # noqa: N815
    hasRevenue: bool  # noqa: N815 - the figure itself is not echoed


class UtilEngineerCostOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    workedMin: int  # noqa: N815
    ordinaryRands: float | None  # noqa: N815 - none: no salary on file
    overtimeRands: float  # noqa: N815
    totalRands: float | None  # noqa: N815
    overtimeMissing: int  # noqa: N815 - approved overtime with no price on file


class UtilContractCostOut(Schema):
    contractId: int | None  # noqa: N815 - none: queues no contract holds
    name: str
    customer: str | None
    workedMin: int  # noqa: N815
    ordinaryRands: float  # noqa: N815
    overtimeRands: float  # noqa: N815
    totalRands: float  # noqa: N815
    revenueRands: float | None  # noqa: N815
    costPctOfRevenue: float | None  # noqa: N815
    overtimePctOfRevenue: float | None  # noqa: N815
    incomplete: bool  # somebody on it has no salary or price on file: the cost is a minimum


class UtilPoolCostOut(Schema):
    pool: str
    closed: int
    estimated: int
    effortMin: int  # noqa: N815
    costRands: float | None  # noqa: N815
    perTicketRands: float | None  # noqa: N815


class UtilCostReportOut(Schema):
    month: date
    basis: str  # "modelled": roster time at the hourly rate from the salary on file
    blendedHourlyRands: float | None  # noqa: N815 - what a ticket is priced at
    engineersWithoutSalary: int  # noqa: N815
    engineers: list[UtilEngineerCostOut]
    contracts: list[UtilContractCostOut]
    pools: list[UtilPoolCostOut]


class BalanceQueueOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    requiredSlots: int  # noqa: N815 - people-half-hours the forecast needs
    scheduledSlots: int  # noqa: N815 - people-half-hours rostered on the phones
    loadRatio: float | None  # noqa: N815
    state: str  # stretched, slack, balanced or unknown (no known requirement)


class BalanceMoveOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    fromQueueId: int  # noqa: N815
    fromQueue: str  # noqa: N815
    toQueueId: int  # noqa: N815
    toQueue: str  # noqa: N815
    slots: int  # half-hours of cover moved


class BalanceDayOut(Schema):
    day: date
    note: str  # suggestions only: nothing is reassigned
    queues: list[BalanceQueueOut]
    suggestions: list[BalanceMoveOut]


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _figures(f: util.Utilisation) -> dict[str, object]:
    return {
        "workedMin": f.worked_min,
        "billableMin": f.billable_min,
        "utilisationPct": f.utilisation_pct,
        "targetPct": f.target_pct,
        "gapPct": f.gap_pct,
    }


@router.get(
    "/report",
    auth=READ,
    response=UtilReportOut,
    summary="Worked against billable hours by team, customer and contract for a month",
)
def get_utilisation(request: HttpRequest, month: date) -> UtilReportOut:
    found = selectors.utilisation(current_user(request), selectors.check_month(month))

    def group(g: selectors.GroupRow) -> UtilGroupOut:
        return UtilGroupOut(
            key=g.key,
            name=g.name,
            customer=g.customer,
            contractId=g.contract_id,
            targetIsDefault=g.target_is_default,
            **_figures(g.figures),  # type: ignore[arg-type]
        )

    return UtilReportOut(
        month=found.month,
        basis="modelled",
        teams=[group(g) for g in found.teams],
        customers=[group(g) for g in found.customers],
        contracts=[group(g) for g in found.contracts],
        people=[
            UtilPersonOut(
                employeeId=p.employee.pk,
                empNo=p.employee.emp_no,
                employee=p.employee.name,
                **_figures(p.figures),  # type: ignore[arg-type]
            )
            for p in found.people
        ],
    )


@router.put(
    "/contracts/{contract_id}/terms",
    auth=TERMS,
    response=UtilTermsOut,
    summary="Set a contract's utilisation target and monthly revenue",
)
def put_terms(request: HttpRequest, contract_id: int, body: UtilTermsIn) -> UtilTermsOut:
    terms = services.set_terms(
        user=current_user(request),
        contract_id=contract_id,
        utilisation_target_pct=Decimal(str(body.utilisationTargetPct)),
        monthly_revenue_zar=(
            Decimal(str(body.monthlyRevenueRands)) if body.monthlyRevenueRands is not None else None
        ),
    )
    return UtilTermsOut(
        contractId=terms.contract_id,
        utilisationTargetPct=float(terms.utilisation_target_pct),
        hasRevenue=terms.monthly_revenue_zar is not None,
    )


@router.get(
    "/costs",
    auth=COST,
    response=UtilCostReportOut,
    summary="Cost per engineer, per contract and per ticket for a month (pay roles only)",
)
def get_costs(request: HttpRequest, month: date) -> UtilCostReportOut:
    found = selectors.costs(current_user(request), selectors.check_month(month))
    contracts: list[UtilContractCostOut] = []
    for c in found.contracts:
        contracts.append(
            UtilContractCostOut(
                contractId=c.contract.pk if c.contract else None,
                name=c.contract.name if c.contract else "No contract",
                customer=c.contract.customer.name if c.contract else None,
                workedMin=c.worked_min,
                ordinaryRands=float(c.ordinary),
                overtimeRands=float(c.overtime),
                totalRands=float(c.total),
                revenueRands=_f(c.revenue),
                costPctOfRevenue=util.share_pct(c.total, c.revenue),
                overtimePctOfRevenue=util.share_pct(c.overtime, c.revenue),
                incomplete=c.incomplete,
            )
        )
    return UtilCostReportOut(
        month=found.month,
        basis="modelled",
        blendedHourlyRands=_f(found.blended_hourly_rate),
        engineersWithoutSalary=found.engineers_without_salary,
        engineers=[
            UtilEngineerCostOut(
                employeeId=p.employee.pk,
                empNo=p.employee.emp_no,
                employee=p.employee.name,
                workedMin=p.worked_min,
                ordinaryRands=_f(p.ordinary),
                overtimeRands=float(p.overtime),
                totalRands=_f(p.total),
                overtimeMissing=p.overtime_missing,
            )
            for p in found.engineers
        ],
        contracts=contracts,
        pools=[
            UtilPoolCostOut(
                pool=p.pool.name,
                closed=p.ticket.closed,
                estimated=p.ticket.estimated,
                effortMin=p.ticket.effort_min,
                costRands=_f(p.ticket.cost),
                perTicketRands=_f(p.ticket.per_ticket),
            )
            for p in found.pools
        ],
    )


@router.get(
    "/balance",
    auth=BALANCE,
    response=BalanceDayOut,
    summary="Over- and under-loaded queues for a day, with suggested moves (never applied)",
)
def get_balance(request: HttpRequest, day: date) -> BalanceDayOut:
    found = selectors.balance(current_user(request), day)
    return BalanceDayOut(
        day=found.day,
        note="These are suggestions. Nobody is moved until a planner changes the roster.",
        queues=[
            BalanceQueueOut(
                queueId=q.queue.pk,
                queue=q.queue.name,
                requiredSlots=q.load.required_slots,
                scheduledSlots=q.load.scheduled_slots,
                loadRatio=q.ratio,
                state=q.state,
            )
            for q in found.queues
        ],
        suggestions=[
            BalanceMoveOut(
                employeeId=m.employee.pk,
                empNo=m.employee.emp_no,
                employee=m.employee.name,
                fromQueueId=m.from_queue.pk,
                fromQueue=m.from_queue.name,
                toQueueId=m.to_queue.pk,
                toQueue=m.to_queue.name,
                slots=m.slots,
            )
            for m in found.suggestions
        ],
    )
