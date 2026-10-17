"""Credentials, queue requirements, skill gaps (SKL-01, WEL-02) and wellbeing prompts (WEL-01)."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema

from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services, wellbeing_selectors
from .models import CredentialKind, EmployeeCredential, QueueRequirement
from .policy import (
    CREDENTIAL_READ_ROLES,
    GAP_ROLES,
    MAX_GAP_DAYS,
    REQUIREMENT_READ_ROLES,
    WELLBEING_ROLES,
    WRITE_ROLES,
)

router = Router(tags=["skills"])
wellbeing_router = Router(tags=["wellbeing"])
FEATURE = Feature.PEOPLE
CREDENTIAL_READ = RoleSessionAuth(*sorted(CREDENTIAL_READ_ROLES), feature=FEATURE)
REQUIREMENT_READ = RoleSessionAuth(*sorted(REQUIREMENT_READ_ROLES), feature=FEATURE)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=FEATURE)
GAPS = RoleSessionAuth(*sorted(GAP_ROLES), feature=FEATURE)
WELLBEING = RoleSessionAuth(*sorted(WELLBEING_ROLES), feature=FEATURE)


class CredentialIn(Schema):
    kind: str
    name: str
    expiresOn: date | None = None  # noqa: N815


class CredentialsIn(Schema):
    credentials: list[CredentialIn]


class CredentialOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    kind: str
    name: str
    expiresOn: date | None  # noqa: N815
    expired: bool


class RequirementIn(Schema):
    kind: str
    name: str
    minPeople: int = 1  # noqa: N815


class RequirementsIn(Schema):
    requirements: list[RequirementIn]


class RequirementOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    kind: str
    name: str
    minPeople: int  # noqa: N815


class SkillGapOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    kind: str
    name: str
    day: date
    shiftCode: str  # noqa: N815
    required: int
    present: int


class WellbeingFlagOut(Schema):
    code: str  # long_run, no_rest, repeated_overtime, rising_absence
    value: int  # the fact behind it: days, never a score


class WellbeingPersonOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    flags: list[WellbeingFlagOut]


class WellbeingOut(Schema):
    asOf: date  # noqa: N815
    people: list[WellbeingPersonOut]


def _credential_out(c: EmployeeCredential, today: date) -> CredentialOut:
    return CredentialOut(
        employeeId=c.employee_id,
        empNo=c.employee.emp_no,
        employee=c.employee.name,
        kind=c.kind,
        name=c.name,
        expiresOn=c.expires_on,
        expired=c.expires_on is not None and c.expires_on < today,
    )


def _requirement_out(r: QueueRequirement) -> RequirementOut:
    return RequirementOut(
        queueId=r.queue_id, queue=r.queue.name, kind=r.kind, name=r.name, minPeople=r.min_people
    )


@router.get("/kinds", auth=CREDENTIAL_READ, response=list[str], summary="Kinds of credential")
def list_kinds(request: HttpRequest) -> list[str]:
    return list(CredentialKind.values)


@router.get(
    "/credentials",
    auth=CREDENTIAL_READ,
    response=list[CredentialOut],
    summary="Credentials you may see (optionally one employee's)",
)
def list_credentials(request: HttpRequest, employee_id: int | None = None) -> list[CredentialOut]:
    today = timezone.localdate()
    return [
        _credential_out(c, today) for c in selectors.credentials(current_user(request), employee_id)
    ]


@router.put(
    "/employees/{employee_id}/credentials",
    auth=WRITE,
    response=list[CredentialOut],
    summary="Replace one employee's credentials",
)
def put_credentials(
    request: HttpRequest, employee_id: int, body: CredentialsIn
) -> list[CredentialOut]:
    user = current_user(request)
    services.set_credentials(
        user=user,
        employee_id=employee_id,
        credentials=[
            services.CredentialInput(c.kind, c.name, c.expiresOn) for c in body.credentials
        ],
    )
    today = timezone.localdate()
    return [_credential_out(c, today) for c in selectors.credentials(user, employee_id)]


@router.get(
    "/requirements",
    auth=REQUIREMENT_READ,
    response=list[RequirementOut],
    summary="What each queue requires",
)
def list_requirements(request: HttpRequest, queue_id: int | None = None) -> list[RequirementOut]:
    return [_requirement_out(r) for r in selectors.requirements(current_user(request), queue_id)]


@router.put(
    "/queues/{queue_id}/requirements",
    auth=WRITE,
    response=list[RequirementOut],
    summary="Replace what one queue requires",
)
def put_requirements(
    request: HttpRequest, queue_id: int, body: RequirementsIn
) -> list[RequirementOut]:
    user = current_user(request)
    services.set_requirements(
        user=user,
        queue_id=queue_id,
        requirements=[
            services.RequirementInput(r.kind, r.name, r.minPeople) for r in body.requirements
        ],
    )
    return [_requirement_out(r) for r in selectors.requirements(user, queue_id)]


@router.get(
    "/gaps",
    auth=GAPS,
    response=list[SkillGapOut],
    summary="Shifts where a required skill has too few people",
)
def list_gaps(request: HttpRequest, start: date, days: int = 7) -> list[SkillGapOut]:
    if not 1 <= days <= MAX_GAP_DAYS:
        raise ApiError(
            422, "skills.days_out_of_range", "Invalid request", f"Ask for 1 to {MAX_GAP_DAYS} days."
        )
    return [
        SkillGapOut(
            queueId=g.queue.pk,
            queue=g.queue.name,
            kind=g.kind,
            name=g.name,
            day=g.day,
            shiftCode=g.shift_code,
            required=g.required,
            present=g.present,
        )
        for g in selectors.skill_gaps(current_user(request), start=start, days=days)
    ]


@wellbeing_router.get(
    "/flags",
    auth=WELLBEING,
    response=WellbeingOut,
    summary="Early-warning prompts for a conversation (no score)",
)
def wellbeing_flags(request: HttpRequest) -> WellbeingOut:
    today = timezone.localdate()
    return WellbeingOut(
        asOf=today,
        people=[
            WellbeingPersonOut(
                employeeId=p.employee.pk,
                empNo=p.employee.emp_no,
                employee=p.employee.name,
                flags=[WellbeingFlagOut(code=f.code, value=f.value) for f in p.flags],
            )
            for p in wellbeing_selectors.prompts(current_user(request), today=today)
        ],
    )
