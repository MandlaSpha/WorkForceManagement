"""Right to erasure for an employee who has left (POPIA): anonymise them, never delete history.

Admin only, in two steps so it cannot happen by accident: `preview` says whether it may be done and
what will be removed (counts), `anonymise` must be sent the employee number again. It removes what
identifies the person (name, number, sign-in, ACD logins, availability, notifications, pay,
free-text overtime reasons) and keeps what the business needs (shifts, leave, overtime and standby
minutes and the costs stored when they were approved) so service level, shrinkage and the totals
of closed months stay right. Audit rows are never touched: they hold ids and counts, not names.
"""

from __future__ import annotations

import secrets
from datetime import date
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.identity.models import IdentityLink
from wfm.notifications.models import Notification
from wfm.overtime.models import (
    EmployeePay,
    OvertimeRequest,
    OvertimeStatus,
    StandbyShift,
    StandbyStatus,
)
from wfm.scheduling.models import AgentLogin, Employee, ShiftAssignment

from .models import (
    OPEN_SWAP_STATUSES,
    Availability,
    LeaveRequest,
    LeaveStatus,
    SwapRequest,
)

PLACEHOLDER_PREFIX = "ERASED-"
DEFAULT_RETENTION_MONTHS = 60


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Anonymising refused", detail)


def retention_months() -> int:
    return int(getattr(settings, "WFM_RETENTION_MONTHS", DEFAULT_RETENTION_MONTHS))


def _months_before(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) - months
    year, month = divmod(index, 12)
    # Day 28 at most, so every month has it; the cut-off is a review prompt, not a deadline.
    return date(year, month + 1, min(day.day, 28))


def is_anonymised(employee: Employee) -> bool:
    return employee.emp_no.startswith(PLACEHOLDER_PREFIX)


def _require_admin(admin: User) -> None:
    if admin.role != Role.ADMIN:
        raise not_found("No such employee.")


def _counts(employee: Employee) -> dict[str, dict[str, int]]:
    user = employee.user
    removes = {
        "agentLogins": AgentLogin.objects.filter(employee=employee).count(),
        "availabilityWindows": Availability.objects.filter(employee=employee).count(),
        "notifications": Notification.objects.filter(recipient=user).count() if user else 0,
        "overtimeReasons": OvertimeRequest.objects.filter(employee=employee)
        .exclude(reason="")
        .count(),
        "payRecords": EmployeePay.objects.filter(employee=employee).count(),
        "signInLinks": (1 + IdentityLink.objects.filter(user=user).count()) if user else 0,
    }
    keeps = {
        "shifts": ShiftAssignment.objects.filter(employee=employee).count(),
        "leaveRequests": LeaveRequest.objects.filter(employee=employee).count(),
        "overtimeRequests": OvertimeRequest.objects.filter(employee=employee).count(),
        "standbyShifts": StandbyShift.objects.filter(employee=employee).count(),
    }
    return {"removes": removes, "keeps": keeps}


def _check_allowed(admin: User, employee: Employee) -> None:
    """Refuse, with a reason a person can act on, unless this person has left and is settled."""
    today = timezone.localdate()
    if is_anonymised(employee):
        raise _refuse(409, "erasure.already_anonymised", "This employee is already anonymised.")
    if employee.user_id is not None and employee.user_id == admin.pk:
        raise _refuse(409, "erasure.own_login", "You cannot anonymise the record you sign in with.")
    if employee.end_date is None or employee.end_date >= today:
        raise _refuse(
            409,
            "erasure.not_left",
            "Only someone whose employment end date is in the past can be anonymised.",
        )
    if (
        ShiftAssignment.objects.filter(employee=employee, day__gte=today).exists()
        or LeaveRequest.objects.filter(
            employee=employee, status=LeaveStatus.APPROVED, end_date__gte=today
        ).exists()
        or StandbyShift.objects.filter(
            employee=employee, status=StandbyStatus.BOOKED, day__gte=today
        ).exists()
        or OvertimeRequest.objects.filter(
            employee=employee, status=OvertimeStatus.APPROVED, day__gte=today
        ).exists()
    ):
        raise _refuse(
            409,
            "erasure.future_work",
            "This person still has shifts, leave, standby or overtime in the future. "
            "Clear them first.",
        )
    if (
        LeaveRequest.objects.filter(employee=employee, status=LeaveStatus.PENDING).exists()
        or OvertimeRequest.objects.filter(employee=employee, status=OvertimeStatus.PENDING).exists()
        or SwapRequest.objects.filter(status__in=OPEN_SWAP_STATUSES)
        .filter(from_employee=employee)
        .exists()
        or SwapRequest.objects.filter(status__in=OPEN_SWAP_STATUSES)
        .filter(to_employee=employee)
        .exists()
    ):
        raise _refuse(
            409,
            "erasure.pending_requests",
            "This person has requests still waiting for a decision. Decide or cancel them first.",
        )


def _employee(admin: User, employee_id: int, *, lock: bool = False) -> Employee:
    _require_admin(admin)
    query = Employee.objects.for_user(admin).select_related("user")
    if lock:
        query = query.select_for_update(no_key=True, of=("self",))
    found: Employee | None = query.filter(pk=employee_id).first()
    if found is None:
        raise not_found("No such employee.")
    return found


def preview(admin: User, employee_id: int) -> dict[str, Any]:
    """Whether it may be done (a refusal is raised with its reason) and what it would remove."""
    employee = _employee(admin, employee_id)
    _check_allowed(admin, employee)
    return {"employeeId": employee.pk, "employeeNumber": employee.emp_no, **_counts(employee)}


def anonymise(admin: User, employee_id: int, typed_number: str) -> dict[str, Any]:
    with transaction.atomic():
        employee = _employee(admin, employee_id, lock=True)
        if is_anonymised(employee):
            raise _refuse(409, "erasure.already_anonymised", "This employee is already anonymised.")
        if typed_number.strip() != employee.emp_no:
            raise _refuse(
                422,
                "erasure.confirmation_mismatch",
                "The employee number you typed does not match.",
            )
        _check_allowed(admin, employee)
        counts = _counts(employee)

        token = secrets.token_hex(5).upper()
        while Employee.objects.filter(emp_no=f"{PLACEHOLDER_PREFIX}{token}").exists():
            token = secrets.token_hex(5).upper()  # pragma: no cover - 40 bits, essentially never
        user = employee.user
        if user is not None:
            Notification.objects.filter(recipient=user).delete()
            IdentityLink.objects.filter(user=user).delete()
            user.username = f"erased-user-{user.pk}"
            user.first_name = user.last_name = user.email = ""
            user.is_active = False
            user.set_unusable_password()
            user.save()
        AgentLogin.objects.filter(employee=employee).delete()
        Availability.objects.filter(employee=employee).delete()
        EmployeePay.objects.filter(employee=employee).delete()
        OvertimeRequest.objects.filter(employee=employee).update(reason="")
        employee.emp_no = f"{PLACEHOLDER_PREFIX}{token}"
        employee.name = f"Former employee {token}"
        employee.user = None
        employee.save(update_fields=["emp_no", "name", "user"])

        pk = str(employee.pk)
        audit.record(  # last write of the transaction
            actor=admin,
            action=Action.EMPLOYEE_ANONYMISED,
            entity_type="employee",
            entity_id=pk,
            subject_employee_id=employee.pk,
            changes=[
                audit.FieldChange("employee", pk, f"removed_{key}", None, str(n))
                for key, n in counts["removes"].items()
            ]
            + [
                audit.FieldChange("employee", pk, f"kept_{key}", None, str(n))
                for key, n in counts["keeps"].items()
            ],
        )
    return {"employeeId": employee.pk, **counts}


def past_retention(admin: User) -> dict[str, Any]:
    """Who has been gone longer than the retention period: for the admin to review, nothing more."""
    _require_admin(admin)
    months = retention_months()
    cutoff = _months_before(timezone.localdate(), months)
    rows = [
        {"employeeId": e.pk, "employeeNumber": e.emp_no, "endDate": e.end_date}
        for e in Employee.objects.for_user(admin)
        .filter(end_date__lt=cutoff)
        .exclude(emp_no__startswith=PLACEHOLDER_PREFIX)
        .order_by("end_date", "emp_no")
    ]
    return {"months": months, "before": cutoff, "employees": rows}
