"""Running and publishing forecasts. Writes happen here, in one transaction, with the audit event
as the LAST write (hard rule: the audit insert holds the audit-chain lock until commit)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from wfm_engine.forecast import DEFAULT_DECAY, DEFAULT_WEEKS, SlotForecast

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError, not_found
from wfm.telephony.models import Queue

from . import modeling, selectors
from .history import load_history
from .models import ForecastInterval, ForecastStatus, ForecastTuning, ForecastVersion
from .staffing import Assumptions, requirement

MAX_DAYS = 31


def run_forecast(
    *,
    user: User,
    queue_id: int,
    date_from: date,
    date_to: date,
    label: str = "",
    method: str = "baseline",
) -> ForecastVersion:
    """Forecast every day from `date_from` to `date_to` and work out the agents each half-hour
    needs. The result is a DRAFT version; publishing it is a separate, deliberate step.

    `method="smoothed"` uses the smoothed model (day-level level, pooled shape). `method="prophet"`
    asks for Prophet, which is used only if it beats the baseline on past days;
    the version records the model that was really used and, if it fell back, why (ADR 0002)."""
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    if queue.outbound_only:
        raise _refused(
            user,
            queue,
            422,
            "forecast.outbound_only",
            "This queue only makes outbound calls, so there is no inbound demand to forecast.",
        )
    if date_to < date_from:
        raise _refused(user, queue, 422, "forecast.range_invalid", "date_to is before date_from.")
    if (date_to - date_from).days + 1 > MAX_DAYS:
        raise _refused(
            user,
            queue,
            422,
            "forecast.range_too_long",
            f"Forecast at most {MAX_DAYS} days at a time.",
        )

    history, observed = load_history(queue)
    days = [date_from + timedelta(days=n) for n in range((date_to - date_from).days + 1)]
    tuning, _ = selectors.tuning_of(user, queue)
    built = modeling.build(history, observed, days, method, tuning)
    modeling.apply_uplifts(built, selectors.event_uplifts(user, queue, date_from, date_to))
    forecastable = built.days
    if not forecastable:
        raise _refused(
            user,
            queue,
            422,
            "forecast.no_history",
            "There is no earlier day with the same weekday to forecast from. Import more call "
            "data first.",
        )

    zone = ZoneInfo(settings.TIME_ZONE)
    params = {
        "weeks": DEFAULT_WEEKS,
        "decay": DEFAULT_DECAY,
        "slTargetPct": float(queue.sl_target_pct),
        "slThresholdS": queue.sl_threshold_s,
        "occupancyCeilingPct": float(queue.occupancy_ceiling_pct),
        "shrinkagePct": float(queue.shrinkage_pct),
        # DAT-10: until an admin confirms them, the staffing assumptions are defaults.
        "assumptionsConfirmed": queue.settings_confirmed,
        "daysWithoutHistory": [d.isoformat() for d in days if d not in forecastable],
        # Newest day of data it could draw on, so a forecast built on old data says so.
        "historyThrough": max(observed).isoformat(),
        **built.params,
    }
    with transaction.atomic():
        version: ForecastVersion = ForecastVersion.objects.create(
            queue=queue,
            label=label.strip()[:100],
            method=built.method,
            params=params,
            date_from=date_from,
            date_to=date_to,
            created_by=user,
        )
        intervals = [
            _interval(version, queue, day, slot, forecast, zone)
            for day, forecast in forecastable.items()
            for slot in forecast.slots
        ]
        ForecastInterval.objects.bulk_create(intervals)
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.FORECAST_RUN,
            entity_type="forecast_version",
            entity_id=str(version.id),
            changes=[
                audit.FieldChange("forecast_version", str(version.id), "queue", None, queue.name),
                audit.FieldChange(
                    "forecast_version", str(version.id), "range", None, f"{date_from}..{date_to}"
                ),
                audit.FieldChange(
                    "forecast_version", str(version.id), "intervals", None, str(len(intervals))
                ),
                audit.FieldChange(
                    "forecast_version", str(version.id), "method", None, built.method
                ),
                *_fallback_changes(version, built),
            ],
        )
    return version


def publish_forecast(*, user: User, version_id: Any) -> ForecastVersion:
    """Make a draft the live forecast of its queue, archiving the one it replaces. Publishing a
    version that is already live changes nothing, so a double click is harmless."""
    try:
        with transaction.atomic():
            found: ForecastVersion | None = (
                ForecastVersion.objects.for_user(user)
                .select_for_update(no_key=True)
                .select_related("queue")
                .filter(pk=version_id)
                .first()
            )
            if found is None:
                raise not_found("No such forecast version.")
            version = found
            if version.status == ForecastStatus.PUBLISHED:
                return version
            if version.status == ForecastStatus.ARCHIVED:
                raise ApiError(
                    409,
                    "forecast.archived",
                    "Forecast is archived",
                    "An archived forecast cannot be published again. Run the forecast again.",
                )

            changes = [
                audit.FieldChange(
                    "forecast_version", str(version.id), "status", "draft", "published"
                )
            ]
            previous = ForecastVersion.objects.filter(
                queue=version.queue, status=ForecastStatus.PUBLISHED
            ).first()
            if previous is not None:
                previous.status = ForecastStatus.ARCHIVED
                previous.save(update_fields=["status"])
                changes.append(
                    audit.FieldChange(
                        "forecast_version", str(previous.id), "status", "published", "archived"
                    )
                )
            version.status = ForecastStatus.PUBLISHED
            version.published_at = Now()
            version.save(update_fields=["status", "published_at"])
            version.refresh_from_db()
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.FORECAST_PUBLISHED,
                entity_type="forecast_version",
                entity_id=str(version.id),
                changes=changes,
            )
            return version
    except IntegrityError:
        # Two people published for the same queue at once; the database let one win.
        raise _refused(
            user,
            None,
            409,
            "forecast.conflict",
            "Another forecast was published at the same moment.",
        ) from None


def discard_forecast(*, user: User, version_id: Any, reason: str) -> None:
    """Delete a DRAFT version that was never live. Anything else is refused (409): a published
    forecast is withdrawn (archived), an archived one is history and stays."""
    with transaction.atomic():
        version = _lock(user, version_id)
        if version.status != ForecastStatus.DRAFT:
            raise ApiError(
                409,
                "forecast.not_draft",
                "Forecast is not a draft",
                "Only a draft can be discarded. Withdraw a published forecast instead.",
            )
        vid, queue_name, span = str(version.id), version.queue.name, _span(version)
        version.delete()  # its half-hours go with it
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.FORECAST_DISCARDED,
            entity_type="forecast_version",
            entity_id=vid,
            reason=reason.strip(),
            changes=[
                audit.FieldChange("forecast_version", vid, "status", "draft", "discarded"),
                audit.FieldChange("forecast_version", vid, "queue", queue_name, None),
                audit.FieldChange("forecast_version", vid, "range", span, None),
            ],
        )


def archive_forecast(*, user: User, version_id: Any, reason: str) -> ForecastVersion:
    """Withdraw the live forecast: it becomes history and the queue has no published forecast, so
    the roster, capacity and dashboard show none for it rather than old numbers. Only a PUBLISHED
    version can be withdrawn (409 otherwise)."""
    with transaction.atomic():
        version = _lock(user, version_id)
        if version.status != ForecastStatus.PUBLISHED:
            raise ApiError(
                409,
                "forecast.not_published",
                "Forecast is not published",
                "Only the live forecast can be withdrawn.",
            )
        version.status = ForecastStatus.ARCHIVED
        version.save(update_fields=["status"])
        audit.record(  # last write of the transaction
            actor=user,
            action=Action.FORECAST_ARCHIVED,
            entity_type="forecast_version",
            entity_id=str(version.id),
            reason=reason.strip(),
            changes=[
                audit.FieldChange(
                    "forecast_version", str(version.id), "status", "published", "archived"
                )
            ],
        )
        return version


def _lock(user: User, version_id: Any) -> ForecastVersion:
    version: ForecastVersion | None = (
        ForecastVersion.objects.for_user(user)
        .select_for_update(no_key=True, of=("self",))
        .select_related("queue")
        .filter(pk=version_id)
        .first()
    )
    if version is None:
        raise not_found("No such forecast version.")
    return version


def _span(version: ForecastVersion) -> str:
    return f"{version.date_from}..{version.date_to}"


def set_tuning(*, user: User, queue_id: int, tuning: modeling.Tuning) -> ForecastTuning:
    """Save how a queue's forecast is tuned. Forecasts already run are not changed."""
    modeling.check_tuning(tuning)
    with transaction.atomic():
        queue: Queue | None = (
            Queue.objects.select_for_update(no_key=True).for_user(user).filter(pk=queue_id).first()
        )
        if queue is None:
            raise not_found("No such queue.")
        row = ForecastTuning.objects.select_for_update(no_key=True).filter(queue=queue).first()
        before = modeling.DEFAULT_TUNING if row is None else _tuning_of_row(row)
        changes = [
            audit.FieldChange("forecast_tuning", str(queue.pk), name, str(old), str(new))
            for name, old, new in (
                ("weeks", before.weeks, tuning.weeks),
                ("decay", before.decay, tuning.decay),
                ("volume_multiplier", before.volume_multiplier, tuning.volume_multiplier),
                ("aht_multiplier", before.aht_multiplier, tuning.aht_multiplier),
            )
            if old != new
        ]
        if row is None:
            changes.append(
                audit.FieldChange("forecast_tuning", str(queue.pk), "saved", "False", "True")
            )
            row = ForecastTuning(queue=queue)
        row.weeks = tuning.weeks
        row.decay = Decimal(str(tuning.decay))
        row.volume_multiplier = Decimal(str(tuning.volume_multiplier))
        row.aht_multiplier = Decimal(str(tuning.aht_multiplier))
        row.updated_by = user
        row.save()
        if changes:
            audit.record(  # last write of the transaction
                actor=user,
                action=Action.FORECAST_TUNING_CHANGED,
                entity_type="forecast_tuning",
                entity_id=str(queue.pk),
                changes=changes,
            )
    return row


def _tuning_of_row(row: ForecastTuning) -> modeling.Tuning:
    return modeling.Tuning(
        row.weeks, float(row.decay), float(row.volume_multiplier), float(row.aht_multiplier)
    )


# --- helpers ---------------------------------------------------------------------------------


def _fallback_changes(version: ForecastVersion, built: modeling.Built) -> list[audit.FieldChange]:
    fallback = built.params.get("fallback")
    if not fallback:
        return []
    return [
        audit.FieldChange(
            "forecast_version", str(version.id), "fallback", "prophet", fallback["reason"]
        )
    ]


def _interval(
    version: ForecastVersion,
    queue: Queue,
    day: date,
    slot: SlotForecast,
    forecast: modeling.DayForecast,
    zone: ZoneInfo,
) -> ForecastInterval:
    start = datetime.combine(day, time(slot.slot // 2, 30 * (slot.slot % 2)), tzinfo=zone)
    raw, with_shrinkage = requirement(slot.volume, slot.aht_s, Assumptions.of_queue(queue))
    # The day's range, shared out in the same proportion as the day's expected total.
    expected = sum(s.volume for s in forecast.slots)
    share = slot.volume / expected if expected > 0 else 0.0
    return ForecastInterval(
        version=version,
        interval_start=start,
        volume=slot.volume,
        volume_lower=None if forecast.lower is None else forecast.lower * share,
        volume_upper=None if forecast.upper is None else forecast.upper * share,
        aht_s=slot.aht_s,
        required_raw=raw,
        required=with_shrinkage,
        days_used=slot.days_used,
    )


def _refused(user: User, queue: Queue | None, status: int, code: str, detail: str) -> ApiError:
    audit.record(
        actor=user,
        action=Action.FORECAST_REFUSED,
        outcome=Outcome.FAILED,
        entity_type="queue" if queue else "forecast_version",
        entity_id=queue.name if queue else "",
        reason=code,
    )
    return ApiError(status, code, "Forecast refused", detail)
