"""Standby rota and call-outs (OT-02)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router, Schema, Status

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, standby_services
from .policy import DECIDE_ROLES, READ_ROLES, REQUEST_ROLES

router = Router(tags=["overtime"])
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.OVERTIME)
REQUEST = RoleSessionAuth(*sorted(REQUEST_ROLES), feature=Feature.OVERTIME)
DECIDE = RoleSessionAuth(*sorted(DECIDE_ROLES), feature=Feature.OVERTIME)


class StandbyIn(Schema):
    employeeId: int  # noqa: N815
    day: date


class CallOutIn(Schema):
    minutes: int  # 0 clears it


class StandbyOut(Schema):
    id: int
    employeeId: int  # noqa: N815
    employee: str
    empNo: str  # noqa: N815
    day: date
    status: str
    # Rands, for the roles that approve overtime only; null for everybody else.
    allowanceRands: float | None  # noqa: N815
    callOutMinutes: int | None  # noqa: N815
    callOutCostRands: float | None  # noqa: N815
    callOutCostMissing: bool  # noqa: N815
    mine: bool


def _out(row: selectors.StandbyRow, user_id: int) -> StandbyOut:
    s = row.shift
    return StandbyOut(
        id=s.pk,
        employeeId=s.employee_id,
        employee=s.employee.name,
        empNo=s.employee.emp_no,
        day=s.day,
        status=s.status,
        allowanceRands=float(row.allowance) if row.allowance is not None else None,
        callOutMinutes=s.call_out_minutes,
        callOutCostRands=float(row.call_out_cost) if row.call_out_cost is not None else None,
        callOutCostMissing=row.call_out_cost_missing,
        mine=s.employee.user_id == user_id,
    )


def _one(request: HttpRequest, standby_id: int) -> StandbyOut:
    user = current_user(request)
    return _out(
        next(r for r in selectors.standby_shifts(user) if r.shift.pk == standby_id), user.pk
    )


@router.get(
    "", auth=READ, response=list[StandbyOut], summary="Standby the signed-in person may see"
)
def list_standby(
    request: HttpRequest, date_from: date | None = None, date_to: date | None = None
) -> list[StandbyOut]:
    user = current_user(request)
    return [
        _out(r, user.pk)
        for r in selectors.standby_shifts(user, date_from=date_from, date_to=date_to)
    ]


@router.post("", auth=REQUEST, response={201: StandbyOut}, summary="Put somebody on standby")
def book(request: HttpRequest, body: StandbyIn) -> Status[StandbyOut]:
    created = standby_services.book(
        user=current_user(request), employee_id=body.employeeId, day=body.day
    )
    return Status(201, _one(request, created.pk))


@router.post("/{standby_id}/cancel", auth=REQUEST, response=StandbyOut, summary="Cancel standby")
def cancel(request: HttpRequest, standby_id: int) -> StandbyOut:
    standby_services.cancel(user=current_user(request), standby_id=standby_id)
    return _one(request, standby_id)


@router.post(
    "/{standby_id}/call-out", auth=DECIDE, response=StandbyOut, summary="Record a call-out"
)
def call_out(request: HttpRequest, standby_id: int, body: CallOutIn) -> StandbyOut:
    standby_services.record_call_out(
        user=current_user(request), standby_id=standby_id, minutes=body.minutes
    )
    return _one(request, standby_id)
