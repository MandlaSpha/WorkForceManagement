"""Importing the employee master (DAT-06) and mapping ACD logins to people (DAT-05).

A rejected row is skipped whole and counted by reason; the report never repeats a cell value, so a
name or number from the file cannot end up in a log. `dry_run` does everything and rolls it back,
so the planner sees exactly what would happen before it does. One audit event summarises a real
import (counts only: no names). Writes happen here with the audit event as the LAST write."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError, not_found
from wfm.telephony.models import CallRecord, Queue

from . import employee_import as reader
from .models import AgentLogin, ContractType, Employee, EmployeeSkill, WorkMode
from .policy import MANAGER_ROLES
from .services import DEFAULT_WEEKLY_HOURS, MAX_WEEKLY_HOURS


class _RollbackError(Exception):
    """Raised inside the transaction of a dry run, to undo everything it did."""


@dataclass(slots=True)
class ImportReport:
    dry_run: bool
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    rejected: Counter[str] = field(default_factory=Counter)
    ignored_columns: list[str] = field(default_factory=list)
    logins_mapped: int = 0


def _skills(text: str, queues: dict[str, Queue]) -> list[tuple[Queue, int]] | str:
    """'TotalSA;Gijima:2' -> [(queue, level)], or the reason code it cannot be read."""
    found: list[tuple[Queue, int]] = []
    for part in (p.strip() for p in text.split(";") if p.strip()):
        name, _, level_text = part.partition(":")
        queue = queues.get(name.strip().lower())
        if queue is None:
            return "queue_unknown"
        try:
            level = int(level_text) if level_text.strip() else 1
        except ValueError:
            return "skill_level_invalid"
        if not 1 <= level <= 3:
            return "skill_level_invalid"
        found.append((queue, level))
    if len({q.pk for q, _ in found}) != len(found):
        return "queue_repeated"
    return found


def import_employees(
    *, user: User, content: bytes, filename: str, dry_run: bool = False
) -> ImportReport:
    try:
        parsed = reader.parse(content, filename)
    except reader.UnreadableFileError as error:
        audit.record(
            actor=user,
            action=Action.EMPLOYEES_IMPORT_REFUSED,
            outcome=Outcome.FAILED,
            entity_type="employees",
            reason="unreadable",
        )
        raise ApiError(422, "employees.unreadable", "Unusable file", str(error)) from error

    report = ImportReport(dry_run=dry_run, ignored_columns=parsed.ignored_columns)
    try:
        with transaction.atomic():
            _apply(user, parsed, report)
            if dry_run:
                raise _RollbackError
    except _RollbackError:
        pass
    return report


def _apply(user: User, parsed: reader.Parsed, report: ImportReport) -> None:
    queues = {q.name.lower(): q for q in Queue.objects.all()}
    locked = Employee.objects.select_related("user").select_for_update(of=("self",), no_key=True)
    existing = {e.emp_no: e for e in locked}
    seen: set[str] = set()
    taken_logins = {a.login: a.employee_id for a in AgentLogin.objects.all()}

    for _, cells in parsed.rows:  # rows are counted by reason, never listed with their content
        code = _row(cells, queues, existing, seen, taken_logins, report)
        if code:
            report.rejected[code] += 1

    if not report.dry_run:
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.EMPLOYEES_IMPORTED,
            entity_type="employees",
            changes=[
                audit.FieldChange("employees", "import", "created", None, str(report.created)),
                audit.FieldChange("employees", "import", "updated", None, str(report.updated)),
                audit.FieldChange(
                    "employees", "import", "rejected", None, str(sum(report.rejected.values()))
                ),
            ],
        )


def _row(
    cells: dict[str, str],
    queues: dict[str, Queue],
    existing: dict[str, Employee],
    seen: set[str],
    taken_logins: dict[str, int],
    report: ImportReport,
) -> str | None:
    """Apply one row; returns the reason code if it was rejected, else None."""
    emp_no, name = cells.get("emp_no", ""), cells.get("name", "")
    if not 1 <= len(emp_no) <= 20:
        return "emp_no_invalid"
    if emp_no in seen:
        return "duplicate_in_file"
    seen.add(emp_no)
    current = existing.get(emp_no)
    if not name and current is None:
        return "name_missing"

    contract = cells.get("contract", "").lower()
    if contract and contract not in ContractType.values:
        return "contract_invalid"
    mode = cells.get("mode", "").lower()
    if mode and mode not in WorkMode.values:
        return "work_mode_invalid"
    hours: Decimal | None = None
    if cells.get("hours"):
        try:
            hours = Decimal(cells["hours"])
        except InvalidOperation:
            return "hours_invalid"
        if not 0 < hours <= MAX_WEEKLY_HOURS:
            return "hours_invalid"
    try:
        start, end = (
            reader.parse_date(cells.get("start", "")),
            reader.parse_date(cells.get("end", "")),
        )
    except ValueError:
        return "date_invalid"
    if start and end and end < start:
        return "dates_invalid"

    skills = _skills(cells["queues"], queues) if cells.get("queues") else None
    if isinstance(skills, str):
        return skills

    manager: Employee | None = None
    if cells.get("manager"):
        manager = existing.get(cells["manager"])
        if manager is None:
            return "manager_unknown"
        if manager.pk == (current.pk if current else None):
            return "manager_self"
        if manager.user is None or manager.user.role not in MANAGER_ROLES:
            return "manager_cannot"

    logins = [x.strip() for x in cells.get("logins", "").split(";") if x.strip()]
    owner = current.pk if current else None
    if any(taken_logins.get(login, owner) != owner for login in logins):
        return "login_taken"

    fields: dict[str, Any] = {}
    if name:
        fields["name"] = name
    if contract:
        fields["contract_type"] = contract
    if mode:
        fields["work_mode"] = mode
    if hours is not None:
        fields["weekly_hours"], fields["weekly_hours_is_default"] = hours, False
    if cells.get("start"):
        fields["start_date"] = start
    if cells.get("end"):
        fields["end_date"] = end
    if manager is not None:
        fields["manager"] = manager

    if current is None:
        fields.setdefault("weekly_hours", DEFAULT_WEEKLY_HOURS)
        fields.setdefault("weekly_hours_is_default", True)
        employee = Employee.objects.create(emp_no=emp_no, **fields)
        existing[emp_no] = employee
        report.created += 1
        changed = True
    else:
        changed = any(getattr(current, k) != v for k, v in fields.items())
        employee = current
        if changed:
            for key, value in fields.items():
                setattr(employee, key, value)
            employee.save()
            report.updated += 1

    if skills is not None:
        before = {s.queue_id: s.level for s in employee.skills.all()}
        after = {q.pk: level for q, level in skills}
        if before != after:
            employee.skills.all().delete()
            EmployeeSkill.objects.bulk_create(
                EmployeeSkill(employee=employee, queue=q, level=level) for q, level in skills
            )
            if current is not None and not changed:
                report.updated += 1
            changed = True
    for login in logins:
        if login not in taken_logins:
            AgentLogin.objects.create(login=login, employee=employee)
            taken_logins[login] = employee.pk
            report.logins_mapped += 1
            if current is not None and not changed:
                report.updated += 1
            changed = True
    if current is not None and not changed:
        report.unchanged += 1
    return None


@dataclass(frozen=True, slots=True)
class UnmappedLogin:
    login: str
    calls: int


def unmapped_logins() -> list[UnmappedLogin]:
    """ACD logins that appear on calls but belong to nobody yet, busiest first."""
    mapped = set(AgentLogin.objects.values_list("login", flat=True))
    counts: Counter[str] = Counter(
        login
        for login in CallRecord.objects.exclude(agent_login="")
        .exclude(agent_login__startswith="erased-")  # replaced when the person was erased
        .values_list("agent_login", flat=True)
        if login not in mapped
    )
    return [UnmappedLogin(login, n) for login, n in counts.most_common()]


def set_agent_logins(*, user: User, employee_id: int, logins: list[str]) -> Employee:
    """Replace the ACD logins that are this person (several logins can be one person)."""
    wanted = sorted({x.strip() for x in logins if x.strip()})
    if any(len(x) > 100 for x in wanted):
        raise ApiError(
            422, "logins.invalid", "Logins refused", "An ACD login is at most 100 characters."
        )
    with transaction.atomic():
        employee: Employee | None = (
            Employee.objects.select_for_update(no_key=True).filter(pk=employee_id).first()
        )
        if employee is None:
            raise not_found("No such employee.")
        taken = AgentLogin.objects.filter(login__in=wanted).exclude(employee=employee)
        if taken.exists():
            raise ApiError(
                409,
                "logins.taken",
                "Logins refused",
                "One of those logins already belongs to another person.",
            )
        before = sorted(
            AgentLogin.objects.filter(employee=employee).values_list("login", flat=True)
        )
        AgentLogin.objects.filter(employee=employee).exclude(login__in=wanted).delete()
        for login in wanted:
            AgentLogin.objects.get_or_create(login=login, defaults={"employee": employee})
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.AGENT_LOGINS_SET,
            entity_type="employee",
            entity_id=str(employee.pk),
            subject_employee_id=employee.pk,
            changes=[
                # Counts, not the logins: they can be people's names.
                audit.FieldChange(
                    "employee", str(employee.pk), "agent_logins", str(len(before)), str(len(wanted))
                )
            ],
        )
    return employee
