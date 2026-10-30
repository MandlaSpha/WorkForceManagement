from __future__ import annotations

from django.http import HttpRequest
from ninja import Router, Status

from wfm.accounts.models import User
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.scheduling.models import ShiftAssignment

from . import swap_selectors as selectors
from . import swap_services as services
from .models import SwapRequest
from .policy import APPROVE_ROLES, SELF_ROLES
from .swap_schemas import BoardOut, RejectIn, SwapIn, SwapOut, SwapShiftOut, TakeIn

router = Router(tags=["people"])

SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=Feature.PEOPLE)
APPROVE = RoleSessionAuth(*sorted(APPROVE_ROLES), feature=Feature.PEOPLE)


@router.get(
    "/my-shifts", auth=SELF, response=list[SwapShiftOut], summary="Your shifts you could post"
)
def my_shifts(request: HttpRequest) -> list[SwapShiftOut]:
    return [_shift_out(a) for a in selectors.my_shifts(current_user(request))]


@router.get(
    "/board",
    auth=SELF,
    response=list[BoardOut],
    summary="Open requests you could take (the poster is not named)",
)
def board(request: HttpRequest) -> list[BoardOut]:
    return [
        BoardOut(
            id=s.pk,
            queue=s.queue.name,
            day=s.from_day,
            shift=s.from_template.code,
            startTime=s.from_template.start_time,
            endTime=s.from_template.end_time,
            createdAt=s.created_at,
        )
        for s in selectors.board(current_user(request))
    ]


@router.get(
    "/{swap_id}/offers",
    auth=SELF,
    response=list[SwapShiftOut],
    summary="Which of your shifts you could offer in return for an open request",
)
def offers(request: HttpRequest, swap_id: int) -> list[SwapShiftOut]:
    user = current_user(request)
    swap = selectors.open_request(user, swap_id)
    if swap is None:
        return []
    return [_shift_out(a) for a in selectors.offers_for(user, swap, selectors.my_shifts(user))]


@router.get("", auth=SELF, response=list[SwapOut], summary="Shift swaps you are part of, or all")
def list_swaps(request: HttpRequest, status: str | None = None) -> list[SwapOut]:
    user = current_user(request)
    return [_swap_out(user, s) for s in selectors.swaps(user, status=status)]


@router.post("", auth=SELF, response={201: SwapOut}, summary="Post one of your shifts to swap")
def propose(request: HttpRequest, body: SwapIn) -> Status[SwapOut]:
    user = current_user(request)
    swap = services.propose(user=user, give_id=body.giveAssignmentId, employee_id=body.employeeId)
    return Status(201, _swap_out(user, swap))


@router.post(
    "/{swap_id}/accept",
    auth=SELF,
    response=SwapOut,
    summary="Take an open request by offering one of your own shifts in return",
)
def accept(request: HttpRequest, swap_id: int, body: TakeIn) -> SwapOut:
    user = current_user(request)
    return _swap_out(
        user,
        services.take(
            user=user, swap_id=swap_id, assignment_id=body.assignmentId, employee_id=body.employeeId
        ),
    )


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
def reject(request: HttpRequest, swap_id: int, body: RejectIn) -> SwapOut:
    user = current_user(request)
    reason = body.reason
    return _swap_out(
        user, services.decide(user=user, swap_id=swap_id, approve=False, reason=reason)
    )


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
        toEmployee=s.to_employee.name if s.to_employee else None,
        toDay=s.to_day,
        toShift=s.to_template.code if s.to_template else None,
        createdAt=s.created_at,
        decidedAt=s.decided_at,
        decisionReason=s.decision_reason,
        asker=s.from_employee.user_id == user.pk,
        colleague=s.to_employee is not None and s.to_employee.user_id == user.pk,
    )
