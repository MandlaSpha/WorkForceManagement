"""Reconciling overtime worked against overtime approved, and the rates and budget around it
(OT-03). Writes are one transaction with the audit event as the LAST write. No audit event holds a
money figure: they say that something changed.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found

from .models import OvertimeBudget, OvertimeRates, OvertimeRequest, OvertimeStatus
from .policy import DECIDE_ROLES, PAY_ROLES
from .services import MAX_MINUTES, _locked, _refuse

CENT = Decimal("0.01")
MAX_RATE = Decimal("100000")


def payable_minutes(request: OvertimeRequest) -> int | None:
    """Worked time is paid only as far as it was approved; None until it has been recorded."""
    if request.worked_minutes is None:
        return None
    return min(request.worked_minutes, request.minutes)


def worked_cost_of(request: OvertimeRequest, worked_minutes: int) -> Decimal | None:
    """The approved price in proportion to the time paid, so it is priced exactly as it was
    approved (same rate, same multiplier) and a later change of rules or pay cannot move it."""
    if request.approved_cost is None:
        return None
    paid = min(worked_minutes, request.minutes)
    return (request.approved_cost * paid / request.minutes).quantize(CENT, rounding=ROUND_HALF_UP)


def record_worked(*, user: User, request_id: int, worked_minutes: int) -> OvertimeRequest:
    """Record how long approved overtime really lasted, once its day has come. It can be corrected
    by recording again. Planner or admin, and never for oneself."""
    if not 0 <= worked_minutes <= MAX_MINUTES:
        raise _refuse(422, "overtime.worked_invalid", "Worked time is between 0 and 12 hours.")
    if user.role not in DECIDE_ROLES:
        raise not_found("No such overtime request.")
    with transaction.atomic():
        found = _locked(user, request_id)
        if found.employee.user_id == user.pk:
            raise _refuse(403, "overtime.own_request", "Somebody else has to record your overtime.")
        if found.status != OvertimeStatus.APPROVED:
            raise _refuse(409, "overtime.not_approved", "Only approved overtime can be reconciled.")
        if found.day > timezone.localdate():
            raise _refuse(409, "overtime.not_yet", "That overtime has not happened yet.")
        before = found.worked_minutes
        found.worked_minutes = worked_minutes
        found.worked_cost = worked_cost_of(found, worked_minutes)
        found.worked_by = user
        found.worked_at = timezone.now()
        found.save(update_fields=["worked_minutes", "worked_cost", "worked_by", "worked_at"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_WORKED_RECORDED,
            entity_type="overtime_request",
            entity_id=str(found.pk),
            subject_employee_id=found.employee_id,
            changes=[
                audit.FieldChange(
                    "overtime_request",
                    str(found.pk),
                    "worked_minutes",
                    None if before is None else str(before),
                    str(worked_minutes),
                )
            ],
        )
    return found


def set_standby_allowance(*, user: User, amount: Decimal) -> OvertimeRates:
    """The rand amount paid for each day on standby. Admin only."""
    if user.role not in PAY_ROLES:
        raise _refuse(403, "auth.forbidden", "Your role may not do this.")
    if not Decimal(0) <= amount <= MAX_RATE:
        raise ApiError(422, "rates.invalid", "Rates refused", "That is not a sensible amount.")
    with transaction.atomic():
        rates, _ = OvertimeRates.objects.select_for_update(no_key=True).get_or_create(pk=1)
        rates.standby_allowance = amount.quantize(CENT, rounding=ROUND_HALF_UP)
        rates.updated_by = user
        rates.save(update_fields=["standby_allowance", "updated_by"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_RATES_CHANGED,
            entity_type="overtime_rates",
            entity_id="1",
            changes=[
                audit.FieldChange("overtime_rates", "1", "standby_allowance", None, "changed")
            ],
        )
    return rates


def set_budget(*, user: User, month: date, amount: Decimal | None) -> OvertimeBudget | None:
    """What is set aside for a month (the first day of it); None removes it. Admin only."""
    if user.role not in PAY_ROLES:
        raise _refuse(403, "auth.forbidden", "Your role may not do this.")
    if amount is not None and not Decimal(0) <= amount <= Decimal("100000000"):
        raise ApiError(422, "budget.invalid", "Budget refused", "That is not a sensible amount.")
    first = month.replace(day=1)
    with transaction.atomic():
        existing = OvertimeBudget.objects.select_for_update(no_key=True).filter(month=first).first()
        result: OvertimeBudget | None
        if amount is None:
            if existing is not None:
                existing.delete()
            result = None
        else:
            result, _ = OvertimeBudget.objects.update_or_create(
                month=first,
                defaults={
                    "amount": amount.quantize(CENT, rounding=ROUND_HALF_UP),
                    "updated_by": user,
                },
            )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_BUDGET_CHANGED,
            entity_type="overtime_budget",
            entity_id=f"{first:%Y-%m}",
            changes=[
                audit.FieldChange(
                    "overtime_budget",
                    f"{first:%Y-%m}",
                    "budget",
                    "set" if existing else "none",
                    "set" if result else "none",
                )
            ],
        )
    return result
