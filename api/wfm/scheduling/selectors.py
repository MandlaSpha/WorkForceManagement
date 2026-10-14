"""Reading rosters and the weekly plan. Everything starts from `Model.objects.for_user(user)`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from wfm_engine.attention import Item, QueueWeek, attention
from wfm_engine.roster import (
    SLOTS_PER_DAY,
    WeekSummary,
    classify,
    coverage,
    summarise,
    variance,
)

from wfm.accounts.models import User
from wfm.core.errors import ApiError, not_found
from wfm.forecasting.models import ForecastInterval, ForecastStatus, ForecastVersion
from wfm.telephony.models import Queue

from .models import (
    Employee,
    EmployeeSkill,
    RosterStatus,
    RosterWeek,
    ShiftAssignment,
    ShiftTemplate,
)

WEEK_DAYS = 7


def _queue(user: User, queue_id: int) -> Queue:
    queue: Queue | None = Queue.objects.for_user(user).filter(pk=queue_id).first()
    if queue is None:
        raise not_found("No such queue.")
    return queue


def _check_monday(week_start: date) -> None:
    if week_start.weekday() != 0:
        raise ApiError(
            422, "roster.not_a_monday", "Invalid request", "A roster week starts on a Monday."
        )


def week_days(week_start: date) -> list[date]:
    return [week_start + timedelta(days=n) for n in range(WEEK_DAYS)]


def shifts(user: User) -> list[ShiftTemplate]:
    return list(ShiftTemplate.objects.for_user(user))


def employees(user: User, queue_id: int | None = None) -> list[Employee]:
    found = Employee.objects.for_user(user).prefetch_related("skills__queue")
    if queue_id is not None:
        found = found.filter(skills__queue_id=queue_id)
    return list(found.order_by("emp_no"))


# --- the roster grid ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RosterRow:
    employee: Employee
    cells: dict[date, ShiftTemplate]
    days_worked: int
    paid_minutes: int


@dataclass(frozen=True, slots=True)
class RosterGrid:
    queue: Queue
    week_start: date
    status: str
    published_at: datetime | None
    rows: list[RosterRow]
    on_counts: dict[date, int]  # people on a shift each day ("7 on")
    shifts: list[ShiftTemplate]


def roster_grid(user: User, queue_id: int, week_start: date) -> RosterGrid:
    _check_monday(week_start)
    queue = _queue(user, queue_id)
    week = RosterWeek.objects.for_user(user).filter(queue=queue, week_start=week_start).first()
    days = week_days(week_start)

    assigned: dict[int, dict[date, ShiftTemplate]] = {}
    if week is not None:
        for a in (
            ShiftAssignment.objects.for_user(user)
            .filter(roster_week=week)
            .select_related("template")
        ):
            assigned.setdefault(a.employee_id, {})[a.day] = a.template

    skilled_ids = set(
        EmployeeSkill.objects.filter(queue=queue).values_list("employee_id", flat=True)
    )
    people = (
        Employee.objects.for_user(user)
        .filter(pk__in=skilled_ids | set(assigned))
        .order_by("emp_no")
    )
    rows = [
        RosterRow(
            employee=e,
            cells=assigned.get(e.pk, {}),
            days_worked=len(assigned.get(e.pk, {})),
            paid_minutes=sum(t.paid_minutes for t in assigned.get(e.pk, {}).values()),
        )
        for e in people
    ]
    return RosterGrid(
        queue=queue,
        week_start=week_start,
        status=week.status if week else RosterStatus.DRAFT,
        published_at=week.published_at if week else None,
        rows=rows,
        on_counts={d: sum(1 for r in rows if d in r.cells) for d in days},
        shifts=shifts(user),
    )


# --- the weekly plan: coverage against requirement ---------------------------------------------


@dataclass(frozen=True, slots=True)
class PlanCell:
    slot: int
    scheduled: int
    required: int | None  # None: the forecast does not say
    variance: int | None
    state: str | None  # under, met, over; None when unknown


@dataclass(frozen=True, slots=True)
class Plan:
    queue: Queue
    week_start: date
    roster_status: str
    forecast: ForecastVersion | None  # the published forecast the requirement comes from
    cells: dict[date, list[PlanCell]]
    summary: WeekSummary


def _local_slot(moment: datetime, zone: ZoneInfo) -> tuple[date, int]:
    local = moment.astimezone(zone)
    return local.date(), local.hour * 2 + local.minute // 30


def week_plan(user: User, queue_id: int, week_start: date) -> Plan:
    """Scheduled people against required agents, for every half-hour of the week.

    The requirement comes from the queue's published forecast. Where there is none, or it does not
    reach a day, the requirement is unknown and nothing is claimed about that half-hour. Coverage
    is gross: breaks and activities are not taken off yet."""
    _check_monday(week_start)
    queue = _queue(user, queue_id)
    zone = ZoneInfo(settings.TIME_ZONE)
    days = week_days(week_start)
    first, last = days[0], days[-1]

    # A night shift that starts on the previous Sunday still covers Monday morning.
    rostered = (
        ShiftAssignment.objects.for_user(user)
        .filter(roster_week__queue=queue, day__gte=first - timedelta(days=1), day__lte=last)
        .select_related("template")
    )
    counted = coverage((a.day, a.template.start_time, a.template.end_time) for a in rostered)
    scheduled = {key: n for key, n in counted.items() if first <= key[0] <= last}

    version: ForecastVersion | None = (
        ForecastVersion.objects.for_user(user)
        .filter(queue=queue, status=ForecastStatus.PUBLISHED)
        .select_related("queue")
        .first()
    )
    required: dict[tuple[date, int], int | None] = {}
    if version is not None:
        start = datetime.combine(first, time.min, tzinfo=zone)
        end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=zone)
        for interval in ForecastInterval.objects.for_user(user).filter(
            version=version, interval_start__gte=start, interval_start__lt=end
        ):
            required[_local_slot(interval.interval_start, zone)] = interval.required

    week = RosterWeek.objects.for_user(user).filter(queue=queue, week_start=week_start).first()
    cells = {
        day: [
            PlanCell(
                slot=slot,
                scheduled=scheduled.get((day, slot), 0),
                required=required.get((day, slot)),
                variance=variance(scheduled.get((day, slot), 0), required.get((day, slot))),
                state=classify(scheduled.get((day, slot), 0), required.get((day, slot))),
            )
            for slot in range(SLOTS_PER_DAY)
        ]
        for day in days
    }
    return Plan(
        queue=queue,
        week_start=week_start,
        roster_status=week.status if week else RosterStatus.DRAFT,
        forecast=version,
        cells=cells,
        summary=summarise(scheduled, required),
    )


@dataclass(frozen=True, slots=True)
class DayGap:
    day: date
    gap: int  # people-half-hours short across every queue with a requirement
    under_intervals: int


@dataclass(frozen=True, slots=True)
class Overview:
    week_start: date
    plans: list[Plan]  # one per queue, worst-staffed first, queues with no forecast last
    days: list[DayGap]
    headcount: int  # people employed at some point in the week
    attention: list[Item]


def overview(user: User, week_start: date) -> Overview:
    """Every queue's week at a glance (the planning dashboard): the plan of each queue, the gap day
    by day across them, who is employed, and what needs attention. Built from `week_plan`, so the
    dashboard and the planner can never disagree."""
    _check_monday(week_start)
    plans = [week_plan(user, queue.pk, week_start) for queue in Queue.objects.for_user(user)]
    plans.sort(
        key=lambda p: (p.summary.intervals_known == 0, -p.summary.gap, p.queue.name),
    )

    days = [
        DayGap(
            day,
            gap=sum(
                max(-cell.variance, 0)
                for plan in plans
                for cell in plan.cells[day]
                if cell.variance is not None
            ),
            under_intervals=sum(
                1 for plan in plans for cell in plan.cells[day] if cell.state == "under"
            ),
        )
        for day in week_days(week_start)
    ]
    last = week_start + timedelta(days=WEEK_DAYS - 1)
    headcount = (
        Employee.objects.for_user(user)
        .filter(Q(start_date__isnull=True) | Q(start_date__lte=last))
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=week_start))
        .count()
    )
    facts = [
        QueueWeek(
            queue_id=plan.queue.pk,
            queue=plan.queue.name,
            # A published forecast that does not reach this week is no forecast for it.
            has_forecast=plan.summary.intervals_known > 0,
            assumptions_confirmed=bool(
                plan.forecast and plan.forecast.params.get("assumptionsConfirmed")
            ),
            intervals_known=plan.summary.intervals_known,
            under_intervals=plan.summary.under_intervals,
            scheduled_total=plan.summary.scheduled_total,
            roster_published=plan.roster_status == RosterStatus.PUBLISHED,
        )
        for plan in plans
    ]
    return Overview(week_start, plans, days, headcount, attention(facts))
