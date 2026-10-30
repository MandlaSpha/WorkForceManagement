"""Posting, taking, deciding and cancelling shift swaps (SWP-01). Writes happen here, in one
transaction, with the audit event as the LAST write.

The flow: a person posts one of their shifts. A colleague on the same queue who could work it
takes it by offering one of their own shifts in return; the other agents never see who posted it
until it is matched. A lead, planner or admin then approves or rejects. The roster rules are
checked when it is taken and again when it is approved, because the roster can change in
between. Approving exchanges the two shifts; nobody approves a swap they are part of."""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.db.models.functions import Now
from django.utils import timezone

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.notifications import services as notifications
from wfm.scheduling import roster_services
from wfm.scheduling.models import Employee, EmployeeSkill, ShiftAssignment

from . import services as leave_services
from . import swap_selectors as selectors
from .models import OPEN_SWAP_STATUSES, SwapRequest, SwapStatus
from .policy import ON_BEHALF_ROLES


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Swap refused", detail)


def _lock_people(*ids: int) -> None:
    """Lock the people involved (in id order, so two swaps cannot wait on each other)."""
    list(Employee.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk"))


def _assignment(employee_id: int, day: date, template_id: int) -> ShiftAssignment | None:
    found: ShiftAssignment | None = (
        ShiftAssignment.objects.filter(employee_id=employee_id, day=day, template_id=template_id)
        .select_related("template", "employee", "roster_week__queue")
        .first()
    )
    return found


def _current(swap: SwapRequest) -> tuple[ShiftAssignment, ShiftAssignment]:
    """The two roster rows a matched swap is about, or a refusal when the roster has moved on."""
    if swap.to_employee_id is None or swap.to_day is None or swap.to_template_id is None:
        raise _refuse(409, "swap.not_matched", "Nobody has taken this request yet.")
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


def propose(*, user: User, give_id: int, employee_id: int | None = None) -> SwapRequest:
    """Post one of your shifts for a colleague on the same queue to take."""
    employee = leave_services.employee_for(user, employee_id, area="swap", refuse_as="Swap refused")
    with transaction.atomic():
        _lock_people(employee.pk)
        give = (
            ShiftAssignment.objects.select_related("template", "employee", "roster_week__queue")
            .filter(pk=give_id, employee=employee)
            .first()
        )
        if give is None:
            raise not_found("No such shift.")
        if give.day < timezone.localdate():
            raise _refuse(422, "swap.in_the_past", "A shift that has started cannot be swapped.")
        if selectors.has_open_swap(give):
            raise _refuse(409, "swap.already_open", "That shift is already in a swap.")
        swap = SwapRequest.objects.create(
            queue=give.roster_week.queue,
            from_employee=give.employee,
            from_day=give.day,
            from_template=give.template,
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


def take(
    *, user: User, swap_id: int, assignment_id: int, employee_id: int | None = None
) -> SwapRequest:
    """Take a posted request by offering one of your own shifts for it. The rules are checked for
    both people; a request on a queue you do not work is 'not found'."""
    employee = leave_services.employee_for(user, employee_id, area="swap", refuse_as="Swap refused")
    with transaction.atomic():
        swap: SwapRequest | None = (
            SwapRequest.objects.select_for_update(of=("self",), no_key=True)
            .select_related("queue", "from_employee", "from_template")
            .filter(pk=swap_id)
            .first()
        )
        if (
            swap is None
            or not EmployeeSkill.objects.filter(employee=employee, queue_id=swap.queue_id).exists()
        ):
            raise not_found("No such shift swap.")
        if swap.status != SwapStatus.OPEN:
            raise _refuse(409, "swap.not_open", "That request has already been taken.")
        if swap.from_employee_id == employee.pk:
            raise _refuse(422, "swap.same_person", "You cannot take your own request.")
        mine = (
            ShiftAssignment.objects.select_related("template", "employee", "roster_week__queue")
            .filter(pk=assignment_id, employee=employee)
            .first()
        )
        if mine is None:
            raise not_found("No such shift.")
        _lock_people(swap.from_employee_id, employee.pk)
        posted = _assignment(swap.from_employee_id, swap.from_day, swap.from_template_id)
        if posted is None:
            raise _refuse(409, "swap.changed", "The posted shift has changed since it was posted.")
        if mine.roster_week.queue_id != swap.queue_id:
            raise _refuse(422, "swap.different_queue", "Both shifts must be on the same queue.")
        if selectors.has_open_swap(mine):
            raise _refuse(409, "swap.already_open", "That shift is already in a swap.")
        _check_rules(user, posted, mine)
        swap.to_employee, swap.to_day, swap.to_template = mine.employee, mine.day, mine.template
        swap.status = SwapStatus.AWAITING_APPROVAL
        swap.colleague_answered_at = Now()
        swap.save(
            update_fields=[
                "to_employee",
                "to_day",
                "to_template",
                "status",
                "colleague_answered_at",
            ]
        )
        _tell_taken(swap, taker=employee)
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.SWAP_ACCEPTED,
            entity_type="swap_request",
            entity_id=str(swap.pk),
            subject_employee_id=employee.pk,
            changes=[
                audit.FieldChange(
                    "swap_request", str(swap.pk), "status", SwapStatus.OPEN, swap.status
                )
            ],
        )
    return selectors.swap_for(user, swap.pk)


def _shift_text(day: date, code: str) -> str:
    return f"{code} on {day:%a %d %b}"


def _tell_taken(swap: SwapRequest, taker: Employee) -> None:
    """The poster hears it was taken (not by whom), and the leads of either person are asked."""
    notifications.notify(
        [swap.from_employee.user],
        kind="swap.taken",
        message=(
            f"Your swap request for {_shift_text(swap.from_day, swap.from_template.code)} was "
            "taken. A lead decides next."
        ),
        link="/shift-swaps",
    )
    deciders = [
        e.manager.user
        for e in (swap.from_employee, taker)
        if e.manager is not None
        and e.manager.user_id not in (swap.from_employee.user_id, taker.user_id)
    ]
    notifications.notify(
        deciders,
        kind="swap.to_approve",
        message="A swap is waiting for your approval.",
        link="/shift-swaps",
    )


def _tell_decided(actor: User, swap: SwapRequest, what: str) -> None:
    """Each person hears the outcome about THEIR shift, not the other person's."""
    if swap.to_employee is None or swap.to_day is None or swap.to_template is None:
        return
    for person, day, code in (
        (swap.from_employee, swap.from_day, swap.from_template.code),
        (swap.to_employee, swap.to_day, swap.to_template.code),
    ):
        if person.user_id != actor.pk:
            notifications.notify(
                [person.user],
                kind=f"swap.{what}",
                message=f"Your swap for {_shift_text(day, code)} was {what}.",
                link="/shift-swaps",
            )


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
    extra: list[audit.FieldChange] | None = None,
    reason: str = "",
) -> SwapRequest:
    """Record the new status and audit it. This is the last write of the transaction."""
    was = swap.status
    swap.status = status
    swap.decided_by = user
    swap.decided_at = Now()
    swap.decision_reason = reason
    swap.save(update_fields=["status", "decided_by", "decided_at", "decision_reason"])
    swap.refresh_from_db()
    if reason:
        extra = [
            *(extra or []),
            audit.FieldChange("swap_request", str(swap.pk), "decision_reason", None, reason),
        ]
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


def decide(*, user: User, swap_id: int, approve: bool, reason: str = "") -> SwapRequest:
    """A lead, planner or admin approves or rejects a matched swap. Approving exchanges the two
    shifts."""
    with transaction.atomic():
        swap = _locked(user, swap_id)
        parties = (
            swap.from_employee.user_id,
            swap.to_employee.user_id if swap.to_employee else None,
        )
        if user.pk in parties:
            raise _refuse(403, "swap.own_request", "Somebody else has to decide a swap you are in.")
        if swap.status != SwapStatus.AWAITING_APPROVAL:
            raise _refuse(409, "swap.not_waiting_for_approval", f"This swap is {swap.status}.")
        if not approve:
            _tell_decided(user, swap, "rejected")
            return _move(
                user, swap, SwapStatus.REJECTED, Action.SWAP_REJECTED, reason=reason.strip()[:300]
            )
        _lock_people(swap.from_employee_id, swap.to_employee_id or 0)
        first, second = _current(swap)
        _check_rules(user, first, second)
        moves = [
            audit.FieldChange(
                "assignment", f"{a.employee_id}:{a.day}", "shift", a.template.code, b.template.code
            )
            for a, b in ((first, second), (second, first))
        ]
        roster_services.exchange(first, second)
        _tell_decided(user, swap, "approved")
        return _move(user, swap, SwapStatus.APPROVED, Action.SWAP_APPROVED, extra=moves)


def cancel(*, user: User, swap_id: int) -> SwapRequest:
    """Whoever posted it (or a planner or admin) withdraws a swap that is still open or waiting
    for approval."""
    with transaction.atomic():
        swap = _locked(user, swap_id)
        posted = swap.from_employee.user_id == user.pk
        if not posted and user.role not in ON_BEHALF_ROLES:
            raise not_found("No such shift swap.")
        if swap.status not in OPEN_SWAP_STATUSES:
            raise _refuse(409, "swap.not_cancellable", f"A {swap.status} swap cannot be cancelled.")
        return _move(user, swap, SwapStatus.CANCELLED, Action.SWAP_CANCELLED)
