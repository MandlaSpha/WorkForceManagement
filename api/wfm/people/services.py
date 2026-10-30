"""Applying for, deciding and cancelling leave. Writes happen here, in one transaction, with the
audit event as the LAST write (hard rule: the audit insert holds the audit-chain lock until
commit)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.functions import Now
from django.utils import timezone
from wfm_engine import leave as rules

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.notifications import services as notifications
from wfm.scheduling.models import Employee, RosterWeek, ShiftAssignment

from . import rules_services, selectors
from .calendar import public_holidays
from .models import LeaveRequest, LeaveStatus, LeaveType
from .policy import APPROVE_ROLES, ON_BEHALF_ROLES

MAX_SPAN_DAYS = 90
LATEST_PAST_DAYS = 30  # sick leave is often written up after the fact; not months later
FURTHEST_AHEAD_DAYS = 730


@dataclass(frozen=True, slots=True)
class Decision:
    request: LeaveRequest
    cleared: int = 0
    restored: int = 0
    not_restored: int = 0


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Leave refused", detail)


def apply(
    *, user: User, leave_type_id: int, start: date, end: date, employee_id: int | None = None
) -> LeaveRequest:
    employee = employee_for(user, employee_id)
    leave_type: LeaveType | None = LeaveType.objects.for_user(user).filter(pk=leave_type_id).first()
    if leave_type is None:
        raise not_found("No such kind of leave.")

    today = timezone.localdate()
    if end < start:
        raise _refuse(422, "leave.range_invalid", "The last day is before the first.")
    if (end - start).days + 1 > MAX_SPAN_DAYS:
        raise _refuse(422, "leave.too_long", f"Ask for at most {MAX_SPAN_DAYS} days at a time.")
    if start < today - timedelta(days=LATEST_PAST_DAYS):
        raise _refuse(
            422, "leave.too_far_back", f"Leave can be asked for up to {LATEST_PAST_DAYS} days back."
        )
    if start > today + timedelta(days=FURTHEST_AHEAD_DAYS):
        raise _refuse(422, "leave.too_far_ahead", "That is too far ahead to plan.")
    if (employee.start_date and start < employee.start_date) or (
        employee.end_date and end > employee.end_date
    ):
        raise _refuse(422, "leave.not_employed", "The leave is outside the person's employment.")

    by_year = rules.working_days_by_year(start, end, public_holidays(start, end))
    days = sum(by_year.values())
    if days == 0:
        raise _refuse(
            422, "leave.no_working_days", "Those dates are weekends and public holidays only."
        )

    with transaction.atomic():
        # Lock the person so two requests made at once cannot both pass the checks below.
        Employee.objects.select_for_update(no_key=True).filter(pk=employee.pk).get()
        _check_overlap(employee, start, end)
        _check_balance(employee, leave_type, by_year)
        rules_services.check_blackout(leave_type, start, end)
        rules_services.check_concurrency(employee, leave_type, start, end)
        request = LeaveRequest.objects.create(
            employee=employee,
            leave_type=leave_type,
            start_date=start,
            end_date=end,
            days=days,
            days_by_year={str(year): n for year, n in by_year.items()},
            requested_by=user,
        )
        if employee.manager is not None and employee.manager.user_id != user.pk:
            notifications.notify(
                [employee.manager.user],
                kind="leave.requested",
                message="Leave is waiting for your decision.",
                link="/leave",
            )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.LEAVE_REQUESTED,
            entity_type="leave_request",
            entity_id=str(request.pk),
            changes=[
                audit.FieldChange("leave_request", str(request.pk), "type", None, leave_type.code),
                audit.FieldChange(
                    "leave_request", str(request.pk), "range", None, f"{start}..{end}"
                ),
                audit.FieldChange("leave_request", str(request.pk), "days", None, str(days)),
            ],
        )
    return request


def decide(*, user: User, request_id: int, approve: bool, reason: str = "") -> Decision:
    """Approve or reject a pending request. Approving writes the leave into the schedule: the
    person's shifts on those days come off the roster (the leave wins, even in a published week),
    and coverage shows the gap. Nobody decides their own request."""
    with transaction.atomic():
        leave = _locked(user, request_id)
        if leave.employee.user_id == user.pk:
            raise _refuse(403, "leave.own_request", "Somebody else has to decide your leave.")
        if leave.status != LeaveStatus.PENDING:
            raise _refuse(409, "leave.not_pending", f"This request is already {leave.status}.")

        cleared: list[dict[str, object]] = []
        if approve:
            # Two approvals at the same moment must not both squeeze under the limit.
            rules_services.lock_limit()
            rules_services.check_concurrency(
                leave.employee, leave.leave_type, leave.start_date, leave.end_date
            )
            assignments = ShiftAssignment.objects.filter(
                employee=leave.employee, day__gte=leave.start_date, day__lte=leave.end_date
            ).select_related("roster_week")
            cleared = [
                {
                    "queueId": a.roster_week.queue_id,
                    "day": a.day.isoformat(),
                    "templateId": a.template_id,
                }
                for a in assignments
            ]
            assignments.delete()
        leave.status = LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED
        leave.decided_by = user
        leave.decided_at = Now()
        leave.cleared_shifts = cleared
        leave.decision_reason = "" if approve else reason.strip()[:300]
        leave.save(
            update_fields=[
                "status",
                "decided_by",
                "decided_at",
                "cleared_shifts",
                "decision_reason",
            ]
        )
        leave.refresh_from_db()
        _tell_about(user, leave, "approved" if approve else "rejected")
        changes = [
            audit.FieldChange("leave_request", str(leave.pk), "status", "pending", leave.status)
        ]
        if leave.decision_reason:
            changes.append(
                audit.FieldChange(
                    "leave_request", str(leave.pk), "decision_reason", None, leave.decision_reason
                )
            )
        if approve:
            changes.append(
                audit.FieldChange(
                    "leave_request", str(leave.pk), "shifts_cleared", None, str(len(cleared))
                )
            )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.LEAVE_APPROVED if approve else Action.LEAVE_REJECTED,
            entity_type="leave_request",
            entity_id=str(leave.pk),
            changes=changes,
        )
    return Decision(leave, cleared=len(cleared))


def cancel(*, user: User, request_id: int) -> Decision:
    """The person (or a planner or admin) withdraws a request. Cancelling approved leave puts the
    shifts it took off the roster back where the person is still free; any that cannot be put back
    are counted so the planner knows to look."""
    with transaction.atomic():
        leave = _locked(user, request_id)
        mine = leave.employee.user_id == user.pk
        if not mine and user.role not in ON_BEHALF_ROLES:
            raise not_found("No such leave request.")
        if leave.status not in (LeaveStatus.PENDING, LeaveStatus.APPROVED):
            raise _refuse(
                409, "leave.not_cancellable", f"A {leave.status} request cannot be cancelled."
            )
        was = leave.status
        restored = skipped = 0
        if was == LeaveStatus.APPROVED:
            if leave.end_date < timezone.localdate():
                raise _refuse(409, "leave.already_taken", "That leave has already been taken.")
            restored, skipped = _restore(leave)
        leave.status = LeaveStatus.CANCELLED
        leave.decided_by = user
        leave.decided_at = Now()
        leave.save(update_fields=["status", "decided_by", "decided_at"])
        leave.refresh_from_db()
        _tell_about(user, leave, "cancelled")
        changes = [audit.FieldChange("leave_request", str(leave.pk), "status", was, "cancelled")]
        if was == LeaveStatus.APPROVED:
            changes += [
                audit.FieldChange(
                    "leave_request", str(leave.pk), "shifts_restored", None, str(restored)
                ),
                audit.FieldChange(
                    "leave_request", str(leave.pk), "shifts_not_restored", None, str(skipped)
                ),
            ]
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.LEAVE_CANCELLED,
            entity_type="leave_request",
            entity_id=str(leave.pk),
            changes=changes,
        )
    return Decision(leave, restored=restored, not_restored=skipped)


def _tell_about(actor: User, leave: LeaveRequest, what: str) -> None:
    """Tell the person their request was decided or cancelled by somebody else. The message
    names the kind and the days, never who decided or why."""
    if leave.employee.user is None or leave.employee.user_id == actor.pk:
        return
    span = (
        f"{leave.start_date:%d %b}"
        if leave.start_date == leave.end_date
        else f"{leave.start_date:%d %b} to {leave.end_date:%d %b}"
    )
    notifications.notify(
        [leave.employee.user],
        kind=f"leave.{what}",
        message=f"Your {leave.leave_type.name.lower()} request for {span} was {what}.",
        link="/leave",
    )


def set_entitlement(*, user: User, type_id: int, days: Decimal | None) -> LeaveType:
    """Set a leave type's days a year (none: no limit) and mark it confirmed."""
    if days is not None and not Decimal(0) <= days <= Decimal(366):
        raise _refuse(422, "leave.entitlement_invalid", "Days a year is between 0 and 366.")
    with transaction.atomic():
        leave_type: LeaveType | None = (
            LeaveType.objects.select_for_update(no_key=True)
            .for_user(user)
            .filter(pk=type_id)
            .first()
        )
        if leave_type is None:
            raise not_found("No such kind of leave.")
        changes = []
        if leave_type.days_per_year != days:
            changes.append(
                audit.FieldChange(
                    "leave_type",
                    str(leave_type.pk),
                    "days_per_year",
                    None if leave_type.days_per_year is None else str(leave_type.days_per_year),
                    None if days is None else str(days),
                )
            )
        if not leave_type.confirmed:
            changes.append(
                audit.FieldChange("leave_type", str(leave_type.pk), "confirmed", "False", "True")
            )
        leave_type.days_per_year = days
        leave_type.confirmed = True
        leave_type.save(update_fields=["days_per_year", "confirmed"])
        leave_type.refresh_from_db()
        if changes:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.LEAVE_ENTITLEMENT_CHANGED,
                entity_type="leave_type",
                entity_id=str(leave_type.pk),
                changes=changes,
            )
    return leave_type


# --- helpers ---------------------------------------------------------------------------------


def employee_for(
    user: User, employee_id: int | None, *, area: str = "leave", refuse_as: str = "Leave refused"
) -> Employee:
    """Whose leave this is: the signed-in person's own, or (planner and admin only) someone's."""
    if employee_id is None:
        own = selectors.own_employee(user)
        if own is None:
            raise ApiError(
                422,
                f"{area}.no_employee_record",
                refuse_as,
                "You are not on the employee list yet, so there is nobody to act for.",
            )
        return own
    employee: Employee | None = Employee.objects.filter(pk=employee_id).first()
    if employee is None or (employee.user_id != user.pk and user.role not in ON_BEHALF_ROLES):
        raise not_found("No such employee.")
    return employee


def _locked(user: User, request_id: int) -> LeaveRequest:
    found: LeaveRequest | None = (
        LeaveRequest.objects.select_for_update(of=("self",), no_key=True)
        .for_user(user)
        .select_related("employee", "leave_type")
        .filter(pk=request_id)
        .first()
    )
    if found is None:
        raise not_found("No such leave request.")
    if user.role not in APPROVE_ROLES and found.employee.user_id != user.pk:
        raise not_found("No such leave request.")
    return found


def _check_overlap(employee: Employee, start: date, end: date) -> None:
    for first, last in LeaveRequest.objects.filter(
        employee=employee, status__in=(LeaveStatus.PENDING, LeaveStatus.APPROVED)
    ).values_list("start_date", "end_date"):
        if rules.overlaps((first, last), (start, end)):
            raise _refuse(
                409,
                "leave.overlaps",
                f"There is already leave asked for or approved from {first} to {last}.",
            )


def _check_balance(employee: Employee, leave_type: LeaveType, by_year: dict[int, int]) -> None:
    for year, days in by_year.items():
        left = selectors.balance(employee, leave_type, year).available
        if left is not None and Decimal(days) > left:
            raise _refuse(
                422,
                "leave.insufficient_balance",
                f"{leave_type.name} has {left} days left in {year}; {days} were asked for.",
            )


def _restore(leave: LeaveRequest) -> tuple[int, int]:
    """Put back the shifts approving took off, where the person is still free that day."""
    restored = skipped = 0
    for shift in leave.cleared_shifts:
        day = date.fromisoformat(shift["day"])
        if ShiftAssignment.objects.filter(employee=leave.employee, day=day).exists():
            skipped += 1
            continue
        week, _ = RosterWeek.objects.get_or_create(
            queue_id=shift["queueId"], week_start=day - timedelta(days=day.weekday())
        )
        ShiftAssignment.objects.create(
            roster_week=week, employee=leave.employee, day=day, template_id=shift["templateId"]
        )
        restored += 1
    return restored, skipped
