"""Attendance: load an agent-state file, see a queue day's adherence, see your own day (ATT-01)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import File, Router, Schema, Status
from ninja.files import UploadedFile

from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .policy import DAYS_AHEAD, DAYS_BACK, IMPORT_ROLES, MAX_UPLOAD_BYTES, READ_ROLES, SELF_ROLES

router = Router(tags=["attendance"])
FEATURE = Feature.PEOPLE
IMPORT = RoleSessionAuth(*sorted(IMPORT_ROLES), feature=FEATURE)
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=FEATURE)
SELF = RoleSessionAuth(*sorted(SELF_ROLES), feature=FEATURE)


class AttendanceRowError(Schema):
    row: int
    reason: str  # never quotes the row


class AttendanceImportOut(Schema):
    id: int
    fileName: str  # noqa: N815
    rowsRead: int  # noqa: N815
    rowsInserted: int  # noqa: N815
    rowsDuplicate: int  # noqa: N815
    rowsRejected: int  # noqa: N815
    rowsUnmapped: int  # noqa: N815
    errors: list[AttendanceRowError]  # the first few rejected rows
    unmappedLogins: list[str]  # noqa: N815 - the first few; never guessed, never stored
    unmappedLoginCount: int  # noqa: N815


class AttendanceSpanOut(Schema):
    start: datetime
    end: datetime


class AttendanceStateOut(Schema):
    state: str
    start: datetime
    end: datetime


class AttendanceFigures(Schema):
    hasData: bool  # noqa: N815 - false: no state rows near the shift, so nothing is claimed
    scheduledMin: int  # noqa: N815
    inAdherenceMin: int  # noqa: N815
    outOfAdherenceMin: int  # noqa: N815
    adherencePct: float | None  # noqa: N815
    lateStartMin: int  # noqa: N815
    earlyFinishMin: int  # noqa: N815
    exceptions: list[str]  # no_show, late_start, early_finish, out_of_adherence


class AttendancePersonOut(AttendanceFigures):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    employee: str
    shiftCode: str  # noqa: N815


class AttendanceQueueDayOut(Schema):
    queue: str
    day: date
    teamAdherencePct: float | None  # noqa: N815 - over the people who have data
    withData: int  # noqa: N815
    withoutData: int  # noqa: N815
    people: list[AttendancePersonOut]


class AttendanceMineOut(AttendanceFigures):
    day: date
    hasShift: bool  # noqa: N815
    shiftCode: str | None  # noqa: N815
    planned: list[AttendanceSpanOut]
    actual: list[AttendanceStateOut]


def _local(value: datetime) -> datetime:
    return value.astimezone(ZoneInfo(settings.TIME_ZONE))


def _figures(person: selectors.PersonDay) -> dict[str, object]:
    r = person.result
    data = person.has_data
    return {
        "hasData": data,
        "scheduledMin": r.scheduled_min,
        "inAdherenceMin": r.in_adherence_min if data else 0,
        "outOfAdherenceMin": r.out_of_adherence_min if data else 0,
        "adherencePct": r.adherence_pct if data else None,
        "lateStartMin": r.late_start_min if data else 0,
        "earlyFinishMin": r.early_finish_min if data else 0,
        "exceptions": r.exceptions if data else [],
    }


def _check_day(day: date) -> None:
    today = timezone.localdate()
    if not today - timedelta(days=DAYS_BACK) <= day <= today + timedelta(days=DAYS_AHEAD):
        raise ApiError(
            422,
            "attendance.date_out_of_range",
            "Day out of range",
            "That day is too far back or ahead.",
        )


@router.post(
    "/imports",
    auth=IMPORT,
    response={201: AttendanceImportOut},
    summary="Import an agent-state file (CSV: login, state, from, to)",
)
def import_states(request: HttpRequest, file: File[UploadedFile]) -> Status[AttendanceImportOut]:
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise ApiError(
            413,
            "attendance.too_large",
            "File too large",
            f"Files are limited to {MAX_UPLOAD_BYTES // 2**20} MB.",
        )
    found = services.import_states(
        user=current_user(request), file_name=file.name or "", content=file.read()
    )
    b = found.batch
    return Status(
        201,
        AttendanceImportOut(
            id=b.pk,
            fileName=b.file_name,
            rowsRead=b.rows_read,
            rowsInserted=b.rows_inserted,
            rowsDuplicate=b.rows_duplicate,
            rowsRejected=b.rows_rejected,
            rowsUnmapped=b.rows_unmapped,
            errors=[AttendanceRowError(row=n, reason=why) for n, why in found.parsed.errors],
            unmappedLogins=found.unmapped_logins,
            unmappedLoginCount=found.unmapped_login_count,
        ),
    )


@router.get(
    "/adherence",
    auth=READ,
    response=AttendanceQueueDayOut,
    summary="Adherence of every person rostered on a queue that day (a lead: their own team)",
)
def get_adherence(request: HttpRequest, queue_id: int, day: date) -> AttendanceQueueDayOut:
    _check_day(day)
    found = selectors.queue_day(current_user(request), queue_id, day)
    return AttendanceQueueDayOut(
        queue=found.queue_name,
        day=found.day,
        teamAdherencePct=found.team_adherence_pct,
        withData=sum(p.has_data for p in found.people),
        withoutData=sum(not p.has_data for p in found.people),
        people=[
            AttendancePersonOut(
                employeeId=p.employee_id,
                empNo=p.emp_no,
                employee=p.name,
                shiftCode=p.shift_code,
                **_figures(p),  # type: ignore[arg-type]
            )
            for p in found.people
        ],
    )


@router.get(
    "/mine",
    auth=SELF,
    response=AttendanceMineOut,
    summary="The signed-in person's own planned and actual day",
)
def get_mine(request: HttpRequest, day: date) -> AttendanceMineOut:
    _check_day(day)
    user = current_user(request)
    employee = selectors.own_employee(user)
    if employee is None:
        raise ApiError(
            422,
            "attendance.no_employee_record",
            "Not on the employee list",
            "You are not on the employee list yet, so there is nothing to show. "
            "A planner adds you.",
        )
    found = selectors.my_day(user, employee, day)
    if found is None:
        return AttendanceMineOut(
            day=day,
            hasShift=False,
            shiftCode=None,
            planned=[],
            actual=[],
            hasData=False,
            scheduledMin=0,
            inAdherenceMin=0,
            outOfAdherenceMin=0,
            adherencePct=None,
            lateStartMin=0,
            earlyFinishMin=0,
            exceptions=[],
        )
    return AttendanceMineOut(
        day=day,
        hasShift=True,
        shiftCode=found.shift_code,
        planned=[AttendanceSpanOut(start=_local(s), end=_local(e)) for s, e in found.planned],
        actual=[
            AttendanceStateOut(state=st, start=_local(s), end=_local(e))
            for st, s, e in found.actual
        ],
        **_figures(found),  # type: ignore[arg-type]
    )
