"""Wellbeing prompts (WEL-01): who sees them, and that they carry facts, never a score.

"Today" is Monday 15 June 2026. Synthetic people only.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from wfm.accounts.models import Role, User
from wfm.overtime.models import OvertimeRequest, OvertimeStatus
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import Employee, RosterWeek, ShiftAssignment, ShiftTemplate
from wfm.scheduling.tests.helpers import login, person, queue, standard_shifts

pytestmark = pytest.mark.django_db

FLAGS = "/api/v1/wellbeing/flags"
TODAY = date(2026, 6, 15)
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.skills.api.timezone.localdate", lambda: TODAY)


def work(employee: Employee, days: list[date]) -> None:
    shift = ShiftTemplate.objects.filter(code="D1").first() or standard_shifts()["D1"]
    q = queue()
    for day in days:
        monday = day - timedelta(days=day.weekday())
        week, _ = RosterWeek.objects.get_or_create(queue=q, week_start=monday)
        ShiftAssignment.objects.create(roster_week=week, employee=employee, day=day, template=shift)


def run_of(n: int) -> list[date]:
    return [TODAY - timedelta(days=i) for i in range(n)]


def overtime(employee: Employee, day: date, status: str = OvertimeStatus.APPROVED) -> None:
    by = User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]
    OvertimeRequest.objects.create(
        employee=employee,
        day=day,
        start_time=time(17, 30),
        end_time=time(19, 0),
        minutes=90,
        status=status,
        requested_by=by,
    )


class World:
    def __init__(self) -> None:
        self.ann = person("E001", user=User.objects.create(username="u-agent", role=Role.AGENT))
        self.bob = person("E002")  # not in the lead's team
        self.lead = lead_of(self.ann)


@pytest.fixture
def world() -> World:
    return World()


def codes_for(role: Role) -> dict[str, list[str]]:
    r = login(role).get(FLAGS)
    assert r.status_code == 200
    return {p["empNo"]: [f["code"] for f in p["flags"]] for p in r.json()["people"]}


class TestWhoSees:
    @pytest.fixture(autouse=True)
    def _overloaded(self, world: World) -> None:
        work(world.ann, run_of(8))
        work(world.bob, run_of(8))
        work(world.lead, run_of(8))

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planner_and_admin_see_everyone_flagged(self, role: Role) -> None:
        assert set(codes_for(role)) == {"E001", "E002", "L001"}

    def test_a_lead_sees_their_own_team_only_and_not_themselves(self) -> None:
        assert set(codes_for(Role.LEAD)) == {"E001"}

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_is_served(self, role: Role) -> None:
        assert login(role).get(FLAGS).status_code == 403

    def test_the_answer_has_no_score_or_ranking(self) -> None:
        body = login(Role.PLANNER).get(FLAGS).json()
        assert set(body) == {"asOf", "people"}
        for p in body["people"]:
            assert set(p) == {"employeeId", "empNo", "employee", "flags"}
            assert all(set(f) == {"code", "value"} for f in p["flags"])
        assert [p["empNo"] for p in body["people"]] == sorted(p["empNo"] for p in body["people"])

    def test_a_left_employee_is_not_flagged(self, world: World) -> None:
        Employee.objects.filter(pk=world.bob.pk).update(end_date=TODAY - timedelta(days=1))
        assert "E002" not in codes_for(Role.PLANNER)


class TestWhatRaisesAFlag:
    def test_nobody_is_flagged_on_an_ordinary_week(self, world: World) -> None:
        work(world.ann, [TODAY - timedelta(days=n) for n in (0, 1, 2, 3, 4, 7, 8, 9)])
        assert codes_for(Role.PLANNER) == {}

    def test_seven_days_in_a_row(self, world: World) -> None:
        work(world.ann, run_of(7))
        assert "long_run" in codes_for(Role.PLANNER)["E001"]

    def test_six_days_is_not_enough(self, world: World) -> None:
        work(world.ann, run_of(6))
        assert codes_for(Role.PLANNER) == {}

    def test_a_future_roster_raises_nothing(self, world: World) -> None:
        work(world.ann, [TODAY + timedelta(days=n) for n in range(1, 10)])
        assert codes_for(Role.PLANNER) == {}

    def test_repeated_overtime_counts_only_approved(self, world: World) -> None:
        for n in (1, 8, 15, 22):
            overtime(world.ann, TODAY - timedelta(days=n))
        assert "repeated_overtime" in codes_for(Role.PLANNER)["E001"]
        OvertimeRequest.objects.update(status=OvertimeStatus.PENDING)
        assert codes_for(Role.PLANNER) == {}

    def test_rising_unplanned_absence_counts_sick_leave_not_annual(self, world: World) -> None:
        by = User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]
        sick = LeaveType.objects.get(code="sick")
        # Wednesday 10 to Friday 12 June: three weekdays this month, none before.
        leave = {
            "employee": world.ann,
            "start_date": date(2026, 6, 10),
            "end_date": date(2026, 6, 12),
            "days": 3,
            "status": LeaveStatus.APPROVED,
            "requested_by": by,
        }
        LeaveRequest.objects.create(leave_type=LeaveType.objects.get(code="annual"), **leave)
        assert codes_for(Role.PLANNER) == {}
        LeaveRequest.objects.create(leave_type=sick, **leave)
        assert codes_for(Role.PLANNER)["E001"] == ["rising_absence"]
        LeaveRequest.objects.filter(leave_type=sick).update(status=LeaveStatus.PENDING)
        assert codes_for(Role.PLANNER) == {}


def test_every_role_is_covered() -> None:
    assert len(ALL_ROLES) == len(Role)
