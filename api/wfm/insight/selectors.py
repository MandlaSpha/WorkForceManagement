"""The scorecard: a few figures, each labelled by where it comes from (RPT-02, RPT-05).

`measured` comes from imported calls, leave or past forecasts; `modelled` mixes measured work with a
plan (the roster); `needs_data` is a figure the product cannot honestly give yet, and says what is
missing. A figure a role may not see is left out, never zeroed. Everything starts from the
`for_user` managers of the pieces it reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from wfm_engine import kpi

from wfm.accounts.models import Role, User
from wfm.forecasting.models import ForecastStatus, ForecastVersion
from wfm.forecasting.selectors import forecast_accuracy
from wfm.people.shrinkage_selectors import monthly as shrinkage_monthly
from wfm.scheduling.models import RosterStatus, ShiftAssignment
from wfm.scheduling.selectors import week_plan
from wfm.telephony.models import IntervalActual
from wfm.telephony.selectors import kpi_summary

MEASURED, MODELLED, NEEDS_DATA = "measured", "modelled", "needs_data"
PLANNING_ROLES = frozenset({Role.ADMIN, Role.PLANNER})  # who may see rosters, leave and plans
ACCURACY_QUEUES = 5  # the busiest queues: a backtest per queue is the slow part
GAP_QUEUES = 20


@dataclass(frozen=True, slots=True)
class Item:
    key: str
    label: str
    value: float | None  # None: no data in the range (never 0)
    unit: str
    basis: str
    note: str = ""


@dataclass(frozen=True, slots=True)
class Day:
    day: date
    offered: int
    service_level_pct: float | None


@dataclass(frozen=True, slots=True)
class Scorecard:
    date_from: date
    date_to: date
    items: list[Item]
    days: list[Day]


def _days(user: User, date_from: date, date_to: date) -> list[Day]:
    zone = ZoneInfo(settings.TIME_ZONE)
    rows = (
        IntervalActual.objects.for_user(user)
        .filter(
            interval_start__gte=_start(date_from, zone),
            interval_start__lt=_start(date_to + timedelta(days=1), zone),
        )
        .annotate(day=TruncDate("interval_start", tzinfo=zone))
        .values("day")
        .annotate(offered_=Sum("offered"), in_sl=Sum("answered_in_sl"), n=Count("id"))
        .order_by("day")
    )
    return [
        Day(
            r["day"],
            r["offered_"],
            (r["in_sl"] / r["offered_"] * 100) if r["offered_"] else None,
        )
        for r in rows
    ]


def _start(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time.min, tzinfo=zone)


def _scheduled_seconds(user: User, date_from: date, date_to: date) -> int:
    """Paid time on PUBLISHED rosters in the range: the roster as promised, not as logged in."""
    minutes = (
        ShiftAssignment.objects.for_user(user)
        .filter(
            day__gte=date_from,
            day__lte=date_to,
            roster_week__status=RosterStatus.PUBLISHED,
        )
        .aggregate(total=Sum("template__paid_minutes"))["total"]
    )
    return int(minutes or 0) * 60


def _shrinkage(user: User, month_of: date) -> float | None:
    teams = shrinkage_monthly(user, month_of)
    contracted = sum((t.summary.contracted_hours for t in teams), Decimal(0))
    away = sum((t.summary.away_hours for t in teams), Decimal(0))
    return float(away * 100 / contracted) if contracted > 0 else None


def _accuracy(user: User, busiest: list[int]) -> float | None:
    scores = []
    for queue_id in busiest[:ACCURACY_QUEUES]:
        pct = forecast_accuracy(user, queue_id).overall_daily_pct
        if pct is not None:
            scores.append(pct)
    return sum(scores) / len(scores) if scores else None


def _gap(user: User, week_of: date) -> tuple[int, int] | None:
    monday = week_of - timedelta(days=week_of.weekday())
    queue_ids = list(
        ForecastVersion.objects.for_user(user)
        .filter(status=ForecastStatus.PUBLISHED)
        .order_by("queue__name")
        .values_list("queue_id", flat=True)
        .distinct()[:GAP_QUEUES]
    )
    if not queue_ids:
        return None
    gap = under = 0
    for queue_id in queue_ids:
        summary = week_plan(user, queue_id, monday).summary
        gap += summary.gap
        under += summary.under_intervals
    return gap, under


def scorecard(user: User, date_from: date, date_to: date) -> Scorecard:
    summary = kpi_summary(user, date_from, date_to)
    k = summary.total.kpis
    totals = summary.total.totals
    items = [
        Item(
            "service_level",
            "Service level",
            k.service_level_pct,
            "%",
            MEASURED,
            "Answered in time, over calls offered.",
        ),
        Item("abandon_rate", "Abandon rate", k.abandon_pct, "%", MEASURED),
        Item("asa", "Average speed of answer", k.asa_s, "s", MEASURED),
        Item("aht", "Average handling time", k.aht_s, "s", MEASURED, "Talk plus wrap-up."),
        Item("offered", "Calls offered", float(k.offered), "calls", MEASURED),
    ]
    planning = user.role in PLANNING_ROLES
    if planning:
        occupancy = kpi.occupancy_pct(
            totals.sum_handle_s, _scheduled_seconds(user, date_from, date_to)
        )
        items.append(
            Item(
                "occupancy",
                "Occupancy",
                occupancy,
                "%",
                MODELLED,
                "Handling time over paid time on published rosters; needs a published roster.",
            )
        )
        items.append(
            Item(
                "planned_shrinkage",
                "Planned shrinkage",
                _shrinkage(user, date_to),
                "%",
                MEASURED,
                "Approved leave over contracted hours, in the month of the last day. Unplanned "
                "shrinkage needs an attendance feed.",
            )
        )
    busiest = [
        q.queue_id
        for q in sorted(summary.queues, key=lambda q: -q.totals.offered)
        if q.queue_id and q.totals.offered
    ]
    items.append(
        Item(
            "forecast_accuracy",
            "Forecast accuracy",
            _accuracy(user, busiest),
            "%",
            MEASURED,
            f"How well past days would have been forecast, for the {ACCURACY_QUEUES} busiest "
            "queues.",
        )
    )
    if planning:
        gap = _gap(user, date_to)
        items.append(
            Item(
                "coverage_gap",
                "Coverage gap",
                float(gap[0]) if gap else None,
                "half-hours",
                MODELLED,
                "People-half-hours short against the published forecast, in the week of the "
                "last day.",
            )
        )
    items.append(
        Item(
            "cost_per_contact",
            "Cost per contact",
            None,
            "R",
            NEEDS_DATA,
            "Needs payroll cost, which is kept out of this view.",
        )
    )
    return Scorecard(date_from, date_to, items, _days(user, date_from, date_to))
