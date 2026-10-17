"""Peaks and troughs of one queue's measured demand (RPT-03), read as the signed-in role."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine import peaks

from wfm.accounts.models import User
from wfm.core.errors import not_found

from .models import IntervalActual, Queue


@dataclass(frozen=True, slots=True)
class PeaksFound:
    queue_name: str
    days_measured: int
    report: peaks.Report


def peaks_report(user: User, queue_id: int, date_from: date, date_to: date) -> PeaksFound:
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
    return PeaksFound(queue.name, len({s.date() for s, _ in rows}), peaks.analyse(rows))
