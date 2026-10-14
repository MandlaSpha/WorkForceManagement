"""Reading forecasts. Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q
from wfm_engine.forecast import DEFAULT_DECAY, DEFAULT_WEEKS, DayAccuracy, backtest

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.telephony.models import Queue

from . import modeling, scenario
from .history import load_history
from .models import ForecastEvent, ForecastInterval, ForecastVersion


def list_versions(user: User, queue_id: int | None = None) -> list[ForecastVersion]:
    versions = (
        ForecastVersion.objects.for_user(user)
        .select_related("queue", "created_by")
        .annotate(interval_count=Count("intervals"))
    )
    if queue_id is not None:
        versions = versions.filter(queue_id=queue_id)
    return list(versions.order_by("-created_at"))


def version_intervals(user: User, version_id: Any) -> list[ForecastInterval]:
    if not ForecastVersion.objects.for_user(user).filter(pk=version_id).exists():
        raise not_found("No such forecast version.")
    return list(
        ForecastInterval.objects.for_user(user)
        .filter(version_id=version_id)
        .order_by("interval_start")
    )


@dataclass(frozen=True, slots=True)
class Accuracy:
    queue: Queue
    overall_pct: float | None  # per half-hour
    overall_daily_pct: float | None  # per day total
    days: list[DayAccuracy]
    weeks: int
    decay: float


def forecast_accuracy(user: User, queue_id: int, method: str = "baseline") -> Accuracy:
    """How well a model would have predicted each past day, using only the days before it (FC-05).
    Measured on real imported data; nothing here is modelled. For Prophet the days are the ones it
    could be refitted for (see `prophet_model.rolling_forecasts`)."""
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    history, observed = load_history(queue)
    result = (
        modeling.prophet_backtest(history, observed)[0]
        if method == "prophet"
        else backtest(history, observed)
    )
    return Accuracy(
        queue, result.interval_pct, result.daily_pct, result.days, DEFAULT_WEEKS, DEFAULT_DECAY
    )


def list_events(user: User, queue_id: int | None = None) -> list[ForecastEvent]:
    """Events, soonest first. With a queue: that queue's own and those for all queues."""
    events = ForecastEvent.objects.for_user(user).select_related("queue")
    if queue_id is not None:
        events = events.filter(Q(queue_id=queue_id) | Q(queue__isnull=True))
    return list(events)


def event_uplifts(
    user: User, queue: Queue, date_from: date, date_to: date
) -> list[modeling.Uplift]:
    """The events that touch the days a forecast covers, as the uplifts it applies."""
    events = (
        ForecastEvent.objects.for_user(user)
        .filter(Q(queue=queue) | Q(queue__isnull=True))
        .filter(date_from__lte=date_to, date_to__gte=date_from)
    )
    return [
        modeling.Uplift(e.pk, e.name, e.date_from, e.date_to, float(e.uplift_pct)) for e in events
    ]


def scenario_source(user: User, version_id: Any) -> tuple[ForecastVersion, list[scenario.Row]]:
    """A forecast version and its half-hours in the shape a scenario works on."""
    version: ForecastVersion | None = (
        ForecastVersion.objects.for_user(user).select_related("queue").filter(pk=version_id).first()
    )
    if version is None:
        raise not_found("No such forecast version.")
    zone = ZoneInfo(settings.TIME_ZONE)
    rows = [
        scenario.Row(i.interval_start.astimezone(zone).date(), i.volume, i.aht_s, i.required)
        for i in ForecastInterval.objects.for_user(user).filter(version=version)
    ]
    return version, rows
