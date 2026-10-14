"""Running and publishing forecasts. Writes happen here, in one transaction, with the audit event
as the LAST write (hard rule: the audit insert holds the audit-chain lock until commit)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models.functions import Now
from wfm_engine.erlang import required_agents
from wfm_engine.forecast import DEFAULT_DECAY, DEFAULT_WEEKS, SlotForecast
from wfm_engine.kpi import INTERVAL_MINUTES

from wfm.accounts.models import User
from wfm.audit import services as audit
from wfm.audit.models import Action, Outcome
from wfm.core.errors import ApiError, not_found
from wfm.telephony.models import Queue

from . import modeling, selectors
from .history import load_history
from .models import ForecastInterval, ForecastStatus, ForecastVersion

MAX_DAYS = 31
INTERVAL_S = INTERVAL_MINUTES * 60


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

    `method="prophet"` asks for Prophet, which is used only if it beats the baseline on past days;
    the version records the model that was really used and, if it fell back, why (ADR 0002)."""
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
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
    built = modeling.build(history, observed, days, method)
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
                .select_for_update()
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
    raw, with_shrinkage = _requirement(slot.volume, slot.aht_s, queue)
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


def _requirement(volume: float, aht_s: float | None, queue: Queue) -> tuple[int | None, int | None]:
    """Agents needed on the phone, and agents to roster once shrinkage is added (ENG-01, ENG-02).
    No call volume needs nobody; calls with no known handling time cannot be staffed honestly."""
    if volume <= 0:
        return 0, 0
    if aht_s is None or aht_s <= 0:
        return None, None
    common: dict[str, Any] = {
        "volume": volume,
        "interval_s": INTERVAL_S,
        "aht_s": aht_s,
        "sl_target": float(queue.sl_target_pct) / 100,
        "threshold_s": queue.sl_threshold_s,
        "occupancy_ceiling": float(queue.occupancy_ceiling_pct) / 100,
    }
    try:
        raw = required_agents(**common, shrinkage=0.0)
        with_shrinkage = required_agents(**common, shrinkage=float(queue.shrinkage_pct) / 100)
    except ValueError:
        return None, None
    return raw, with_shrinkage


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
