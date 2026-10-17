"""Declared availability, the roster rule it feeds, and the agent's own schedule, on PostgreSQL.

Today is frozen at Wednesday 20 May 2026. D1 is 09:00-17:30, E1 07:00-15:30, L1 13:00-22:00,
N1 22:00-06:00. A (E001) is the agent login, B (E002) the colleague. Monday 25 May is weekday 0.

A person who says "Monday 12:00-13:00, I cannot work" cannot be rostered on D1 or E1 that Monday
(both cover 12:00) but can on Tuesday, and a "would rather" window never blocks anything.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.people.models import Availability, LeaveType
from wfm.scheduling.tests.helpers import (
    MON,
    NEXT_MON,
    TUE,
    assign,
    person,
    queue,
    standard_shifts,
)
from wfm.scheduling.tests.helpers import login as scheduling_login

from .team import lead_of

pytestmark = pytest.mark.django_db

AV = "/api/v1/people/availability"
SCHEDULE = "/api/v1/people/my-schedule"
TODAY = date(2026, 5, 20)


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


def login(role: Role = Role.PLANNER) -> Client:
    return scheduling_login(role)


def colleague_client() -> Client:
    user, _ = User.objects.get_or_create(username="u-colleague", defaults={"role": Role.AGENT})
    client = Client()
    client.force_login(user)
    return client


def declare(
    client: Client, weekday: int, start: str, end: str, kind: str = "unavailable", **x: Any
) -> Any:
    body = {"weekday": weekday, "startTime": start, "endTime": end, "kind": kind, **x}
    return client.post(AV, body, content_type="application/json")


@pytest.fixture
def staff() -> dict[str, Any]:
    shifts = standard_shifts()
    login(Role.AGENT)
    colleague_client()
    a = person("E001", user=User.objects.get(username="u-agent"))
    b = person("E002", user=User.objects.get(username="u-colleague"))
    lead_of(a, b)
    return {"shifts": shifts, "a": a, "b": b}


class TestDeclaring:
    def test_an_agent_declares_a_window_and_sees_it_listed(self, staff: dict[str, Any]) -> None:
        response = declare(login(Role.AGENT), 0, "12:00", "13:00")
        assert response.status_code == 201, response.content
        body = response.json()
        assert (body["weekday"], body["kind"], body["employee"]) == (
            0,
            "unavailable",
            "Person E001",
        )
        listed = login(Role.AGENT).get(AV).json()
        assert [(w["weekday"], w["startTime"], w["endTime"]) for w in listed] == [
            (0, "12:00:00", "13:00:00")
        ]

    def test_nothing_declared_is_an_empty_list_not_a_claim_of_availability(
        self, staff: dict[str, Any]
    ) -> None:
        assert login(Role.AGENT).get(AV).json() == []

    @pytest.mark.parametrize(
        ("args", "code"),
        [
            ((7, "09:00", "10:00", "unavailable"), "availability.window_invalid"),
            ((0, "09:15", "10:00", "unavailable"), "availability.window_invalid"),
            ((0, "10:00", "09:00", "unavailable"), "availability.window_invalid"),
            ((0, "10:00", "10:00", "unavailable"), "availability.window_invalid"),
            ((0, "09:00", "10:00", "always"), "availability.kind_invalid"),
        ],
    )
    def test_nonsense_is_refused_with_a_reason(
        self, staff: dict[str, Any], args: tuple[Any, ...], code: str
    ) -> None:
        response = declare(login(Role.AGENT), *args)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert Availability.objects.count() == 0

    def test_windows_that_overlap_are_refused_but_ones_that_touch_are_fine(
        self, staff: dict[str, Any]
    ) -> None:
        agent = login(Role.AGENT)
        assert declare(agent, 0, "09:00", "12:00").status_code == 201
        clash = declare(agent, 0, "11:30", "14:00", "preferred")  # shares 11:30-12:00
        assert (clash.status_code, clash.json()["code"]) == (409, "availability.overlaps")
        assert declare(agent, 0, "12:00", "14:00", "preferred").status_code == 201
        assert declare(agent, 1, "09:00", "12:00").status_code == 201  # another weekday

    def test_the_end_of_the_day_can_be_written_as_midnight(self, staff: dict[str, Any]) -> None:
        assert declare(login(Role.AGENT), 4, "18:00", "00:00").status_code == 201


class TestRemoving:
    def test_the_owner_removes_a_window_and_it_is_audited_without_times_of_anyone_else(
        self, staff: dict[str, Any]
    ) -> None:
        window_id = declare(login(Role.AGENT), 0, "12:00", "13:00").json()["id"]
        assert login(Role.AGENT).delete(f"{AV}/{window_id}").status_code == 200
        assert Availability.objects.count() == 0
        actions = list(
            AuditEvent.objects.filter(action__startswith="availability.")
            .order_by("chain_seq")
            .values_list("action", flat=True)
        )
        assert actions == [Action.AVAILABILITY_ADDED, Action.AVAILABILITY_REMOVED]

    def test_another_agent_cannot_remove_it_and_is_told_it_does_not_exist(
        self, staff: dict[str, Any]
    ) -> None:
        window_id = declare(login(Role.AGENT), 0, "12:00", "13:00").json()["id"]
        assert colleague_client().delete(f"{AV}/{window_id}").status_code == 404
        assert Availability.objects.count() == 1

    def test_a_planner_can_remove_anyones_window(self, staff: dict[str, Any]) -> None:
        window_id = declare(login(Role.AGENT), 0, "12:00", "13:00").json()["id"]
        assert login(Role.PLANNER).delete(f"{AV}/{window_id}").status_code == 200


class TestWhoSeesWhat:
    def test_an_agent_cannot_read_or_declare_for_a_colleague_but_a_planner_can_declare(
        self, staff: dict[str, Any]
    ) -> None:
        other = staff["b"].pk
        agent = login(Role.AGENT)
        assert agent.get(AV, {"employee_id": other}).status_code == 404
        assert declare(agent, 0, "09:00", "10:00", employeeId=other).status_code == 404
        on_behalf = declare(login(Role.PLANNER), 0, "09:00", "10:00", employeeId=other)
        assert on_behalf.status_code == 201
        assert on_behalf.json()["employee"] == "Person E002"
        assert Availability.objects.get().created_by.username == "u-planner"

    def test_a_colleague_never_sees_anothers_windows(self, staff: dict[str, Any]) -> None:
        declare(login(Role.AGENT), 0, "09:00", "10:00")
        assert colleague_client().get(AV).json() == []

    def test_a_lead_can_read_anyones_declared_availability(self, staff: dict[str, Any]) -> None:
        declare(login(Role.AGENT), 0, "09:00", "10:00")
        listed = login(Role.LEAD).get(AV, {"employee_id": staff["a"].pk}).json()
        assert len(listed) == 1

    def test_a_person_with_no_employee_record_is_told_so(self) -> None:
        response = login(Role.AGENT).get(AV)
        assert (response.status_code, response.json()["code"]) == (
            422,
            "availability.no_employee_record",
        )

    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_roles_that_do_not_work_a_roster_are_refused_everywhere(
        self, role: Role, staff: dict[str, Any]
    ) -> None:
        client = login(role)
        assert client.get(AV).status_code == 403
        assert declare(client, 0, "09:00", "10:00").status_code == 403
        assert client.delete(f"{AV}/1").status_code == 403
        assert client.get(SCHEDULE).status_code == 403


class TestTheRosterHonoursIt:
    def test_a_shift_covering_a_cannot_work_hour_is_refused(self, staff: dict[str, Any]) -> None:
        declare(login(Role.AGENT), 0, "12:00", "13:00")
        for code in ("D1", "E1"):  # both are working at 12:00
            response = assign(login(), queue(), staff["a"], MON, staff["shifts"][code])
            assert (response.status_code, response.json()["code"]) == (422, "roster.unavailable")

    def test_other_days_and_other_people_are_not_affected(self, staff: dict[str, Any]) -> None:
        declare(login(Role.AGENT), 0, "12:00", "13:00")
        assert assign(login(), queue(), staff["a"], TUE, staff["shifts"]["D1"]).status_code == 200
        assert assign(login(), queue(), staff["b"], MON, staff["shifts"]["D1"]).status_code == 200

    def test_a_would_rather_window_never_blocks_a_shift(self, staff: dict[str, Any]) -> None:
        declare(login(Role.AGENT), 0, "12:00", "13:00", "preferred")
        assert assign(login(), queue(), staff["a"], MON, staff["shifts"]["D1"]).status_code == 200

    def test_a_night_shift_is_blocked_by_the_next_mornings_window(
        self, staff: dict[str, Any]
    ) -> None:
        declare(login(Role.AGENT), 1, "01:00", "02:00")  # Tuesday small hours
        response = assign(login(), queue(), staff["a"], MON, staff["shifts"]["N1"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.unavailable")

    def test_the_refusal_is_audited_like_any_other_roster_refusal(
        self, staff: dict[str, Any]
    ) -> None:
        declare(login(Role.AGENT), 0, "12:00", "13:00")
        assign(login(), queue(), staff["a"], MON, staff["shifts"]["D1"])
        refused = AuditEvent.objects.filter(action=Action.ROSTER_REFUSED).latest("chain_seq")
        assert refused.reason == "roster.unavailable"

    def test_a_swap_cannot_put_someone_on_a_shift_in_their_cannot_work_hours(
        self, staff: dict[str, Any]
    ) -> None:
        planner = login()
        assign(planner, queue(), staff["a"], MON, staff["shifts"]["D1"])
        assign(planner, queue(), staff["b"], TUE, staff["shifts"]["L1"])  # 13:00-22:00
        declare(login(Role.AGENT), 1, "13:00", "14:00")  # A cannot work Tuesday 13:00
        from wfm.scheduling.models import ShiftAssignment

        give = ShiftAssignment.objects.get(employee=staff["a"], day=MON)
        take = ShiftAssignment.objects.get(employee=staff["b"], day=TUE)
        posted = login(Role.AGENT).post(
            "/api/v1/people/swaps", {"giveAssignmentId": give.pk}, content_type="application/json"
        )
        response = colleague_client().post(
            f"/api/v1/people/swaps/{posted.json()['id']}/accept",
            {"assignmentId": take.pk},
            content_type="application/json",
        )
        assert (response.status_code, response.json()["code"]) == (422, "roster.unavailable")


class TestMySchedule:
    @pytest.fixture
    def rota(self, staff: dict[str, Any]) -> dict[str, Any]:
        planner = login()
        assign(planner, queue(), staff["a"], MON, staff["shifts"]["D1"])
        assign(planner, queue(), staff["a"], TUE, staff["shifts"]["E1"])
        assign(planner, queue(), staff["a"], NEXT_MON, staff["shifts"]["L1"])
        assign(planner, queue(), staff["b"], MON, staff["shifts"]["D1"])
        planner.post(
            "/api/v1/scheduling/roster/publish",
            {"queueId": queue().pk, "weekStart": str(MON)},
            content_type="application/json",
        )
        return staff

    def test_it_shows_only_my_published_shifts_and_counts_the_ones_not_yet_published(
        self, rota: dict[str, Any]
    ) -> None:
        body = (
            login(Role.AGENT)
            .get(SCHEDULE, {"from_date": "2026-05-25", "to_date": "2026-06-07"})
            .json()
        )
        assert [(s["day"], s["shift"]) for s in body["shifts"]] == [
            ("2026-05-25", "D1"),
            ("2026-05-26", "E1"),
        ]
        # The 1 June shift is in a week the planner has not published: counted, never shown.
        assert body["unpublishedShifts"] == 1
        # A colleague's shift on the same day is not in my schedule.
        assert body["employee"] == "Person E001"

    def test_my_breaks_and_activities_show_on_my_shift_and_nobody_elses(
        self, rota: dict[str, Any]
    ) -> None:
        # Failure caught: a colleague's training showing on my schedule, or mine not showing.
        from wfm.scheduling.models import ShiftActivity, ShiftAssignment

        mine = ShiftAssignment.objects.get(employee__user__username="u-agent", day=MON)
        theirs = ShiftAssignment.objects.get(employee__user__username="u-colleague", day=MON)
        planner = User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[
            0
        ]
        ShiftActivity.objects.create(
            assignment=mine, kind="lunch", offset_slots=6, slots=2, created_by=planner
        )
        ShiftActivity.objects.create(
            assignment=theirs, kind="training", offset_slots=2, slots=4, created_by=planner
        )
        body = login(Role.AGENT).get(SCHEDULE, {"from_date": "2026-05-25"}).json()
        first = body["shifts"][0]["activities"]
        assert first == [{"kind": "lunch", "startTime": "12:00", "endTime": "13:00"}]
        other = colleague_client().get(SCHEDULE, {"from_date": "2026-05-25"}).json()
        assert other["shifts"][0]["activities"] == [
            {"kind": "training", "startTime": "10:00", "endTime": "12:00"}
        ]

    def test_the_colleague_sees_only_their_own_shift(self, rota: dict[str, Any]) -> None:
        body = colleague_client().get(SCHEDULE, {"from_date": "2026-05-25"}).json()
        assert [(s["day"], s["shift"]) for s in body["shifts"]] == [("2026-05-25", "D1")]
        assert body["unpublishedShifts"] == 0

    def test_leave_asked_or_approved_is_shown_but_rejected_leave_is_not(
        self, rota: dict[str, Any]
    ) -> None:
        kind = LeaveType.objects.get(code="unpaid").pk

        def ask(day: str) -> int:
            response = login(Role.AGENT).post(
                "/api/v1/people/leave/requests",
                {"leaveTypeId": kind, "startDate": day, "endDate": day},
                content_type="application/json",
            )
            return int(response.json()["id"])

        approved, rejected = ask("2026-06-02"), ask("2026-06-03")
        ask("2026-06-04")  # left pending
        login(Role.LEAD).post(f"/api/v1/people/leave/requests/{approved}/approve")
        login(Role.LEAD).post(f"/api/v1/people/leave/requests/{rejected}/reject")
        body = (
            login(Role.AGENT)
            .get(SCHEDULE, {"from_date": "2026-06-01", "to_date": "2026-06-07"})
            .json()
        )
        assert sorted((x["startDate"], x["status"]) for x in body["leave"]) == [
            ("2026-06-02", "approved"),
            ("2026-06-04", "pending"),
        ]

    def test_open_swaps_are_counted(self, rota: dict[str, Any]) -> None:
        from wfm.scheduling.models import ShiftAssignment

        give = ShiftAssignment.objects.get(employee=rota["a"], day=TUE)
        offered = login(Role.AGENT).post(
            "/api/v1/people/swaps", {"giveAssignmentId": give.pk}, content_type="application/json"
        )
        assert offered.status_code == 201, offered.content
        body = login(Role.AGENT).get(SCHEDULE, {"from_date": "2026-05-25"}).json()
        assert body["openSwaps"] == 1

    @pytest.mark.parametrize(
        "params",
        [
            {"from_date": "2026-06-10", "to_date": "2026-06-01"},
            {"from_date": "2026-01-01", "to_date": "2026-12-31"},
        ],
    )
    def test_a_backwards_or_huge_range_is_refused(
        self, rota: dict[str, Any], params: dict[str, str]
    ) -> None:
        response = login(Role.AGENT).get(SCHEDULE, params)
        assert (response.status_code, response.json()["code"]) == (422, "schedule.range_invalid")

    def test_someone_not_on_the_employee_list_is_told_so(self) -> None:
        response = login(Role.AGENT).get(SCHEDULE)
        assert (response.status_code, response.json()["code"]) == (
            422,
            "schedule.no_employee_record",
        )


class TestOnlyTheOwnerOrAPlannerRemoves:
    def test_a_lead_can_read_a_team_members_windows_but_not_remove_them(
        self, staff: dict[str, Any]
    ) -> None:
        window_id = declare(login(Role.AGENT), 0, "12:00", "13:00").json()["id"]
        lead = login(Role.LEAD)  # leads the team A is in (the fixture)
        assert len(lead.get(AV, {"employee_id": staff["a"].pk}).json()) == 1
        # Failure caught: being able to see a window is not being able to delete someone's
        # declared hours.
        assert lead.delete(f"{AV}/{window_id}").status_code == 404
        assert Availability.objects.count() == 1
