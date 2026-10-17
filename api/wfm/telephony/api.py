from __future__ import annotations

from datetime import date

from django.conf import settings
from django.http import HttpRequest
from ninja import File, Router, Status
from ninja.files import UploadedFile

from wfm.accounts.models import Role
from wfm.core.errors import ApiError
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .models import ImportBatch, Queue
from .peaks_api import router as peaks_router
from .policy import IMPORT_ROLES, VIEW_ROLES
from .schemas import (
    Coverage,
    ImportOut,
    KpiOut,
    Metric,
    MonthsOut,
    QueueKpisOut,
    QueueOut,
    QueueSettingsIn,
)

router = Router(tags=["telephony"])
router.add_router("", peaks_router)


@router.post(
    "/imports",
    auth=RoleSessionAuth(*sorted(IMPORT_ROLES), feature=Feature.TELEPHONY),
    response={201: ImportOut},
    summary="Import an ACD Call Detail Report (.xlsx)",
)
def import_report(request: HttpRequest, file: File[UploadedFile]) -> Status[ImportOut]:
    """Reads the Call Record Report sheet, skips calls already imported, builds the 30-minute
    intervals and returns the import report with its reconciliation."""
    limit = settings.WFM_CDR_MAX_UPLOAD_MB * 1024 * 1024
    if file.size is not None and file.size > limit:
        raise ApiError(
            413,
            "import.too_large",
            "File too large",
            f"Imports are limited to {settings.WFM_CDR_MAX_UPLOAD_MB} MB.",
        )
    user = current_user(request)
    batch = services.import_cdr(user=user, file_name=file.name or "", content=file.read())
    return Status(201, _import_out(batch))


@router.get(
    "/imports",
    auth=RoleSessionAuth(*sorted(IMPORT_ROLES), feature=Feature.TELEPHONY),
    response=list[ImportOut],
    summary="Recent imports, newest first",
)
def list_imports(request: HttpRequest) -> list[ImportOut]:
    user = current_user(request)
    return [_import_out(batch) for batch in selectors.recent_imports(user)]


@router.get(
    "/queues",
    auth=RoleSessionAuth(*VIEW_ROLES, feature=Feature.TELEPHONY),
    response=list[QueueOut],
    summary="Queues the signed-in role may see",
)
def list_queues(request: HttpRequest) -> list[QueueOut]:
    user = current_user(request)
    return [_queue_out(q) for q in selectors.visible_queues(user)]


@router.put(
    "/queues/{queue_id}/settings",
    auth=RoleSessionAuth(Role.ADMIN, feature=Feature.TELEPHONY),
    response=QueueOut,
    summary="Set and confirm a queue's staffing assumptions",
)
def set_queue_settings(request: HttpRequest, queue_id: int, body: QueueSettingsIn) -> QueueOut:
    queue = services.update_queue_settings(
        user=current_user(request),
        queue_id=queue_id,
        sl_target_pct=body.slTargetPct,
        sl_threshold_s=body.slThresholdS,
        occupancy_ceiling_pct=body.occupancyCeilingPct,
        shrinkage_pct=body.shrinkagePct,
        outbound_only=body.outboundOnly,
    )
    return _queue_out(queue)


@router.get(
    "/months",
    auth=RoleSessionAuth(*VIEW_ROLES, feature=Feature.TELEPHONY),
    response=MonthsOut,
    summary="The months that have call data",
)
def list_months(request: HttpRequest) -> MonthsOut:
    return MonthsOut(months=selectors.months_with_data(current_user(request)))


@router.get(
    "/kpis",
    auth=RoleSessionAuth(*VIEW_ROLES, feature=Feature.TELEPHONY),
    response=KpiOut,
    summary="Measured service figures for a date range",
)
def kpis(
    request: HttpRequest, date_from: date, date_to: date, queue_id: int | None = None
) -> KpiOut:
    if date_to < date_from:
        raise ApiError(422, "range.invalid", "Invalid range", "date_to is before date_from.")
    if (date_to - date_from).days + 1 > selectors.MAX_RANGE_DAYS:
        raise ApiError(
            422,
            "range.too_long",
            "Range too long",
            f"Ask for at most {selectors.MAX_RANGE_DAYS} days at a time.",
        )
    user = current_user(request)
    summary = selectors.kpi_summary(user, date_from, date_to, queue_id)
    return KpiOut(
        dateFrom=date_from.isoformat(),
        dateTo=date_to.isoformat(),
        slThresholdS=settings.WFM_SL_THRESHOLD_S,
        total=_queue_kpis(summary.total, summary.intervals_total),
        queues=[_queue_kpis(q, summary.intervals_total) for q in summary.queues],
    )


def _metric(value: float | None, used: int, total: int) -> Metric:
    return Metric(
        value=value, basis="measured", coverage=Coverage(intervalsUsed=used, intervalsTotal=total)
    )


def _queue_kpis(q: selectors.QueueKpis, intervals_total: int) -> QueueKpisOut:
    def metric(value: float | None) -> Metric:
        return _metric(value, q.intervals_used, intervals_total)

    return QueueKpisOut(
        queueId=q.queue_id,
        queue=q.name,
        confirmed=q.confirmed,
        offered=q.kpis.offered,
        answered=q.kpis.answered,
        abandoned=q.kpis.abandoned,
        abandonPct=metric(q.kpis.abandon_pct),
        serviceLevelPct=metric(q.kpis.service_level_pct),
        asaS=metric(q.kpis.asa_s),
        ahtS=metric(q.kpis.aht_s),
    )


def _import_out(batch: ImportBatch) -> ImportOut:
    return ImportOut(
        id=batch.id,
        fileName=batch.file_name,
        createdAt=batch.created_at,
        uploadedBy=batch.uploaded_by.get_full_name() or batch.uploaded_by.username,
        sourceTimezone=batch.source_timezone,
        periodStart=batch.period_start,
        periodEnd=batch.period_end,
        rowsRead=batch.rows_read,
        rowsInserted=batch.rows_inserted,
        rowsDuplicate=batch.rows_duplicate,
        rowsRejected=batch.rows_rejected,
        rejectedSummary=batch.rejected_summary,
        warnings=batch.warnings_summary,
        sheetsIgnored=batch.sheets_ignored,
        reconciles=bool(batch.reconciliation.get("matches")),
        reconciliation=batch.reconciliation,
    )


def _queue_out(q: Queue) -> QueueOut:
    return QueueOut(
        id=q.pk,
        name=q.name,
        confirmed=q.confirmed,
        slTargetPct=float(q.sl_target_pct),
        slThresholdS=q.sl_threshold_s,
        occupancyCeilingPct=float(q.occupancy_ceiling_pct),
        shrinkagePct=float(q.shrinkage_pct),
        settingsConfirmed=q.settings_confirmed,
        outboundOnly=q.outbound_only,
    )
