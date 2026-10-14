from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.scheduling.models import ShiftAssignment

from . import swap_selectors as selectors
from . import swap_services as services
from .models import SwapRequest
from .policy import APPROVE_ROLES, SELF_ROLES
from .swap_schemas import SwapIn, SwapOut, SwapShiftOut

router = Router(tags=["people"])

SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=Feature.PEOPLE)
APPROVE = RoleSessionAuth(*sorted(APPROVE_ROLES), feature=Feature.PEOPLE)


@router.get(
    "/my-shifts", auth=SELF, response=list[SwapShiftOut], summary="Your shifts you could swap"
)
def my_shifts(request: HttpRequest) -> list[SwapShiftOut]:
    return [_shift_out(a) for a in selectors.my_shifts(current_user(request))]


@router.get(
    "/options",
    auth=SELF,
    response=list[SwapShiftOut],
    summary="Colleagues' shifts one of yours could be swapped for",
)
def options(request: HttpRequest, give_assignment_id: int) -> list[SwapShiftOut]:
    user = current_user(request)
    mine = {a.pk: a for a in selectors.my_shifts(user)}
    if give_assignment_id not in mine:
        raise not_found("No such shift.")
    return [_shift_out(a) for a in selectors.options(user, mine[give_assignment_id])]


@router.get("", auth=SELF, response=list[SwapOut], summary="Shift swaps you are part of, or all")
def list_swaps(request: HttpRequest, status: str | None = None) -> list[SwapOut]:
    user = current_user(request)
    return [_swap_out(user, s) for s in selectors.swaps(user, status=status)]


@router.post("", auth=SELF, response={201: SwapOut}, summary="Offer a shift for a colleague's")
def propose(request: HttpRequest, body: SwapIn) -> Status[SwapOut]:
    user = current_user(request)
    swap = services.propose(
        user=user,
        give_id=body.giveAssignmentId,
        take_id=body.takeAssignmentId,
        employee_id=body.employeeId,
    )
    return Status(201, _swap_out(user, swap))


@router.post("/{swap_id}/accept", auth=SELF, response=SwapOut, summary="Accept a colleague's offer")
def accept(request: HttpRequest, swap_id: int) -> SwapOut:
    user = current_user(request)
    return _swap_out(user, services.respond(user=user, swap_id=swap_id, accept=True))


@router.post("/{swap_id}/decline", auth=SELF, response=SwapOut, summary="Decline an offer")
def decline(request: HttpRequest, swap_id: int) -> SwapOut:
    user = current_user(request)
    return _swap_out(user, services.respond(user=user, swap_id=swap_id, accept=False))


@router.post(
    "/{swap_id}/approve",
    auth=APPROVE,
    response=SwapOut,
    summary="Approve a swap: the two shifts are exchanged",
)
def approve(request: HttpRequest, swap_id: int) -> SwapOut:
    user = current_user(request)
    return _swap_out(user, services.decide(user=user, swap_id=swap_id, approve=True))


@router.post("/{swap_id}/reject", auth=APPROVE, response=SwapOut, summary="Reject a swap")
def reject(request: HttpRequest, swap_id: int) -> SwapOut:
    user = current_user(request)
    return _swap_out(user, services.decide(user=user, swap_id=swap_id, approve=False))


@router.post("/{swap_id}/cancel", auth=SELF, response=SwapOut, summary="Withdraw a swap")
def cancel(request: HttpRequest, swap_id: int) -> SwapOut:
    user = current_user(request)
    return _swap_out(user, services.cancel(user=user, swap_id=swap_id))


def _shift_out(a: ShiftAssignment) -> SwapShiftOut:
    return SwapShiftOut(
        assignmentId=a.pk,
        queueId=a.roster_week.queue_id,
        queue=a.roster_week.queue.name,
        day=a.day,
        shift=a.template.code,
        startTime=a.template.start_time,
        endTime=a.template.end_time,
        employeeId=a.employee_id,
        employee=a.employee.name,
    )


def _swap_out(user: User, s: SwapRequest) -> SwapOut:
    return SwapOut(
        id=s.pk,
        queue=s.queue.name,
        status=s.status,
        fromEmployee=s.from_employee.name,
        fromDay=s.from_day,
        fromShift=s.from_template.code,
        toEmployee=s.to_employee.name,
        toDay=s.to_day,
        toShift=s.to_template.code,
        createdAt=s.created_at,
        decidedAt=s.decided_at,
        asker=s.from_employee.user_id == user.pk,
        colleague=s.to_employee.user_id == user.pk,
    )
