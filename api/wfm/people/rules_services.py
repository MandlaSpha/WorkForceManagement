"""Blackout periods and the limit on people away at once (LV-04).

Both apply only to leave of a `restricted` kind: sick, family responsibility and maternity leave
cannot wait, so they are never refused for these. Writes happen here with the audit event as the
LAST write of the transaction; only an admin (the customer's) sets the rules."""

from __future__ import annotations

from datetime import date, timedelta

from django.db import transaction
from wfm_engine import leave as rules

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.scheduling.models import Employee

from .calendar import public_holidays
from .models import LeaveBlackout, LeaveLimit, LeaveRequest, LeaveStatus, LeaveType

MAX_BLACKOUT_DAYS = 366


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Leave refused", detail)


def _invalid(code: str, detail: str) -> ApiError:
    return ApiError(422, code, "Rule refused", detail)


def limit() -> LeaveLimit:
    row: LeaveLimit = LeaveLimit.objects.get_or_create(pk=1)[0]
    return row


def check_blackout(leave_type: LeaveType, start: date, end: date) -> None:
    if not leave_type.restricted:
        return
    for blackout in LeaveBlackout.objects.filter(date_from__lte=end, date_to__gte=start):
        raise _refuse(
            409,
            "leave.blackout",
            f"{blackout.name} ({blackout.date_from} to {blackout.date_to}) is a blackout "
            f"period: {leave_type.name} cannot be asked for then.",
        )


def check_concurrency(employee: Employee, leave_type: LeaveType, start: date, end: date) -> None:
    """Refuse when one more person away would pass the limit on any working day of the leave.
    Counts approved leave of restricted kinds for everybody else."""
    if not leave_type.restricted:
        return
    most = limit().max_concurrent
    if most is None:
        return
    days = rules.working_day_list(start, end, public_holidays(start, end))
    wanted = set(days)
    away: dict[date, int] = {}
    others = LeaveRequest.objects.filter(
        status=LeaveStatus.APPROVED,
        leave_type__restricted=True,
        start_date__lte=end,
        end_date__gte=start,
    ).exclude(employee=employee)
    for first, last in others.values_list("start_date", "end_date"):
        day = max(first, start)
        while day <= min(last, end):
            if day in wanted:
                away[day] = away.get(day, 0) + 1
            day += timedelta(days=1)
    over = rules.first_day_over_limit(days, away, most)
    if over is not None:
        raise _refuse(
            409,
            "leave.too_many_away",
            f"{away.get(over, 0)} people are already away on {over}; at most {most} may be "
            "away at once.",
        )


def lock_limit() -> None:
    """Hold the limit row while an approval is checked and written, so two approvals made at the
    same moment cannot both pass the check."""
    limit()
    LeaveLimit.objects.select_for_update(no_key=True).get(pk=1)


def add_blackout(*, user: User, name: str, date_from: date, date_to: date) -> LeaveBlackout:
    name = name.strip()
    if not 1 <= len(name) <= 60:
        raise _invalid(
            "blackout.name_invalid", "A blackout period needs a name of 1 to 60 letters."
        )
    if date_to < date_from:
        raise _invalid("blackout.dates_invalid", "The last day is before the first.")
    if (date_to - date_from).days + 1 > MAX_BLACKOUT_DAYS:
        raise _invalid(
            "blackout.too_long", f"A blackout period is at most {MAX_BLACKOUT_DAYS} days."
        )
    with transaction.atomic():
        found = LeaveBlackout.objects.create(
            name=name, date_from=date_from, date_to=date_to, created_by=user
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.LEAVE_BLACKOUT_ADDED,
            entity_type="leave_blackout",
            entity_id=str(found.pk),
            changes=[
                audit.FieldChange(
                    "leave_blackout", str(found.pk), "period", None, f"{date_from}..{date_to}"
                )
            ],
        )
    return found


def remove_blackout(*, user: User, blackout_id: int) -> None:
    with transaction.atomic():
        found = LeaveBlackout.objects.select_for_update(no_key=True).filter(pk=blackout_id).first()
        if found is None:
            raise not_found("No such blackout period.")
        period, pk = f"{found.date_from}..{found.date_to}", found.pk
        found.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.LEAVE_BLACKOUT_REMOVED,
            entity_type="leave_blackout",
            entity_id=str(pk),
            changes=[audit.FieldChange("leave_blackout", str(pk), "period", period, None)],
        )


def set_limit(*, user: User, max_concurrent: int | None) -> LeaveLimit:
    if max_concurrent is not None and not 1 <= max_concurrent <= 1000:
        raise _invalid(
            "limit.invalid", "The most away at once is 1 to 1000, or blank for no limit."
        )
    with transaction.atomic():
        lock_limit()
        row = LeaveLimit.objects.get(pk=1)
        was = row.max_concurrent
        row.max_concurrent, row.updated_by = max_concurrent, user
        row.save(update_fields=["max_concurrent", "updated_by"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.LEAVE_LIMIT_CHANGED,
            entity_type="leave_limit",
            entity_id="1",
            changes=[
                audit.FieldChange(
                    "leave_limit",
                    "1",
                    "max_concurrent",
                    None if was is None else str(was),
                    None if max_concurrent is None else str(max_concurrent),
                )
            ],
        )
    return row
