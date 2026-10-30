from __future__ import annotations

import json

from django.http import HttpRequest, HttpResponse
from ninja import Router, Status

from wfm.accounts.models import Role, User
from wfm.core.errors import ApiError, not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.scheduling.models import Employee

from . import erasure, selectors, services, subject_export
from .ess_api import router as ess_router
from .models import LeaveRequest, LeaveType
from .policy import APPROVE_ROLES, CONFIG_ROLES, SELF_ROLES
from .rules_api import router as rules_router
from .schemas import (
    BalanceOut,
    BalancesOut,
    DecisionOut,
    EntitlementIn,
    ErasureConfirmIn,
    ErasureDoneOut,
    ErasurePreviewOut,
    ImpactOut,
    LeaveRejectIn,
    LeaveRequestIn,
    LeaveRequestOut,
    LeaveTypeOut,
    RetentionOut,
)
from .shrinkage_api import router as shrinkage_router
from .swap_api import router as swap_router
from .team_api import router as team_router

router = Router(tags=["people"])
router.add_router("/swaps", swap_router)
router.add_router("/leave", rules_router)
router.add_router("", ess_router)
router.add_router("", shrinkage_router)
router.add_router("", team_router)

SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=Feature.PEOPLE)
APPROVE = RoleSessionAuth(*sorted(APPROVE_ROLES), feature=Feature.PEOPLE)
CONFIG = RoleSessionAuth(*sorted(CONFIG_ROLES), feature=Feature.PEOPLE)
ADMIN_ONLY = RoleSessionAuth(Role.ADMIN, feature=Feature.PEOPLE)


@router.get("/leave/types", auth=SELF, response=list[LeaveTypeOut], summary="Kinds of leave")
def list_types(request: HttpRequest) -> list[LeaveTypeOut]:
    return [_type_out(t) for t in selectors.leave_types(current_user(request))]


@router.put(
    "/leave/types/{type_id}",
    auth=CONFIG,
    response=LeaveTypeOut,
    summary="Set the days a year of a kind of leave",
)
def set_entitlement(request: HttpRequest, type_id: int, body: EntitlementIn) -> LeaveTypeOut:
    return _type_out(
        services.set_entitlement(user=current_user(request), type_id=type_id, days=body.daysPerYear)
    )


@router.get(
    "/leave/balances",
    auth=SELF,
    response=BalancesOut,
    summary="A person's leave balances for a year (their own unless a planner or admin asks)",
)
def get_balances(request: HttpRequest, year: int, employee_id: int | None = None) -> BalancesOut:
    user = current_user(request)
    employee = _employee(request, employee_id)
    balances = [
        (leave_type, selectors.balance(employee, leave_type, year))
        for leave_type in selectors.leave_types(user)
    ]
    return BalancesOut(
        employeeId=employee.pk,
        employee=employee.name,
        year=year,
        balances=[
            BalanceOut(
                typeId=t.pk,
                code=t.code,
                name=t.name,
                entitlement=None if b.entitlement is None else float(b.entitlement),
                taken=float(b.taken),
                pending=float(b.pending),
                available=None if b.available is None else float(b.available),
            )
            for t, b in balances
        ],
    )


@router.get(
    "/leave/requests",
    auth=SELF,
    response=list[LeaveRequestOut],
    summary="Leave requests: your own, or everyone's for leads, planners and admins",
)
def list_requests(
    request: HttpRequest, status: str | None = None, employee_id: int | None = None
) -> list[LeaveRequestOut]:
    user = current_user(request)
    return [
        _request_out(user, r)
        for r in selectors.requests(user, status=status, employee_id=employee_id)
    ]


@router.post("/leave/requests", auth=SELF, response={201: LeaveRequestOut}, summary="Ask for leave")
def apply(request: HttpRequest, body: LeaveRequestIn) -> Status[LeaveRequestOut]:
    user = current_user(request)
    created = services.apply(
        user=user,
        leave_type_id=body.leaveTypeId,
        start=body.startDate,
        end=body.endDate,
        employee_id=body.employeeId,
    )
    return Status(201, _request_out(user, created))


@router.get(
    "/leave/requests/{request_id}/impact",
    auth=APPROVE,
    response=ImpactOut,
    summary="What approving a request would do to coverage",
)
def get_impact(request: HttpRequest, request_id: int) -> ImpactOut:
    user = current_user(request)
    result = selectors.impact(user, selectors.request_for(user, request_id))
    return ImpactOut(
        shifts=result.shifts,
        hours=result.hours,
        intervals=result.intervals,
        newlyUnder=result.newly_under,
        alreadyUnder=result.already_under,
        unknown=result.unknown,
    )


@router.post(
    "/leave/requests/{request_id}/approve",
    auth=APPROVE,
    response=DecisionOut,
    summary="Approve a request: it is written into the roster and coverage follows",
)
def approve(request: HttpRequest, request_id: int) -> DecisionOut:
    user = current_user(request)
    return _decision_out(user, services.decide(user=user, request_id=request_id, approve=True))


@router.post(
    "/leave/requests/{request_id}/reject",
    auth=APPROVE,
    response=DecisionOut,
    summary="Reject a request",
)
def reject(request: HttpRequest, request_id: int, body: LeaveRejectIn) -> DecisionOut:
    user = current_user(request)
    reason = body.reason
    return _decision_out(
        user, services.decide(user=user, request_id=request_id, approve=False, reason=reason)
    )


@router.post(
    "/leave/requests/{request_id}/cancel",
    auth=SELF,
    response=DecisionOut,
    summary="Withdraw a request; cancelling approved leave puts its shifts back where it can",
)
def cancel(request: HttpRequest, request_id: int) -> DecisionOut:
    user = current_user(request)
    return _decision_out(user, services.cancel(user=user, request_id=request_id))


def _employee(request: HttpRequest, employee_id: int | None) -> Employee:
    user = current_user(request)
    if employee_id is None:
        own = selectors.own_employee(user)
        if own is None:
            raise ApiError(
                422,
                "leave.no_employee_record",
                "Leave refused",
                "You are not on the employee list yet, so there is nobody to take leave for.",
            )
        return own
    employee = selectors.employee_in_scope(user, employee_id)
    if employee is None:
        raise not_found("No such employee.")
    return employee


def _type_out(t: LeaveType) -> LeaveTypeOut:
    return LeaveTypeOut(
        id=t.pk,
        code=t.code,
        name=t.name,
        paid=t.paid,
        daysPerYear=None if t.days_per_year is None else float(t.days_per_year),
        confirmed=t.confirmed,
        restricted=t.restricted,
    )


def _request_out(user: User, r: LeaveRequest) -> LeaveRequestOut:
    return LeaveRequestOut(
        id=r.pk,
        employeeId=r.employee_id,
        employee=r.employee.name,
        empNo=r.employee.emp_no,
        leaveTypeId=r.leave_type_id,
        leaveType=r.leave_type.name,
        startDate=r.start_date,
        endDate=r.end_date,
        days=r.days,
        status=r.status,
        createdAt=r.created_at,
        decidedAt=r.decided_at,
        shiftsCleared=len(r.cleared_shifts),
        decisionReason=r.decision_reason,
        mine=r.employee.user_id == user.pk,
    )


def _decision_out(user: User, decision: services.Decision) -> DecisionOut:
    return DecisionOut(
        request=_request_out(user, decision.request),
        shiftsCleared=decision.cleared,
        shiftsRestored=decision.restored,
        shiftsNotRestored=decision.not_restored,
    )


@router.get(
    "/employees/{employee_id}/data-export",
    auth=CONFIG,
    response={200: None},
    summary="Everything held about one employee, for a subject-access request",
)
def employee_data_export(request: HttpRequest, employee_id: int) -> HttpResponse:
    data = subject_export.export(current_user(request), employee_id)
    response = HttpResponse(
        json.dumps(data, indent=2, ensure_ascii=False), content_type="application/json"
    )
    response["Content-Disposition"] = f'attachment; filename="subject-access-{employee_id}.json"'
    response["Cache-Control"] = "no-store"
    return response


@router.post(
    "/employees/{employee_id}/erasure-request",
    auth=ADMIN_ONLY,
    response=ErasurePreviewOut,
    summary="Whether a leaver may be anonymised, and what would be removed (changes nothing)",
)
def erasure_request(request: HttpRequest, employee_id: int) -> dict[str, object]:
    return erasure.preview(current_user(request), employee_id)


@router.post(
    "/employees/{employee_id}/anonymise",
    auth=ADMIN_ONLY,
    response=ErasureDoneOut,
    summary="Anonymise a leaver (cannot be undone); the employee number must be typed again",
)
def employee_anonymise(
    request: HttpRequest, employee_id: int, body: ErasureConfirmIn
) -> dict[str, object]:
    return erasure.anonymise(current_user(request), employee_id, body.employeeNumber)


@router.get(
    "/retention",
    auth=ADMIN_ONLY,
    response=RetentionOut,
    summary="Leavers gone longer than the retention period, for the admin to review",
)
def retention(request: HttpRequest) -> dict[str, object]:
    return erasure.past_retention(current_user(request))
