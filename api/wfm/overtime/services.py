"""Asking for, deciding and cancelling overtime, and setting the pay it is priced from (OT-01).

Writes happen here, in one transaction, with the audit event as the LAST write. A request is
checked against the same rules the roster keeps (rest between shifts, days in a row, the weekly
cap, leave) when it is asked for and again when it is approved, with the employee row locked, so
two requests made at the same moment cannot each be fine alone and wrong together.

A salary is never written to the audit trail, a log or a notification.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models.functions import Now
from django.utils import timezone
from wfm_engine.roster import breaks_rest_rule, consecutive_run, shift_span

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.notifications import services as notifications
from wfm.people.models import LeaveRequest, LeaveStatus
from wfm.scheduling.models import Employee, ShiftAssignment
from wfm.scheduling.selectors import rules_on

from .models import EmployeePay, OvertimeRequest, OvertimeStatus
from .policy import ALL_SCOPE_ROLES, DECIDE_ROLES, REQUEST_ROLES
from .selectors import price_of

LATEST_PAST_DAYS = 31  # overtime is often written up after the fact; not months later
FURTHEST_AHEAD_DAYS = 366
MAX_MINUTES = 720
MAX_REASON = 200
MAX_SALARY = Decimal("1000000")
LOOK_AROUND_DAYS = 14  # work this far either side can reach every rule: rest, a run of days, a week


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Overtime refused", detail)


def _span(day: date, start: time, end: time) -> tuple[datetime, datetime]:
    return datetime.combine(day, start), datetime.combine(day, end)


def _employee_in_scope(user: User, employee_id: int) -> Employee:
    """The person this is for, locked: anybody for a planner or admin, only their own team for a
    lead. Anyone else, and anyone outside the team, is a 404."""
    found: Employee | None = (
        Employee.objects.select_for_update(no_key=True, of=("self",))
        .select_related("manager")
        .filter(pk=employee_id)
        .first()
    )
    if found is None or user.role not in REQUEST_ROLES:
        raise not_found("No such employee.")
    if user.role == Role.LEAD and (found.manager is None or found.manager.user_id != user.pk):
        raise not_found("No such employee.")
    return found


def _check(
    employee: Employee,
    day: date,
    start: time,
    end: time,
    minutes: int,
    ignoring: int | None = None,
) -> None:
    """Every rule overtime must keep, against the roster and other overtime of the same person."""
    if (employee.start_date and day < employee.start_date) or (
        employee.end_date and day > employee.end_date
    ):
        raise _refuse(422, "overtime.not_employed", "This person is not employed on that day.")
    if LeaveRequest.objects.filter(
        employee=employee, status=LeaveStatus.APPROVED, start_date__lte=day, end_date__gte=day
    ).exists():
        raise _refuse(409, "overtime.on_leave", "This person is on approved leave that day.")

    rules = rules_on(day)
    around = {
        "day__gte": day - timedelta(days=LOOK_AROUND_DAYS),
        "day__lte": day + timedelta(days=LOOK_AROUND_DAYS),
    }
    others = OvertimeRequest.objects.filter(
        employee=employee,
        status__in=(OvertimeStatus.PENDING, OvertimeStatus.APPROVED),
        **around,
    )
    if ignoring is not None:
        others = others.exclude(pk=ignoring)
    others_list = list(others)
    shifts = list(
        ShiftAssignment.objects.filter(employee=employee, **around).select_related("template")
    )

    # Work on the same day is one stretch with the overtime: it may sit beside a shift (that is what
    # overtime usually is) but not on top of it. Work on other days needs the rest between.
    today_spans = [shift_span(a.day, a.template.start_time, a.template.end_time) for a in shifts]
    today_spans += [_span(o.day, o.start_time, o.end_time) for o in others_list]
    began, finished = _span(day, start, end)
    if any(a < finished and began < b for a, b in today_spans if a.date() == day):
        raise _refuse(409, "overtime.overlap", "This overlaps a shift or other overtime that day.")
    spans = [span for span in today_spans if span[0].date() != day]
    if breaks_rest_rule(spans, (began, finished), min_hours=rules.min_rest_hours):
        raise _refuse(
            409,
            "overtime.rest_period",
            f"This would leave less than {rules.min_rest_hours} hours of rest.",
        )
    worked = {a.day for a in shifts} | {o.day for o in others_list}
    if consecutive_run(worked - {day}, day) > rules.max_consecutive_days:
        raise _refuse(
            409,
            "overtime.too_many_days",
            f"This would be more than {rules.max_consecutive_days} days in a row.",
        )
    if rules.max_weekly_hours is not None:
        monday = day - timedelta(days=day.weekday())
        sunday = monday + timedelta(days=6)
        week_minutes = sum(
            a.template.paid_minutes for a in shifts if monday <= a.day <= sunday
        ) + sum(o.minutes for o in others_list if monday <= o.day <= sunday)
        if week_minutes + minutes > rules.max_weekly_hours * 60:
            raise _refuse(
                409,
                "overtime.over_weekly_cap",
                f"This would take the person over the {rules.max_weekly_hours} hour weekly limit.",
            )


def _tell_approvers(actor: User) -> None:
    approvers = User.objects.filter(role__in=DECIDE_ROLES, is_active=True).exclude(pk=actor.pk)
    notifications.notify(
        approvers,
        kind="overtime.requested",
        message="An overtime request is waiting for approval.",
        link="/overtime",
    )


def _tell_employee(actor: User, request: OvertimeRequest, what: str) -> None:
    """Tell the person it concerns. The message names the day, never who decided or what it pays."""
    user = request.employee.user
    if user is None or user.pk == actor.pk:
        return
    notifications.notify(
        [user],
        kind=f"overtime.{what}",
        message=f"Your overtime on {request.day:%a %d %b} was {what}.",
        # No link: an agent has no overtime screen to go to.
    )


def request_overtime(
    *,
    user: User,
    employee_id: int,
    day: date,
    start_time: time,
    end_time: time,
    reason: str = "",
) -> OvertimeRequest:
    today = timezone.localdate()
    earliest, latest = (
        today - timedelta(days=LATEST_PAST_DAYS),
        today + timedelta(days=FURTHEST_AHEAD_DAYS),
    )
    if not earliest <= day <= latest:
        raise _refuse(422, "overtime.date_out_of_range", "That day is too far back or ahead.")
    if end_time <= start_time:
        raise _refuse(422, "overtime.times_invalid", "The end must be after the start.")
    began, finished = _span(day, start_time, end_time)
    minutes = int((finished - began).total_seconds() // 60)
    if minutes > MAX_MINUTES:
        raise _refuse(422, "overtime.too_long", "One request is at most 12 hours.")
    reason = reason.strip()
    if len(reason) > MAX_REASON:
        raise _refuse(422, "overtime.reason_too_long", f"Keep the reason to {MAX_REASON} letters.")
    with transaction.atomic():
        employee = _employee_in_scope(user, employee_id)
        _check(employee, day, start_time, end_time, minutes)
        created = OvertimeRequest.objects.create(
            employee=employee,
            day=day,
            start_time=start_time,
            end_time=end_time,
            minutes=minutes,
            reason=reason,
            requested_by=user,
        )
        _tell_approvers(user)
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_REQUESTED,
            entity_type="overtime_request",
            entity_id=str(created.pk),
            subject_employee_id=employee.pk,
            changes=[
                audit.FieldChange(
                    "overtime_request", str(created.pk), "status", None, OvertimeStatus.PENDING
                ),
                audit.FieldChange(
                    "overtime_request", str(created.pk), "minutes", None, str(minutes)
                ),
            ],
        )
    return created


def _locked(user: User, request_id: int) -> OvertimeRequest:
    found: OvertimeRequest | None = (
        OvertimeRequest.objects.select_for_update(of=("self",), no_key=True)
        .for_user(user)
        .select_related("employee", "employee__user", "employee__manager")
        .filter(pk=request_id)
        .first()
    )
    if found is None:
        raise not_found("No such overtime request.")
    return found


def decide(*, user: User, request_id: int, approve: bool) -> OvertimeRequest:
    """Approve or reject a waiting request. Approving checks the rules again, so leave approved or
    a shift rostered since it was asked for cannot slip past, and records the price it was approved
    at. Nobody decides overtime for themselves."""
    if user.role not in DECIDE_ROLES:
        raise not_found("No such overtime request.")
    with transaction.atomic():
        found = _locked(user, request_id)
        if found.employee.user_id == user.pk:
            raise _refuse(403, "overtime.own_request", "Somebody else has to decide your overtime.")
        if found.status != OvertimeStatus.PENDING:
            raise _refuse(409, "overtime.not_pending", f"This request is already {found.status}.")
        if approve:
            Employee.objects.select_for_update(no_key=True).get(pk=found.employee_id)
            _check(
                found.employee, found.day, found.start_time, found.end_time, found.minutes, found.pk
            )
            found.approved_cost = price_of(
                found, EmployeePay.objects.filter(employee=found.employee).first()
            )
        found.status = OvertimeStatus.APPROVED if approve else OvertimeStatus.REJECTED
        found.decided_by = user
        found.decided_at = Now()
        found.save(update_fields=["status", "decided_by", "decided_at", "approved_cost"])
        found.refresh_from_db()
        _tell_employee(user, found, found.status)
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_APPROVED if approve else Action.OVERTIME_REJECTED,
            entity_type="overtime_request",
            entity_id=str(found.pk),
            subject_employee_id=found.employee_id,
            changes=[
                audit.FieldChange(
                    "overtime_request", str(found.pk), "status", "pending", found.status
                )
            ],
        )
    return found


def cancel(*, user: User, request_id: int) -> OvertimeRequest:
    """Take back a waiting or approved request that has not happened yet: whoever asked for it, or
    a planner or admin."""
    with transaction.atomic():
        found = _locked(user, request_id)
        if found.requested_by_id != user.pk and user.role not in ALL_SCOPE_ROLES:
            raise not_found("No such overtime request.")
        if found.status not in (OvertimeStatus.PENDING, OvertimeStatus.APPROVED):
            raise _refuse(
                409, "overtime.not_cancellable", f"This request is already {found.status}."
            )
        if found.day < timezone.localdate():
            raise _refuse(409, "overtime.past", "Overtime that has happened cannot be cancelled.")
        before = found.status
        found.status = OvertimeStatus.CANCELLED
        found.approved_cost = None
        found.save(update_fields=["status", "approved_cost"])
        _tell_employee(user, found, "cancelled")
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_CANCELLED,
            entity_type="overtime_request",
            entity_id=str(found.pk),
            subject_employee_id=found.employee_id,
            changes=[
                audit.FieldChange("overtime_request", str(found.pk), "status", before, "cancelled")
            ],
        )
    return found


def set_pay(
    *,
    user: User,
    employee_id: int,
    monthly_salary: Decimal | None,
    works_sundays: bool,
    clear: bool = False,
) -> EmployeePay | None:
    """Set the pay overtime is priced from, or remove it (`clear`). With no new salary the one on
    file is kept and only the Sunday flag changes: a salary is never read back, so it cannot be
    re-typed just to change something else. Admin only. The audit event says that pay changed, never
    what it is."""
    if monthly_salary is not None and not Decimal(0) < monthly_salary <= MAX_SALARY:
        raise ApiError(
            422, "pay.invalid", "Pay refused", "The monthly salary is not a sensible amount."
        )
    with transaction.atomic():
        employee = Employee.objects.select_for_update(no_key=True).filter(pk=employee_id).first()
        if employee is None:
            raise not_found("No such employee.")
        existing = EmployeePay.objects.filter(employee=employee).first()
        result: EmployeePay | None = existing
        if clear:
            if existing is not None:
                existing.delete()
            result = None
        elif monthly_salary is None:
            if existing is None:
                raise ApiError(
                    422, "pay.no_salary", "Pay refused", "There is no salary on file yet to change."
                )
            existing.ordinarily_works_sundays = works_sundays
            existing.updated_by = user
            existing.save(update_fields=["ordinarily_works_sundays", "updated_by"])
        else:
            result, _ = EmployeePay.objects.update_or_create(
                employee=employee,
                defaults={
                    "monthly_salary": monthly_salary,
                    "ordinarily_works_sundays": works_sundays,
                    "updated_by": user,
                },
            )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.OVERTIME_PAY_CHANGED,
            entity_type="employee",
            entity_id=str(employee.pk),
            subject_employee_id=employee.pk,
            changes=[
                audit.FieldChange(
                    "employee_pay",
                    str(employee.pk),
                    "pay",
                    "on file" if existing else "none",
                    "on file" if result else "none",
                )
            ],
        )
    return result
