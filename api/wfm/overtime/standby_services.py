"""Standby rota and call-outs (OT-02).

A standby day carries an allowance fixed when it is booked. A call-out is the time worked while on
standby, recorded afterwards by somebody other than the person and priced like overtime at the
rules and pay in force. Writes are one transaction with the audit event as the LAST write; events
and notifications carry no money.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import not_found
from wfm.notifications import services as notifications
from wfm.people.models import LeaveRequest, LeaveStatus

from .models import EmployeePay, OvertimeRates, StandbyShift, StandbyStatus
from .policy import ALL_SCOPE_ROLES, DECIDE_ROLES
from .selectors import callout_price
from .services import (
    FURTHEST_AHEAD_DAYS,
    LATEST_PAST_DAYS,
    MAX_MINUTES,
    _employee_in_scope,
    _refuse,
)


def book(*, user: User, employee_id: int, day: date) -> StandbyShift:
    today = timezone.localdate()
    if (
        not today - timedelta(days=LATEST_PAST_DAYS)
        <= day
        <= today + timedelta(days=FURTHEST_AHEAD_DAYS)
    ):
        raise _refuse(422, "standby.date_out_of_range", "That day is too far back or ahead.")
    with transaction.atomic():
        employee = _employee_in_scope(user, employee_id)
        if (employee.start_date and day < employee.start_date) or (
            employee.end_date and day > employee.end_date
        ):
            raise _refuse(422, "standby.not_employed", "This person is not employed on that day.")
        if LeaveRequest.objects.filter(
            employee=employee, status=LeaveStatus.APPROVED, start_date__lte=day, end_date__gte=day
        ).exists():
            raise _refuse(409, "standby.on_leave", "This person is on approved leave that day.")
        rates = OvertimeRates.objects.filter(pk=1).first()
        try:
            with transaction.atomic():
                created = StandbyShift.objects.create(
                    employee=employee,
                    day=day,
                    allowance=rates.standby_allowance if rates else 0,
                    booked_by=user,
                )
        except IntegrityError as clash:
            raise _refuse(
                409, "standby.already_booked", "This person is already on standby that day."
            ) from clash
        if employee.user_id and employee.user_id != user.pk:
            notifications.notify(
                [employee.user],
                kind="standby.booked",
                message=f"You are on standby on {day:%a %d %b}.",
            )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.STANDBY_BOOKED,
            entity_type="standby_shift",
            entity_id=str(created.pk),
            subject_employee_id=employee.pk,
            changes=[audit.FieldChange("standby_shift", str(created.pk), "day", None, str(day))],
        )
    return created


def _locked(user: User, standby_id: int) -> StandbyShift:
    found: StandbyShift | None = (
        StandbyShift.objects.select_for_update(of=("self",), no_key=True)
        .for_user(user)
        .select_related("employee", "employee__user", "employee__manager")
        .filter(pk=standby_id)
        .first()
    )
    if found is None:
        raise not_found("No such standby.")
    return found


def cancel(*, user: User, standby_id: int) -> StandbyShift:
    """Take someone off standby before the day is over: whoever booked it, or a planner or admin."""
    with transaction.atomic():
        found = _locked(user, standby_id)
        if found.booked_by_id != user.pk and user.role not in ALL_SCOPE_ROLES:
            raise not_found("No such standby.")
        if found.status != StandbyStatus.BOOKED:
            raise _refuse(409, "standby.not_booked", f"This standby is already {found.status}.")
        if found.day < timezone.localdate() or found.call_out_minutes:
            raise _refuse(
                409,
                "standby.past",
                "Standby that has happened or had a call-out cannot be cancelled.",
            )
        found.status = StandbyStatus.CANCELLED
        found.save(update_fields=["status"])
        if found.employee.user_id and found.employee.user_id != user.pk:
            notifications.notify(
                [found.employee.user],
                kind="standby.cancelled",
                message=f"Your standby on {found.day:%a %d %b} was cancelled.",
            )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.STANDBY_CANCELLED,
            entity_type="standby_shift",
            entity_id=str(found.pk),
            subject_employee_id=found.employee_id,
            changes=[
                audit.FieldChange("standby_shift", str(found.pk), "status", "booked", "cancelled")
            ],
        )
    return found


def record_call_out(*, user: User, standby_id: int, minutes: int) -> StandbyShift:
    """Record the time worked while on standby (0 clears it), priced like overtime on that day.
    Planner or admin, once the day has come, and never for oneself."""
    if user.role not in DECIDE_ROLES:
        raise not_found("No such standby.")
    if not 0 <= minutes <= MAX_MINUTES:
        raise _refuse(422, "standby.call_out_invalid", "A call-out is between 0 and 12 hours.")
    with transaction.atomic():
        found = _locked(user, standby_id)
        if found.employee.user_id == user.pk:
            raise _refuse(403, "overtime.own_request", "Somebody else has to record your call-out.")
        if found.status != StandbyStatus.BOOKED:
            raise _refuse(409, "standby.not_booked", f"This standby is {found.status}.")
        if found.day > timezone.localdate():
            raise _refuse(409, "standby.not_yet", "That standby has not happened yet.")
        before = found.call_out_minutes
        found.call_out_minutes = minutes or None
        found.call_out_cost = (
            callout_price(
                found, minutes, EmployeePay.objects.filter(employee=found.employee).first()
            )
            if minutes
            else None
        )
        found.call_out_by = user if minutes else None
        found.save(update_fields=["call_out_minutes", "call_out_cost", "call_out_by"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.STANDBY_CALL_OUT_RECORDED,
            entity_type="standby_shift",
            entity_id=str(found.pk),
            subject_employee_id=found.employee_id,
            changes=[
                audit.FieldChange(
                    "standby_shift",
                    str(found.pk),
                    "call_out_minutes",
                    None if before is None else str(before),
                    str(minutes),
                )
            ],
        )
    return found
