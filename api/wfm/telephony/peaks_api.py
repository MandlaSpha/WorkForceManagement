"""Peaks and troughs of measured demand for one queue (RPT-03)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import HttpRequest
from ninja import Router, Schema
from wfm_engine import peaks

from wfm.core.errors import ApiError, not_found
from wfm.core.features import Feature
from wfm.core.permissions import RoleSessionAuth, current_user

from .models import IntervalActual, Queue
from .policy import VIEW_ROLES
from .selectors import MAX_RANGE_DAYS

router = Router(tags=["telephony"])


class DayOut(Schema):
    day: date
    offered: int


class IntervalOut(Schema):
    start: str  # local time, "YYYY-MM-DD HH:MM"
    offered: int


class SlotOut(Schema):
    slot: str  # "HH:MM"
    averageOffered: Decimal  # noqa: N815
    days: int


class PeaksOut(Schema):
    queueId: int  # noqa: N815
    dateFrom: date  # noqa: N815
    dateTo: date  # noqa: N815
    daysMeasured: int  # noqa: N815
    busiestDays: list[DayOut]  # noqa: N815
    quietestDays: list[DayOut]  # noqa: N815
    busiestIntervals: list[IntervalOut]  # noqa: N815
    busiestSlots: list[SlotOut]  # noqa: N815
    quietestSlots: list[SlotOut]  # noqa: N815


def _slots(found: list[peaks.SlotAverage]) -> list[SlotOut]:
    return [
        SlotOut(slot=f"{s.slot:%H:%M}", averageOffered=s.average_offered, days=s.days)
        for s in found
    ]


def _days(found: list[peaks.DayTotal]) -> list[DayOut]:
    return [DayOut(day=d.day, offered=d.offered) for d in found]


@router.get(
    "/peaks",
    auth=RoleSessionAuth(*sorted(VIEW_ROLES), feature=Feature.TELEPHONY),
    response=PeaksOut,
    summary="Busiest and quietest days and half-hours of a queue, from measured calls",
)
def peaks_and_troughs(
    request: HttpRequest, queue_id: int, date_from: date, date_to: date
) -> PeaksOut:
    if date_to < date_from:
        raise ApiError(422, "range.invalid", "Invalid range", "date_to is before date_from.")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ApiError(
            422,
            "range.too_long",
            "Range too long",
            f"Ask for at most {MAX_RANGE_DAYS} days at a time.",
        )
    user = current_user(request)
    queue = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(date_from, time.min, tzinfo=zone)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone)
    rows = [
        (s.astimezone(zone).replace(tzinfo=None), offered)
        for s, offered in IntervalActual.objects.for_user(user)
        .filter(queue=queue, interval_start__gte=start, interval_start__lt=end)
        .values_list("interval_start", "offered")
    ]
    report = peaks.analyse(rows)
    return PeaksOut(
        queueId=queue.pk,
        dateFrom=date_from,
        dateTo=date_to,
        daysMeasured=len({s.date() for s, _ in rows}),
        busiestDays=_days(report.busiest_days),
        quietestDays=_days(report.quietest_days),
        busiestIntervals=[
            IntervalOut(start=f"{i.start:%Y-%m-%d %H:%M}", offered=i.offered)
            for i in report.busiest_intervals
        ],
        busiestSlots=_slots(report.busiest_slots),
        quietestSlots=_slots(report.quietest_slots),
    )
