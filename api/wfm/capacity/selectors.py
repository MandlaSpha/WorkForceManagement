"""Reading capacity. Everything starts from `Model.objects.for_user(user)` or the narrow
role-checked accessors on the models whose figures it adds up."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from wfm_engine.capacity import Split, combine, peak, split_demand

from wfm.accounts.models import User
from wfm.core.errors import ApiError
from wfm.forecasting.models import ForecastInterval, ForecastStatus
from wfm.scheduling.models import ContractType, Employee
from wfm.telephony.models import Queue

from .models import CapacityLimits
from .policy import READ_ROLES

SLOTS = 48
MAX_WEEKS = 12


@dataclass(frozen=True, slots=True)
class Day:
    day: date
    queues_covered: int
    queues_total: int
    peak: int | None
    complete: bool
    split: Split | None
    permanent_on_books: int
    seasonal_on_books: int
    seasonal_to_hire: int | None


@dataclass(frozen=True, slots=True)
class Week:
    week_start: date
    days: list[Day]

    @property
    def peak_day(self) -> Day | None:
        known = [d for d in self.days if d.peak is not None]
        return max(known, key=lambda d: d.peak or 0, default=None)

    @property
    def seasonal_peak(self) -> int | None:
        known = [d.split.seasonal for d in self.days if d.split is not None]
        return max(known, default=None)

    @property
    def overflow_days(self) -> int:
        return sum(1 for d in self.days if d.split is not None and d.split.overflow > 0)

    @property
    def days_forecast(self) -> int:
        return sum(1 for d in self.days if d.queues_covered > 0)

    @property
    def days_incomplete(self) -> int:
        return sum(1 for d in self.days if d.queues_covered > 0 and not d.complete)


@dataclass(frozen=True, slots=True)
class Capacity:
    limits: CapacityLimits
    weeks: list[Week]


def limits(user: User) -> CapacityLimits:
    """The saved limits, or the tender's figures (unconfirmed) when nobody has set them."""
    found: CapacityLimits | None = CapacityLimits.objects.for_user(user).first()
    return found if found is not None else CapacityLimits()


def capacity(user: User, week_start: date, weeks: int) -> Capacity:
    """Agents needed at the busiest moment of each day, split into permanent, seasonal and
    overflow, from the PUBLISHED forecast of every queue (CAP-01). A day with no forecast has no
    figures, never zeros; a day where only some queues are forecast says the figure is a minimum.
    """
    if user.role not in READ_ROLES:
        return Capacity(CapacityLimits(), [])
    if week_start.weekday() != 0:
        raise ApiError(422, "capacity.not_a_monday", "Invalid request", "A week starts on Monday.")
    if not 1 <= weeks <= MAX_WEEKS:
        raise ApiError(
            422, "capacity.weeks_invalid", "Invalid request", f"Ask for 1 to {MAX_WEEKS} weeks."
        )

    pools = limits(user)
    days = [week_start + timedelta(days=n) for n in range(weeks * 7)]
    needed = _requirement_by_day(user, days)
    queues_total = Queue.objects.for_user(user).count()
    staff = list(
        Employee.objects.headcount_for(user, READ_ROLES).values_list(
            "contract_type", "start_date", "end_date"
        )
    )

    built: list[Day] = []
    for day in days:
        per_queue = needed.get(day, [])
        peak_value, complete = peak(combine(per_queue))
        complete = complete and len(per_queue) == queues_total
        split = (
            None
            if peak_value is None
            else split_demand(peak_value, pools.permanent_limit, pools.seasonal_limit)
        )
        on_books = _on_books(staff, day)
        built.append(
            Day(
                day=day,
                queues_covered=len(per_queue),
                queues_total=queues_total,
                peak=peak_value,
                complete=complete,
                split=split,
                permanent_on_books=on_books[ContractType.PERMANENT],
                seasonal_on_books=on_books[ContractType.SEASONAL],
                seasonal_to_hire=(
                    None
                    if split is None
                    else max(split.seasonal - on_books[ContractType.SEASONAL], 0)
                ),
            )
        )
    return Capacity(pools, [Week(built[i].day, built[i : i + 7]) for i in range(0, len(built), 7)])


def _requirement_by_day(user: User, days: list[date]) -> dict[date, list[list[int | None]]]:
    """For each day, one list of 48 half-hour requirements per queue that has a published forecast
    for it."""
    zone = ZoneInfo(settings.TIME_ZONE)
    first = datetime.combine(days[0], time.min, tzinfo=zone)
    after = datetime.combine(days[-1] + timedelta(days=1), time.min, tzinfo=zone)
    rows = (
        ForecastInterval.objects.aggregate_for(user, READ_ROLES)
        .filter(
            version__status=ForecastStatus.PUBLISHED,
            interval_start__gte=first,
            interval_start__lt=after,
        )
        .values_list("version__queue_id", "interval_start", "required")
    )
    grid: dict[tuple[int, date], list[int | None]] = {}
    for queue_id, start, required in rows.iterator():
        local = start.astimezone(zone)
        slots = grid.setdefault((queue_id, local.date()), [None] * SLOTS)
        slots[local.hour * 2 + local.minute // 30] = required
    by_day: dict[date, list[list[int | None]]] = {}
    for (_queue_id, day), slots in sorted(grid.items()):
        by_day.setdefault(day, []).append(slots)
    return by_day


def _on_books(staff: list[tuple[str, date | None, date | None]], day: date) -> dict[str, int]:
    counts = {ContractType.PERMANENT.value: 0, ContractType.SEASONAL.value: 0}
    for contract, start, end in staff:
        if (start is None or start <= day) and (end is None or end >= day):
            counts[contract] = counts.get(contract, 0) + 1
    return counts
