"""Overtime requests, their approval and the pay they are priced from (OT-01)."""

from __future__ import annotations

from datetime import date, time
from decimal import Decimal

from django.http import HttpRequest
from ninja import Router, Schema, Status

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .models import OvertimeStatus
from .policy import DECIDE_ROLES, PAY_ROLES, READ_ROLES, REQUEST_ROLES

router = Router(tags=["overtime"])
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
