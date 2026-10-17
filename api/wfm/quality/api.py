"""Quality results: load a file, review a team's people, see your own (QUA-01).

The scoring stays in the quality tool. There is no league table: people are listed in
employee-number order with no rank, and an agent can read only their own results."""

from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from django.utils import timezone
from ninja import File, Router, Schema, Status
from ninja.files import UploadedFile
from wfm_engine.quality import Summary

from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .policy import (
    DEFAULT_DAYS,
    IMPORT_ROLES,
    MAX_UPLOAD_BYTES,
    REVIEW_ROLES,
    SELF_ROLES,
)

router = Router(tags=["quality"])
FEATURE = Feature.PEOPLE
IMPORT = RoleSessionAuth(*sorted(IMPORT_ROLES), feature=FEATURE)
REVIEW = RoleSessionAuth(*sorted(REVIEW_ROLES), feature=FEATURE)
SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=FEATURE)


class QualityRowError(Schema):
    row: int
    reason: str  # never quotes the row


class QualityImportOut(Schema):
    id: int
    fileName: str  # noqa: N815
    rowsRead: int  # noqa: N815
    rowsCreated: int  # noqa: N815
    rowsUpdated: int  # noqa: N815
    rowsUnchanged: int  # noqa: N815
    rowsRejected: int  # noqa: N815
    rowsUnmapped: int  # noqa: N815
    errors: list[QualityRowError]  # the first few rejected rows
    ignoredColumns: list[str]  # noqa: N815 - names only; never read or stored
    unmappedLogins: list[str]  # noqa: N815 - the first few; never guessed, never stored
    unmappedLoginCount: int  # noqa: N815


class QualitySummaryOut(Schema):
    evaluations: int
    averageScorePct: float | None  # noqa: N815
    latestScorePct: float | None  # noqa: N815
    latestOn: date | None  # noqa: N815
    csatCount: int  # noqa: N815
    csatAverage: float | None  # noqa: N815 - 1 to 5
    coachingDue: date | None  # noqa: N815
    coachingIsDue: bool  # noqa: N815


class QualityPersonSummaryOut(QualitySummaryOut):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str


class QualityTeamOut(Schema):
    days: int
    asOf: date  # noqa: N815
    people: list[QualityPersonSummaryOut]  # employee-number order; no rank, no team average


class QualityEvaluationOut(Schema):
    evaluatedOn: date  # noqa: N815
    kind: str
    ref: str
    scorePct: float  # noqa: N815
    csat: int | None
    coachingDue: date | None  # noqa: N815


class QualityPersonOut(QualitySummaryOut):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    days: int
    results: list[QualityEvaluationOut]  # newest first


def _summary(s: Summary) -> dict[str, object]:
    return {
        "evaluations": s.evaluations,
        "averageScorePct": s.average_score_pct,
        "latestScorePct": s.latest_score_pct,
        "latestOn": s.latest_on,
        "csatCount": s.csat_count,
        "csatAverage": s.csat_average,
        "coachingDue": s.coaching_due,
        "coachingIsDue": s.coaching_is_due,
    }


def _person_out(found: selectors.PersonResults, days: int) -> QualityPersonOut:
    return QualityPersonOut(
        employeeId=found.employee.pk,
        empNo=found.employee.emp_no,
        employee=found.employee.name,
        days=days,
        results=[
            QualityEvaluationOut(
                evaluatedOn=r.evaluated_on,
                kind=r.kind,
                ref=r.ref,
                scorePct=float(r.score_pct),
                csat=r.csat,
                coachingDue=r.coaching_due,
            )
            for r in found.results
        ],
        **_summary(found.summary),  # type: ignore[arg-type]
    )


@router.post(
    "/imports",
    auth=IMPORT,
    response={201: QualityImportOut},
    summary="Import quality results (CSV or Excel: login, date, score, and optional columns)",
)
def import_results(request: HttpRequest, file: File[UploadedFile]) -> Status[QualityImportOut]:
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise ApiError(
            413,
            "quality.too_large",
            "File too large",
            f"Files are limited to {MAX_UPLOAD_BYTES // 2**20} MB.",
        )
    found = services.import_results(
        user=current_user(request), file_name=file.name or "", content=file.read()
    )
    b = found.batch
    return Status(
        201,
        QualityImportOut(
            id=b.pk,
            fileName=b.file_name,
            rowsRead=b.rows_read,
            rowsCreated=b.rows_created,
            rowsUpdated=b.rows_updated,
            rowsUnchanged=b.rows_unchanged,
            rowsRejected=b.rows_rejected,
            rowsUnmapped=b.rows_unmapped,
            errors=[QualityRowError(row=n, reason=why) for n, why in found.errors],
            ignoredColumns=found.ignored_columns,
            unmappedLogins=found.unmapped_logins,
            unmappedLoginCount=found.unmapped_login_count,
        ),
    )


@router.get(
    "/team",
    auth=REVIEW,
    response=QualityTeamOut,
    summary="One summary per person in the caller's scope (a lead: their own team)",
)
def get_team(request: HttpRequest, days: int = DEFAULT_DAYS) -> QualityTeamOut:
    today = timezone.localdate()
    found = selectors.team(current_user(request), today, days)
    return QualityTeamOut(
        days=days,
        asOf=today,
        people=[
            QualityPersonSummaryOut(
                employeeId=p.employee.pk,
                empNo=p.employee.emp_no,
                employee=p.employee.name,
                **_summary(p.summary),  # type: ignore[arg-type]
            )
            for p in found
        ],
    )


@router.get(
    "/people/{employee_id}",
    auth=REVIEW,
    response=QualityPersonOut,
    summary="One person's results (out of the caller's scope is a 404)",
)
def get_person(
    request: HttpRequest, employee_id: int, days: int = DEFAULT_DAYS
) -> QualityPersonOut:
    found = selectors.person(current_user(request), employee_id, timezone.localdate(), days)
    return _person_out(found, days)


@router.get(
    "/mine",
    auth=SELF,
    response=QualityPersonOut,
    summary="The signed-in person's own quality results",
)
def get_mine(request: HttpRequest, days: int = DEFAULT_DAYS) -> QualityPersonOut:
    user = current_user(request)
    employee = selectors.own_employee(user)
    if employee is None:
        raise ApiError(
            422,
            "quality.no_employee_record",
            "Not on the employee list",
            "You are not on the employee list yet, so there is nothing to show. "
            "A planner adds you.",
        )
    return _person_out(selectors.person(user, employee.pk, timezone.localdate(), days), days)
