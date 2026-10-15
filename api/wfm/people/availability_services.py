"""Declaring and removing availability windows. Writes happen here with the audit event as the
LAST write of the transaction. A person manages their own; a planner or admin can for anyone."""

from __future__ import annotations

from datetime import time

from django.db import transaction
from wfm_engine import availability as rules

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.scheduling.models import Employee

from . import services as leave_services
from .models import Availability, AvailabilityKind
from .policy import ON_BEHALF_ROLES


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Availability refused", detail)


def _label(w: Availability) -> str:
    return f"{w.kind} {w.weekday} {w.start_time:%H:%M}-{w.end_time:%H:%M}"


def add_window(
    *,
    user: User,
    weekday: int,
    start: time,
    end: time,
    kind: str,
    employee_id: int | None = None,
) -> Availability:
    employee = leave_services.employee_for(
        user, employee_id, area="availability", refuse_as="Availability refused"
    )
    if kind not in AvailabilityKind.values:
        raise _refuse(422, "availability.kind_invalid", "Choose 'cannot work' or 'would rather'.")
    try:
        new = rules.window_of(weekday, start, end)
    except ValueError as problem:
        raise _refuse(422, "availability.window_invalid", str(problem)) from None
    with transaction.atomic():
        Employee.objects.select_for_update(no_key=True).filter(pk=employee.pk).first()
        for other in Availability.objects.filter(employee=employee, weekday=weekday):
            if rules.overlap(new, rules.window_of(other.weekday, other.start_time, other.end_time)):
                raise _refuse(
                    409,
                    "availability.overlaps",
                    "That overlaps a window already declared on that day.",
                )
        window = Availability.objects.create(
            employee=employee,
            weekday=weekday,
            start_time=start,
            end_time=end,
            kind=kind,
            created_by=user,
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.AVAILABILITY_ADDED,
            entity_type="availability",
            entity_id=str(window.pk),
            subject_employee_id=employee.pk,
            changes=[
                audit.FieldChange("availability", str(window.pk), "window", None, _label(window))
            ],
        )
    return window


def remove_window(*, user: User, window_id: int) -> None:
    with transaction.atomic():
        window = (
            Availability.objects.select_for_update(of=("self",), no_key=True)
            .for_user(user)
            .select_related("employee")
            .filter(pk=window_id)
            .first()
        )
        if window is None:
            raise not_found("No such availability window.")
        if window.employee.user_id != user.pk and user.role not in ON_BEHALF_ROLES:
            raise not_found("No such availability window.")
        label, employee_id, pk = _label(window), window.employee_id, window.pk
        window.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.AVAILABILITY_REMOVED,
            entity_type="availability",
            entity_id=str(pk),
            subject_employee_id=employee_id,
            changes=[audit.FieldChange("availability", str(pk), "window", label, None)],
        )
