"""Service metrics from imported tickets, beside staffing (KPI-01). Reads only."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema
from wfm_engine.servicekpi import ServiceKpis

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user
from wfm.servicedesk.policy import READ_ROLES

from . import kpi_selectors, selectors

router = Router(tags=["service-kpis"])
READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.SERVICE_DESK)


class ServiceKpiFigures(Schema):
    closed: int
    mttrH: float | None  # noqa: N815 - hours from opened to closed
    fcrKnown: int  # noqa: N815 - closed tickets that carry a first-contact flag
    fcrPct: float | None  # noqa: N815
    csatCount: int  # noqa: N815
    csatAverage: float | None  # noqa: N815 - 1 to 5
    csatSatisfiedPct: float | None  # noqa: N815 - rated 4 or 5
    npsCount: int  # noqa: N815
    nps: float | None  # -100 to 100
    backlogCount: int  # noqa: N815
    backlogAvgAgeDays: float | None  # noqa: N815
    backlogMedianAgeDays: float | None  # noqa: N815
    backlogOldestAgeDays: float | None  # noqa: N815
    costPerTicketRands: float | None  # noqa: N815 - pay roles only; none for everyone else
    ticketsPriced: int  # noqa: N815 - closed tickets with an effort estimate
    requiredFte: float | None  # noqa: N815 - people needed over the next 7 days


class ServiceKpiPoolOut(ServiceKpiFigures):
    poolId: int  # noqa: N815
    pool: str
    staffingComplete: bool  # noqa: N815 - false: a minimum (estimates or arrival rate missing)


class ServiceKpiReportOut(Schema):
    month: date
    asOf: date  # noqa: N815
    basis: str  # "measured": counted from the imported tickets; staffing is modelled
    costVisible: bool  # noqa: N815
    total: ServiceKpiFigures
    pools: list[ServiceKpiPoolOut]


def _figures(
    f: ServiceKpis, cost: Decimal | None, priced: int, fte: float | None
) -> dict[str, Any]:
    d = asdict(f)
    return {
        "closed": d["closed"],
        "mttrH": d["mttr_h"],
        "fcrKnown": d["fcr_known"],
        "fcrPct": d["fcr_pct"],
        "csatCount": d["csat_count"],
        "csatAverage": d["csat_average"],
        "csatSatisfiedPct": d["csat_satisfied_pct"],
        "npsCount": d["nps_count"],
        "nps": d["nps"],
        "backlogCount": d["backlog_count"],
        "backlogAvgAgeDays": d["backlog_avg_age_days"],
        "backlogMedianAgeDays": d["backlog_median_age_days"],
        "backlogOldestAgeDays": d["backlog_oldest_age_days"],
        "costPerTicketRands": None if cost is None else float(cost),
        "ticketsPriced": priced,
        "requiredFte": fte,
    }


@router.get(
    "/report",
    auth=READ,
    response=ServiceKpiReportOut,
    summary="MTTR, FCR, CSAT, NPS, backlog age and cost per ticket by pool, beside staffing",
)
def get_report(request: HttpRequest, month: date) -> ServiceKpiReportOut:
    found = kpi_selectors.service_kpis(
        current_user(request), selectors.check_month(month), timezone.now()
    )
    return ServiceKpiReportOut(
        month=found.month,
        asOf=found.as_of,
        basis="measured",
        costVisible=found.cost_visible,
        total=ServiceKpiFigures(
            **_figures(
                found.total,
                found.total_cost_per_ticket,
                found.total_tickets_priced,
                found.total_required_fte,
            )
        ),
        pools=[
            ServiceKpiPoolOut(
                poolId=p.pool.pk,
                pool=p.pool.name,
                staffingComplete=p.staffing_complete,
                **_figures(p.figures, p.cost_per_ticket, p.tickets_priced, p.required_fte),
            )
            for p in found.pools
        ],
    )
