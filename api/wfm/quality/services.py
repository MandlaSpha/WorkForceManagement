"""Importing quality results (QUA-01).

Logins are mapped to people through `AgentLogin`; an unmapped login is reported, never guessed and
never stored. A bad row is reported with a reason and its line number and not stored. A result
already held (same person, day, kind and reference) is updated when the file says something
different, so the quality tool stays the source of truth. The audit event carries counts only: no
login, name, score or date.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError
from wfm.scheduling.employee_import import UnreadableFileError
from wfm.scheduling.models import AgentLogin

from . import importer
from .models import QualityImport, QualityResult
from .policy import MAX_UPLOAD_BYTES, SHOWN_UNMAPPED

CHUNK = 2000


@dataclass(frozen=True, slots=True)
class ImportResult:
    batch: QualityImport
    errors: list[tuple[int, str]]
    ignored_columns: list[str]
    unmapped_logins: list[str]  # the first few, sorted
    unmapped_login_count: int


def _refuse(status: int, code: str, detail: str) -> ApiError:
    return ApiError(status, code, "Quality import refused", detail)


def import_results(*, user: User, file_name: str, content: bytes) -> ImportResult:
    if len(content) > MAX_UPLOAD_BYTES:
        raise _refuse(
            413, "quality.too_large", f"Files are limited to {MAX_UPLOAD_BYTES // 2**20} MB."
        )
    try:
        parsed = importer.parse(content, file_name, timezone.localdate())
    except UnreadableFileError as error:
        audit.record(
            actor=user,
            action=Action.QUALITY_IMPORT_REFUSED,
            outcome=Outcome.FAILED,
            entity_type="quality_import",
            reason="unreadable",
        )
        raise _refuse(422, "quality.unreadable", str(error)) from error
    if parsed.rows_read == 0:
        raise _refuse(422, "quality.empty", "The file has no rows.")

    logins = {e.login for _, e in parsed.rows}
    mapping = dict(AgentLogin.objects.filter(login__in=logins).values_list("login", "employee_id"))
    unmapped = sorted(logins - mapping.keys())
    usable = [e for _, e in parsed.rows if e.login in mapping]
    unmapped_rows = len(parsed.rows) - len(usable)

    with transaction.atomic():
        held = {
            (r.employee_id, r.evaluated_on, r.kind, r.ref): r
            for r in QualityResult.objects.filter(
                employee_id__in={mapping[e.login] for e in usable},
                evaluated_on__in={e.evaluated_on for e in usable},
            )
        }
        batch = QualityImport.objects.create(
            file_name=file_name[:255],
            uploaded_by=user,
            rows_read=parsed.rows_read,
            rows_created=0,
            rows_updated=0,
            rows_unchanged=0,
            rows_rejected=parsed.rejected,
            rows_unmapped=unmapped_rows,
        )
        create: list[QualityResult] = []
        update: list[QualityResult] = []
        unchanged = 0
        for e in usable:
            employee_id = mapping[e.login]
            values = {
                "score_pct": Decimal(str(e.score_pct)),
                "csat": e.csat,
                "coaching_due": e.coaching_due,
            }
            current = held.get((employee_id, e.evaluated_on, e.kind, e.ref))
            if current is None:
                create.append(
                    QualityResult(
                        batch=batch,
                        employee_id=employee_id,
                        evaluated_on=e.evaluated_on,
                        kind=e.kind,
                        ref=e.ref,
                        **values,
                    )
                )
            elif any(getattr(current, name) != value for name, value in values.items()):
                for name, value in values.items():
                    setattr(current, name, value)
                current.batch = batch
                update.append(current)
            else:
                unchanged += 1
        QualityResult.objects.bulk_create(create, batch_size=CHUNK)
        QualityResult.objects.bulk_update(
            update, ["score_pct", "csat", "coaching_due", "batch"], batch_size=CHUNK
        )
        batch.rows_created, batch.rows_updated, batch.rows_unchanged = (
            len(create),
            len(update),
            unchanged,
        )
        batch.save(update_fields=["rows_created", "rows_updated", "rows_unchanged"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.QUALITY_IMPORTED,
            entity_type="quality_import",
            entity_id=str(batch.pk),
            changes=[
                audit.FieldChange("quality_import", str(batch.pk), name, None, str(value))
                for name, value in (
                    ("rows_read", batch.rows_read),
                    ("rows_created", batch.rows_created),
                    ("rows_updated", batch.rows_updated),
                    ("rows_unchanged", batch.rows_unchanged),
                    ("rows_rejected", batch.rows_rejected),
                    ("rows_unmapped", batch.rows_unmapped),
                )
            ],
        )
    return ImportResult(
        batch=batch,
        errors=parsed.errors,
        ignored_columns=parsed.ignored_columns,
        unmapped_logins=unmapped[:SHOWN_UNMAPPED],
        unmapped_login_count=len(unmapped),
    )
