"""Shift templates and employees (requirements SCH-01, EMP-01). Writes happen here, in one
transaction, with the audit event as the LAST write (hard rule: the audit insert holds the
audit-chain lock until commit). The roster itself is in `roster_services.py`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from wfm_engine.roster import on_grid, shift_minutes

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.telephony.models import Queue

from .models import (
    ContractType,
    Employee,
    EmployeeSkill,
    ShiftAssignment,
    ShiftTemplate,
    WorkMode,
)

DEFAULT_WEEKLY_HOURS = Decimal("40")
MAX_WEEKLY_HOURS = Decimal("60")


def _invalid(code: str, detail: str, status: int = 422) -> ApiError:
    return ApiError(status, code, "Invalid request", detail)


# --- shift templates ---------------------------------------------------------------------------


def _check_shift(code: str, start: time, end: time, paid_minutes: int) -> str:
    code = code.strip()
    if not 1 <= len(code) <= 10:
        raise _invalid("shift.code_invalid", "A shift code is 1 to 10 characters.")
    if not (on_grid(start) and on_grid(end)):
        raise _invalid("shift.not_on_grid", "Shift times must be on the hour or half-hour.")
    if start == end:
        raise _invalid("shift.no_length", "A shift must have a length.")
    if not 0 < paid_minutes <= shift_minutes(start, end):
        raise _invalid(
            "shift.paid_minutes_invalid",
            f"Paid minutes must be between 1 and the shift's length ({shift_minutes(start, end)}).",
        )
    return code


def create_shift(
    *, user: User, code: str, start_time: time, end_time: time, paid_minutes: int
) -> ShiftTemplate:
    code = _check_shift(code, start_time, end_time, paid_minutes)
    if ShiftTemplate.objects.filter(code=code).exists():
        raise _invalid("shift.code_taken", f"There is already a shift called {code}.", 409)
    try:
        with transaction.atomic():
            shift = ShiftTemplate.objects.create(
                code=code, start_time=start_time, end_time=end_time, paid_minutes=paid_minutes
            )
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.SHIFT_CREATED,
                entity_type="shift_template",
                entity_id=str(shift.pk),
                changes=[
                    audit.FieldChange("shift_template", str(shift.pk), "code", None, code),
                    audit.FieldChange(
                        "shift_template",
                        str(shift.pk),
                        "times",
                        None,
                        f"{start_time:%H:%M}-{end_time:%H:%M} ({paid_minutes} paid min)",
                    ),
                ],
            )
    except IntegrityError:
        raise _invalid(
            "shift.code_taken", f"There is already a shift called {code}.", 409
        ) from None
    return shift


def _shift_in_use(shift: ShiftTemplate) -> bool:
    return ShiftAssignment.objects.filter(template=shift).exists()


def update_shift(
    *, user: User, shift_id: int, code: str, start_time: time, end_time: time, paid_minutes: int
) -> ShiftTemplate:
    """Change a shift. Once anybody is rostered on it, its times are fixed: changing them would
    silently rewrite coverage and rest periods of rosters that already exist, published ones
    included. Make a new shift instead."""
    code = _check_shift(code, start_time, end_time, paid_minutes)
    with transaction.atomic():
        shift: ShiftTemplate | None = (
            ShiftTemplate.objects.select_for_update().for_user(user).filter(pk=shift_id).first()
        )
        if shift is None:
            raise not_found("No such shift.")
        if _shift_in_use(shift) and (
            (shift.start_time, shift.end_time, shift.paid_minutes)
            != (start_time, end_time, paid_minutes)
        ):
            raise _invalid(
                "shift.in_use",
                "People are rostered on this shift, so its times cannot change. "
                "Create a new shift instead.",
                409,
            )
        if ShiftTemplate.objects.filter(code=code).exclude(pk=shift.pk).exists():
            raise _invalid("shift.code_taken", f"There is already a shift called {code}.", 409)
        changes = [
            audit.FieldChange("shift_template", str(shift.pk), name, str(old), str(new))
            for name, old, new in (
                ("code", shift.code, code),
                ("start_time", shift.start_time, start_time),
                ("end_time", shift.end_time, end_time),
                ("paid_minutes", shift.paid_minutes, paid_minutes),
            )
            if old != new
        ]
        shift.code, shift.start_time, shift.end_time, shift.paid_minutes = (
            code,
            start_time,
            end_time,
            paid_minutes,
        )
        shift.save()
        if changes:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.SHIFT_CHANGED,
                entity_type="shift_template",
                entity_id=str(shift.pk),
                changes=changes,
            )
    return shift


def delete_shift(*, user: User, shift_id: int) -> None:
    with transaction.atomic():
        shift: ShiftTemplate | None = (
            ShiftTemplate.objects.select_for_update().for_user(user).filter(pk=shift_id).first()
        )
        if shift is None:
            raise not_found("No such shift.")
        if _shift_in_use(shift):
            raise _invalid(
                "shift.in_use", "People are rostered on this shift, so it cannot be deleted.", 409
            )
        code = shift.code
        shift.delete()
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.SHIFT_DELETED,
            entity_type="shift_template",
            entity_id=str(shift_id),
            changes=[audit.FieldChange("shift_template", str(shift_id), "code", code, None)],
        )


# --- employees ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SkillInput:
    queue_id: int
    level: int = 1


def _check_employee(
    *,
    emp_no: str,
    name: str,
    contract_type: str,
    work_mode: str,
    weekly_hours: Decimal | None,
    start_date: date | None,
    end_date: date | None,
    skills: Sequence[SkillInput],
) -> tuple[str, str, dict[int, Queue]]:
    emp_no, name = emp_no.strip(), name.strip()
    if not 1 <= len(emp_no) <= 20:
        raise _invalid("employee.emp_no_invalid", "An employee number is 1 to 20 characters.")
    if not name:
        raise _invalid("employee.name_missing", "An employee needs a name.")
    if contract_type not in ContractType.values:
        raise _invalid("employee.contract_invalid", "Unknown contract type.")
    if work_mode not in WorkMode.values:
        raise _invalid("employee.work_mode_invalid", "Unknown work mode.")
    if weekly_hours is not None and not 0 < weekly_hours <= MAX_WEEKLY_HOURS:
        raise _invalid(
            "employee.hours_invalid",
            f"Weekly hours must be above 0 and at most {MAX_WEEKLY_HOURS}.",
        )
    if start_date and end_date and end_date < start_date:
        raise _invalid("employee.dates_invalid", "The end date is before the start date.")
    if any(not 1 <= s.level <= 3 for s in skills):
        raise _invalid("employee.skill_level_invalid", "A skill level is 1, 2 or 3.")
    if len({s.queue_id for s in skills}) != len(skills):
        raise _invalid("employee.skill_duplicate", "A queue is listed twice.")
    queues = {q.pk: q for q in Queue.objects.filter(pk__in=[s.queue_id for s in skills])}
    if len(queues) != len(skills):
        raise _invalid("employee.skill_queue_unknown", "A skill names a queue that does not exist.")
    return emp_no, name, queues


def create_employee(
    *,
    user: User,
    emp_no: str,
    name: str,
    contract_type: str = ContractType.PERMANENT,
    work_mode: str = WorkMode.OFFICE,
    weekly_hours: Decimal | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    skills: Sequence[SkillInput] = (),
) -> Employee:
    emp_no, name, queues = _check_employee(
        emp_no=emp_no,
        name=name,
        contract_type=contract_type,
        work_mode=work_mode,
        weekly_hours=weekly_hours,
        start_date=start_date,
        end_date=end_date,
        skills=skills,
    )
    if Employee.objects.filter(emp_no=emp_no).exists():
        raise _invalid("employee.emp_no_taken", f"Employee number {emp_no} is already used.", 409)
    try:
        with transaction.atomic():
            employee: Employee = Employee.objects.create(
                emp_no=emp_no,
                name=name,
                contract_type=contract_type,
                work_mode=work_mode,
                weekly_hours=weekly_hours if weekly_hours is not None else DEFAULT_WEEKLY_HOURS,
                weekly_hours_is_default=weekly_hours is None,
                start_date=start_date,
                end_date=end_date,
            )
            EmployeeSkill.objects.bulk_create(
                EmployeeSkill(employee=employee, queue=queues[s.queue_id], level=s.level)
                for s in skills
            )
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.EMPLOYEE_CREATED,
                entity_type="employee",
                entity_id=str(employee.pk),
                subject_employee_id=employee.pk,
                changes=[
                    audit.FieldChange("employee", str(employee.pk), "emp_no", None, emp_no),
                    audit.FieldChange(
                        "employee",
                        str(employee.pk),
                        "skills",
                        None,
                        ", ".join(sorted(queues[s.queue_id].name for s in skills)),
                    ),
                ],
            )
    except IntegrityError:
        raise _invalid(
            "employee.emp_no_taken", f"Employee number {emp_no} is already used.", 409
        ) from None
    return employee


def update_employee(
    *,
    user: User,
    employee_id: int,
    emp_no: str,
    name: str,
    contract_type: str,
    work_mode: str,
    weekly_hours: Decimal | None,
    start_date: date | None,
    end_date: date | None,
    skills: Sequence[SkillInput],
) -> Employee:
    emp_no, name, queues = _check_employee(
        emp_no=emp_no,
        name=name,
        contract_type=contract_type,
        work_mode=work_mode,
        weekly_hours=weekly_hours,
        start_date=start_date,
        end_date=end_date,
        skills=skills,
    )
    with transaction.atomic():
        employee: Employee | None = (
            Employee.objects.select_for_update().for_user(user).filter(pk=employee_id).first()
        )
        if employee is None:
            raise not_found("No such employee.")
        if Employee.objects.filter(emp_no=emp_no).exclude(pk=employee.pk).exists():
            raise _invalid(
                "employee.emp_no_taken", f"Employee number {emp_no} is already used.", 409
            )

        wanted = {s.queue_id for s in skills}
        dropped = set(employee.skills.values_list("queue_id", flat=True)) - wanted
        if (
            dropped
            and ShiftAssignment.objects.filter(
                employee=employee, roster_week__queue_id__in=dropped
            ).exists()
        ):
            raise _invalid(
                "employee.skill_in_use",
                "This person is rostered on a queue you are removing. Clear those shifts first.",
                409,
            )

        before: dict[str, Any] = {
            "emp_no": employee.emp_no,
            "name": employee.name,
            "contract_type": employee.contract_type,
            "work_mode": employee.work_mode,
            "weekly_hours": employee.weekly_hours,
            "start_date": employee.start_date,
            "end_date": employee.end_date,
        }
        employee.emp_no, employee.name = emp_no, name
        employee.contract_type, employee.work_mode = contract_type, work_mode
        if weekly_hours is not None:
            employee.weekly_hours, employee.weekly_hours_is_default = weekly_hours, False
        employee.start_date, employee.end_date = start_date, end_date
        employee.save()
        employee.skills.all().delete()
        EmployeeSkill.objects.bulk_create(
            EmployeeSkill(employee=employee, queue=queues[s.queue_id], level=s.level)
            for s in skills
        )
        after = {k: getattr(employee, k) for k in before}
        # A name is personal data: the trail says it changed, not what it was or became.
        changes = [
            audit.FieldChange(
                "employee",
                str(employee.pk),
                k,
                None if k == "name" else str(before[k]),
                "changed" if k == "name" else str(after[k]),
            )
            for k in before
            if before[k] != after[k]
        ]
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.EMPLOYEE_CHANGED,
            entity_type="employee",
            entity_id=str(employee.pk),
            subject_employee_id=employee.pk,
            changes=changes,
        )
    return employee
