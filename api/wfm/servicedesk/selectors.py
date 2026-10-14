"""Reading the service desk workload. Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine import workload

from wfm.accounts.models import User
from wfm.core.errors import ApiError

from .models import ServicePool, WorkItem

LOOKBACK_DAYS = 28  # how far back arrivals are measured
MAX_DAYS = 31


@dataclass(frozen=True, slots=True)
class PoolDemand:
    pool: ServicePool
    demand: workload.Demand


def demand(user: User, as_of: date, days: int) -> tuple[list[PoolDemand], int]:
    """What each pool needs over `days` days from the start of `as_of`, and how many working days
    that is. Breached means past its deadline when `as_of` begins."""
    if not 1 <= days <= MAX_DAYS:
        raise ApiError(
            422, "servicedesk.days_invalid", "Invalid request", f"Ask for 1 to {MAX_DAYS} days."
        )
    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(as_of, time.min, tzinfo=zone)
    horizon_end = datetime.combine(as_of + timedelta(days=days - 1), time.max, tzinfo=zone)
    working = workload.working_days(as_of, days)
    window_first = as_of - timedelta(days=LOOKBACK_DAYS)

    items = WorkItem.objects.for_user(user)
    open_by_pool: dict[int, list[workload.OpenItem]] = defaultdict(list)
    for pool_id, effort, due in items.filter(closed_at__isnull=True).values_list(
        "pool_id", "effort_minutes", "due_at"
    ):
        open_by_pool[pool_id].append(workload.OpenItem(effort, due))

    opened_by_pool: dict[int, list[tuple[date, int | None]]] = defaultdict(list)
    window_start = datetime.combine(window_first, time.min, tzinfo=zone)
    for pool_id, opened, effort in items.filter(
        opened_at__gte=window_start, opened_at__lt=start
    ).values_list("pool_id", "opened_at", "effort_minutes"):
        opened_by_pool[pool_id].append((opened.astimezone(zone).date(), effort))

    result: list[PoolDemand] = []
    for pool in ServicePool.objects.for_user(user):
        rate = workload.arrival_rate_per_working_day(
            opened_by_pool.get(pool.pk, []), window_first, LOOKBACK_DAYS
        )
        figures = workload.demand(
            open_by_pool.get(pool.pk, []),
            as_of=start,
            horizon_end=horizon_end,
            horizon_working_days=working,
            productive_min_per_day=pool.productive_minutes_per_day,
            arrival_per_working_day=rate,
        )
        result.append(PoolDemand(pool, figures))
    # Most people needed first, pools nothing can be said about last.
    result.sort(
        key=lambda p: (p.demand.required_fte is None, -(p.demand.required_fte or 0), p.pool.name)
    )
    return result, working
