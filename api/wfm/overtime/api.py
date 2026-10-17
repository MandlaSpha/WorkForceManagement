"""Overtime requests, their approval and the pay they are priced from (OT-01)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from django.http import HttpRequest, HttpResponse
from ninja import Router, Schema, Status

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import payroll_export, reconcile_services, selectors, services
from .models import OvertimeStatus
from .policy import DECIDE_ROLES, PAY_ROLES, READ_ROLES, REQUEST_ROLES
from .standby_api import router as standby_router

router = Router(tags=["overtime"])
router.add_router("/standby", standby_router)
FEATURE = Feature.OVERTIME
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
REQUEST = RoleSessionAuth(*sorted(REQUEST_ROLES), feature=FEATURE)
# Cancelling is open to whoever may ask; the service narrows it to the requester or a planner.
DECIDE = RoleSessionAuth(*sorted(DECIDE_ROLES), feature=FEATURE)
PAY = RoleSessionAuth(*sorted(PAY_ROLES), feature=FEATURE)


class OvertimeIn(Schema):
    employeeId: int  # noqa: N815
    day: date
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    reason: str = ""


class OvertimeOut(Schema):
    id: int
    employeeId: int  # noqa: N815
    employee: str
    empNo: str  # noqa: N815
    day: date
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    minutes: int
    reason: str
    status: str
    kind: str  # weekday, sunday or holiday
    # Rands. Only for the roles that approve overtime; null for everybody else, and when no salary
    # is on file (then `costMissing` says so).
    costRands: float | None  # noqa: N815
    costMissing: bool  # noqa: N815
    mine: bool  # it is the signed-in person's own overtime
    # OT-03. Minutes recorded as really worked (null until recorded), how many of them were paid
    # (never more than approved), and how many were beyond what was approved.
    workedMinutes: int | None  # noqa: N815
    paidMinutes: int | None  # noqa: N815
    extraMinutes: int  # noqa: N815
    workedCostRands: float | None  # noqa: N815 - the paid time at the approved price


class OvertimePayIn(Schema):
    # None keeps the salary on file and changes only the Sunday flag.
    monthlySalary: float | None = None  # noqa: N815
    ordinarilyWorksSundays: bool = False  # noqa: N815
    clear: bool = False  # remove the salary on file


class OvertimePayOut(Schema):
    employeeId: int  # noqa: N815
    employee: str
    empNo: str  # noqa: N815
    hasSalary: bool  # noqa: N815 - whether one is on file; the figure is never returned
    ordinarilyWorksSundays: bool  # noqa: N815


def _out(row: selectors.Row, user_id: int) -> OvertimeOut:
    r = row.request
    return OvertimeOut(
        id=r.pk,
        employeeId=r.employee_id,
        employee=r.employee.name,
        empNo=r.employee.emp_no,
        day=r.day,
        startTime=r.start_time,
        endTime=r.end_time,
        minutes=r.minutes,
        reason=r.reason,
        status=r.status,
        kind=row.kind,
        costRands=float(row.cost) if row.cost is not None else None,
        costMissing=row.cost_missing,
        mine=r.employee.user_id == user_id,
        workedMinutes=r.worked_minutes,
        paidMinutes=reconcile_services.payable_minutes(r),
        extraMinutes=max(0, (r.worked_minutes or 0) - r.minutes),
        workedCostRands=float(row.worked_cost) if row.worked_cost is not None else None,
    )


def _one(request: HttpRequest, request_id: int) -> OvertimeOut:
    user = current_user(request)
    rows = selectors.requests(user)
    row = next(r for r in rows if r.request.pk == request_id)
    return _out(row, user.pk)


@router.get(
    "/requests",
    auth=READ,
    response=list[OvertimeOut],
    summary="Overtime requests the signed-in person may see",
)
def list_requests(
    request: HttpRequest,
    status: OvertimeStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[OvertimeOut]:
    user = current_user(request)
    rows = selectors.requests(
        user, status=status.value if status else None, date_from=date_from, date_to=date_to
    )
    return [_out(r, user.pk) for r in rows]


@router.post("/requests", auth=REQUEST, response={201: OvertimeOut}, summary="Ask for overtime")
def ask(request: HttpRequest, body: OvertimeIn) -> Status[OvertimeOut]:
    created = services.request_overtime(
        user=current_user(request),
        employee_id=body.employeeId,
        day=body.day,
        start_time=body.startTime,
        end_time=body.endTime,
        reason=body.reason,
    )
    return Status(201, _one(request, created.pk))


@router.post(
    "/requests/{request_id}/approve", auth=DECIDE, response=OvertimeOut, summary="Approve overtime"
)
def approve(request: HttpRequest, request_id: int) -> OvertimeOut:
    services.decide(user=current_user(request), request_id=request_id, approve=True)
    return _one(request, request_id)


@router.post(
    "/requests/{request_id}/reject", auth=DECIDE, response=OvertimeOut, summary="Reject overtime"
)
def reject(request: HttpRequest, request_id: int) -> OvertimeOut:
    services.decide(user=current_user(request), request_id=request_id, approve=False)
    return _one(request, request_id)


@router.post(
    "/requests/{request_id}/cancel", auth=REQUEST, response=OvertimeOut, summary="Cancel overtime"
)
def cancel(request: HttpRequest, request_id: int) -> OvertimeOut:
    services.cancel(user=current_user(request), request_id=request_id)
    return _one(request, request_id)


@router.get(
    "/pay",
    auth=PAY,
    response=list[OvertimePayOut],
    summary="Who has a salary on file (never the figure)",
)
def list_pay(request: HttpRequest) -> list[OvertimePayOut]:
    return [_pay(s) for s in selectors.pay_statuses(current_user(request))]


@router.put(
    "/pay/{employee_id}", auth=PAY, response=OvertimePayOut, summary="Set or clear a salary"
)
def put_pay(request: HttpRequest, employee_id: int, body: OvertimePayIn) -> OvertimePayOut:
    user = current_user(request)
    services.set_pay(
        user=user,
        employee_id=employee_id,
        monthly_salary=Decimal(str(body.monthlySalary)) if body.monthlySalary is not None else None,
        works_sundays=body.ordinarilyWorksSundays,
        clear=body.clear,
    )
    return _pay(next(s for s in selectors.pay_statuses(user) if s.employee.pk == employee_id))


def _pay(status: selectors.PayStatus) -> OvertimePayOut:
    return OvertimePayOut(
        employeeId=status.employee.pk,
        employee=status.employee.name,
        empNo=status.employee.emp_no,
        hasSalary=status.has_salary,
        ordinarilyWorksSundays=status.ordinarily_works_sundays,
    )


class WorkedIn(Schema):
    minutes: int


@router.post(
    "/requests/{request_id}/worked",
    auth=DECIDE,
    response=OvertimeOut,
    summary="Record how long approved overtime really lasted",
)
def record_worked(request: HttpRequest, request_id: int, body: WorkedIn) -> OvertimeOut:
    reconcile_services.record_worked(
        user=current_user(request), request_id=request_id, worked_minutes=body.minutes
    )
    return _one(request, request_id)


class SummaryOut(Schema):
    month: date
    approved: int
    approvedMinutes: int  # noqa: N815
    unreconciled: int
    workedMinutes: int  # noqa: N815
    extraMinutes: int  # noqa: N815
    overtimeCostRands: float  # noqa: N815
    missingPrices: int  # noqa: N815
    standbyDays: int  # noqa: N815
    standbyAllowancesRands: float  # noqa: N815
    callOutMinutes: int  # noqa: N815
    callOutCostRands: float  # noqa: N815
    totalRands: float  # noqa: N815
    budgetRands: float | None  # noqa: N815
    standbyAllowanceRands: float  # noqa: N815 - the rate for a day on standby


@router.get(
    "/summary",
    auth=DECIDE,
    response=SummaryOut,
    summary="Overtime and standby for a month against the budget",
)
def month_summary(request: HttpRequest, month: date) -> SummaryOut:
    user = current_user(request)
    s = selectors.summary(user, month)
    rate = selectors.standby_allowance(user) or 0
    return SummaryOut(
        month=s.month,
        approved=s.approved,
        approvedMinutes=s.approved_minutes,
        unreconciled=s.unreconciled,
        workedMinutes=s.worked_minutes,
        extraMinutes=s.extra_minutes,
        overtimeCostRands=float(s.overtime_cost),
        missingPrices=s.missing_prices,
        standbyDays=s.standby_days,
        standbyAllowancesRands=float(s.standby_allowances),
        callOutMinutes=s.call_out_minutes,
        callOutCostRands=float(s.call_out_cost),
        totalRands=float(s.total),
        budgetRands=float(s.budget) if s.budget is not None else None,
        standbyAllowanceRands=float(rate),
    )


class RatesIn(Schema):
    standbyAllowance: float  # noqa: N815


class RatesOut(Schema):
    standbyAllowance: float  # noqa: N815


@router.put("/rates", auth=PAY, response=RatesOut, summary="Set the standby allowance for a day")
def put_rates(request: HttpRequest, body: RatesIn) -> RatesOut:
    rates = reconcile_services.set_standby_allowance(
        user=current_user(request), amount=Decimal(str(body.standbyAllowance))
    )
    return RatesOut(standbyAllowance=float(rates.standby_allowance))


class BudgetIn(Schema):
    amount: float | None = None  # none removes the budget


class BudgetOut(Schema):
    month: date
    amount: float | None


@router.put("/budget/{month}", auth=PAY, response=BudgetOut, summary="Set the budget for a month")
def put_budget(request: HttpRequest, month: date, body: BudgetIn) -> BudgetOut:
    saved = reconcile_services.set_budget(
        user=current_user(request),
        month=month,
        amount=Decimal(str(body.amount)) if body.amount is not None else None,
    )
    return BudgetOut(
        month=month.replace(day=1), amount=float(saved.amount) if saved is not None else None
    )


@router.get(
    "/payroll.csv",
    auth=DECIDE,
    response={200: None},
    summary="The payroll file for a month (hours, leave, overtime, standby, call-outs)",
)
def payroll_file(request: HttpRequest, month: date) -> HttpResponse:
    text = payroll_export.export(current_user(request), month)
    response = HttpResponse(text, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="payroll-{month:%Y-%m}.csv"'
    response["Cache-Control"] = "no-store"
    return response
