"""Shift swaps on a real PostgreSQL, with the outcomes worked out by hand.

Today is frozen at Wednesday 20 May 2026. Shifts: D1 09:00-17:30, E1 07:00-15:30, L1 13:00-22:00,
P1 10:00-14:00 (4 paid hours). A (E001, the agent login) is on D1 Monday 25 May; B (E002, the
colleague login) is on L1 Tuesday 26 May. Swapping puts A on L1 on Tuesday and B on D1 on Monday.

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


def colleague_client() -> Client:
    user, _ = User.objects.get_or_create(username="u-colleague", defaults={"role": Role.AGENT})
    client = Client()
    client.force_login(user)
    return client


def row(employee: Employee, day: date) -> ShiftAssignment | None:
    return (
        ShiftAssignment.objects.filter(employee=employee, day=day)
        .select_related("template")
        .first()
    )


def code(employee: Employee, day: date) -> str | None:
    found = row(employee, day)
    return found.template.code if found else None


def offer(client: Client, give: ShiftAssignment, take: ShiftAssignment, **extra: Any) -> Any:
    body = {"giveAssignmentId": give.pk, "takeAssignmentId": take.pk, **extra}
    return client.post(SW, body, content_type="application/json")


def act(client: Client, swap_id: int, what: str) -> Any:
    return client.post(f"{SW}/{swap_id}/{what}")


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
    return {
        "shifts": shifts,
        "a": a,
        "b": b,
        "give": row(a, MON),
        "take": row(b, TUE),
    }


def asked(rota: dict[str, Any]) -> int:
    response = offer(login(Role.AGENT), rota["give"], rota["take"])
    assert response.status_code == 201, response.content
    return int(response.json()["id"])


def agreed(rota: dict[str, Any]) -> int:
    swap_id = asked(rota)
    assert act(colleague_client(), swap_id, "accept").status_code == 200
    return swap_id


class TestTheWholeFlow:
    def test_ask_accept_approve_exchanges_the_two_shifts(self, rota: dict[str, Any]) -> None:
        a, b = rota["a"], rota["b"]
        swap_id = asked(rota)
        assert SwapRequest.objects.get(pk=swap_id).status == SwapStatus.AWAITING_COLLEAGUE
        # Nothing moves until a lead agrees.
        assert (code(a, MON), code(b, TUE)) == ("D1", "L1")

        accepted = act(colleague_client(), swap_id, "accept").json()
        assert accepted["status"] == "awaiting_approval"
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
        # Publishing makes the roster final for planning, but an approved swap is the sanctioned
        # way for it to change afterwards.
        login().post(
            "/api/v1/scheduling/roster/publish",
            {"queueId": queue().pk, "weekStart": str(MON)},
            content_type="application/json",
        )
        assert (
            RosterWeek.objects.get(queue=queue(), week_start=MON).status == RosterStatus.PUBLISHED
        )
        swap_id = agreed(rota)
        assert act(login(Role.LEAD), swap_id, "approve").status_code == 200
        assert (
            RosterWeek.objects.get(queue=queue(), week_start=MON).status == RosterStatus.PUBLISHED
        )

    def test_the_colleague_can_decline_and_nothing_moves(self, rota: dict[str, Any]) -> None:
        swap_id = asked(rota)
        declined = act(colleague_client(), swap_id, "decline").json()
        assert declined["status"] == "declined"
        assert (code(rota["a"], MON), code(rota["b"], TUE)) == ("D1", "L1")
        # A declined swap cannot be revived by approving it.
        assert act(login(Role.LEAD), swap_id, "approve").status_code == 409

    def test_a_lead_can_reject_an_agreed_swap(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        assert act(login(Role.LEAD), swap_id, "reject").json()["status"] == "rejected"
        assert (code(rota["a"], MON), code(rota["b"], TUE)) == ("D1", "L1")

    def test_the_asker_can_withdraw_until_it_is_approved(self, rota: dict[str, Any]) -> None:
        swap_id = agreed(rota)
        assert act(login(Role.AGENT), swap_id, "cancel").json()["status"] == "cancelled"
        assert act(login(Role.LEAD), swap_id, "approve").status_code == 409

    def test_an_approved_swap_cannot_be_withdrawn_it_would_leave_the_roster_half_done(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = agreed(rota)
        act(login(Role.LEAD), swap_id, "approve")
        response = act(login(Role.AGENT), swap_id, "cancel")
        assert (response.status_code, response.json()["code"]) == (409, "swap.not_cancellable")
        assert (code(rota["a"], TUE), code(rota["b"], MON)) == ("L1", "D1")

    def test_a_swap_is_answered_in_order_the_colleague_before_the_lead(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        # The lead cannot skip the colleague's say.
        response = act(login(Role.LEAD), swap_id, "approve")
        assert (response.status_code, response.json()["code"]) == (
            409,
            "swap.not_waiting_for_approval",
        )
        # And a colleague cannot answer twice.
        act(colleague_client(), swap_id, "accept")
        again = act(colleague_client(), swap_id, "accept")
        assert (again.status_code, again.json()["code"]) == (409, "swap.not_waiting_for_colleague")


class TestRulesStopABadSwap:
    def test_less_than_eleven_hours_of_rest_is_refused_when_asked(
        self, rota: dict[str, Any]
    ) -> None:
        assign(login(), queue(), rota["a"], WED, rota["shifts"]["E1"])
        response = offer(login(Role.AGENT), rota["give"], rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.rest_period")
        assert SwapRequest.objects.count() == 0

    def test_a_rule_broken_after_it_was_asked_still_stops_the_approval(
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
        assert row(rota["a"], MON) is not None  # A kept their own shift

    def test_contract_hours_apply_to_the_person_taking_the_longer_shift(self) -> None:
        shifts = standard_shifts()
        login(Role.AGENT)
        colleague_client()
        short = person("E001", hours=7, user=User.objects.get(username="u-agent"))
        other = person("E002", user=User.objects.get(username="u-colleague"))
        planner = login()
        assign(planner, queue(), short, MON, shifts["P1"])  # 4 hours
        assign(planner, queue(), other, TUE, shifts["D1"])  # 8 hours
        response = offer(login(Role.AGENT), row(short, MON), row(other, TUE))  # type: ignore[arg-type]
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
        assert (
            login(Role.LEAD).post(f"{LEAVE}/requests/{leave.json()['id']}/approve").status_code
            == 200
        )
        response = offer(login(Role.AGENT), rota["give"], rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.on_leave")

    def test_someone_already_working_that_day_cannot_take_a_second_shift(
        self, rota: dict[str, Any]
    ) -> None:
        assign(login(), queue(), rota["a"], TUE, rota["shifts"]["E1"])
        response = offer(login(Role.AGENT), rota["give"], rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "roster.already_rostered")

    def test_both_shifts_must_be_on_the_same_queue(self, rota: dict[str, Any]) -> None:
        other_queue = queue("QueueB")
        b2 = person("E003", queues=("QueueB",), user=None)
        assign(login(), other_queue, b2, TUE, rota["shifts"]["L1"])
        response = offer(login(Role.AGENT), rota["give"], row(b2, TUE))  # type: ignore[arg-type]
        assert (response.status_code, response.json()["code"]) == (422, "swap.different_queue")

    def test_a_shift_cannot_be_swapped_with_yourself(self, rota: dict[str, Any]) -> None:
        assign(login(), queue(), rota["a"], TUE, rota["shifts"]["E1"])
        response = offer(login(Role.AGENT), rota["give"], row(rota["a"], TUE))  # type: ignore[arg-type]
        assert (response.status_code, response.json()["code"]) == (422, "swap.same_person")

    def test_a_shift_that_has_started_cannot_be_swapped(
        self, rota: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TUE)  # Monday is gone
        response = offer(login(Role.AGENT), rota["give"], rota["take"])
        assert (response.status_code, response.json()["code"]) == (422, "swap.in_the_past")

    def test_a_shift_cannot_be_in_two_open_swaps_at_once(self, rota: dict[str, Any]) -> None:
        asked(rota)
        c = person("E003", user=None)
        assign(login(), queue(), c, WED, rota["shifts"]["D1"])
        again = offer(login(Role.AGENT), rota["give"], row(c, WED))  # type: ignore[arg-type]
        assert (again.status_code, again.json()["code"]) == (409, "swap.already_open")


class TestWhoMayDoWhat:
    def test_you_can_only_give_away_your_own_shift(self, rota: dict[str, Any]) -> None:
        # The colleague tries to offer A's shift as if it were theirs.
        response = offer(colleague_client(), rota["give"], rota["take"])
        assert response.status_code == 404

    def test_an_agent_cannot_act_for_someone_else_but_a_planner_can(
        self, rota: dict[str, Any]
    ) -> None:
        on_behalf = {"employeeId": rota["a"].pk}
        assert (
            offer(
                login(Role.AGENT), rota["give"], rota["take"], **{"employeeId": rota["b"].pk}
            ).status_code
            == 404
        )
        assert (
            offer(login(Role.PLANNER), rota["give"], rota["take"], **on_behalf).status_code == 201
        )

    def test_only_the_colleague_can_answer_not_the_asker_or_an_outsider(
        self, rota: dict[str, Any]
    ) -> None:
        swap_id = asked(rota)
        assert act(login(Role.AGENT), swap_id, "accept").status_code == 404  # the asker
        # An outsider: another agent who is not in the swap.
        outsider, _ = User.objects.get_or_create(
            username="u-outsider", defaults={"role": Role.AGENT}
        )
        person("E009", user=outsider)
        client = Client()
        client.force_login(outsider)
        assert act(client, swap_id, "accept").status_code == 404
        assert act(client, swap_id, "decline").status_code == 404
        assert act(client, swap_id, "cancel").status_code == 404
        assert client.get(SW).json() == []  # and they cannot see it either

    def test_the_colleague_cannot_withdraw_the_askers_swap(self, rota: dict[str, Any]) -> None:
        swap_id = asked(rota)
        assert act(colleague_client(), swap_id, "cancel").status_code == 404

    def test_nobody_decides_a_swap_they_are_part_of(self, rota: dict[str, Any]) -> None:
        # A lead who is one of the two people cannot approve it, even though leads can approve.
        lead_user = User.objects.get_or_create(username="u-lead", defaults={"role": Role.LEAD})[0]
        lead_person = Employee.objects.get(user=lead_user)  # the team lead from the fixture
        assign(login(), queue(), lead_person, WED, rota["shifts"]["D1"])
        response = offer(login(Role.AGENT), rota["give"], row(lead_person, WED))  # type: ignore[arg-type]
        swap_id = response.json()["id"]
        assert act(login(Role.LEAD), swap_id, "accept").status_code == 200
        refused = act(login(Role.LEAD), swap_id, "approve")
        assert (refused.status_code, refused.json()["code"]) == (403, "swap.own_request")
        assert act(login(Role.PLANNER), swap_id, "approve").status_code == 200

    def test_an_agent_sees_only_swaps_they_are_in_and_a_lead_sees_all(
        self, rota: dict[str, Any]
    ) -> None:
        asked(rota)
        assert len(login(Role.AGENT).get(SW).json()) == 1
        assert len(colleague_client().get(SW).json()) == 1
        assert len(login(Role.LEAD).get(SW).json()) == 1
        outsider, _ = User.objects.get_or_create(
            username="u-outsider", defaults={"role": Role.AGENT}
        )
        person("E009", user=outsider)
        client = Client()
        client.force_login(outsider)
        assert client.get(SW).json() == []

    def test_a_person_with_no_employee_record_has_nothing_to_swap(self) -> None:
        response = login(Role.AGENT).get(f"{SW}/my-shifts")
        assert (response.status_code, response.json()) == (200, [])


class TestChoosingAShiftToTake:
    def test_options_are_colleagues_shifts_that_would_pass_every_rule(
        self, rota: dict[str, Any]
    ) -> None:
        shifts = rota["shifts"]
        planner = login()
        assign(planner, queue(), rota["a"], WED, shifts["E1"])  # makes L1 on Tuesday break rest
        d = person("E004", user=None)
        assign(planner, queue(), d, TUE, shifts["E1"])  # ends 15:30, 15.5 hours before Wednesday
        taken = person("E005", user=None)
        assign(planner, queue(), taken, date(2026, 5, 28), shifts["D1"])
        in_a_swap = row(taken, date(2026, 5, 28))
        # E005's shift is already in someone else's swap, so it is not on offer.
        outsider = person("E006", user=None)
        assign(planner, queue(), outsider, date(2026, 5, 29), shifts["D1"])
        login(Role.PLANNER).post(
            SW,
            {
                "giveAssignmentId": row(outsider, date(2026, 5, 29)).pk,  # type: ignore[union-attr]
                "takeAssignmentId": in_a_swap.pk,  # type: ignore[union-attr]
                "employeeId": outsider.pk,
            },
            content_type="application/json",
        )
        mine = row(rota["a"], MON)
        listing = login(Role.AGENT).get(f"{SW}/options", {"give_assignment_id": mine.pk}).json()  # type: ignore[union-attr]
        offered = sorted((o["employee"], o["day"], o["shift"]) for o in listing)
        # Only D's Tuesday E1: B's Tuesday L1 breaks A's rest, A's own shifts are never offered,
        # and the two shifts in the open swap are taken.
        assert offered == [("Person E004", "2026-05-26", "E1")]

    def test_you_can_only_ask_for_options_on_your_own_shifts(self, rota: dict[str, Any]) -> None:
        response = login(Role.AGENT).get(f"{SW}/options", {"give_assignment_id": rota["take"].pk})
        assert response.status_code == 404

    def test_my_shifts_lists_only_my_coming_shifts_not_ones_already_in_a_swap(
        self, rota: dict[str, Any]
    ) -> None:
        assert [s["day"] for s in login(Role.AGENT).get(f"{SW}/my-shifts").json()] == [str(MON)]
        asked(rota)
        assert login(Role.AGENT).get(f"{SW}/my-shifts").json() == []


ENDPOINTS = [
    ("get", f"{SW}"),
    ("get", f"{SW}/my-shifts"),
    ("get", f"{SW}/options?give_assignment_id=1"),
    ("post", f"{SW}"),
    ("post", f"{SW}/1/accept"),
    ("post", f"{SW}/1/decline"),
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
