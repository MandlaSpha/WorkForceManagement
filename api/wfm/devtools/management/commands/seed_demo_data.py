"""Fill a development database with an invented, believable contact centre (development only).

Run after `seed_demo` (it needs the demo planner and lead). Nothing here comes from real data:
names are made up from word lists, volumes from a seeded random generator. Writes go through the
real services where there is one (employees, forecasts, roster, leave, events), so the demo also
exercises the rules and fills the audit trail the way real use would.

What a presenter gets to talk about (see docs/08-WALKTHROUGH.md):
- 12 weeks of call history for three queues, with peaks, a busy Monday, public holidays,
  month-end pressure, an outage day and a day the recorder was down.
- Staff: full-time, part-time and seasonal, some skilled on two queues.
- Forecasts for the next four weeks, published, and two campaign events that move them.
- Rosters: this week and next published (next Monday deliberately short, next Thursday
  deliberately over-staffed), the week after still in draft, the fourth not started.
- Leave in every state: approved and already applied to the roster, waiting with a visible effect
  on coverage, rejected, cancelled, and taken in the past.
- A service desk with open, overdue and closed tickets in two pools.
"""

from __future__ import annotations

import os
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit import services as audit
from wfm.audit.models import ActorType
from wfm.core.errors import ApiError
from wfm.devtools.demo_history import SHAPES, build_history
from wfm.forecasting import event_services
from wfm.forecasting import services as forecast_services
from wfm.forecasting.models import ForecastInterval, ForecastStatus
from wfm.people import services as leave_services
from wfm.people.models import LeaveType
from wfm.scheduling import roster_services
from wfm.scheduling import services as scheduling_services
from wfm.scheduling.models import ContractType, Employee, EmployeeSkill, ShiftTemplate
from wfm.scheduling.services import SkillInput
from wfm.servicedesk.models import ServicePool, WorkItem
from wfm.telephony.models import IntervalActual, Queue

SHIFTS = (  # code, start, end, paid minutes (a break is unpaid)
    ("D1", time(7, 0), time(15, 30), 480),
    ("D2", time(9, 0), time(17, 30), 480),
    ("D3", time(11, 0), time(19, 30), 480),
    ("N1", time(18, 0), time(3, 0), 480),
    ("N2", time(21, 0), time(6, 0), 480),
)
SHIFTS_OF_QUEUE = {
    "Demo Support": ("D1", "D2", "D3"),
    "Demo Billing": ("D1", "D2"),
    "Demo Night Desk": ("N1", "N2"),
}
# Staff per queue: (full-time, part-time, seasonal). Billing's last four also work Support.
HEADCOUNT = {"Demo Support": (30, 4, 6), "Demo Billing": (12, 2, 0), "Demo Night Desk": (8, 0, 0)}
FORECAST_DAYS = 28
FIRST = [
    "Thandi",
    "Pieter",
    "Lerato",
    "Sipho",
    "Anele",
    "Johan",
    "Naledi",
    "Kagiso",
    "Zanele",
    "Willem",
    "Palesa",
    "Bongani",
    "Marlene",
    "Themba",
    "Ayesha",
    "Dumisani",
    "Karabo",
    "Hendrik",
    "Lindiwe",
    "Tshepo",
    "Nomsa",
    "Ruan",
    "Refilwe",
    "Sizwe",
]
LAST = [
    "Dlamini",
    "Botha",
    "Mokoena",
    "Naidoo",
    "Khumalo",
    "Venter",
    "Mahlangu",
    "Pretorius",
    "Sithole",
    "Nel",
    "Molefe",
    "Jacobs",
    "Zulu",
    "Steyn",
    "Ndlovu",
    "Fourie",
    "Radebe",
    "Coetzee",
    "Mthembu",
    "Pillay",
    "Maseko",
    "Joubert",
    "Tshabalala",
    "Smit",
]
# Rostering aims at this share of the forecast need, by (week index, weekday). Next Monday is
# short on purpose, next Thursday over-staffed, to give the roster and dashboard something to show.
SHORT_MONDAY = (1, 0, 0.8)
LONG_THURSDAY = (1, 3, 1.3)
ROSTERED_WEEKS = 3


@dataclass
class Cast:
    planner: User
    lead: User
    admin: User


class Command(BaseCommand):
    help = "Fill a development database with an invented, believable contact centre."

    def handle(self, *args: Any, **options: Any) -> None:
        if not (settings.DEBUG or os.environ.get("WFM_ALLOW_DEMO_SEED") == "1"):
            raise CommandError("Demo seeding is disabled here (set WFM_ALLOW_DEMO_SEED=1).")
        if Queue.objects.filter(name__in=[s.name for s in SHAPES]).exists():
            raise CommandError("The demo data is already here. Use a fresh database.")
        cast = self._cast()
        today = timezone.localdate()
        zone = ZoneInfo(settings.TIME_ZONE)

        queues = self._queues_and_history(today, zone)
        self.stdout.write("History written.")
        self._shifts(cast)
        staff = self._staff(cast, queues, today)
        self.stdout.write(f"{sum(len(v) for v in staff.values())} staff created.")
        self._forecasts_and_events(cast, queues, today)
        self.stdout.write("Forecasts published.")
        self._rosters(cast, queues, staff, today)
        self.stdout.write("Rosters built.")
        self._leave(cast, staff["Demo Support"], today)
        self.stdout.write("Leave in every state.")
        self._service_desk(today, zone)
        audit.record(
            actor=None,
            action="system.seed_demo_data",
            actor_type=ActorType.SYSTEM,
            reason="Invented demo data created",
        )
        self.stdout.write(self.style.SUCCESS("Demo data ready."))

    # --- people who act ------------------------------------------------------------------------

    def _cast(self) -> Cast:
        users = {u.role: u for u in User.objects.filter(username__in=["planner", "lead", "admin"])}
        missing = {Role.PLANNER, Role.LEAD, Role.ADMIN} - set(users)
        if missing:
            raise CommandError("Run seed_demo first: it creates the planner, lead and admin.")
        return Cast(users[Role.PLANNER], users[Role.LEAD], users[Role.ADMIN])

    # --- call history --------------------------------------------------------------------------

    @transaction.atomic
    def _queues_and_history(self, today: date, zone: ZoneInfo) -> dict[str, Queue]:
        queues: dict[str, Queue] = {}
        for shape in SHAPES:
            support = shape.name == "Demo Support"
            queues[shape.name] = Queue.objects.create(
                name=shape.name,
                confirmed=True,
                # Support's settings are confirmed; the others still show the "assumed" notice.
                settings_confirmed=support,
                sl_target_pct=Decimal("80"),
                sl_threshold_s=20,
                shrinkage_pct=Decimal("30"),
            )
            IntervalActual.objects.bulk_create(
                build_history(queues[shape.name], shape, today, zone), batch_size=2000
            )
        return queues

    # --- shifts and staff ----------------------------------------------------------------------

    def _shifts(self, cast: Cast) -> None:
        for code, start, end, paid in SHIFTS:
            scheduling_services.create_shift(
                user=cast.planner, code=code, start_time=start, end_time=end, paid_minutes=paid
            )

    def _staff(
        self, cast: Cast, queues: dict[str, Queue], today: date
    ) -> dict[str, list[Employee]]:
        rng = random.Random("wfm-demo-staff")
        names = [f"{a} {b}" for a in FIRST for b in LAST]
        rng.shuffle(names)
        number = 0
        staff: dict[str, list[Employee]] = {}
        demo_agent = Employee.objects.filter(emp_no="DEMO-AGENT").first()
        for queue_name, (full, part, seasonal) in HEADCOUNT.items():
            queue = queues[queue_name]
            extra = SkillInput(queues["Demo Support"].pk) if queue_name == "Demo Billing" else None
            made: list[Employee] = []
            for index in range(full + part + seasonal):
                number += 1
                is_part = full <= index < full + part
                is_seasonal = index >= full + part
                skills = [SkillInput(queue.pk)]
                if extra is not None and index >= full - 2:  # the last few cover both queues
                    skills.append(extra)
                made.append(
                    scheduling_services.create_employee(
                        user=cast.planner,
                        emp_no=f"DEMO-{number:03d}",
                        name=names[number],
                        contract_type=(
                            ContractType.SEASONAL if is_seasonal else ContractType.PERMANENT
                        ),
                        weekly_hours=Decimal("20") if is_part else Decimal("40"),
                        start_date=today - timedelta(days=30) if is_seasonal else None,
                        end_date=today + timedelta(days=75) if is_seasonal else None,
                        skills=skills,
                    )
                )
            staff[queue_name] = made
        if demo_agent is not None:  # the demo `agent` login works the Support queue
            EmployeeSkill.objects.get_or_create(employee=demo_agent, queue=queues["Demo Support"])
            staff["Demo Support"].append(demo_agent)
        return staff

    # --- forecasts and events ------------------------------------------------------------------

    def _forecasts_and_events(self, cast: Cast, queues: dict[str, Queue], today: date) -> None:
        pay_day = next(
            today + timedelta(days=n) for n in range(0, 62) if (today + timedelta(days=n)).day == 25
        )
        event_services.create_event(
            user=cast.planner,
            name="Month-end billing run",
            queue_id=queues["Demo Billing"].pk,
            date_from=pay_day,
            date_to=pay_day + timedelta(days=5),
            uplift_pct=Decimal("30"),
        )
        event_services.create_event(
            user=cast.planner,
            name="SMS campaign",
            queue_id=queues["Demo Support"].pk,
            date_from=today + timedelta(days=8),
            date_to=today + timedelta(days=9),
            uplift_pct=Decimal("20"),
        )
        for queue in queues.values():
            version = forecast_services.run_forecast(
                user=cast.planner,
                queue_id=queue.pk,
                date_from=today,
                date_to=today + timedelta(days=FORECAST_DAYS - 1),
                label="Demo forecast",
            )
            forecast_services.publish_forecast(user=cast.planner, version_id=version.id)

    # --- rosters -------------------------------------------------------------------------------

    def _rosters(
        self,
        cast: Cast,
        queues: dict[str, Queue],
        staff: dict[str, list[Employee]],
        today: date,
    ) -> None:
        zone = ZoneInfo(settings.TIME_ZONE)
        shifts = {s.code: s for s in ShiftTemplate.objects.all()}
        week0 = today - timedelta(days=today.weekday())
        for queue_name, queue in queues.items():
            need = self._need(queue, zone)
            covered: dict[datetime, int] = {}
            days_worked: dict[tuple[int, date], int] = {}
            codes = SHIFTS_OF_QUEUE[queue_name]
            for offset in range(ROSTERED_WEEKS * 7):
                day = week0 + timedelta(days=offset)
                if day < today:
                    continue
                week = offset // 7
                scale = 1.0
                if (week, day.weekday()) == SHORT_MONDAY[:2]:
                    scale = SHORT_MONDAY[2]
                if (week, day.weekday()) == LONG_THURSDAY[:2]:
                    scale = LONG_THURSDAY[2]
                self._roster_day(
                    cast,
                    queue,
                    staff[queue_name],
                    day,
                    week0,
                    shifts,
                    codes,
                    need,
                    covered,
                    days_worked,
                    scale,
                )
            for week in range(2):  # this week and next are final; the third stays a draft
                roster_services.publish(
                    user=cast.planner,
                    queue_id=queue.pk,
                    week_start=week0 + timedelta(days=7 * week),
                )

    def _need(self, queue: Queue, zone: ZoneInfo) -> dict[datetime, int]:
        live = ForecastInterval.objects.filter(
            version__queue=queue, version__status=ForecastStatus.PUBLISHED
        )
        return {
            row.interval_start.astimezone(zone): row.required or 0
            for row in live.only("interval_start", "required")
        }

    def _roster_day(
        self,
        cast: Cast,
        queue: Queue,
        people: Sequence[Employee],
        day: date,
        week0: date,
        shifts: dict[str, ShiftTemplate],
        codes: Sequence[str],
        need: dict[datetime, int],
        covered: dict[datetime, int],
        days_worked: dict[tuple[int, date], int],
        scale: float,
    ) -> None:
        """Add shifts to the day one at a time, each the one that closes the most remaining gap,
        until the forecast need (times `scale`) is met or nobody suitable is left."""
        week_start = day - timedelta(days=day.weekday())
        zone = ZoneInfo(settings.TIME_ZONE)

        def slots(code: str) -> list[datetime]:
            template = shifts[code]
            start = datetime.combine(day, template.start_time, tzinfo=zone)
            end = datetime.combine(day, template.end_time, tzinfo=zone)
            if end <= start:
                end += timedelta(days=1)
            count = int((end - start).total_seconds() // 1800)
            return [start + timedelta(minutes=30 * n) for n in range(count)]

        def gain(code: str) -> float:
            return sum(
                min(1.0, max(0.0, need.get(s, 0) * scale - covered.get(s, 0))) for s in slots(code)
            )

        tried: set[int] = set()
        while True:
            best = max(codes, key=gain)
            if gain(best) < 4:  # less than two hours of real gap: not worth a shift
                return
            candidates = sorted(
                (p for p in people if p.pk not in tried),
                key=lambda p: (
                    days_worked.get((p.pk, week_start), 0),
                    (p.pk + day.toordinal()) % 7,
                ),
            )
            for person in candidates:
                tried.add(person.pk)
                limit = int(float(person.weekly_hours) * 60 // 480)
                if days_worked.get((person.pk, week_start), 0) >= limit:
                    continue
                try:
                    roster_services.assign(
                        user=cast.planner,
                        queue_id=queue.pk,
                        employee_id=person.pk,
                        day=day,
                        template_id=shifts[best].pk,
                    )
                except ApiError:
                    continue  # a rule refused this person today: try the next
                days_worked[(person.pk, week_start)] = (
                    days_worked.get((person.pk, week_start), 0) + 1
                )
                for s in slots(best):
                    covered[s] = covered.get(s, 0) + 1
                break
            else:
                return

    # --- leave ---------------------------------------------------------------------------------

    def _leave(self, cast: Cast, people: Sequence[Employee], today: date) -> None:
        kinds = {t.code: t.pk for t in LeaveType.objects.all()}
        monday = today - timedelta(days=today.weekday()) + timedelta(days=7)  # next Monday

        def ask(person: Employee, kind: str, start: date, end: date) -> Any:
            return leave_services.apply(
                user=cast.planner,
                leave_type_id=kinds[kind],
                start=start,
                end=end,
                employee_id=person.pk,
            )

        # Approved, and already taken off next week's roster.
        approved = ask(people[0], "annual", monday + timedelta(days=2), monday + timedelta(days=4))
        leave_services.decide(user=cast.lead, request_id=approved.pk, approve=True)
        # Waiting, over next Monday (the short day): the impact panel shows what it would cost.
        ask(people[1], "annual", monday, monday + timedelta(days=1))
        # Waiting, further out, for a course.
        ask(people[2], "training", monday + timedelta(days=14), monday + timedelta(days=15))
        # Turned down: too many on leave that week.
        refused = ask(people[3], "annual", monday + timedelta(days=7), monday + timedelta(days=11))
        leave_services.decide(user=cast.lead, request_id=refused.pk, approve=False)
        # Approved and then withdrawn, so the shifts went back.
        withdrawn = ask(people[4], "family", monday + timedelta(days=8), monday + timedelta(days=8))
        leave_services.decide(user=cast.lead, request_id=withdrawn.pk, approve=True)
        leave_services.cancel(user=cast.planner, request_id=withdrawn.pk)
        # Already taken: sick leave over the last working days.
        back = today - timedelta(days=3)
        while back.weekday() > 4 or (back + timedelta(days=1)).weekday() > 4:
            back -= timedelta(days=1)
        taken = ask(people[5], "sick", back, back + timedelta(days=1))
        leave_services.decide(user=cast.lead, request_id=taken.pk, approve=True)

    # --- service desk --------------------------------------------------------------------------

    @transaction.atomic
    def _service_desk(self, today: date, zone: ZoneInfo) -> None:
        rng = random.Random("wfm-demo-tickets")
        now = datetime.now(tz=zone)
        due_after = {
            "P1": timedelta(hours=4),
            "P2": timedelta(hours=8),
            "P3": timedelta(days=3),
            "P4": timedelta(days=5),
        }
        number = 0
        for pool_name, count in (("Service Desk", 180), ("NOC", 90)):
            pool = ServicePool.objects.create(name=pool_name)
            items = []
            for _ in range(count):
                number += 1
                priority = rng.choices(["P1", "P2", "P3", "P4"], [5, 20, 50, 25])[0]
                opened = now - timedelta(minutes=rng.randint(30, 30 * 24 * 60))
                due = opened + due_after[priority]
                is_open = rng.random() < 0.3
                items.append(
                    WorkItem(
                        ref=f"DEMO-INC{number:05d}",
                        pool=pool,
                        priority=priority,
                        opened_at=opened,
                        due_at=due,
                        effort_minutes=rng.choice([15, 30, 45, 60, 90, 120, 240]),
                        closed_at=None
                        if is_open
                        else opened + timedelta(minutes=rng.randint(20, 3 * 24 * 60)),
                    )
                )
            WorkItem.objects.bulk_create(items)
