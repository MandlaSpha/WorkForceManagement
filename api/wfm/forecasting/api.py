from __future__ import annotations

from typing import Literal
from uuid import UUID

from django.http import HttpRequest
from ninja import Router, Status

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import event_services, selectors, services
from .models import ForecastEvent, ForecastInterval, ForecastVersion
from .policy import READ_ROLES, WRITE_ROLES
from .schemas import (
    AccuracyOut,
    DayAccuracyOut,
    EventIn,
    EventOut,
    ForecastIntervalOut,
    ForecastVersionOut,
    RunForecastIn,
)

router = Router(tags=["forecasting"])

READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.FORECASTING)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=Feature.FORECASTING)


@router.post(
    "/versions",
    auth=WRITE,
    response={201: ForecastVersionOut},
    summary="Run a forecast for a queue and a range of days (a draft)",
)
def run_forecast(request: HttpRequest, body: RunForecastIn) -> Status[ForecastVersionOut]:
    version = services.run_forecast(
        user=current_user(request),
        queue_id=body.queueId,
        date_from=body.dateFrom,
        date_to=body.dateTo,
        label=body.label,
        method=body.method,
    )
    return Status(201, _version_out(version, interval_count=version.intervals.count()))


@router.get(
    "/versions",
    auth=READ,
    response=list[ForecastVersionOut],
    summary="Forecast versions, newest first",
)
def list_versions(request: HttpRequest, queue_id: int | None = None) -> list[ForecastVersionOut]:
    versions = selectors.list_versions(current_user(request), queue_id)
    return [_version_out(v, interval_count=getattr(v, "interval_count", 0)) for v in versions]


@router.post(
    "/versions/{version_id}/publish",
    auth=WRITE,
    response=ForecastVersionOut,
    summary="Make a draft the live forecast of its queue",
)
def publish_version(request: HttpRequest, version_id: UUID) -> ForecastVersionOut:
    version = services.publish_forecast(user=current_user(request), version_id=version_id)
    return _version_out(version, interval_count=version.intervals.count())


@router.get(
    "/versions/{version_id}/intervals",
    auth=READ,
    response=list[ForecastIntervalOut],
    summary="The half-hour forecast and staffing requirement of a version",
)
def version_intervals(request: HttpRequest, version_id: UUID) -> list[ForecastIntervalOut]:
    return [
        _interval_out(i) for i in selectors.version_intervals(current_user(request), version_id)
    ]


@router.get(
    "/accuracy",
    auth=READ,
    response=AccuracyOut,
    summary="How well a model would have predicted each past day (backtest)",
)
def accuracy(
    request: HttpRequest, queue_id: int, method: Literal["baseline", "prophet"] = "baseline"
) -> AccuracyOut:
    result = selectors.forecast_accuracy(current_user(request), queue_id, method)
    return AccuracyOut(
        queueId=result.queue.pk,
        queue=result.queue.name,
        overallAccuracyPct=result.overall_pct,
        overallDailyAccuracyPct=result.overall_daily_pct,
        weeks=result.weeks,
        decay=result.decay,
        days=[
            DayAccuracyOut(
                date=d.day,
                accuracyPct=d.accuracy_pct,
                dailyAccuracyPct=d.daily_pct,
                daysUsed=d.days_used,
            )
            for d in result.days
        ],
    )


@router.get(
    "/events", auth=READ, response=list[EventOut], summary="The events calendar, soonest first"
)
def list_events(request: HttpRequest, queue_id: int | None = None) -> list[EventOut]:
    return [_event_out(e) for e in selectors.list_events(current_user(request), queue_id)]


@router.post("/events", auth=WRITE, response={201: EventOut}, summary="Add an event")
def create_event(request: HttpRequest, body: EventIn) -> Status[EventOut]:
    event = event_services.create_event(
        user=current_user(request),
        name=body.name,
        queue_id=body.queueId,
        date_from=body.dateFrom,
        date_to=body.dateTo,
        uplift_pct=body.upliftPct,
    )
    return Status(201, _event_out(event))


@router.put("/events/{event_id}", auth=WRITE, response=EventOut, summary="Change an event")
def update_event(request: HttpRequest, event_id: int, body: EventIn) -> EventOut:
    event = event_services.update_event(
        user=current_user(request),
        event_id=event_id,
        name=body.name,
        queue_id=body.queueId,
        date_from=body.dateFrom,
        date_to=body.dateTo,
        uplift_pct=body.upliftPct,
    )
    return _event_out(event)


@router.delete(
    "/events/{event_id}", auth=WRITE, response=dict[str, bool], summary="Remove an event"
)
def delete_event(request: HttpRequest, event_id: int) -> dict[str, bool]:
    event_services.delete_event(user=current_user(request), event_id=event_id)
    return {"ok": True}


def _event_out(event: ForecastEvent) -> EventOut:
    return EventOut(
        id=event.pk,
        name=event.name,
        queueId=event.queue_id,
        queue=event.queue.name if event.queue else None,
        dateFrom=event.date_from,
        dateTo=event.date_to,
        upliftPct=float(event.uplift_pct),
    )


def _version_out(version: ForecastVersion, *, interval_count: int) -> ForecastVersionOut:
    return ForecastVersionOut(
        id=version.id,
        queueId=version.queue_id,
        queue=version.queue.name,
        label=version.label,
        status=version.status,
        method=version.method,
        dateFrom=version.date_from,
        dateTo=version.date_to,
        createdAt=version.created_at,
        createdBy=version.created_by.get_full_name() or version.created_by.username,
        publishedAt=version.published_at,
        intervalCount=interval_count,
        assumptionsConfirmed=bool(version.params.get("assumptionsConfirmed")),
        fallback=version.params.get("fallback"),
        daysWithoutHistory=version.params.get("daysWithoutHistory", []),
        historyThrough=version.params.get("historyThrough"),
        params=version.params,
    )


def _interval_out(interval: ForecastInterval) -> ForecastIntervalOut:
    return ForecastIntervalOut(
        start=interval.interval_start,
        volume=interval.volume,
        volumeLower=interval.volume_lower,
        volumeUpper=interval.volume_upper,
        ahtS=interval.aht_s,
        requiredRaw=interval.required_raw,
        required=interval.required,
        daysUsed=interval.days_used,
    )
