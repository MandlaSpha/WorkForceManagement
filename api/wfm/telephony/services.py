"""Importing a Call Detail Report (DAT-01..04).

Two steps with different rules:
- `_plan` reads the file and the database and decides whether the import may go ahead. It writes
  nothing, so refusing is always safe.
- `_store` writes everything in one transaction, with the audit event as the LAST write (hard
  rule: the audit insert holds the audit-chain lock until commit).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from wfm_engine.cdr import CallRow
from wfm_engine.kpi import INTERVAL_MINUTES, interval_start

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError

from . import intervals, reconciliation
from .models import CallRecord, ImportBatch, Queue
from .workbook import ParsedWorkbook, WorkbookError, read_call_records

INSERT_CHUNK = 2000
LOOKUP_CHUNK = 5000
_UNSAFE_NAME = re.compile(r"[^\w .()\-]+")


class _RefusedError(Exception):
    """An import that must not go ahead. Turned into an audited ApiError in one place."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str,
        violations: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(code)
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.violations = violations or []


@dataclass(frozen=True)
class _Plan:
    parsed: ParsedWorkbook
    fresh: list[CallRow]  # calls not yet in the system, first occurrence only
    rows_duplicate: int
    zone: ZoneInfo
    period_start: datetime
    period_end: datetime


def import_cdr(*, user: User, file_name: str, content: bytes) -> ImportBatch:
    """Import one workbook. Refuses (and audits the refusal) when the file is unusable or adds
    nothing new; otherwise stores the calls, rebuilds the 30-minute intervals, reconciles and
    audits, atomically."""
    digest = hashlib.sha256(content).hexdigest()
    try:
        plan = _plan(digest, content)
    except _RefusedError as refused:
        raise _audited(user, digest, refused) from None
    try:
        return _store(user, _safe_name(file_name), digest, plan)
    except IntegrityError:
        # Two uploads of the same data at once (a double click) both passed `_plan`. The database
        # constraints let exactly one win and rolled the other back; say so instead of a 500.
        raise _audited(
            user,
            digest,
            _RefusedError(
                409,
                "import.conflict",
                "Import conflict",
                "The same data was imported at the same moment. Check the import list.",
            ),
        ) from None


def _plan(digest: str, content: bytes) -> _Plan:
    if ImportBatch.objects.filter(sha256=digest).exists():
        raise _RefusedError(
            409,
            "import.duplicate_file",
            "File already imported",
            "This exact file was imported before.",
        )

    try:
        parsed = read_call_records(content)
    except WorkbookError as error:
        violations = [{"field": name, "code": error.code} for name in error.columns]
        raise _RefusedError(422, error.code, "Unusable file", error.detail, violations) from None
    if not parsed.rows:
        raise _RefusedError(
            422, "import.no_rows", "Unusable file", "The sheet has no readable call rows."
        )

    zone = ZoneInfo(settings.WFM_CDR_SOURCE_TIMEZONE)
    calls = _first_occurrences(parsed)
    period_start = min(c.start_at for c in calls).replace(tzinfo=zone)
    period_end = max(c.start_at for c in calls).replace(tzinfo=zone)
    if ImportBatch.objects.filter(
        period_start=period_start, period_end=period_end, rows_read=parsed.rows_read
    ).exists():
        raise _RefusedError(
            409,
            "import.duplicate_period",
            "Period already imported",
            "A file with the same date range and row count was imported before. A different "
            "month is needed (this catches a month exported twice).",
        )

    known = _known_call_ids([c.call_id for c in calls])
    fresh = [c for c in calls if c.call_id not in known]
    if not fresh:
        raise _RefusedError(
            409,
            "import.nothing_new",
            "Nothing new to import",
            "Every call in this file is already in the system.",
        )
    return _Plan(
        parsed=parsed,
        fresh=fresh,
        rows_duplicate=len(parsed.rows) - len(fresh),
        zone=zone,
        period_start=period_start,
        period_end=period_end,
    )


def _store(user: User, file_name: str, digest: str, plan: _Plan) -> ImportBatch:
    parsed, fresh, zone = plan.parsed, plan.fresh, plan.zone
    first = interval_start(min(c.start_at for c in fresh).replace(tzinfo=zone))
    end = interval_start(max(c.start_at for c in fresh).replace(tzinfo=zone)) + timedelta(
        minutes=INTERVAL_MINUTES
    )
    with transaction.atomic():
        queues = _ensure_queues({c.queue for c in fresh})
        batch = ImportBatch.objects.create(
            file_name=file_name,
            sha256=digest,
            uploaded_by=user,
            source_timezone=settings.WFM_CDR_SOURCE_TIMEZONE,
            period_start=plan.period_start,
            period_end=plan.period_end,
            rows_read=parsed.rows_read,
            rows_inserted=len(fresh),
            rows_duplicate=plan.rows_duplicate,
            rows_rejected=sum(parsed.rejected.values()),
            rejected_summary=dict(parsed.rejected),
            rejected_samples=parsed.rejected_samples,
            warnings_summary=dict(parsed.warnings),
            sheets_ignored=parsed.sheets_ignored,
        )
        _insert_calls(batch, fresh, queues, zone)
        intervals.rebuild([q.pk for q in queues.values()], first, end)
        batch.reconciliation = reconciliation.reconcile(batch, fresh, first, end)
        batch.save(update_fields=["reconciliation"])

        audit.record(  # last write of the transaction
            actor=user,
            action=Action.CDR_IMPORTED,
            entity_type="import_batch",
            entity_id=str(batch.id),
            batch_id=batch.id,
            changes=[
                audit.FieldChange("import_batch", str(batch.id), name, None, str(value))
                for name, value in (
                    ("rows_read", batch.rows_read),
                    ("rows_inserted", batch.rows_inserted),
                    ("rows_duplicate", batch.rows_duplicate),
                    ("rows_rejected", batch.rows_rejected),
                    ("reconciles", batch.reconciliation["matches"]),
                )
            ],
        )
    return batch


def _audited(user: User, digest: str, refused: _RefusedError) -> ApiError:
    """Audit a refusal in its own committed transaction, then hand back the error to raise."""
    audit.record(
        actor=user,
        action=Action.CDR_IMPORT_REFUSED,
        outcome=Outcome.FAILED,
        entity_type="import_file",
        entity_id=digest[:16],
        reason=refused.code,
    )
    return ApiError(refused.status, refused.code, refused.title, refused.detail, refused.violations)


def _safe_name(file_name: str) -> str:
    base = file_name.replace("\\", "/").rsplit("/", 1)[-1]
    return _UNSAFE_NAME.sub("_", base)[:255] or "upload.xlsx"


def _first_occurrences(parsed: ParsedWorkbook) -> list[CallRow]:
    seen: set[int] = set()
    kept: list[CallRow] = []
    for _, row in parsed.rows:
        if row.call_id not in seen:
            seen.add(row.call_id)
            kept.append(row)
    return kept


def _known_call_ids(call_ids: Sequence[int]) -> set[int]:
    known: set[int] = set()
    for at in range(0, len(call_ids), LOOKUP_CHUNK):
        chunk = call_ids[at : at + LOOKUP_CHUNK]
        known.update(CallRecord.objects.filter(call_id__in=chunk).values_list("call_id", flat=True))
    return known


def _ensure_queues(names: set[str]) -> dict[str, Queue]:
    """Queues are created on first sight, unconfirmed, for an admin to confirm."""
    Queue.objects.bulk_create([Queue(name=n) for n in sorted(names)], ignore_conflicts=True)
    return {q.name: q for q in Queue.objects.filter(name__in=names)}


def _aware(moment: datetime | None, zone: ZoneInfo) -> datetime | None:
    return moment.replace(tzinfo=zone) if moment else None


def _insert_calls(
    batch: ImportBatch, calls: Sequence[CallRow], queues: dict[str, Queue], zone: ZoneInfo
) -> None:
    for at in range(0, len(calls), INSERT_CHUNK):
        CallRecord.objects.bulk_create(
            [
                CallRecord(
                    call_id=c.call_id,
                    batch=batch,
                    queue=queues[c.queue],
                    call_type=c.call_type,
                    status=c.status,
                    agent_login=c.agent_login or "",
                    start_at=c.start_at.replace(tzinfo=zone),
                    queue_at=_aware(c.queue_at, zone),
                    agent_at=_aware(c.agent_at, zone),
                    hangup_at=_aware(c.hangup_at, zone),
                    call_duration_s=c.call_duration_s,
                    wait_s=c.wait_s,
                    talk_s=c.talk_s,
                    wrap_s=c.wrap_s,
                    hold_s=c.hold_s,
                    hangup_by=c.hangup_by,
                )
                for c in calls[at : at + INSERT_CHUNK]
            ]
        )
