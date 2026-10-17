"""Importing agent-state intervals (ATT-01).

Logins are mapped to people through `AgentLogin`; an unmapped login is reported, never guessed and
never stored. A bad row is reported with a reason and not stored. An interval already held (same
login and start) is skipped. The audit event carries counts only: no login, name or time.
"""

from __future__ import annotations

from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from wfm_engine.adherence import ParsedStates, parse_state_csv

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action
from wfm.core.errors import ApiError
from wfm.scheduling.models import AgentLogin

from .models import AgentStateImport, AgentStateInterval
from .policy import MAX_ROWS, MAX_UPLOAD_BYTES

SHOWN_UNMAPPED = 50


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch: AgentStateImport
    parsed: ParsedStates
    unmapped_logins: list[str]  # the first few, sorted
    unmapped_login_count: int


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Attendance import refused", detail)


def import_states(*, user: User, file_name: str, content: bytes) -> ImportResult:
    if len(content) > MAX_UPLOAD_BYTES:
        raise _refuse(
            413, "attendance.too_large", f"Files are limited to {MAX_UPLOAD_BYTES // 2**20} MB."
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as bad:
        raise _refuse(422, "attendance.not_utf8", "The file must be UTF-8 text (CSV).") from bad
    parsed = parse_state_csv(text)
    if parsed.header_error:
        raise _refuse(422, "attendance.bad_header", parsed.header_error)
    if parsed.rows_read == 0:
        raise _refuse(422, "attendance.empty", "The file has no rows.")
    if parsed.rows_read > MAX_ROWS:
        raise _refuse(422, "attendance.too_many_rows", f"At most {MAX_ROWS} rows a file.")

    zone = ZoneInfo(settings.TIME_ZONE)
    logins = {r.login for r in parsed.rows}
    mapping = dict(AgentLogin.objects.filter(login__in=logins).values_list("login", "employee_id"))
    unmapped = sorted(logins - mapping.keys())

    # One interval per login and start: the first in the file wins, then anything already held.
    seen: set[tuple[str, object]] = set()
    fresh = []
    duplicates = unmapped_rows = 0
    for row in parsed.rows:
        if row.login not in mapping:
            unmapped_rows += 1
            continue
        start = row.start.replace(tzinfo=zone)
        if (row.login, start) in seen:
            duplicates += 1
            continue
        seen.add((row.login, start))
        fresh.append((row, start))

    with transaction.atomic():
        held: set[tuple[str, object]] = set()
        if fresh:
            held = set(
                AgentStateInterval.objects.filter(
                    login__in={r.login for r, _ in fresh},
                    start_at__gte=min(s for _, s in fresh),
                    start_at__lte=max(s for _, s in fresh),
                ).values_list("login", "start_at")
            )
        todo = [(r, s) for r, s in fresh if (r.login, s) not in held]
        duplicates += len(fresh) - len(todo)
        batch = AgentStateImport.objects.create(
            file_name=file_name[:255],
            uploaded_by=user,
            rows_read=parsed.rows_read,
            rows_inserted=len(todo),
            rows_duplicate=duplicates,
            rows_rejected=parsed.rows_rejected,
            rows_unmapped=unmapped_rows,
        )
        AgentStateInterval.objects.bulk_create(
            [
                AgentStateInterval(
                    batch=batch,
                    employee_id=mapping[r.login],
                    login=r.login,
                    state=r.state,
                    start_at=s,
                    end_at=r.end.replace(tzinfo=zone),
                )
                for r, s in todo
            ],
            batch_size=2000,
            ignore_conflicts=True,  # a second upload racing this one cannot make it fail
        )
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.ATTENDANCE_IMPORTED,
            entity_type="attendance_import",
            entity_id=str(batch.pk),
            changes=[
                audit.FieldChange("attendance_import", str(batch.pk), name, None, str(value))
                for name, value in (
                    ("rows_read", batch.rows_read),
                    ("rows_inserted", batch.rows_inserted),
                    ("rows_duplicate", batch.rows_duplicate),
                    ("rows_rejected", batch.rows_rejected),
                    ("rows_unmapped", batch.rows_unmapped),
                )
            ],
        )
    return ImportResult(
        batch=batch,
        parsed=parsed,
        unmapped_logins=unmapped[:SHOWN_UNMAPPED],
        unmapped_login_count=len(unmapped),
    )
