"""Reading forecasts. Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Count
from wfm_engine.forecast import DEFAULT_DECAY, DEFAULT_WEEKS, DayAccuracy, backtest

from wfm.accounts.models import User
from wfm.core.errors import not_found
from wfm.telephony.models import Queue

from .history import load_history
from .models import ForecastInterval, ForecastVersion


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


def forecast_accuracy(user: User, queue_id: int) -> Accuracy:
    """How well the baseline would have predicted each past day, using only the days before it
    (FC-05). Measured on real imported data; nothing here is modelled."""
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    history, observed = load_history(queue)
    result = backtest(history, observed)
    return Accuracy(
        queue, result.interval_pct, result.daily_pct, result.days, DEFAULT_WEEKS, DEFAULT_DECAY
    )
