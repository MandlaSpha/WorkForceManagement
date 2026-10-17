"""One queue's day against its forecast: what was forecast, what came, who is scheduled, what the
rest of the day now looks like, and where the people fall short (INT-01, INT-02, INT-03).

Calls are what has been IMPORTED, not a live feed: a finished half-hour with no data is unknown, and
the screen says how far the data reaches.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from wfm_engine import intraday as engine

from wfm.accounts.models import User
from wfm.forecasting.models import ForecastInterval
from wfm.forecasting.staffing import Assumptions, requirement
from wfm.scheduling.selectors import week_plan
from wfm.telephony.models import IntervalActual

SLOTS = 48


@dataclass(frozen=True, slots=True)
class Slot:
    slot: int
    forecast: float | None  # calls forecast; None: no published forecast reaches this day
    actual: int | None  # calls offered; None: not imported (or not yet happened)
    reforecast: float | None
    scheduled: int
    required: int | None  # from the published forecast
    expected_required: int | None  # from the re-forecast, for the half-hours still to come


@dataclass(frozen=True, slots=True)
class Intraday:
    queue_name: str
    day: date
    elapsed: int  # half-hours of the day that are over
    has_forecast: bool
    ratio: float | None
    data_through: int | None  # the last half-hour with imported calls
    service_level_pct: float | None  # measured over the finished half-hours with calls
    slots: list[Slot]
    alerts: list[engine.Alert]


def _elapsed(day: date, now: datetime) -> int:
    local = timezone.localtime(now, ZoneInfo(settings.TIME_ZONE))
    if day < local.date():
        return SLOTS
    if day > local.date():
        return 0
    return (local.hour * 60 + local.minute) // 30


def intraday(user: User, queue_id: int, day: date, now: datetime | None = None) -> Intraday:
    now = now or timezone.now()
    zone = ZoneInfo(settings.TIME_ZONE)
    monday = day - timedelta(days=day.weekday())
    plan = week_plan(user, queue_id, monday)  # the queue is checked here: out of scope is a 404
    cells = plan.cells[day]
    elapsed = _elapsed(day, now)

    start = datetime.combine(day, time.min, tzinfo=zone)
    end = start + timedelta(days=1)
    forecast: list[float | None] = [None] * SLOTS
    aht: list[float | None] = [None] * SLOTS
    if plan.forecast is not None:
        for row in ForecastInterval.objects.for_user(user).filter(
            version=plan.forecast, interval_start__gte=start, interval_start__lt=end
        ):
            index = (
                row.interval_start.astimezone(zone).hour * 60
                + row.interval_start.astimezone(zone).minute
            ) // 30
            forecast[index] = row.volume
            aht[index] = row.aht_s

    actual: list[int | None] = [None] * SLOTS
    in_sl: list[int] = [0] * SLOTS
    for row in IntervalActual.objects.for_user(user).filter(
        queue_id=queue_id, interval_start__gte=start, interval_start__lt=end
    ):
        local = row.interval_start.astimezone(zone)
        index = (local.hour * 60 + local.minute) // 30
        actual[index] = row.offered
        in_sl[index] = row.answered_in_sl

    has_forecast = plan.forecast is not None and any(v is not None for v in forecast)
    basis = [v if v is not None else 0.0 for v in forecast]
    re = engine.reforecast(basis, actual, elapsed) if has_forecast else None

    assumptions = Assumptions.of_queue(plan.queue)
    expected: list[int | None] = [None] * SLOTS
    if re is not None:
        for i in range(elapsed, SLOTS):
            if forecast[i] is not None:
                expected[i] = requirement(re.volumes[i], aht[i], assumptions)[1]

    scheduled = [c.scheduled for c in cells]
    # Judge the rest of the day by the re-forecast need where there is one, else the forecast's.
    judged = [expected[i] if expected[i] is not None else cells[i].required for i in range(SLOTS)]
    found = engine.alerts(scheduled, judged, elapsed) if has_forecast else []

    finished = [i for i in range(min(elapsed, SLOTS)) if actual[i]]
    offered = sum(actual[i] or 0 for i in finished)
    on_time = sum(in_sl[i] for i in finished)
    return Intraday(
        queue_name=plan.queue.name,
        day=day,
        elapsed=elapsed,
        has_forecast=has_forecast,
        ratio=re.ratio if re else None,
        data_through=max((i for i in range(SLOTS) if actual[i] is not None), default=None),
        service_level_pct=(on_time / offered * 100) if offered else None,
        slots=[
            Slot(
                slot=i,
                forecast=forecast[i],
                actual=actual[i] if i < elapsed else None,
                reforecast=re.volumes[i] if re and forecast[i] is not None else None,
                scheduled=scheduled[i],
                required=cells[i].required,
                expected_required=expected[i],
            )
            for i in range(SLOTS)
        ],
        alerts=found,
    )
