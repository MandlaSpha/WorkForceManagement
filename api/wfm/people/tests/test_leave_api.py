"""Leave and approvals on a real PostgreSQL, with the numbers worked out by hand.

Today is frozen at Wednesday 20 May 2026. QueueA's published requirement is 2 people at every
half-hour of 09:00-17:30 (17 half-hours) on Monday 25 May and none on Tuesday 26 May. E001 (the
agent) is rostered on D1 (09:00-17:30) on Monday and Tuesday, E002 on Monday only.

Annual leave Monday 25 to Tuesday 26 May is 2 working days. Approving it takes E001's two shifts
off the roster. Of those 34 half-hours, the 17 on Monday were covered with none to spare (2
scheduled, 2 required) and become short; Tuesday needed nobody so nothing becomes short.
    impact   shifts 2, hours 17.0, intervals 34, newly under 17, already under 0

Public holidays: Freedom Day (Monday 27 April) and Workers' Day (Friday 1 May) 2026, so leave from
Monday 27 April to Friday 1 May is 3 working days, not 5.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import ShiftAssignment
from wfm.scheduling.tests.helpers import (
    ASSIGN,
    MON,
    PLAN,
    TUE,
    assign,
    params,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)
from wfm.scheduling.tests.helpers import login as scheduling_login

from .team import lead_of

pytestmark = pytest.mark.django_db

LEAVE = "/api/v1/people/leave"
TODAY = date(2026, 5, 20)


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


def login(role: Role = Role.PLANNER) -> Client:
    return scheduling_login(role)


def freeze(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: day)


def kind(code: str = "annual") -> int:
    return LeaveType.objects.get(code=code).pk


def ask(client: Client, start: date, end: date, code: str = "annual", **extra: Any) -> Any:
    body = {"leaveTypeId": kind(code), "startDate": str(start), "endDate": str(end), **extra}
    return client.post(f"{LEAVE}/requests", body, content_type="application/json")


def act(client: Client, request_id: int, what: str) -> Any:
    return client.post(
        f"{LEAVE}/requests/{request_id}/{what}",
        **({"data": {}, "content_type": "application/json"} if what == "reject" else {}),
    )


@pytest.fixture
def week() -> dict[str, Any]:
    """E001 (linked to the agent login) on D1 Monday and Tuesday, E002 on D1 Monday."""
    shifts = standard_shifts()
    login(Role.AGENT)
    agent = User.objects.get(username="u-agent")
    publish_forecast(queue(), {**{(MON, s): 2 for s in range(18, 35)}, (TUE, 18): 0})
    e1 = person("E001", user=agent)
    e2 = person("E002")
    lead_of(e1, e2)
    assign(login(), queue(), e1, MON, shifts["D1"])
    assign(login(), queue(), e1, TUE, shifts["D1"])
    assign(login(), queue(), e2, MON, shifts["D1"])
    return {"shifts": shifts, "e1": e1, "e2": e2, "agent": agent}


def monday_cell(slot: int = 18) -> dict[str, Any]:
    body = login().get(PLAN, params(queue(), MON)).json()
    return body["cells"][str(MON)][slot]  # type: ignore[no-any-return]


class TestApplying:
    def test_an_agent_asks_for_leave_and_it_waits_for_a_decision(
        self, week: dict[str, Any]
    ) -> None:
        response = ask(login(Role.AGENT), MON, TUE)
        assert response.status_code == 201, response.content
        body = response.json()
        assert (body["status"], body["days"], body["employee"], body["mine"]) == (
            "pending",
            2,
            "Person E001",
            True,
        )

    def test_weekends_and_public_holidays_are_not_leave_days(
        self, week: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        freeze(monkeypatch, date(2026, 4, 20))
        body = ask(login(Role.AGENT), date(2026, 4, 27), date(2026, 5, 1)).json()
        assert body["days"] == 3  # Tue 28, Wed 29, Thu 30 April

    def test_dates_that_are_only_a_weekend_are_refused(self, week: dict[str, Any]) -> None:
        response = ask(login(Role.AGENT), date(2026, 5, 23), date(2026, 5, 24))
        assert (response.status_code, response.json()["code"]) == (422, "leave.no_working_days")

    def test_leave_across_new_year_is_taken_from_both_years(
        self, week: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        freeze(monkeypatch, date(2026, 12, 1))
        # Mon 28 Dec 2026 to Fri 8 Jan 2027: 4 days in 2026, 1 Jan is a holiday, 5 days in 2027.
        body = ask(login(Role.AGENT), date(2026, 12, 28), date(2027, 1, 8)).json()
        assert body["days"] == 9
        assert LeaveRequest.objects.get(pk=body["id"]).days_by_year == {"2026": 4, "2027": 5}

    @pytest.mark.parametrize(
        ("start", "end", "code"),
        [
            (date(2026, 5, 26), date(2026, 5, 25), "leave.range_invalid"),
            (date(2026, 6, 1), date(2026, 9, 30), "leave.too_long"),  # 122 days
            (date(2026, 4, 1), date(2026, 4, 2), "leave.too_far_back"),  # 49 days ago
            (date(2028, 6, 1), date(2028, 6, 2), "leave.too_far_ahead"),
        ],
    )
    def test_nonsense_dates_are_refused_with_a_reason(
        self, week: dict[str, Any], start: date, end: date, code: str
    ) -> None:
        response = ask(login(Role.AGENT), start, end)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert LeaveRequest.objects.count() == 0

    def test_recent_past_is_allowed_for_sick_leave_written_up_afterwards(
        self, week: dict[str, Any]
    ) -> None:
        assert (
            ask(login(Role.AGENT), date(2026, 5, 11), date(2026, 5, 12), "sick").status_code == 201
        )

    def test_leave_outside_the_persons_employment_is_refused(self, week: dict[str, Any]) -> None:
        week["e1"].end_date = date(2026, 5, 29)
        week["e1"].save()
        response = ask(login(Role.AGENT), date(2026, 5, 28), date(2026, 6, 2))
        assert response.json()["code"] == "leave.not_employed"

    def test_a_person_not_on_the_employee_list_cannot_take_leave(self) -> None:
        response = ask(login(Role.AGENT), MON, TUE)
        assert (response.status_code, response.json()["code"]) == (422, "leave.no_employee_record")


class TestBalances:
    def test_start_as_the_bcea_defaults_and_say_nobody_has_confirmed_them(self) -> None:
        types = {t["code"]: t for t in login(Role.AGENT).get(f"{LEAVE}/types").json()}
        assert (types["annual"]["daysPerYear"], types["sick"]["daysPerYear"]) == (15, 10)
        assert types["family"]["daysPerYear"] == 3
        assert types["unpaid"]["daysPerYear"] is None  # no limit
        assert all(t["confirmed"] is False for t in types.values())

    def test_pending_leave_is_set_aside_so_it_cannot_be_asked_for_twice(
        self, week: dict[str, Any]
    ) -> None:
        ask(login(Role.AGENT), MON, TUE)
        annual = self.balance("annual")
        assert (annual["entitlement"], annual["taken"], annual["pending"], annual["available"]) == (
            15,
            0,
            2,
            13,
        )

    def test_approved_leave_is_taken_and_a_rejected_one_gives_the_days_back(
        self, week: dict[str, Any]
    ) -> None:
        first = ask(login(Role.AGENT), MON, TUE).json()["id"]
        second = ask(login(Role.AGENT), date(2026, 6, 1), date(2026, 6, 2)).json()["id"]
        act(login(Role.LEAD), first, "approve")
        act(login(Role.LEAD), second, "reject")
        annual = self.balance("annual")
        assert (annual["taken"], annual["pending"], annual["available"]) == (2, 0, 13)

    def test_asking_for_more_than_is_left_is_refused_and_says_how_much_is_left(
        self, week: dict[str, Any]
    ) -> None:
        # Sick leave is 10 days a year: Mon 25 May to Fri 5 Jun is exactly 10 working days.
        assert ask(login(Role.AGENT), MON, date(2026, 6, 5), "sick").status_code == 201
        response = ask(login(Role.AGENT), date(2026, 6, 8), date(2026, 6, 8), "sick")
        assert (response.status_code, response.json()["code"]) == (
            422,
            "leave.insufficient_balance",
        )
        assert "0.0 days left" in response.json()["detail"]

    def test_exactly_the_whole_entitlement_is_allowed(self, week: dict[str, Any]) -> None:
        assert ask(login(Role.AGENT), MON, date(2026, 6, 5), "sick").status_code == 201

    def test_a_kind_of_leave_with_no_limit_has_none_to_exceed(self, week: dict[str, Any]) -> None:
        # 60 days of unpaid leave: from Monday 1 June, about three months.
        assert (
            ask(login(Role.AGENT), date(2026, 6, 1), date(2026, 8, 28), "unpaid").status_code == 201
        )
        assert self.balance("unpaid")["available"] is None

    def test_a_year_is_counted_on_its_own(
        self, week: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        freeze(monkeypatch, date(2026, 12, 1))
        ask(login(Role.AGENT), date(2026, 12, 28), date(2027, 1, 8))
        body = login(Role.AGENT).get(f"{LEAVE}/balances", {"year": 2027}).json()
        annual = next(b for b in body["balances"] if b["code"] == "annual")
        assert (annual["pending"], annual["available"]) == (5, 10)

    @staticmethod
    def balance(code: str) -> dict[str, Any]:
        body = login(Role.AGENT).get(f"{LEAVE}/balances", {"year": 2026}).json()
        return next(b for b in body["balances"] if b["code"] == code)


class TestOverlap:
    def test_a_second_request_for_the_same_days_is_refused(self, week: dict[str, Any]) -> None:
        ask(login(Role.AGENT), MON, TUE)
        response = ask(login(Role.AGENT), TUE, date(2026, 5, 27))
        assert (response.status_code, response.json()["code"]) == (409, "leave.overlaps")

    def test_the_next_day_is_fine(self, week: dict[str, Any]) -> None:
        ask(login(Role.AGENT), MON, TUE)
        assert ask(login(Role.AGENT), date(2026, 5, 27), date(2026, 5, 27)).status_code == 201

    def test_a_cancelled_request_frees_its_days(self, week: dict[str, Any]) -> None:
        first = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.AGENT), first, "cancel")
        assert ask(login(Role.AGENT), MON, TUE).status_code == 201


class TestCoverageImpactBeforeApproval:
    def test_shows_the_hours_the_intervals_and_what_would_become_short(
        self, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        body = login(Role.LEAD).get(f"{LEAVE}/requests/{request_id}/impact").json()
        assert body == {
            "shifts": 2,
            "hours": 17.0,
            "intervals": 34,
            "newlyUnder": 17,
            "alreadyUnder": 0,
            "unknown": 0,
        }

    def test_a_person_with_no_shifts_on_those_days_has_no_impact(
        self, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), date(2026, 6, 1), date(2026, 6, 2)).json()["id"]
        body = login(Role.LEAD).get(f"{LEAVE}/requests/{request_id}/impact").json()
        assert (body["shifts"], body["hours"], body["newlyUnder"]) == (0, 0.0, 0)

    def test_looking_changes_nothing(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        login(Role.LEAD).get(f"{LEAVE}/requests/{request_id}/impact")
        assert ShiftAssignment.objects.count() == 3
        assert LeaveRequest.objects.get(pk=request_id).status == LeaveStatus.PENDING


class TestApprovalWritesIntoTheSchedule:
    def test_the_persons_shifts_come_off_the_roster_and_coverage_shows_the_gap(
        self, week: dict[str, Any]
    ) -> None:
        assert monday_cell()["scheduled"] == 2  # E001 and E002
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]

        body = act(login(Role.LEAD), request_id, "approve").json()

        assert (body["request"]["status"], body["shiftsCleared"]) == ("approved", 2)
        assert not ShiftAssignment.objects.filter(employee=week["e1"]).exists()
        cell = monday_cell()
        assert (cell["scheduled"], cell["required"], cell["variance"]) == (1, 2, -1)

    def test_the_roster_then_refuses_to_put_the_person_on_those_days(
        self, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        response = login().put(
            ASSIGN,
            {
                "queueId": queue().pk,
                "employeeId": week["e1"].pk,
                "day": str(MON),
                "templateId": week["shifts"]["D1"].pk,
            },
            content_type="application/json",
        )
        assert (response.status_code, response.json()["code"]) == (422, "roster.on_leave")

    def test_the_day_after_the_leave_is_still_open_to_rostering(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        wednesday = date(2026, 5, 27)
        response = assign(login(), queue(), week["e1"], wednesday, week["shifts"]["D1"])
        assert response.status_code == 200

    def test_leave_wins_even_over_a_published_week(self, week: dict[str, Any]) -> None:
        login().post(
            "/api/v1/scheduling/roster/publish",
            {"queueId": queue().pk, "weekStart": str(MON)},
            content_type="application/json",
        )
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        body = act(login(Role.LEAD), request_id, "approve").json()
        assert body["shiftsCleared"] == 2

    def test_rejecting_leaves_the_roster_alone(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        body = act(login(Role.LEAD), request_id, "reject").json()
        assert (body["request"]["status"], body["shiftsCleared"]) == ("rejected", 0)
        assert ShiftAssignment.objects.filter(employee=week["e1"]).count() == 2


class TestCancellingReverses:
    def test_cancelling_approved_leave_puts_the_shifts_back(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")

        body = act(login(Role.AGENT), request_id, "cancel").json()

        assert (body["request"]["status"], body["shiftsRestored"], body["shiftsNotRestored"]) == (
            "cancelled",
            2,
            0,
        )
        assert monday_cell()["scheduled"] == 2  # coverage is back
        assert ShiftAssignment.objects.filter(employee=week["e1"]).count() == 2

    def test_a_shift_that_cannot_go_back_is_counted_not_hidden(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        # While on leave the person was put on Monday some other way (the roster refuses this,
        # so it is written directly): that day cannot be restored over it.
        ShiftAssignment.objects.create(
            roster_week=ShiftAssignment.objects.filter(employee=week["e2"]).get().roster_week,
            employee=week["e1"],
            day=MON,
            template=week["shifts"]["L1"],
        )
        body = act(login(Role.AGENT), request_id, "cancel").json()
        assert (body["shiftsRestored"], body["shiftsNotRestored"]) == (1, 1)

    def test_pending_leave_can_be_withdrawn(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        body = act(login(Role.AGENT), request_id, "cancel").json()
        assert body["request"]["status"] == "cancelled"
        assert ShiftAssignment.objects.filter(employee=week["e1"]).count() == 2  # untouched

    def test_leave_already_taken_cannot_be_cancelled(
        self, week: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        freeze(monkeypatch, date(2026, 6, 1))  # the leave is over
        response = act(login(Role.AGENT), request_id, "cancel")
        assert (response.status_code, response.json()["code"]) == (409, "leave.already_taken")

    @pytest.mark.parametrize("what", ["rejected", "cancelled"])
    def test_a_decided_or_withdrawn_request_cannot_be_cancelled_again(
        self, week: dict[str, Any], what: str
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "reject" if what == "rejected" else "approve")
        if what == "cancelled":
            act(login(Role.AGENT), request_id, "cancel")
        response = act(login(Role.AGENT), request_id, "cancel")
        assert (response.status_code, response.json()["code"]) == (409, "leave.not_cancellable")


class TestControls:
    def test_nobody_decides_their_own_leave(self) -> None:
        lead = User.objects.create(username="lead-self", role=Role.LEAD)
        person("E050", user=lead)
        client = Client()
        client.force_login(lead)
        request_id = ask(client, MON, TUE).json()["id"]
        response = act(client, request_id, "approve")
        assert (response.status_code, response.json()["code"]) == (403, "leave.own_request")
        assert LeaveRequest.objects.get(pk=request_id).status == LeaveStatus.PENDING
        assert act(login(Role.PLANNER), request_id, "approve").status_code == 200

    def test_a_decision_is_made_once(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        for what in ("approve", "reject"):
            response = act(login(Role.PLANNER), request_id, what)
            assert (response.status_code, response.json()["code"]) == (409, "leave.not_pending")

    def test_a_planner_can_ask_on_someones_behalf_and_it_says_who_asked(
        self, week: dict[str, Any]
    ) -> None:
        response = ask(login(Role.PLANNER), MON, TUE, employeeId=week["e2"].pk)
        assert response.status_code == 201
        assert (
            LeaveRequest.objects.get(pk=response.json()["id"]).requested_by.username == "u-planner"
        )

    def test_an_agent_cannot_ask_for_somebody_else(self, week: dict[str, Any]) -> None:
        response = ask(login(Role.AGENT), MON, TUE, employeeId=week["e2"].pk)
        assert response.status_code == 404
        assert LeaveRequest.objects.count() == 0

    def test_only_the_person_or_a_planner_can_withdraw_a_request(
        self, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        assert act(login(Role.LEAD), request_id, "cancel").status_code == 404
        assert act(login(Role.PLANNER), request_id, "cancel").status_code == 200


class TestWhoSeesWhat:
    def test_an_agent_sees_only_their_own_requests(self, week: dict[str, Any]) -> None:
        ask(login(Role.AGENT), MON, TUE)
        ask(login(Role.PLANNER), date(2026, 6, 1), date(2026, 6, 1), employeeId=week["e2"].pk)
        mine = login(Role.AGENT).get(f"{LEAVE}/requests").json()
        assert [(r["empNo"], r["mine"]) for r in mine] == [("E001", True)]

    @pytest.mark.parametrize("role", [Role.LEAD, Role.PLANNER, Role.ADMIN])
    def test_leads_planners_and_admins_see_everyones(
        self, role: Role, week: dict[str, Any]
    ) -> None:
        ask(login(Role.AGENT), MON, TUE)
        ask(login(Role.PLANNER), date(2026, 6, 1), date(2026, 6, 1), employeeId=week["e2"].pk)
        assert len(login(role).get(f"{LEAVE}/requests").json()) == 2

    def test_an_agent_cannot_read_someone_elses_request_or_its_impact_or_balances(
        self, week: dict[str, Any]
    ) -> None:
        other = ask(login(Role.PLANNER), MON, TUE, employeeId=week["e2"].pk).json()["id"]
        agent = login(Role.AGENT)
        assert act(agent, other, "cancel").status_code == 404
        assert agent.get(f"{LEAVE}/requests/{other}/impact").status_code == 403
        assert (
            agent.get(f"{LEAVE}/balances", {"year": 2026, "employee_id": week["e2"].pk}).status_code
            == 404
        )

    def test_the_status_filter(self, week: dict[str, Any]) -> None:
        first = ask(login(Role.AGENT), MON, TUE).json()["id"]
        ask(login(Role.AGENT), date(2026, 6, 1), date(2026, 6, 1))
        act(login(Role.LEAD), first, "approve")
        pending = login(Role.LEAD).get(f"{LEAVE}/requests", {"status": "pending"}).json()
        assert len(pending) == 1


class TestRoles:
    @pytest.mark.parametrize("role", [Role.AGENT, Role.LEAD, Role.PLANNER, Role.ADMIN])
    def test_people_who_work_a_roster_read_the_kinds_of_leave(self, role: Role) -> None:
        assert login(role).get(f"{LEAVE}/types").status_code == 200

    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_others_are_refused_everywhere(self, role: Role, week: dict[str, Any]) -> None:
        client = login(role)
        assert client.get(f"{LEAVE}/types").status_code == 403
        assert client.get(f"{LEAVE}/requests").status_code == 403
        assert client.get(f"{LEAVE}/balances", {"year": 2026}).status_code == 403
        assert ask(client, MON, TUE).status_code == 403

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_deciding_is_for_leads_planners_and_admins(
        self, role: Role, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        assert act(login(role), request_id, "approve").status_code == 403
        assert act(login(role), request_id, "reject").status_code == 403
        assert LeaveRequest.objects.get(pk=request_id).status == LeaveStatus.PENDING


class TestEntitlements:
    def put(self, client: Client, code: str, days: Any) -> Any:
        return client.put(
            f"{LEAVE}/types/{kind(code)}", {"daysPerYear": days}, content_type="application/json"
        )

    def test_the_admin_sets_them_and_that_confirms_them(self, week: dict[str, Any]) -> None:
        response = self.put(login(Role.ADMIN), "annual", 20)
        assert response.status_code == 200
        assert (response.json()["daysPerYear"], response.json()["confirmed"]) == (20, True)
        annual = next(
            b
            for b in login(Role.AGENT).get(f"{LEAVE}/balances", {"year": 2026}).json()["balances"]
            if b["code"] == "annual"
        )
        assert annual["available"] == 20

    def test_none_means_no_limit(self) -> None:
        assert self.put(login(Role.ADMIN), "annual", None).json()["daysPerYear"] is None

    @pytest.mark.parametrize("days", [-1, 367])
    def test_nonsense_is_refused(self, days: int) -> None:
        response = self.put(login(Role.ADMIN), "annual", days)
        assert (response.status_code, response.json()["code"]) == (422, "leave.entitlement_invalid")

    @pytest.mark.parametrize("role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE])
    def test_nobody_else_sets_them(self, role: Role) -> None:
        assert self.put(login(role), "annual", 99).status_code == 403
        assert LeaveType.objects.get(code="annual").days_per_year == 15


class TestAudit:
    @staticmethod
    def changes(action: Action) -> dict[str, tuple[str | None, str | None]]:
        event = AuditEvent.objects.filter(action=action).latest("chain_seq")
        return {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }

    def test_asking_records_what_when_and_by_whom_without_any_reason_text(
        self, week: dict[str, Any]
    ) -> None:
        ask(login(Role.AGENT), MON, TUE, "sick")
        event = AuditEvent.objects.get(action=Action.LEAVE_REQUESTED)
        assert event.actor_role == Role.AGENT
        assert self.changes(Action.LEAVE_REQUESTED) == {
            "type": (None, "sick"),
            "range": (None, "2026-05-25..2026-05-26"),
            "days": (None, "2"),
        }

    def test_approving_says_who_and_how_many_shifts_it_took_off(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        event = AuditEvent.objects.get(action=Action.LEAVE_APPROVED)
        assert event.actor_role == Role.LEAD
        assert self.changes(Action.LEAVE_APPROVED) == {
            "status": ("pending", "approved"),
            "shifts_cleared": (None, "2"),
        }

    def test_rejecting_and_cancelling_are_recorded(self, week: dict[str, Any]) -> None:
        first = ask(login(Role.AGENT), MON, TUE).json()["id"]
        second = ask(login(Role.AGENT), date(2026, 6, 1), date(2026, 6, 1)).json()["id"]
        act(login(Role.LEAD), first, "reject")
        act(login(Role.AGENT), second, "cancel")
        assert self.changes(Action.LEAVE_REJECTED) == {"status": ("pending", "rejected")}
        assert self.changes(Action.LEAVE_CANCELLED) == {"status": ("pending", "cancelled")}

    def test_cancelling_approved_leave_records_what_was_put_back(
        self, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        act(login(Role.LEAD), request_id, "approve")
        act(login(Role.AGENT), request_id, "cancel")
        assert self.changes(Action.LEAVE_CANCELLED) == {
            "status": ("approved", "cancelled"),
            "shifts_restored": (None, "2"),
            "shifts_not_restored": (None, "0"),
        }

    def test_a_refused_request_leaves_no_trace_of_one(self, week: dict[str, Any]) -> None:
        ask(login(Role.AGENT), date(2026, 5, 23), date(2026, 5, 24))
        assert not AuditEvent.objects.filter(action=Action.LEAVE_REQUESTED).exists()

    def test_changing_an_entitlement_records_before_and_after(self) -> None:
        login(Role.ADMIN).put(
            f"{LEAVE}/types/{kind('annual')}", {"daysPerYear": 18}, content_type="application/json"
        )
        assert self.changes(Action.LEAVE_ENTITLEMENT_CHANGED) == {
            "days_per_year": ("15.0", "18"),
            "confirmed": ("False", "True"),
        }


class TestRejectReason:
    def test_the_reason_is_trimmed_stored_audited_and_shown_to_the_requester(
        self, week: dict[str, Any]
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        response = login(Role.LEAD).post(
            f"{LEAVE}/requests/{request_id}/reject",
            {"reason": "  Month end, short staffed  "},
            content_type="application/json",
        )
        assert response.json()["request"]["decisionReason"] == "Month end, short staffed"
        mine = login(Role.AGENT).get(f"{LEAVE}/requests").json()
        assert [r["decisionReason"] for r in mine] == ["Month end, short staffed"]
        event = AuditEvent.objects.get(action=Action.LEAVE_REJECTED)
        assert AuditChange.objects.filter(
            event=event, field="decision_reason", new_value="Month end, short staffed"
        ).exists()

    def test_a_reason_is_optional_and_bounded(self, week: dict[str, Any]) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        too_long = login(Role.PLANNER).post(
            f"{LEAVE}/requests/{request_id}/reject",
            {"reason": "x" * 301},
            content_type="application/json",
        )
        assert too_long.status_code == 422
        assert (
            act(login(Role.PLANNER), request_id, "reject").json()["request"]["decisionReason"] == ""
        )

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_roles_that_cannot_decide_cannot_reject_with_a_reason(
        self, week: dict[str, Any], role: Role
    ) -> None:
        request_id = ask(login(Role.AGENT), MON, TUE).json()["id"]
        response = login(role).post(
            f"{LEAVE}/requests/{request_id}/reject",
            {"reason": "no"},
            content_type="application/json",
        )
        assert response.status_code in (403, 404)
        assert LeaveRequest.objects.get(pk=request_id).decision_reason == ""
