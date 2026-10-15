"""Notifications: who sees what, and what each event tells whom.

Today is frozen at Wednesday 20 May 2026. A (E001, login u-agent) and B (E002, login u-colleague)
are managed by the lead (login u-lead). A works D1 on Monday 25 May, B works L1 on Tuesday 26 May.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.notifications import services
from wfm.notifications.models import Notification
from wfm.people.models import LeaveType
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import ShiftAssignment
from wfm.scheduling.tests.helpers import MON, TUE, WED, assign, person, queue, standard_shifts
from wfm.scheduling.tests.helpers import login as scheduling_login

pytestmark = pytest.mark.django_db

N = "/api/v1/notifications"
SW = "/api/v1/people/swaps"
LEAVE = "/api/v1/people/leave"
TODAY = date(2026, 5, 20)


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


def as_user(username: str, role: Role = Role.AGENT) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def login(role: Role = Role.PLANNER) -> Client:
    return scheduling_login(role)


def messages(username: str) -> list[str]:
    user = User.objects.get(username=username)
    return list(Notification.objects.filter(recipient=user).values_list("message", flat=True))


@pytest.fixture
def team() -> dict[str, Any]:
    shifts = standard_shifts()
    as_user("u-agent")
    as_user("u-colleague")
    a = person("E001", user=User.objects.get(username="u-agent"))
    b = person("E002", user=User.objects.get(username="u-colleague"))
    lead_of(a, b)
    planner = login()
    assign(planner, queue(), a, MON, shifts["D1"])
    assign(planner, queue(), b, TUE, shifts["L1"])
    return {"shifts": shifts, "a": a, "b": b}


class TestTheInbox:
    @pytest.mark.parametrize("role", list(Role))
    def test_every_role_has_an_inbox_of_its_own(self, role: Role) -> None:
        response = login(role).get(N)
        assert response.status_code == 200
        assert response.json() == {"unread": 0, "items": []}

    def test_you_see_only_your_own(self) -> None:
        services.notify([User.objects.create(username="x", role=Role.AGENT)], kind="t", message="m")
        mine = User.objects.get_or_create(username="u-agent", defaults={"role": Role.AGENT})[0]
        services.notify([mine], kind="t", message="for you")
        assert [i["message"] for i in as_user("u-agent").get(N).json()["items"]] == ["for you"]

    def test_marking_one_read_lowers_the_unread_count_and_is_harmless_twice(self) -> None:
        user = User.objects.get_or_create(username="u-agent", defaults={"role": Role.AGENT})[0]
        services.notify([user], kind="t", message="one")
        services.notify([user], kind="t", message="two")
        client = as_user("u-agent")
        first = client.get(N).json()["items"][0]["id"]
        assert client.post(f"{N}/{first}/read").json()["read"] is True
        assert client.post(f"{N}/{first}/read").status_code == 200
        assert client.get(N).json()["unread"] == 1

    def test_nobody_can_read_or_mark_somebody_elses_notification(self) -> None:
        other = User.objects.create(username="other", role=Role.AGENT)
        services.notify([other], kind="t", message="private")
        theirs = Notification.objects.get().pk
        # Failure caught: marking someone else's as read would hide it from them.
        assert as_user("u-agent").post(f"{N}/{theirs}/read").status_code == 404
        assert Notification.objects.get(pk=theirs).read_at is None

    def test_read_all_only_touches_my_own(self) -> None:
        me = User.objects.get_or_create(username="u-agent", defaults={"role": Role.AGENT})[0]
        other = User.objects.create(username="other", role=Role.AGENT)
        services.notify([me, other], kind="t", message="both")
        assert as_user("u-agent").post(f"{N}/read-all").json() == {"marked": 1}
        assert Notification.objects.get(recipient=other).read_at is None

    def test_a_person_is_told_once_even_if_named_twice_and_nobody_is_skipped_wrongly(self) -> None:
        user = User.objects.create(username="u", role=Role.AGENT)
        gone = User.objects.create(username="gone", role=Role.AGENT, is_active=False)
        assert services.notify([user, user, None, gone], kind="t", message="m") == 1


class TestEventsTellTheRightPeople:
    def test_publishing_tells_everyone_on_the_roster_and_only_them(
        self, team: dict[str, Any]
    ) -> None:
        extra = person("E003", user=None)  # rostered but has no login: nobody to tell
        assign(login(), queue(), extra, MON, team["shifts"]["D1"])
        login().post(
            "/api/v1/scheduling/roster/publish",
            {"queueId": queue().pk, "weekStart": str(MON)},
            content_type="application/json",
        )
        # A is on Monday's week and so is B (Tuesday of the same week): both told once.
        assert messages("u-agent") == ["Your roster for the week of 25 May is published."]
        assert messages("u-colleague") == ["Your roster for the week of 25 May is published."]
        assert messages("u-planner") == []
        assert Notification.objects.count() == 2

    def test_an_agent_asking_for_leave_tells_their_lead_not_themselves(
        self, team: dict[str, Any]
    ) -> None:
        kind = LeaveType.objects.get(code="unpaid").pk
        as_user("u-agent").post(
            f"{LEAVE}/requests",
            {"leaveTypeId": kind, "startDate": str(MON), "endDate": str(MON)},
            content_type="application/json",
        )
        assert messages("u-lead") == ["Leave is waiting for your decision."]
        assert messages("u-agent") == []

    def test_the_decision_tells_the_person_what_it_was_for_without_saying_who_decided(
        self, team: dict[str, Any]
    ) -> None:
        kind = LeaveType.objects.get(code="unpaid").pk
        request_id = (
            as_user("u-agent")
            .post(
                f"{LEAVE}/requests",
                {"leaveTypeId": kind, "startDate": str(MON), "endDate": str(TUE)},
                content_type="application/json",
            )
            .json()["id"]
        )
        as_user("u-lead", Role.LEAD).post(f"{LEAVE}/requests/{request_id}/approve")
        assert messages("u-agent") == [
            "Your unpaid leave request for 25 May to 26 May was approved."
        ]
        assert messages("u-lead") == ["Leave is waiting for your decision."]  # nothing new

    def test_withdrawing_your_own_request_does_not_notify_you_but_a_planner_doing_it_does(
        self, team: dict[str, Any]
    ) -> None:
        kind = LeaveType.objects.get(code="unpaid").pk
        body = {"leaveTypeId": kind, "startDate": str(MON), "endDate": str(MON)}
        first = as_user("u-agent").post(f"{LEAVE}/requests", body, content_type="application/json")
        as_user("u-agent").post(f"{LEAVE}/requests/{first.json()['id']}/cancel")
        assert messages("u-agent") == []
        second_body = {**body, "startDate": str(WED), "endDate": str(WED)}
        second = as_user("u-agent").post(
            f"{LEAVE}/requests", second_body, content_type="application/json"
        )
        login(Role.PLANNER).post(f"{LEAVE}/requests/{second.json()['id']}/cancel")
        assert messages("u-agent") == ["Your unpaid leave request for 27 May was cancelled."]

    def test_a_swap_being_taken_tells_the_poster_and_asks_the_lead_without_naming_anyone(
        self, team: dict[str, Any]
    ) -> None:
        give = ShiftAssignment.objects.get(employee=team["a"], day=MON)
        mine = ShiftAssignment.objects.get(employee=team["b"], day=TUE)
        posted = as_user("u-agent").post(
            SW, {"giveAssignmentId": give.pk}, content_type="application/json"
        )
        as_user("u-colleague").post(
            f"{SW}/{posted.json()['id']}/accept",
            {"assignmentId": mine.pk},
            content_type="application/json",
        )
        assert messages("u-agent") == [
            "Your swap request for D1 on Mon 25 May was taken. A lead decides next."
        ]
        assert messages("u-lead") == ["A swap is waiting for your approval."]
        assert messages("u-colleague") == []
        # Failure caught: the poster learning who took it before a lead has decided.
        everything = " ".join(Notification.objects.values_list("message", flat=True))
        assert "Person E002" not in everything
        assert "E002" not in everything

    def test_the_outcome_tells_each_person_about_their_own_shift(
        self, team: dict[str, Any]
    ) -> None:
        give = ShiftAssignment.objects.get(employee=team["a"], day=MON)
        mine = ShiftAssignment.objects.get(employee=team["b"], day=TUE)
        swap_id = (
            as_user("u-agent")
            .post(SW, {"giveAssignmentId": give.pk}, content_type="application/json")
            .json()["id"]
        )
        as_user("u-colleague").post(
            f"{SW}/{swap_id}/accept", {"assignmentId": mine.pk}, content_type="application/json"
        )
        as_user("u-lead", Role.LEAD).post(f"{SW}/{swap_id}/approve")
        assert messages("u-agent")[0] == "Your swap for D1 on Mon 25 May was approved."
        assert messages("u-colleague") == ["Your swap for L1 on Tue 26 May was approved."]

    def test_a_refused_action_tells_nobody(self, team: dict[str, Any]) -> None:
        # A also works E1 on Wednesday, so taking B's Tuesday L1 leaves 9 hours of rest: refused.
        assign(login(), queue(), team["a"], WED, team["shifts"]["E1"])
        give = ShiftAssignment.objects.get(employee=team["a"], day=MON)
        mine = ShiftAssignment.objects.get(employee=team["b"], day=TUE)
        swap_id = (
            as_user("u-agent")
            .post(SW, {"giveAssignmentId": give.pk}, content_type="application/json")
            .json()["id"]
        )
        refused = as_user("u-colleague").post(
            f"{SW}/{swap_id}/accept", {"assignmentId": mine.pk}, content_type="application/json"
        )
        assert refused.status_code == 422
        assert Notification.objects.count() == 0
