"""Asking for, answering, deciding and cancelling shift swaps (SWP-01). Writes happen here, in one
transaction, with the audit event as the LAST write.

The flow: a person offers one of their shifts for a colleague's; the colleague accepts or
declines; a lead, planner or admin approves or rejects. The roster rules are checked when it is
asked, when the colleague accepts and again when it is approved, because the roster can change
in between. Approving exchanges the two shifts; nobody approves a swap they are part of."""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.db.models.functions import Now
from django.utils import timezone

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.scheduling import roster_services
from wfm.scheduling.models import Employee, ShiftAssignment

from . import services as leave_services
from . import swap_selectors as selectors
from .models import OPEN_SWAP_STATUSES, SwapRequest, SwapStatus
from .policy import ON_BEHALF_ROLES


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Swap refused", detail)


def _lock_people(*ids: int) -> None:
    """Lock both people (in id order, so two swaps cannot wait on each other)."""
    list(Employee.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk"))


def _assignment(employee_id: int, day: date, template_id: int) -> ShiftAssignment | None:
    found: ShiftAssignment | None = (
        ShiftAssignment.objects.filter(employee_id=employee_id, day=day, template_id=template_id)
        .select_related("template", "employee", "roster_week__queue")
        .first()
    )
    return found


def _current(swap: SwapRequest) -> tuple[ShiftAssignment, ShiftAssignment]:
    """The two roster rows the swap is about, or a refusal when the roster has moved on."""
    first = _assignment(swap.from_employee_id, swap.from_day, swap.from_template_id)
    second = _assignment(swap.to_employee_id, swap.to_day, swap.to_template_id)
    if first is None or second is None:
        raise _refuse(409, "swap.changed", "One of the shifts has changed since this was asked.")
    return first, second


def _check_rules(user: User, first: ShiftAssignment, second: ShiftAssignment) -> None:
    today = timezone.localdate()
    if first.day < today or second.day < today:
        raise _refuse(422, "swap.in_the_past", "A shift that has started cannot be swapped.")
    refusal = roster_services.exchange_refusal(user, first, second)
    if refusal is not None:
        raise _refuse(422, *refusal)


def propose(
    *, user: User, give_id: int, take_id: int, employee_id: int | None = None
) -> SwapRequest:
    """Offer `give_id` (your shift) for `take_id` (a colleague's, on the same queue)."""
    employee = leave_services.employee_for(user, employee_id, area="swap", refuse_as="Swap refused")
    with transaction.atomic():
        rows = ShiftAssignment.objects.select_related("template", "employee", "roster_week__queue")
        give = rows.filter(pk=give_id, employee=employee).first()
        take = rows.filter(pk=take_id).first()
        if give is None or take is None:
            raise not_found("No such shift.")
        _lock_people(give.employee_id, take.employee_id)
        if take.employee_id == give.employee_id:
            raise _refuse(422, "swap.same_person", "Pick a colleague's shift, not your own.")
        if give.roster_week.queue_id != take.roster_week.queue_id:
            raise _refuse(422, "swap.different_queue", "Both shifts must be on the same queue.")
        if selectors.has_open_swap(give) or selectors.has_open_swap(take):
            raise _refuse(409, "swap.already_open", "One of the shifts is already in a swap.")
        _check_rules(user, give, take)
        swap = SwapRequest.objects.create(
            queue=give.roster_week.queue,
            from_employee=give.employee,
            from_day=give.day,
            from_template=give.template,
            to_employee=take.employee,
            to_day=take.day,
            to_template=take.template,
            requested_by=user,
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.SWAP_REQUESTED,
            entity_type="swap_request",
            entity_id=str(swap.pk),
            subject_employee_id=give.employee_id,
            changes=[audit.FieldChange("swap_request", str(swap.pk), "status", None, swap.status)],
        )
    return selectors.swap_for(user, swap.pk)


def _locked(user: User, swap_id: int) -> SwapRequest:
    found: SwapRequest | None = (
        SwapRequest.objects.select_for_update(of=("self",), no_key=True)
        .for_user(user)
        .select_related("queue", "from_employee", "to_employee", "from_template", "to_template")
        .filter(pk=swap_id)
        .first()
    )
    if found is None:
        raise not_found("No such shift swap.")
    return found


def _move(
    user: User,
    swap: SwapRequest,
    status: str,
    action: Action,
    *,
    colleague: bool = False,
    extra: list[audit.FieldChange] | None = None,
) -> SwapRequest:
    """Record the new status and audit it. This is the last write of the transaction."""
    was = swap.status
    swap.status = status
    if colleague:
        swap.colleague_answered_at = Now()
        swap.save(update_fields=["status", "colleague_answered_at"])
    else:
        swap.decided_by = user
        swap.decided_at = Now()
        swap.save(update_fields=["status", "decided_by", "decided_at"])
    swap.refresh_from_db()
    audit.record(  # last write of the transaction
        actor=user,
        action=action,
        entity_type="swap_request",
        entity_id=str(swap.pk),
        subject_employee_id=swap.from_employee_id,
        changes=[
            audit.FieldChange("swap_request", str(swap.pk), "status", was, swap.status),
            *(extra or []),
        ],
    )
    return swap


def respond(*, user: User, swap_id: int, accept: bool) -> SwapRequest:
    """The colleague (or a planner or admin for them) accepts or declines."""
    with transaction.atomic():
        swap = _locked(user, swap_id)
        if swap.to_employee.user_id != user.pk and user.role not in ON_BEHALF_ROLES:
            raise not_found("No such shift swap.")
        if swap.status != SwapStatus.AWAITING_COLLEAGUE:
            raise _refuse(409, "swap.not_waiting_for_colleague", f"This swap is {swap.status}.")
        if not accept:
            return _move(user, swap, SwapStatus.DECLINED, Action.SWAP_DECLINED, colleague=True)
        _lock_people(swap.from_employee_id, swap.to_employee_id)
        _check_rules(user, *_current(swap))
        return _move(user, swap, SwapStatus.AWAITING_APPROVAL, Action.SWAP_ACCEPTED, colleague=True)


def decide(*, user: User, swap_id: int, approve: bool) -> SwapRequest:
    """A lead, planner or admin approves or rejects. Approving exchanges the two shifts."""
    with transaction.atomic():
        swap = _locked(user, swap_id)
        if user.pk in (swap.from_employee.user_id, swap.to_employee.user_id):
            raise _refuse(403, "swap.own_request", "Somebody else has to decide a swap you are in.")
        if swap.status != SwapStatus.AWAITING_APPROVAL:
            raise _refuse(409, "swap.not_waiting_for_approval", f"This swap is {swap.status}.")
        if not approve:
            return _move(user, swap, SwapStatus.REJECTED, Action.SWAP_REJECTED)
        _lock_people(swap.from_employee_id, swap.to_employee_id)
        first, second = _current(swap)
        _check_rules(user, first, second)
        moves = [
            audit.FieldChange(
                "assignment", f"{a.employee_id}:{a.day}", "shift", a.template.code, b.template.code
            )
            for a, b in ((first, second), (second, first))
        ]
        roster_services.exchange(first, second)
        return _move(user, swap, SwapStatus.APPROVED, Action.SWAP_APPROVED, extra=moves)


def cancel(*, user: User, swap_id: int) -> SwapRequest:
    """Whoever asked (or a planner or admin) withdraws a swap that is still open."""
    with transaction.atomic():
        swap = _locked(user, swap_id)
        asked = swap.from_employee.user_id == user.pk
        if not asked and user.role not in ON_BEHALF_ROLES:
            raise not_found("No such shift swap.")
        if swap.status not in OPEN_SWAP_STATUSES:
            raise _refuse(409, "swap.not_cancellable", f"A {swap.status} swap cannot be cancelled.")
        return _move(user, swap, SwapStatus.CANCELLED, Action.SWAP_CANCELLED)
