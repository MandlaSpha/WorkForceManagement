"""Reading shift swaps. Everything starts from `Model.objects.for_user(user)`, except the board of
open requests, which is scoped to what the person could actually take and carries no names."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.scheduling import roster_services
from wfm.scheduling.models import Employee, ShiftAssignment

from . import selectors
from .models import OPEN_SWAP_STATUSES, SwapRequest

LOOKAHEAD_DAYS = 28  # how far ahead a swap can be asked for
MAX_BOARD = 30  # open requests looked at for one person: each is checked against the rules


def swaps(user: User, *, status: str | None = None) -> QuerySet[SwapRequest]:
    found = SwapRequest.objects.for_user(user).select_related(
        "queue", "from_employee", "to_employee", "from_template", "to_template"
    )
    if status:
        found = found.filter(status=status)
    return found.order_by("-from_day", "-id")


def swap_for(user: User, swap_id: int) -> SwapRequest:
    found: SwapRequest | None = swaps(user).filter(pk=swap_id).first()
    if found is None:
        raise not_found("No such shift swap.")
    return found


def has_open_swap(assignment: ShiftAssignment) -> bool:
    """Is this person's shift on this day already part of a swap that is still open?"""
    in_swap = Q(from_employee=assignment.employee, from_day=assignment.day) | Q(
        to_employee=assignment.employee, to_day=assignment.day
    )
    return SwapRequest.objects.filter(status__in=OPEN_SWAP_STATUSES).filter(in_swap).exists()


def my_shifts(user: User) -> list[ShiftAssignment]:
    """The signed-in person's coming shifts that could be given away: not already in a swap."""
    own = selectors.own_employee(user)
    if own is None:
        return []
    today = timezone.localdate()
    found = (
        ShiftAssignment.objects.filter(
            employee=own, day__gte=today, day__lte=today + timedelta(days=LOOKAHEAD_DAYS)
        )
        .select_related("template", "roster_week__queue", "employee")
        .order_by("day")
    )
    return [a for a in found if not has_open_swap(a)]


def posted_shift(swap: SwapRequest) -> ShiftAssignment | None:
    """The roster row the request was posted for, or None if the roster has moved on."""
    found: ShiftAssignment | None = (
        ShiftAssignment.objects.filter(
            employee_id=swap.from_employee_id, day=swap.from_day, template_id=swap.from_template_id
        )
        .select_related("template", "employee", "roster_week__queue")
        .first()
    )
    return found


def _open_for(employee: Employee) -> QuerySet[SwapRequest]:
    today = timezone.localdate()
    return (
        SwapRequest.objects.open_to(employee)
        .filter(from_day__gte=today, from_day__lte=today + timedelta(days=LOOKAHEAD_DAYS))
        .select_related("queue", "from_template")
        .order_by("from_day", "id")
        .distinct()
    )


def open_request(user: User, swap_id: int) -> SwapRequest | None:
    """An open request this person could take (on their queues, not their own), else None."""
    own = selectors.own_employee(user)
    return _open_for(own).filter(pk=swap_id).first() if own else None


def offers_for(user: User, swap: SwapRequest, mine: list[ShiftAssignment]) -> list[ShiftAssignment]:
    """Which of my shifts could be traded for this request without breaking a rule for either of
    us (rest, hours, leave, availability, one shift a day)."""
    posted = posted_shift(swap)
    if posted is None:
        return []
    return [
        m
        for m in mine
        if m.roster_week.queue_id == swap.queue_id
        and roster_services.exchange_refusal(user, posted, m) is None
    ]


def board(user: User) -> list[SwapRequest]:
    """Open requests I could take: on my queues, from someone else, and with at least one of my
    shifts that works. The poster is not named."""
    own = selectors.own_employee(user)
    if own is None:
        return []
    mine = my_shifts(user)
    found: list[SwapRequest] = []
    for swap in _open_for(own)[:MAX_BOARD]:
        posted = posted_shift(swap)
        if posted is None:
            continue
        if any(
            m.roster_week.queue_id == swap.queue_id
            and roster_services.exchange_refusal(user, posted, m) is None
            for m in mine
        ):
            found.append(swap)
    return found
