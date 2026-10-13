"""Reading a queue's measured history in the shape the forecast engine wants."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine.forecast import SlotHistory

from wfm.telephony.models import IntervalActual, Queue


def load_history(queue: Queue) -> tuple[list[SlotHistory], set[date]]:
    """Every half-hour slot of the queue that had inbound calls, and the days that have data.

    Days are South African days and slots count half-hours from local midnight, because that is
    how people plan. A day is "observed" when any of its slots has calls; a day with no rows at
    all was never imported, which is not the same as a day with no calls. (Whole days are
    assumed: an import that stops mid-day would make that day look quiet.)
    """
    zone = ZoneInfo(settings.TIME_ZONE)
    rows = IntervalActual.objects.filter(queue=queue).values_list(
        "interval_start", "offered", "answered", "sum_handle_s"
    )
    history: list[SlotHistory] = []
    observed: set[date] = set()
    for start, offered, answered, handle_s in rows.iterator():
        local = start.astimezone(zone)
        history.append(
            SlotHistory(
                local.date(), local.hour * 2 + local.minute // 30, offered, answered, handle_s
            )
        )
        observed.add(local.date())
    return history, observed
