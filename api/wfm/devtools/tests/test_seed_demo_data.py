from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
from django.test import override_settings
from django.utils import timezone

from wfm.audit.models import AuditEvent
from wfm.devtools.demo_history import outage_day, recorder_gap_day
from wfm.devtools.management.commands.seed_demo_data import planning_monday
from wfm.forecasting.models import ForecastStatus, ForecastVersion
from wfm.people.models import LeaveRequest, LeaveStatus, SwapRequest, SwapStatus
from wfm.scheduling.models import Employee, RosterStatus, RosterWeek, ShiftAssignment
from wfm.servicedesk.models import WorkItem
from wfm.telephony.models import IntervalActual, Queue

pytestmark = pytest.mark.django_db

PASSWORD = "demo-password-123"


@pytest.fixture
def seeded() -> None:
    with override_settings(DEBUG=True):
        call_command("seed_demo", password=PASSWORD)
        call_command("seed_demo_data")


def _offered_on(queue: Queue, day: date) -> int:
    zone = ZoneInfo(settings.TIME_ZONE)
    start = datetime.combine(day, time(0, 0), tzinfo=zone)
    rows = IntervalActual.objects.filter(
        queue=queue, interval_start__gte=start, interval_start__lt=start + timedelta(days=1)
    )
    return rows.aggregate(total=Sum("offered"))["total"] or 0


@override_settings(DEBUG=False)
def test_refuses_outside_development(monkeypatch: pytest.MonkeyPatch) -> None:
    # Invented data in a real customer's database would be mistaken for theirs.
    monkeypatch.delenv("WFM_ALLOW_DEMO_SEED", raising=False)
    with pytest.raises(CommandError, match="disabled"):
        call_command("seed_demo_data")


@override_settings(DEBUG=True)
def test_needs_the_demo_logins_first() -> None:
    with pytest.raises(CommandError, match="seed_demo"):
        call_command("seed_demo_data")


def test_a_second_run_is_refused_rather_than_doubling_everything(seeded: None) -> None:
    with override_settings(DEBUG=True), pytest.raises(CommandError, match="already here"):
        call_command("seed_demo_data")


def test_history_has_the_real_life_shapes_a_planner_expects(seeded: None) -> None:
    today = timezone.localdate()
    support = Queue.objects.get(name="Service Desk")
    assert Queue.objects.count() == 3
    # A recorder outage is a day with NO rows (not observed), unlike a quiet day with few calls.
    gap = recorder_gap_day(today)
    assert not IntervalActual.objects.filter(
        queue=support, interval_start__date__range=(gap, gap)
    ).exists()
    # An outage day carries far more calls than the same weekday a week later.
    outage = outage_day(today)
    assert _offered_on(support, outage) > 1.4 * _offered_on(support, outage + timedelta(days=7))
    # Every row is internally consistent: nobody answered who was not offered.
    for row in IntervalActual.objects.all().iterator():
        assert row.answered + row.abandoned == row.offered
        assert row.answered_in_sl <= row.answered


def test_forecasts_are_live_and_rosters_are_in_the_planned_states(seeded: None) -> None:
    live = ForecastVersion.objects.filter(status=ForecastStatus.PUBLISHED)
    assert live.count() == 3
    statuses = {
        (week.week_start, week.queue.name): week.status for week in RosterWeek.objects.all()
    }
    week0 = planning_monday(timezone.localdate())
    for name in ("Service Desk", "Billing Support", "Night Desk"):
        assert statuses[(week0, name)] == RosterStatus.PUBLISHED
        assert statuses[(week0 + timedelta(days=7), name)] == RosterStatus.PUBLISHED
        assert statuses[(week0 + timedelta(days=14), name)] == RosterStatus.DRAFT
    assert not ShiftAssignment.objects.filter(
        day__gte=week0 + timedelta(days=21)
    ).exists()  # the fourth week is left for the presenter to plan
    # Nobody works more hours than their contract, in any week (the rules ran, not bypassed).
    per_week: dict[tuple[int, object], int] = {}
    for a in ShiftAssignment.objects.select_related("template", "roster_week"):
        key = (a.employee_id, a.roster_week.week_start)
        per_week[key] = per_week.get(key, 0) + a.template.paid_minutes
    hours = {e.pk: float(e.weekly_hours) * 60 for e in Employee.objects.all()}
    assert all(minutes <= hours[pk] for (pk, _), minutes in per_week.items())


def test_leave_is_in_every_state_and_approved_leave_is_off_the_roster(seeded: None) -> None:
    states = set(LeaveRequest.objects.values_list("status", flat=True))
    assert states == {
        LeaveStatus.APPROVED,
        LeaveStatus.PENDING,
        LeaveStatus.REJECTED,
        LeaveStatus.CANCELLED,
    }
    assert LeaveRequest.objects.filter(status=LeaveStatus.PENDING).count() == 2
    for leave in LeaveRequest.objects.filter(status=LeaveStatus.APPROVED):
        assert not ShiftAssignment.objects.filter(
            employee=leave.employee, day__range=(leave.start_date, leave.end_date)
        ).exists()


def test_service_desk_has_open_overdue_and_closed_work(seeded: None) -> None:
    now = timezone.now()
    assert WorkItem.objects.filter(closed_at__isnull=False).exists()
    assert WorkItem.objects.filter(closed_at__isnull=True, due_at__lt=now).exists()
    assert WorkItem.objects.filter(closed_at__isnull=True, due_at__gt=now).exists()


def test_the_seeding_is_audited_and_the_chain_still_verifies(seeded: None) -> None:
    # The seed went through the audited services; a broken chain would mean it bypassed them.
    assert AuditEvent.objects.filter(action="system.seed_demo_data").count() == 1
    assert AuditEvent.objects.filter(action="roster.assigned").exists()
    call_command("audit_verify")


def test_swaps_are_in_the_states_a_demo_needs_and_the_approved_one_moved_the_roster(
    seeded: None,
) -> None:
    states = list(SwapRequest.objects.values_list("status", flat=True))
    assert SwapStatus.OPEN in states
    assert SwapStatus.AWAITING_APPROVAL in states
    assert SwapStatus.APPROVED in states
    # The open requests are ones the demo agent could take, so their board has something on it.
    from django.contrib.auth import get_user_model

    from wfm.people import swap_selectors

    agent = get_user_model().objects.get(username="agent")
    assert swap_selectors.board(agent), "the demo agent's board should not be empty"
    # The approved swap really happened: each person now holds the other's shift.
    done = SwapRequest.objects.get(status=SwapStatus.APPROVED)
    assert done.to_employee is not None
    assert done.to_day is not None
    assert ShiftAssignment.objects.filter(
        employee=done.to_employee, day=done.from_day, template=done.from_template
    ).exists()
    assert ShiftAssignment.objects.filter(
        employee=done.from_employee, day=done.to_day, template=done.to_template
    ).exists()


def test_declared_availability_is_in_the_data_and_the_roster_respected_it(seeded: None) -> None:
    from wfm.people.models import Availability

    # Part-timers cannot work Thursday or Friday, the demo agent never works Sundays.
    assert Availability.objects.filter(kind="unavailable").exists()
    assert Availability.objects.filter(kind="preferred", employee__emp_no="DEMO-AGENT").exists()
    for window in Availability.objects.filter(kind="unavailable"):
        worked = ShiftAssignment.objects.filter(
            employee=window.employee, day__week_day__isnull=False
        )
        assert not [a for a in worked if a.day.weekday() == window.weekday]


def test_contracts_hold_the_queues_to_their_promises_and_billing_is_the_one_at_risk(
    seeded: None,
) -> None:
    from django.contrib.auth import get_user_model

    from wfm.contracts import selectors as contract_selectors

    planner = get_user_model().objects.get(username="planner")
    week = planning_monday(timezone.localdate())
    rows = {r.contract.name: r for r in contract_selectors.contract_rows(planner, week)}
    assert set(rows) == {"Member support", "Claims line"}
    # The promise is written onto the queues the contract holds.
    billing = Queue.objects.get(name="Billing Support")
    assert (float(billing.sl_target_pct), billing.sl_threshold_s) == (90.0, 30)
    # Billing is short of people all week by design, so its contract is at risk.
    assert rows["Claims line"].at_risk
    assert rows["Claims line"].gap > 0


def test_each_lead_has_swap_work_from_their_own_team(seeded: None) -> None:
    # Failure caught: a demo where one lead sees every swap and the other none, so the two-team
    # approval flow (a lead decides only for their own people) cannot be shown.
    from django.contrib.auth import get_user_model

    users = get_user_model().objects
    for username in ("lead", "lead2"):
        mine = SwapRequest.objects.for_user(users.get(username=username))
        assert mine.exclude(from_employee__user__username=username).exists(), username
    waiting = SwapRequest.objects.filter(status=SwapStatus.AWAITING_APPROVAL)
    assert waiting.exists()
    for swap in waiting:
        decider = swap.from_employee.manager
        assert decider is not None, "a waiting swap must have a lead who can decide it"
