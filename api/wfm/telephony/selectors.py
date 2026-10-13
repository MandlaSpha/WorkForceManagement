"""Reading call data. Everything starts from `Model.objects.for_user(user)` so a role only ever
sees the queues it may see, and only aggregates, never a call or a person."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce, TruncMonth
from wfm_engine.kpi import INTERVAL_MINUTES, Kpis, Totals, kpis

from wfm.accounts.models import User
from wfm.core.errors import not_found

from .models import ImportBatch, IntervalActual, Queue

INTERVALS_PER_DAY = 24 * 60 // INTERVAL_MINUTES
MAX_RANGE_DAYS = 366


@dataclass(frozen=True, slots=True)
class QueueKpis:
    queue_id: int | None  # None for the all-queues total
    name: str
    confirmed: bool
    totals: Totals
    kpis: Kpis
    intervals_used: int


@dataclass(frozen=True, slots=True)
class KpiSummary:
    date_from: date
    date_to: date
    intervals_total: int  # 30-minute intervals in the range: the most any queue could have
    total: QueueKpis
    queues: list[QueueKpis]


def visible_queues(user: User) -> list[Queue]:
    return list(Queue.objects.for_user(user).order_by("name"))


def recent_imports(user: User, limit: int = 50) -> list[ImportBatch]:
    return list(
        ImportBatch.objects.for_user(user)
        .select_related("uploaded_by")
        .order_by("-created_at")[:limit]
    )


def months_with_data(user: User) -> list[str]:
    """The calendar months (`YYYY-MM`, South African time) that have call data this role may see,
    oldest first. The dashboard offers exactly these, and opens on the latest."""
    zone = ZoneInfo(settings.TIME_ZONE)
    months = (
        IntervalActual.objects.for_user(user)
        .annotate(month=TruncMonth("interval_start", tzinfo=zone))
        .values_list("month", flat=True)
        .distinct()
        .order_by("month")
    )
    return [m.astimezone(zone).strftime("%Y-%m") for m in months]


def kpi_summary(
    user: User, date_from: date, date_to: date, queue_id: int | None = None
) -> KpiSummary:
    """Measured service figures for the days from `date_from` to `date_to` inclusive, in the
    display time zone (Africa/Johannesburg). Days with no calls simply contribute nothing."""
    queues = Queue.objects.for_user(user)
    if queue_id is not None:
        queues = queues.filter(pk=queue_id)
        if not queues.exists():
            raise not_found("No such queue.")

    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    days = (date_to - date_from).days + 1

    rows = {
        row["queue_id"]: row
        for row in IntervalActual.objects.for_user(user)
        .filter(queue__in=queues, interval_start__gte=start, interval_start__lt=end)
        .values("queue_id")
        .annotate(
            used=Count("id"),
            offered_=Coalesce(Sum("offered"), 0),
            answered_=Coalesce(Sum("answered"), 0),
            abandoned_=Coalesce(Sum("abandoned"), 0),
            in_sl=Coalesce(Sum("answered_in_sl"), 0),
            wait=Coalesce(Sum("sum_wait_s"), 0),
            handle=Coalesce(Sum("sum_handle_s"), 0),
        )
    }

    result: list[QueueKpis] = []
    grand = Totals()
    for queue in queues.order_by("name"):
        row = rows.get(queue.pk)
        totals = (
            Totals(
                offered=row["offered_"],
                answered=row["answered_"],
                abandoned=row["abandoned_"],
                answered_in_sl=row["in_sl"],
                sum_wait_s=row["wait"],
                sum_handle_s=row["handle"],
            )
            if row
            else Totals()
        )
        grand = grand + totals
        result.append(
            QueueKpis(
                queue.pk,
                queue.name,
                queue.confirmed,
                totals,
                kpis(totals),
                row["used"] if row else 0,
            )
        )

    total = QueueKpis(
        None, "All queues", True, grand, kpis(grand), sum(q.intervals_used for q in result)
    )
    return KpiSummary(date_from, date_to, days * INTERVALS_PER_DAY, total, result)
