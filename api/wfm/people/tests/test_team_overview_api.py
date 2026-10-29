"""The Team screen's aggregate read (GET /people/team-overview).

Two teams: L1 (login u-lead) manages Ann; L2 (u-lead2) manages Bob, whose name is a canary that a
lead of the other team must never see. Ann is on the 09:00 to 17:30 shift Monday to Wednesday of
the week of Monday 25 May 2026 (24 paid hours of a 40 hour contract). "Today" is Wednesday 27 May.
Synthetic people only.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from wfm.accounts.models import Role, User
from wfm.attendance.models import AgentStateImport, AgentStateInterval
from wfm.people.models import (
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    SwapRequest,
    SwapStatus,
)
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import (
    Employee,
    RosterStatus,
    RosterWeek,
    ShiftAssignment,
    ShiftTemplate,
)
from wfm.scheduling.tests.helpers import MON, TUE, WED, login, person, queue, standard_shifts

pytestmark = pytest.mark.django_db

URL = "/api/v1/people/team-overview"
WEEK = {"week_start": str(MON)}
CANARY = "Canary Bob Otherteam"
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.team_selectors.timezone.localdate", lambda: WED)


def as_user(username: str, role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def work(employee: Employee, days: list[date], template: ShiftTemplate, status: str) -> None:
    q = queue()
    for day in days:
        monday = day - timedelta(days=day.weekday())
        week, _ = RosterWeek.objects.get_or_create(
            queue=q, week_start=monday, defaults={"status": status}
        )
        ShiftAssignment.objects.create(
            roster_week=week, employee=employee, day=day, template=template
        )


class World:
    def __init__(self) -> None:
        self.shifts = standard_shifts()
        self.ann = person(
            "E001", name="Ann Agent", user=User.objects.create(username="u-agent", role=Role.AGENT)
        )
        self.bob = person("E002", name=CANARY)
        self.lead = lead_of(self.ann)
        l2_user = User.objects.create(username="u-lead2", role=Role.LEAD)
        self.lead2 = person("L002", name="Lead Two", user=l2_user)
        self.bob.manager = self.lead2
        self.bob.save(update_fields=["manager"])
        d1 = self.shifts["D1"]
        work(self.ann, [MON, TUE, WED], d1, RosterStatus.PUBLISHED)
        work(self.bob, [MON, TUE], d1, RosterStatus.PUBLISHED)
        self.annual = LeaveType.objects.get(code="annual")

    def ann_states(self, *, full: bool) -> None:
        """Ann on the phones for the whole of Monday's shift (full) or half of it."""
        batch = AgentStateImport.objects.create(
            file_name="x.csv",
            uploaded_by=User.objects.get_or_create(
                username="u-planner", defaults={"role": Role.PLANNER}
            )[0],
            rows_read=1,
            rows_inserted=1,
            rows_duplicate=0,
            rows_rejected=0,
            rows_unmapped=0,
        )
        end = time(15, 30) if full else time(11, 0)  # UTC; the shift is 07:00 to 15:30 UTC
        AgentStateInterval.objects.create(
            batch=batch,
            employee=self.ann,
            login="ann1",
            state="available",
            start_at=datetime.combine(MON, time(7, 0), tzinfo=UTC),  # 09:00 in Johannesburg
            end_at=datetime.combine(MON, end, tzinfo=UTC),
        )


@pytest.fixture
def world() -> World:
    return World()


def get(client: Client, **query: Any) -> Any:
    return client.get(URL, {**WEEK, **query})


class TestRoles:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_admin_planner_and_lead_are_served(self, world: World, role: Role) -> None:
        response = get(login(role))
        assert response.status_code == 200
        assert response.json()["weekStart"] == str(MON)

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_is_served(self, world: World, role: Role) -> None:
        # Failure caught: an agent seeing colleagues' hours, or a read-only role seeing names.
        assert get(login(role)).status_code == 403

    def test_signed_out_is_refused(self, world: World) -> None:
        assert get(Client()).status_code == 401


class TestScope:
    def test_a_lead_sees_their_own_team_only(self, world: World) -> None:
        # Failure caught: a lead's screen listing the other team, or themselves.
        body = get(as_user("u-lead", Role.LEAD)).json()
        assert [p["empNo"] for p in body["people"]] == ["E001"]
        assert CANARY not in json.dumps(body)
        assert body["managers"] == []

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planner_and_admin_see_everyone_and_the_team_filter(
        self, world: World, role: Role
    ) -> None:
        body = get(login(role)).json()
        assert {p["empNo"] for p in body["people"]} == {"E001", "E002", "L002", "L001"}
        assert {m["name"] for m in body["managers"]} == {"Person L001", "Lead Two"}

    def test_a_planner_can_narrow_to_one_team(self, world: World) -> None:
        body = get(login(Role.PLANNER), manager_id=world.lead2.pk).json()
        assert [p["empNo"] for p in body["people"]] == ["E002"]

    def test_a_lead_naming_another_teams_manager_gets_404_not_403(self, world: World) -> None:
        # Failure caught: 403 would reveal that the other team exists; data would leak the team.
        lead = as_user("u-lead", Role.LEAD)
        other = get(lead, manager_id=world.lead2.pk)
        assert other.status_code == 404
        assert CANARY not in other.content.decode()
        assert get(lead, manager_id=world.lead.pk).status_code == 200

    def test_naming_someone_who_manages_nobody_is_404(self, world: World) -> None:
        assert get(login(Role.PLANNER), manager_id=world.bob.pk).status_code == 404
        assert get(login(Role.PLANNER), manager_id=999_999).status_code == 404

    def test_a_left_employee_is_not_listed(self, world: World) -> None:
        world.ann.end_date = MON - timedelta(days=1)
        world.ann.save(update_fields=["end_date"])
        assert get(as_user("u-lead", Role.LEAD)).json()["people"] == []


class TestCard:
    def card(self, role: Role = Role.LEAD) -> dict[str, Any]:
        client = as_user("u-lead", role) if role == Role.LEAD else login(role)
        return next(p for p in get(client).json()["people"] if p["empNo"] == "E001")

    def test_hours_and_shifts_come_from_the_published_roster(self, world: World) -> None:
        card = self.card()
        assert (card["rosteredHours"], card["contractHours"], card["shifts"]) == (24.0, 40.0, 3)
        assert [s["shift"] for s in card["shiftList"]] == ["D1", "D1", "D1"]
        assert card["shiftList"][0]["startTime"] == "09:00"

    def test_a_draft_week_is_not_counted(self, world: World) -> None:
        # Failure caught: unpublished shifts shown to a lead as if they were the plan.
        RosterWeek.objects.update(status=RosterStatus.DRAFT)
        assert self.card()["shifts"] == 0

    def test_no_adherence_data_is_none_not_zero(self, world: World) -> None:
        # Failure caught: a missing agent-state feed shown as 0 % or as off track.
        card = self.card()
        assert card["adherencePct"] is None
        assert card["onTrack"] is None
        assert all(s["adherencePct"] is None for s in card["shiftList"])
        summary = get(login(Role.PLANNER)).json()["summary"]
        assert summary["withAdherence"] == 0
        assert summary["onTrack"] == 0

    def test_adherence_comes_from_the_state_feed(self, world: World) -> None:
        world.ann_states(full=True)
        card = self.card()
        assert card["adherencePct"] is not None
        assert card["onTrack"] is (card["adherencePct"] >= 90.0)
        assert card["shiftList"][0]["adherencePct"] == card["adherencePct"]
        assert card["shiftList"][1]["adherencePct"] is None  # Tuesday has no state rows

    def test_half_a_shift_on_the_phones_is_off_track(self, world: World) -> None:
        # Failure caught: the on-track rule not using the shared threshold.
        world.ann_states(full=False)
        card = self.card()
        assert card["adherencePct"] is not None
        assert card["adherencePct"] < 90.0
        assert card["onTrack"] is False

    def test_pending_leave_open_swaps_and_balance(self, world: World) -> None:
        by = User.objects.get(username="u-agent")
        LeaveRequest.objects.create(
            employee=world.ann,
            leave_type=world.annual,
            start_date=MON + timedelta(days=14),
            end_date=MON + timedelta(days=15),
            days=2,
            days_by_year={"2026": 2},
            status=LeaveStatus.PENDING,
            requested_by=by,
        )
        SwapRequest.objects.create(
            queue=queue(),
            from_employee=world.ann,
            from_day=TUE,
            from_template=world.shifts["D1"],
            status=SwapStatus.OPEN,
            requested_by=by,
        )
        card = self.card()
        assert (card["pendingLeave"], card["openSwaps"]) == (1, 1)
        assert card["pendingRequests"][0]["leaveType"] == "Annual leave"
        balance = card["leaveBalances"][0]
        assert (balance["entitlementDays"], balance["pendingDays"], balance["availableDays"]) == (
            15.0,
            2.0,
            13.0,
        )

    def test_a_swap_with_the_other_team_names_nobody(self, world: World) -> None:
        # Failure caught: a colleague's name or id beside a swap, and the other team's person
        # being credited with the swap on the lead's screen.
        by = User.objects.get(username="u-agent")
        SwapRequest.objects.create(
            queue=queue(),
            from_employee=world.ann,
            from_day=TUE,
            from_template=world.shifts["D1"],
            to_employee=world.bob,
            to_day=MON,
            to_template=world.shifts["D1"],
            status=SwapStatus.AWAITING_APPROVAL,
            requested_by=by,
        )
        body = get(as_user("u-lead", Role.LEAD)).json()
        assert [p["empNo"] for p in body["people"]] == ["E001"]
        assert body["people"][0]["openSwaps"] == 1
        assert CANARY not in json.dumps(body)


class TestWellbeing:
    def overloaded(self, world: World) -> None:
        # Eight days in a row up to today, so a "long run" prompt exists for Ann.
        work(
            world.ann,
            [WED - timedelta(days=n) for n in range(3, 8)],
            world.shifts["D1"],
            RosterStatus.PUBLISHED,
        )

    def test_the_chip_is_a_yes_for_lead_and_planner_and_has_no_reason(self, world: World) -> None:
        # Failure caught: the code, the days or any wording of the reason reaching the card.
        self.overloaded(world)
        for client in (as_user("u-lead", Role.LEAD), login(Role.PLANNER)):
            raw = get(client).content.decode()
            card = next(p for p in json.loads(raw)["people"] if p["empNo"] == "E001")
            assert card["checkIn"] is True
            for word in ("long_run", "no_rest", "repeated_overtime", "rising_absence", "flags"):
                assert word not in raw

    def test_nobody_without_a_prompt_has_no_chip(self, world: World) -> None:
        body = get(login(Role.PLANNER)).json()
        assert not any(p["checkIn"] for p in body["people"])


class TestPrivacy:
    def test_no_pay_figure_anywhere_in_the_answer(self, world: World) -> None:
        # Failure caught: an hourly rate, overtime money or a cost added to a person.
        raw = get(login(Role.ADMIN)).content.decode().lower()
        for word in ("rate", "pay", "salary", "cost", "overtime", "zar", "multiplier"):
            assert word not in raw

    def test_the_person_has_exactly_the_documented_fields(self, world: World) -> None:
        person_keys = set(get(login(Role.ADMIN)).json()["people"][0])
        assert person_keys == {
            "employeeId", "empNo", "name", "contractType", "contractHours", "rosteredHours",
            "shifts", "adherencePct", "onTrack", "pendingLeave", "openSwaps", "checkIn",
            "shiftList", "leaveBalances", "pendingRequests",
        }  # fmt: skip

    def test_people_are_in_employee_number_order_not_ranked(self, world: World) -> None:
        # Failure caught: sorting by performance on the server.
        world.ann_states(full=True)
        numbers = [p["empNo"] for p in get(login(Role.PLANNER)).json()["people"]]
        assert numbers == sorted(numbers)


class TestSummaryAndQueries:
    def test_summary_adds_up_hours_without_comparing_people(self, world: World) -> None:
        s = get(as_user("u-lead", Role.LEAD)).json()["summary"]
        assert (s["headcount"], s["rosteredHours"], s["contractHours"], s["rosteredPct"]) == (
            1,
            24.0,
            40.0,
            60.0,
        )

    def test_an_empty_team_is_an_empty_list(self, world: World) -> None:
        user = User.objects.create(username="u-lead3", role=Role.LEAD)
        person("L003", user=user)
        body = get(as_user("u-lead3", Role.LEAD)).json()
        assert body["people"] == []
        assert body["summary"]["headcount"] == 0

    def test_a_week_day_other_than_monday_means_that_week(self, world: World) -> None:
        body = get(login(Role.PLANNER), week_start=str(WED)).json()
        assert body["weekStart"] == str(MON)

    def test_query_count_does_not_grow_with_the_team(self, world: World) -> None:
        # Failure caught: a query per person (an N+1) in the card builder.
        lead = as_user("u-lead", Role.LEAD)

        def queries() -> int:
            with CaptureQueriesContext(connection) as captured:
                assert get(lead).status_code == 200
            return len(captured)

        before = queries()
        for n in range(10):
            member = person(f"X{n:03d}")
            member.manager = world.lead
            member.save(update_fields=["manager"])
            work(member, [MON], world.shifts["D1"], RosterStatus.PUBLISHED)
        assert queries() == before
