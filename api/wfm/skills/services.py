"""Writing credentials and queue requirements (SKL-01, WEL-02). Both replace the whole set for
one person or queue, in one transaction, and are audited as a before and after list."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from django.db import transaction

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError, not_found
from wfm.scheduling.models import Employee
from wfm.telephony.models import Queue

from .models import CredentialKind, EmployeeCredential, QueueRequirement
from .policy import MAX_CREDENTIALS, MAX_REQUIREMENTS


@dataclass(frozen=True, slots=True)
class CredentialInput:
    kind: str
    name: str
    expires_on: date | None = None


@dataclass(frozen=True, slots=True)
class RequirementInput:
    kind: str
    name: str
    min_people: int = 1


def _invalid(code: str, detail: str) -> ApiError:
    return ApiError(422, code, "Invalid request", detail)


def _clean(kind: str, name: str) -> str:
    if kind not in CredentialKind.values:
        raise _invalid(
            "skills.kind_invalid", "A credential is a certification, language or clearance."
        )
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > 80:
        raise _invalid("skills.name_invalid", "A name is 1 to 80 characters.")
    return cleaned


def _label_credential(kind: str, name: str, expires_on: date | None) -> str:
    return f"{kind}: {name}" + (f" (to {expires_on.isoformat()})" if expires_on else "")


def set_credentials(
    *, user: User, employee_id: int, credentials: Sequence[CredentialInput]
) -> list[EmployeeCredential]:
    if len(credentials) > MAX_CREDENTIALS:
        raise _invalid("skills.too_many", f"At most {MAX_CREDENTIALS} credentials a person.")
    wanted = [CredentialInput(c.kind, _clean(c.kind, c.name), c.expires_on) for c in credentials]
    if len({(c.kind, c.name.casefold()) for c in wanted}) != len(wanted):
        raise _invalid("skills.duplicate", "A credential is listed twice.")
    with transaction.atomic():
        employee = (
            Employee.objects.for_user(user)
            .select_for_update(of=("self",), no_key=True)
            .filter(pk=employee_id)
            .first()
        )
        if employee is None:
            raise not_found("No such employee.")
        before = sorted(
            _label_credential(c.kind, c.name, c.expires_on)
            for c in EmployeeCredential.objects.filter(employee=employee)
        )
        EmployeeCredential.objects.filter(employee=employee).delete()
        saved = EmployeeCredential.objects.bulk_create(
            EmployeeCredential(
                employee=employee,
                kind=c.kind,
                name=c.name,
                expires_on=c.expires_on,
                updated_by=user,
            )
            for c in wanted
        )
        after = sorted(_label_credential(c.kind, c.name, c.expires_on) for c in wanted)
        if before != after:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.CREDENTIALS_SET,
                entity_type="employee",
                entity_id=str(employee.pk),
                subject_employee_id=employee.pk,
                changes=[
                    audit.FieldChange(
                        "employee",
                        str(employee.pk),
                        "credentials",
                        "; ".join(before),
                        "; ".join(after),
                    )
                ],
            )
    return saved


def set_requirements(
    *, user: User, queue_id: int, requirements: Sequence[RequirementInput]
) -> list[QueueRequirement]:
    if len(requirements) > MAX_REQUIREMENTS:
        raise _invalid("skills.too_many", f"At most {MAX_REQUIREMENTS} requirements a queue.")
    wanted = [RequirementInput(r.kind, _clean(r.kind, r.name), r.min_people) for r in requirements]
    if any(not 1 <= r.min_people <= 500 for r in wanted):
        raise _invalid("skills.min_people_invalid", "At least 1 person is required.")
    if len({(r.kind, r.name.casefold()) for r in wanted}) != len(wanted):
        raise _invalid("skills.duplicate", "A requirement is listed twice.")
    with transaction.atomic():
        queue = (
            Queue.objects.for_user(user)
            .select_for_update(of=("self",), no_key=True)
            .filter(pk=queue_id)
            .first()
        )
        if queue is None:
            raise not_found("No such queue.")
        before = sorted(
            f"{r.kind}: {r.name} x{r.min_people}"
            for r in QueueRequirement.objects.filter(queue=queue)
        )
        QueueRequirement.objects.filter(queue=queue).delete()
        saved = QueueRequirement.objects.bulk_create(
            QueueRequirement(queue=queue, kind=r.kind, name=r.name, min_people=r.min_people)
            for r in wanted
        )
        after = sorted(f"{r.kind}: {r.name} x{r.min_people}" for r in wanted)
        if before != after:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.QUEUE_REQUIREMENTS_SET,
                entity_type="queue",
                entity_id=str(queue.pk),
                changes=[
                    audit.FieldChange(
                        "queue", str(queue.pk), "requirements", "; ".join(before), "; ".join(after)
                    )
                ],
            )
    return saved
