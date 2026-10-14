"""Reading shift swaps. Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, QuerySet
from django.utils import timezone

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.scheduling import roster_services
from wfm.scheduling.models import ShiftAssignment

from . import selectors
from .models import OPEN_SWAP_STATUSES, SwapRequest

LOOKAHEAD_DAYS = 28  # how far ahead a swap can be asked for
MAX_OPTIONS = 40  # colleagues' shifts offered at once: each is checked against the rules


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


def options(user: User, give: ShiftAssignment) -> list[ShiftAssignment]:
    """Colleagues' shifts on the same queue that this shift could be swapped for: not in another
    swap, and passing every roster rule for both people. (A colleague's name and shift are shown
    to the people who work the same queue, as on any posted roster.)"""
    today = timezone.localdate()
    candidates = (
        ShiftAssignment.objects.filter(
            roster_week__queue=give.roster_week.queue,
            day__gte=today,
            day__lte=today + timedelta(days=LOOKAHEAD_DAYS),
        )
        .exclude(employee=give.employee)
        .select_related("template", "roster_week__queue", "employee")
        .order_by("day", "employee__name")
    )
    found: list[ShiftAssignment] = []
    for candidate in candidates:
        if has_open_swap(candidate):
            continue
        if roster_services.exchange_refusal(user, give, candidate) is None:
            found.append(candidate)
            if len(found) == MAX_OPTIONS:
                break
    return found
