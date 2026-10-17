from __future__ import annotations

from datetime import date

from django.http import HttpRequest
from ninja import Router

from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from . import selectors, services
from .hiring_api import router as hiring_router
from .models import CapacityLimits
from .policy import READ_ROLES, WRITE_ROLES
from .schemas import CapacityDayOut, CapacityOut, CapacityWeekOut, LimitsIn, LimitsOut

router = Router(tags=["capacity"])
router.add_router("", hiring_router)

READ = RoleSessionAuth(*sorted(READ_ROLES), feature=Feature.CAPACITY)
WRITE = RoleSessionAuth(*sorted(WRITE_ROLES), feature=Feature.CAPACITY)


@router.get(
    "",
    auth=READ,
    response=CapacityOut,
    summary="Agents needed at the busiest moment of each day, by permanent and seasonal pool",
)
def get_capacity(request: HttpRequest, week_start: date, weeks: int = 4) -> CapacityOut:
    result = selectors.capacity(current_user(request), week_start, weeks)
    return CapacityOut(
        limits=_limits_out(result.limits),
        weeks=[
            CapacityWeekOut(
                weekStart=week.week_start,
                peak=None if week.peak_day is None else week.peak_day.peak,
                peakDay=None if week.peak_day is None else week.peak_day.day,
                seasonalPeak=week.seasonal_peak,
                overflowDays=week.overflow_days,
                daysForecast=week.days_forecast,
                daysIncomplete=week.days_incomplete,
                days=[
                    CapacityDayOut(
                        day=d.day,
                        queuesCovered=d.queues_covered,
                        queuesTotal=d.queues_total,
                        peak=d.peak,
                        complete=d.complete,
                        permanent=None if d.split is None else d.split.permanent,
                        seasonal=None if d.split is None else d.split.seasonal,
                        overflow=None if d.split is None else d.split.overflow,
                        permanentOnBooks=d.permanent_on_books,
                        seasonalOnBooks=d.seasonal_on_books,
                        seasonalToHire=d.seasonal_to_hire,
                    )
                    for d in week.days
                ],
            )
            for week in result.weeks
        ],
    )


@router.put(
    "/limits", auth=WRITE, response=LimitsOut, summary="Set the permanent and seasonal pools"
)
def set_limits(request: HttpRequest, body: LimitsIn) -> LimitsOut:
    return _limits_out(
        services.set_limits(
            user=current_user(request),
            permanent_limit=body.permanentLimit,
            seasonal_limit=body.seasonalLimit,
        )
    )


def _limits_out(limits: CapacityLimits) -> LimitsOut:
    return LimitsOut(
        permanentLimit=limits.permanent_limit,
        seasonalLimit=limits.seasonal_limit,
        confirmed=limits.confirmed,
    )
