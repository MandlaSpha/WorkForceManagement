"""Shift swaps on a real PostgreSQL, with the outcomes worked out by hand.

Today is frozen at Wednesday 20 May 2026. Shifts: D1 09:00-17:30, E1 07:00-15:30, L1 13:00-22:00,
P1 10:00-14:00 (4 paid hours). A (E001, the agent login) is on D1 Monday 25 May; B (E002, the
colleague login) is on L1 Tuesday 26 May. A posts the Monday shift; B takes it by offering the
Tuesday one; a lead approves; A then works L1 on Tuesday and B works D1 on Monday.

Privacy: other agents see a posted request as a shift and a queue, never the poster's name; names
are shown to the two people only once the request is matched, and to leads, planners and admins.

The rules that must stop a bad swap, each with the numbers that break it:
- rest: A also works E1 on Wednesday 27 (07:00). L1 on Tuesday ends 22:00, so 9 hours of rest
  against the 11 required.
- hours: a person on a 7-hour contract cannot take an 8-hour shift in exchange for a 4-hour one.
- leave: A on approved leave on Tuesday cannot take Tuesday's shift.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.people.models import LeaveType, SwapRequest, SwapStatus
from wfm.scheduling.models import Employee, RosterStatus, RosterWeek, ShiftAssignment
from wfm.scheduling.tests.helpers import (
    MON,
    TUE,
    WED,
    assign,
    person,
    queue,
    standard_shifts,
)
from wfm.scheduling.tests.helpers import login as scheduling_login

from .team import lead_of

pytestmark = pytest.mark.django_db

SW = "/api/v1/people/swaps"
LEAVE = "/api/v1/people/leave"
TODAY = date(2026, 5, 20)


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


def login(role: Role = Role.PLANNER) -> Client:
    return scheduling_login(role)


def as_agent(username: str) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": Role.AGENT})
    client = Client()
    client.force_login(user)
    return client


def colleague_client() -> Client:
    return as_agent("u-colleague")


def row(employee: Employee, day: date) -> ShiftAssignment:
    found: ShiftAssignment = ShiftAssignment.objects.select_related("template").get(
        employee=employee, day=day
    )
    return found


def code(employee: Employee, day: date) -> str | None:
    found = ShiftAssignment.objects.filter(employee=employee, day=day).select_related("template")
    return found.first().template.code if found.exists() else None  # type: ignore[union-attr]


def post(client: Client, give: ShiftAssignment, **extra: Any) -> Any:
    body = {"giveAssignmentId": give.pk, **extra}
    return client.post(SW, body, content_type="application/json")


def take(client: Client, swap_id: int, mine: ShiftAssignment, **extra: Any) -> Any:
    body = {"assignmentId": mine.pk, **extra}
    return client.post(f"{SW}/{swap_id}/accept", body, content_type="application/json")


def act(client: Client, swap_id: int, what: str) -> Any:
    path = f"{SW}/{swap_id}/{what}"
    if what == "reject":
        return client.post(path, {}, content_type="application/json")
    return client.post(path)


def trade(giver: Client, give: ShiftAssignment, taker: Client, mine: ShiftAssignment) -> Any:
    """Post a shift and have a colleague take it by offering `mine`; returns the taking response
    (or the posting one if posting itself was refused)."""
    posted = post(giver, give)
    if posted.status_code != 201:
        return posted
    return take(taker, posted.json()["id"], mine)


@pytest.fixture
def rota() -> dict[str, Any]:
    shifts = standard_shifts()
    login(Role.AGENT)
    colleague_client()
    a = person("E001", user=User.objects.get(username="u-agent"))
    b = person("E002", user=User.objects.get(username="u-colleague"))
    lead_of(a, b)
    planner = login()
    assign(planner, queue(), a, MON, shifts["D1"])
    assign(planner, queue(), b, TUE, shifts["L1"])
    return {"shifts": shifts, "a": a, "b": b, "give": row(a, MON), "take": row(b, TUE)}


def asked(rota: dict[str, Any]) -> int:
    response = post(login(Role.AGENT), rota["give"])
    assert response.status_code == 201, response.content
    return int(response.json()["id"])


def agreed(rota: dict[str, Any]) -> int:
    swap_id = asked(rota)
    response = take(colleague_client(), swap_id, rota["take"])
    assert response.status_code == 200, response.content
    return swap_id


class TestTheWholeFlow:
    def test_post_take_approve_exchanges_the_two_shifts(self, rota: dict[str, Any]) -> None:
        a, b = rota["a"], rota["b"]
        swap_id = asked(rota)
        assert SwapRequest.objects.get(pk=swap_id).status == SwapStatus.OPEN
        # Nothing moves until a lead agrees.
        assert (code(a, MON), code(b, TUE)) == ("D1", "L1")

        taken = take(colleague_client(), swap_id, rota["take"]).json()
        assert taken["status"] == "awaiting_approval"
        assert (code(a, MON), code(b, TUE)) == ("D1", "L1")

        approved = act(login(Role.LEAD), swap_id, "approve").json()
        assert approved["status"] == "approved"
        # A now works Tuesday L1, B works Monday D1, and nobody works the shift they gave away.
        assert (code(a, TUE), code(b, MON)) == ("L1", "D1")
        assert (code(a, MON), code(b, TUE)) == (None, None)

    def test_the_audit_trail_tells_the_story_in_order_with_the_shift_moves(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = agreed(rota)
        act(login(Role.LEAD), swap_id, "approve")
        events = AuditEvent.objects.filter(action__startswith="swap.").order_by("chain_seq")
        assert [e.action for e in events] == [
            Action.SWAP_REQUESTED,
            Action.SWAP_ACCEPTED,
            Action.SWAP_APPROVED,
        ]
        assert [e.actor_role for e in events] == [Role.AGENT, Role.AGENT, Role.LEAD]
        moves = [
            (c.old_value, c.new_value)
            for c in AuditChange.objects.filter(event=events[2])
            if c.field == "shift"
        ]
        # A's D1 became L1 and B's L1 became D1: what changed, for whom, recorded.
        assert sorted(moves) == [("D1", "L1"), ("L1", "D1")]

    def test_a_published_week_can_be_swapped_and_stays_published(
        self, rota: dict[str, Any]
    ) -> None:
        login().post(
            "/api/v1/scheduling/roster/publish",
            {"queueId": queue().pk, "weekStart": str(MON)},
            content_type="application/json",
        )
        swap_id = agreed(rota)
        assert act(login(Role.LEAD), swap_id, "approve").status_code == 200
        week = RosterWeek.objects.get(queue=queue(), week_start=MON)
        assert week.status == RosterStatus.PUBLISHED

    def test_a_lead_can_reject_a_matched_swap(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        assert act(login(Role.LEAD), swap_id, "reject").json()["status"] == "rejected"
        assert (code(rota["a"], MON), code(rota["b"], TUE)) == ("D1", "L1")

    def test_the_poster_can_withdraw_an_open_or_a_matched_request(
        self, rota: dict[str, Any]
    ) -> None:
        open_id = asked(rota)
        assert act(login(Role.AGENT), open_id, "cancel").json()["status"] == "cancelled"
        # The shift is free to post again after withdrawing.
        again = asked(rota)
        take(colleague_client(), again, rota["take"])
        assert act(login(Role.AGENT), again, "cancel").json()["status"] == "cancelled"
        assert act(login(Role.LEAD), again, "approve").status_code == 409

    def test_an_approved_swap_cannot_be_withdrawn_it_would_leave_the_roster_half_done(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = agreed(rota)
        act(login(Role.LEAD), swap_id, "approve")
        response = act(login(Role.AGENT), swap_id, "cancel")
        assert (response.status_code, response.json()["code"]) == (409, "swap.not_cancellable")
        assert (code(rota["a"], TUE), code(rota["b"], MON)) == ("L1", "D1")

    def test_a_lead_cannot_approve_a_request_nobody_has_taken(self, rota: dict[str, Any]) -> None:
        swap_id = asked(rota)
        response = act(login(Role.LEAD), swap_id, "approve")
        assert (response.status_code, response.json()["code"]) == (
            409,
            "swap.not_waiting_for_approval",
        )

    def test_a_request_can_only_be_taken_once(self, rota: dict[str, Any]) -> None:
        swap_id = asked(rota)
        take(colleague_client(), swap_id, rota["take"])
        other = person(
            "E030",
            user=User.objects.get_or_create(username="u-other", defaults={"role": Role.AGENT})[0],
        )
        assign(login(), queue(), other, WED, rota["shifts"]["D1"])
        again = take(as_agent("u-other"), swap_id, row(other, WED))
        assert (again.status_code, again.json()["code"]) == (409, "swap.not_open")


class TestOtherAgentsDoNotSeeWho:
    """The poster's name must not reach another agent until the request is matched."""

    def test_the_board_shows_the_shift_and_queue_but_no_name(self, rota: dict[str, Any]) -> None:
        asked(rota)
        listing = colleague_client().get(f"{SW}/board")
        entry = listing.json()[0]
        assert (entry["queue"], entry["day"], entry["shift"]) == ("QueueA", "2026-05-25", "D1")
        # Failure caught: a name or an employee number anywhere in the payload.
        assert "Person E001" not in listing.content.decode()
        assert "E001" not in listing.content.decode()
        assert set(entry) == {"id", "queue", "day", "shift", "startTime", "endTime", "createdAt"}

    def test_another_agent_cannot_read_an_open_request_through_the_swap_list_or_by_id(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        assert colleague_client().get(SW).json() == []
        for what in ("approve", "reject", "cancel"):
            assert act(colleague_client(), swap_id, what).status_code in (403, 404)
        assert SwapRequest.objects.get(pk=swap_id).status == SwapStatus.OPEN

    def test_the_poster_does_not_see_their_own_request_on_the_board(
        self, rota: dict[str, Any]
    ) -> None:
        asked(rota)
        assert login(Role.AGENT).get(f"{SW}/board").json() == []

    def test_names_are_shown_to_both_people_once_matched(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        for client in (login(Role.AGENT), colleague_client()):
            seen = client.get(SW).json()[0]
            assert seen["id"] == swap_id
            assert (seen["fromEmployee"], seen["toEmployee"]) == ("Person E001", "Person E002")

    def test_a_third_agent_never_sees_a_matched_swap_either(self, rota: dict[str, Any]) -> None:
        agreed(rota)
        assert as_agent("u-third").get(SW).json() == []
        assert as_agent("u-third").get(f"{SW}/board").json() == []

    def test_only_people_who_work_the_queue_can_see_or_take_the_request(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        other_queue = queue("QueueB")
        user = User.objects.get_or_create(username="u-b-only", defaults={"role": Role.AGENT})[0]
        outsider = person("E040", queues=("QueueB",), user=user)
        assign(login(), other_queue, outsider, WED, rota["shifts"]["D1"])
        client = as_agent("u-b-only")
        assert client.get(f"{SW}/board").json() == []
        # Failure caught: a request on a queue you do not work must look like it is not there.
        assert take(client, swap_id, row(outsider, WED)).status_code == 404
        assert client.get(f"{SW}/{swap_id}/offers").json() == []

    def test_a_lead_sees_who_posted_a_team_members_request(self, rota: dict[str, Any]) -> None:
        asked(rota)
        seen = login(Role.LEAD).get(SW).json()[0]
        assert seen["fromEmployee"] == "Person E001"
        assert seen["toEmployee"] is None


class TestOnlyWhatWorksIsOnTheBoard:
    def test_a_request_is_hidden_when_none_of_my_shifts_would_work(
        self, rota: dict[str, Any]
    ) -> None:
        # A also works E1 on Wednesday, so taking B's Tuesday L1 would leave 9 hours of rest. The
        # trade is impossible from A's side, so B must not be offered A's request... but A is the
        # poster here: B's only shift is the Tuesday L1.
        assign(login(), queue(), rota["a"], WED, rota["shifts"]["E1"])
        asked(rota)
        assert colleague_client().get(f"{SW}/board").json() == []

    def test_an_agent_with_no_shift_to_offer_sees_an_empty_board(
        self, rota: dict[str, Any]
    ) -> None:
        asked(rota)
        user = User.objects.get_or_create(username="u-free", defaults={"role": Role.AGENT})[0]
        person("E041", user=user)  # skilled on the queue, but not rostered
        assert as_agent("u-free").get(f"{SW}/board").json() == []

    def test_offers_list_only_my_shifts_that_would_pass_every_rule(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        planner = login()
        # B also works Thursday (D1) and Friday (E1): each could be traded for A's Monday D1.
        thu, fri = date(2026, 5, 28), date(2026, 5, 29)
        assign(planner, queue(), rota["b"], thu, rota["shifts"]["D1"])
        assign(planner, queue(), rota["b"], fri, rota["shifts"]["E1"])
        offered = colleague_client().get(f"{SW}/{swap_id}/offers").json()
        assert sorted((o["day"], o["shift"]) for o in offered) == [
            ("2026-05-26", "L1"),
            ("2026-05-28", "D1"),
            ("2026-05-29", "E1"),
        ]

    def test_offers_for_a_request_i_cannot_take_is_empty(self, rota: dict[str, Any]) -> None:
        swap_id = asked(rota)
        assert login(Role.AGENT).get(f"{SW}/{swap_id}/offers").json() == []  # my own request
        assert as_agent("u-third").get(f"{SW}/{swap_id}/offers").json() == []
        assert colleague_client().get(f"{SW}/999999/offers").json() == []


class TestRulesStopABadSwap:
    def test_less_than_eleven_hours_of_rest_is_refused_when_taken(
        self, rota: dict[str, Any]
    ) -> None:
        assign(login(), queue(), rota["a"], WED, rota["shifts"]["E1"])
        response = trade(login(Role.AGENT), rota["give"], colleague_client(), rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.rest_period")
        # The request stays open for someone whose shifts do fit.
        assert SwapRequest.objects.get().status == SwapStatus.OPEN

    def test_a_rule_broken_after_it_was_matched_still_stops_the_approval(
        self, rota: dict[str, Any]
    ) -> None:
        # The roster moves on while the swap waits: the checks run again at the decision, and
        # because the swap is one transaction, neither shift moves.
        swap_id = agreed(rota)
        assign(login(), queue(), rota["a"], WED, rota["shifts"]["E1"])
        response = act(login(Role.LEAD), swap_id, "approve")
        assert (response.status_code, response.json()["code"]) == (422, "roster.rest_period")
        assert SwapRequest.objects.get(pk=swap_id).status == SwapStatus.AWAITING_APPROVAL
        assert (code(rota["a"], MON), code(rota["b"], TUE)) == ("D1", "L1")

    def test_a_shift_that_was_changed_or_removed_stops_the_approval(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = agreed(rota)
        assign(login(), queue(), rota["b"], TUE, None)  # the planner takes B off Tuesday
        response = act(login(Role.LEAD), swap_id, "approve")
        assert (response.status_code, response.json()["code"]) == (409, "swap.changed")
        assert ShiftAssignment.objects.filter(employee=rota["a"], day=MON).exists()

    def test_taking_a_request_whose_shift_was_removed_is_refused(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        assign(login(), queue(), rota["a"], MON, None)
        response = take(colleague_client(), swap_id, rota["take"])
        assert (response.status_code, response.json()["code"]) == (409, "swap.changed")

    def test_contract_hours_apply_to_the_person_taking_the_longer_shift(self) -> None:
        shifts = standard_shifts()
        login(Role.AGENT)
        colleague_client()
        short = person("E001", hours=7, user=User.objects.get(username="u-agent"))
        other = person("E002", user=User.objects.get(username="u-colleague"))
        planner = login()
        assign(planner, queue(), short, MON, shifts["P1"])  # 4 hours
        assign(planner, queue(), other, TUE, shifts["D1"])  # 8 hours
        response = trade(login(Role.AGENT), row(short, MON), colleague_client(), row(other, TUE))
        assert (response.status_code, response.json()["code"]) == (422, "roster.over_hours")

    def test_a_person_on_approved_leave_cannot_take_a_shift_that_day(
        self, rota: dict[str, Any]
    ) -> None:
        kind = LeaveType.objects.get(code="unpaid").pk
        leave = login(Role.AGENT).post(
            f"{LEAVE}/requests",
            {"leaveTypeId": kind, "startDate": str(TUE), "endDate": str(TUE)},
            content_type="application/json",
        )
        login(Role.LEAD).post(f"{LEAVE}/requests/{leave.json()['id']}/approve")
        response = trade(login(Role.AGENT), rota["give"], colleague_client(), rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.on_leave")

    def test_someone_already_working_that_day_cannot_take_a_second_shift(
        self, rota: dict[str, Any]
    ) -> None:
        assign(login(), queue(), rota["a"], TUE, rota["shifts"]["E1"])
        response = trade(login(Role.AGENT), rota["give"], colleague_client(), rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.already_rostered")

    def test_the_shift_offered_in_return_must_be_on_the_same_queue(
        self, rota: dict[str, Any]
    ) -> None:
        other_queue = queue("QueueB")
        b2 = person("E003", queues=("QueueB", "QueueA"), user=None)
        assign(login(), other_queue, b2, TUE, rota["shifts"]["L1"])
        swap_id = asked(rota)
        response = take(login(), swap_id, row(b2, TUE), employeeId=b2.pk)
        assert (response.status_code, response.json()["code"]) == (422, "swap.different_queue")

    def test_you_cannot_take_your_own_request(self, rota: dict[str, Any]) -> None:
        assign(login(), queue(), rota["a"], TUE, rota["shifts"]["E1"])
        swap_id = asked(rota)
        response = take(login(Role.AGENT), swap_id, row(rota["a"], TUE))
        assert (response.status_code, response.json()["code"]) == (422, "swap.same_person")

    def test_a_shift_that_has_started_cannot_be_posted(
        self, rota: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TUE)  # Monday is gone
        response = post(login(Role.AGENT), rota["give"])
        assert (response.status_code, response.json()["code"]) == (422, "swap.in_the_past")

    def test_a_shift_cannot_be_in_two_open_swaps_at_once(self, rota: dict[str, Any]) -> None:
        asked(rota)
        again = post(login(Role.AGENT), rota["give"])
        assert (again.status_code, again.json()["code"]) == (409, "swap.already_open")

    def test_a_shift_in_an_open_request_cannot_also_be_offered_in_return(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)  # A's Monday is posted
        post(colleague_client(), rota["take"])  # and B has posted their own Tuesday
        response = take(colleague_client(), swap_id, rota["take"])
        assert (response.status_code, response.json()["code"]) == (409, "swap.already_open")


class TestWhoMayDoWhat:
    def test_you_can_only_post_your_own_shift(self, rota: dict[str, Any]) -> None:
        # The colleague tries to post A's shift as if it were theirs.
        assert post(colleague_client(), rota["give"]).status_code == 404

    def test_an_agent_cannot_act_for_someone_else_but_a_planner_can(
        self, rota: dict[str, Any]
    ) -> None:
        assert post(login(Role.AGENT), rota["give"], employeeId=rota["b"].pk).status_code == 404
        assert post(login(Role.PLANNER), rota["give"], employeeId=rota["a"].pk).status_code == 201

    def test_a_planner_can_take_a_request_on_someones_behalf_an_agent_cannot(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        refused = take(as_agent("u-third"), swap_id, rota["take"], employeeId=rota["b"].pk)
        assert refused.status_code == 404
        taken = take(login(Role.PLANNER), swap_id, rota["take"], employeeId=rota["b"].pk)
        assert taken.status_code == 200
        assert taken.json()["status"] == "awaiting_approval"

    def test_you_can_only_offer_your_own_shift_in_return(self, rota: dict[str, Any]) -> None:
        swap_id = asked(rota)
        # Another agent tries to offer A's own shift (the poster's) as theirs.
        assert take(colleague_client(), swap_id, rota["give"]).status_code == 404

    def test_only_the_poster_or_a_planner_withdraws(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        assert act(colleague_client(), swap_id, "cancel").status_code == 404  # who took it
        assert act(as_agent("u-third"), swap_id, "cancel").status_code == 404
        assert act(login(Role.PLANNER), swap_id, "cancel").json()["status"] == "cancelled"

    def test_nobody_decides_a_swap_they_are_part_of(self, rota: dict[str, Any]) -> None:
        # A lead who is one of the two people cannot approve it, even though leads can approve.
        lead_user = User.objects.get(username="u-lead")
        lead_person = Employee.objects.get(user=lead_user)  # the team lead from the fixture
        assign(login(), queue(), lead_person, WED, rota["shifts"]["D1"])
        swap_id = asked(rota)
        assert take(login(Role.LEAD), swap_id, row(lead_person, WED)).status_code == 200
        refused = act(login(Role.LEAD), swap_id, "approve")
        assert (refused.status_code, refused.json()["code"]) == (403, "swap.own_request")
        assert act(login(Role.PLANNER), swap_id, "approve").status_code == 200

    def test_an_agent_sees_only_swaps_they_are_in_and_a_lead_sees_their_teams(
        self, rota: dict[str, Any]
    ) -> None:
        asked(rota)
        assert len(login(Role.AGENT).get(SW).json()) == 1
        assert colleague_client().get(SW).json() == []  # an open request is not theirs to list
        assert len(login(Role.LEAD).get(SW).json()) == 1

    def test_a_person_with_no_employee_record_has_nothing_to_swap(self) -> None:
        response = login(Role.AGENT).get(f"{SW}/my-shifts")
        assert (response.status_code, response.json()) == (200, [])
        assert login(Role.AGENT).get(f"{SW}/board").json() == []

    def test_my_shifts_lists_only_my_coming_shifts_not_ones_already_in_a_swap(
        self, rota: dict[str, Any]
    ) -> None:
        assert [s["day"] for s in login(Role.AGENT).get(f"{SW}/my-shifts").json()] == [str(MON)]
        asked(rota)
        assert login(Role.AGENT).get(f"{SW}/my-shifts").json() == []


ENDPOINTS = [
    ("get", f"{SW}"),
    ("get", f"{SW}/my-shifts"),
    ("get", f"{SW}/board"),
    ("get", f"{SW}/1/offers"),
    ("post", f"{SW}"),
    ("post", f"{SW}/1/accept"),
    ("post", f"{SW}/1/approve"),
    ("post", f"{SW}/1/reject"),
    ("post", f"{SW}/1/cancel"),
]


class TestRoles:
    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    @pytest.mark.parametrize(("method", "path"), ENDPOINTS)
    def test_roles_that_do_not_work_a_roster_are_refused_everywhere(
        self, role: Role, method: str, path: str
    ) -> None:
        client = login(role)
        if method == "get":
            response = client.get(path)
        else:
            response = client.post(path, {}, content_type="application/json")
        assert response.status_code == 403

    @pytest.mark.parametrize("path", ["approve", "reject"])
    def test_an_agent_cannot_approve_or_reject_even_their_own_swap(
        self, rota: dict[str, Any], path: str
    ) -> None:
        swap_id = agreed(rota)
        assert act(login(Role.AGENT), swap_id, path).status_code == 403
        assert act(colleague_client(), swap_id, path).status_code == 403
        assert SwapRequest.objects.get(pk=swap_id).status == SwapStatus.AWAITING_APPROVAL

    @pytest.mark.parametrize("role", [Role.LEAD, Role.PLANNER, Role.ADMIN])
    def test_leads_planners_and_admins_can_approve(self, rota: dict[str, Any], role: Role) -> None:
        assert act(login(role), agreed(rota), "approve").status_code == 200

    def test_an_unknown_swap_is_not_found(self) -> None:
        assert act(login(Role.LEAD), 999999, "approve").status_code == 404


class TestTheShiftBeingGivenAwayIsNotHeldAgainstYou:
    def test_two_people_can_swap_shifts_on_the_same_day(self, rota: dict[str, Any]) -> None:
        # B works L1 on Monday as well; A (D1) and B (L1) trade within the day.
        assign(login(), queue(), rota["b"], MON, rota["shifts"]["L1"])
        response = trade(
            login(Role.AGENT), row(rota["a"], MON), colleague_client(), row(rota["b"], MON)
        )
        # Failure caught: counting the person's own shift as 'already working that day' refuses
        # every same-day swap.
        assert response.status_code == 200, response.content
        assert act(login(Role.LEAD), response.json()["id"], "approve").status_code == 200
        assert (code(rota["a"], MON), code(rota["b"], MON)) == ("L1", "D1")

    def test_rest_is_measured_without_the_shift_you_hand_over(self, rota: dict[str, Any]) -> None:
        # P works L1 (13:00-22:00) on Tuesday, Q works E1 (07:00 start) on Wednesday. P takes Q's
        # Wednesday E1 and hands over Tuesday's L1: with the L1 gone there is no short rest, but
        # counting it would show 9 hours between 22:00 and 07:00 and wrongly refuse.
        p, q = person("E020"), person("E021")
        planner = login()
        assign(planner, queue(), p, TUE, rota["shifts"]["L1"])
        assign(planner, queue(), q, WED, rota["shifts"]["E1"])
        swap_id = post(planner, row(q, WED), employeeId=q.pk).json()["id"]
        response = take(planner, swap_id, row(p, TUE), employeeId=p.pk)
        assert response.status_code == 200, response.content


class TestRejectReason:
    def test_both_parties_and_approvers_see_the_reason_other_agents_never(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = agreed(rota)
        response = login(Role.LEAD).post(
            f"{SW}/{swap_id}/reject",
            {"reason": " Too little rest "},
            content_type="application/json",
        )
        assert response.json()["decisionReason"] == "Too little rest"
        for client in (login(Role.AGENT), colleague_client(), login(Role.PLANNER)):
            assert client.get(SW).json()[0]["decisionReason"] == "Too little rest"
        stranger = as_agent("u-stranger")
        assert stranger.get(SW).json() == []
        assert "Too little rest" not in stranger.get(f"{SW}/board").content.decode()
        event = AuditEvent.objects.get(action=Action.SWAP_REJECTED)
        assert AuditChange.objects.filter(
            event=event, field="decision_reason", new_value="Too little rest"
        ).exists()

    def test_the_reason_is_optional_and_bounded(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        too_long = login(Role.LEAD).post(
            f"{SW}/{swap_id}/reject", {"reason": "x" * 301}, content_type="application/json"
        )
        assert too_long.status_code == 422
        assert act(login(Role.LEAD), swap_id, "reject").json()["decisionReason"] == ""

    def test_an_agent_cannot_reject_with_a_reason(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        response = colleague_client().post(
            f"{SW}/{swap_id}/reject", {"reason": "no"}, content_type="application/json"
        )
        assert response.status_code == 403
