"""Service metrics from imported tickets, shown beside staffing (KPI-01).

Everything starts from `WorkItem.objects.for_user(user)`. The metric maths is
`wfm_engine.servicekpi`; the price of a ticket is NOT recomputed here: it is the pool cost of
`selectors.costs` (`wfm_engine.utilisation.ticket_cost`), so it exists once and is shown to the pay
roles only. Tickets belong to a resource pool, not to a contract or a queue, so pools are the
grouping.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from wfm_engine import servicekpi as kpi

from wfm.accounts.models import User
from wfm.servicedesk import selectors as desk
from wfm.servicedesk.models import ServicePool, WorkItem

from . import selectors
from .policy import COST_ROLES

STAFFING_DAYS = 7  # the people the pool needs over the next week, from the service desk workload
CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class PoolKpis:
    pool: ServicePool
    figures: kpi.ServiceKpis
    cost_per_ticket: Decimal | None
    tickets_priced: int
    required_fte: float | None
    staffing_complete: bool


@dataclass(frozen=True, slots=True)
class ServiceKpiReport:
    month: date
    as_of: date
    pools: list[PoolKpis]
    total: kpi.ServiceKpis
    total_cost_per_ticket: Decimal | None
    total_tickets_priced: int
    total_required_fte: float | None
    cost_visible: bool


def service_kpis(user: User, month: date, now: datetime) -> ServiceKpiReport:
    zone = ZoneInfo(settings.TIME_ZONE)
    first = selectors.month_start(month)
    start = datetime.combine(first, time.min, tzinfo=zone)
    end = datetime.combine(selectors.month_end(first) + timedelta(days=1), time.min, tzinfo=zone)
    as_of = min(now, end)

    by_pool: dict[int, list[kpi.Ticket]] = {}
    # Closed in the month, or open at the end of it: nothing else can change a figure.
    rows = (
        WorkItem.objects.for_user(user)
        .filter(opened_at__lt=end)
        .filter(Q(closed_at__isnull=True) | Q(closed_at__gte=start))
        .values_list("pool_id", "opened_at", "closed_at", "first_contact_resolved", "csat", "nps")
    )
    for pool_id, opened, closed, fcr, csat, nps in rows:
        by_pool.setdefault(pool_id, []).append(kpi.Ticket(opened, closed, fcr, csat, nps))

    cost_visible = user.role in COST_ROLES
    priced = (
        {p.pool.pk: p.ticket for p in selectors.costs(user, first).pools} if cost_visible else {}
    )
    staffing = {
        d.pool.pk: d.demand
        for d in desk.demand(user, as_of.astimezone(zone).date(), STAFFING_DAYS)[0]
    }

    def run(tickets: list[kpi.Ticket]) -> kpi.ServiceKpis:
        return kpi.kpis(tickets, period_start=start, period_end=end, as_of=as_of)

    pools: list[PoolKpis] = []
    for pool in ServicePool.objects.for_user(user):
        cost = priced.get(pool.pk)
        need = staffing.get(pool.pk)
        pools.append(
            PoolKpis(
                pool=pool,
                figures=run(by_pool.get(pool.pk, [])),
                cost_per_ticket=cost.per_ticket if cost else None,
                tickets_priced=cost.estimated if cost else 0,
                required_fte=need.required_fte if need else None,
                staffing_complete=need.complete if need else False,
            )
        )

    known = [p.required_fte for p in pools if p.required_fte is not None]
    cost_total = sum((c.cost for c in priced.values() if c.cost is not None), Decimal(0))
    count_priced = sum(c.estimated for c in priced.values() if c.cost is not None)
    return ServiceKpiReport(
        month=first,
        as_of=as_of.astimezone(zone).date(),
        pools=pools,
        total=run([t for tickets in by_pool.values() for t in tickets]),
        total_cost_per_ticket=(
            (cost_total / count_priced).quantize(CENT, rounding=ROUND_HALF_UP)
            if count_priced
            else None
        ),
        total_tickets_priced=count_priced,
        total_required_fte=sum(known) if known else None,
        cost_visible=cost_visible,
    )
