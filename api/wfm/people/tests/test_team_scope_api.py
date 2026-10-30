"""A lead decides leave and swaps for their own team only; planners and admins for everybody.

Two teams: L1 (login u-lead) manages A (the u-agent login); L2 (login u-lead2) manages B (the
u-colleague login). Today is frozen at Wednesday 20 May 2026.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.people.models import LeaveType
from wfm.scheduling.models import Employee, ShiftAssignment
from wfm.scheduling.tests.helpers import EMPLOYEES, MON, TUE, assign, person, queue, standard_shifts
from wfm.scheduling.tests.helpers import login as scheduling_login

from .team import lead_of

pytestmark = pytest.mark.django_db

LEAVE = "/api/v1/people/leave"
SW = "/api/v1/people/swaps"
AV = "/api/v1/people/availability"
TODAY = date(2026, 5, 20)


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


def as_user(username: str, role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def login(role: Role = Role.PLANNER) -> Client:
    return scheduling_login(role)


@pytest.fixture
def teams() -> dict[str, Any]:
    shifts = standard_shifts()
    as_user("u-agent", Role.AGENT)
    as_user("u-colleague", Role.AGENT)
    a = person("E001", user=User.objects.get(username="u-agent"))
    b = person("E002", user=User.objects.get(username="u-colleague"))
    l1 = lead_of(a)
    l2_user = User.objects.get_or_create(username="u-lead2", defaults={"role": Role.LEAD})[0]
    l2 = person("L002", user=l2_user)
    b.manager = l2
    b.save(update_fields=["manager"])
    planner = login()
    assign(planner, queue(), a, MON, shifts["D1"])
    assign(planner, queue(), b, TUE, shifts["L1"])
    return {"shifts": shifts, "a": a, "b": b, "l1": l1, "l2": l2}


def ask_leave(client: Client, day: date) -> int:
    kind = LeaveType.objects.get(code="unpaid").pk
    response = client.post(
        f"{LEAVE}/requests",
        {"leaveTypeId": kind, "startDate": str(day), "endDate": str(day)},
        content_type="application/json",
    )
    assert response.status_code == 201, response.content
    return int(response.json()["id"])


class TestLeaveIsScopedToTheTeam:
    def test_a_lead_sees_only_their_teams_requests(self, teams: dict[str, Any]) -> None:
        mine = ask_leave(as_user("u-agent", Role.AGENT), MON)
        theirs = ask_leave(as_user("u-colleague", Role.AGENT), TUE)

        def ids(client: Client) -> list[int]:
            return sorted(r["id"] for r in client.get(f"{LEAVE}/requests").json())

        assert ids(as_user("u-lead", Role.LEAD)) == [mine]
        assert ids(as_user("u-lead2", Role.LEAD)) == [theirs]
        assert ids(login(Role.PLANNER)) == sorted([mine, theirs])
        assert ids(login(Role.ADMIN)) == sorted([mine, theirs])

    def test_a_lead_cannot_decide_or_even_see_another_teams_request(
        self, teams: dict[str, Any]
    ) -> None:
        theirs = ask_leave(as_user("u-colleague", Role.AGENT), TUE)
        lead = as_user("u-lead", Role.LEAD)
        for what in ("approve", "reject"):
            assert (
                lead.post(
                    f"{LEAVE}/requests/{theirs}/{what}", {}, content_type="application/json"
                ).status_code
                == 404
            )
        assert lead.get(f"{LEAVE}/requests/{theirs}/impact").status_code == 404
        # Their own lead can.
        assert (
            as_user("u-lead2", Role.LEAD).post(f"{LEAVE}/requests/{theirs}/approve").status_code
            == 200
        )

    def test_a_lead_with_nobody_in_their_team_sees_and_decides_nothing(
        self, teams: dict[str, Any]
    ) -> None:
        request_id = ask_leave(as_user("u-agent", Role.AGENT), MON)
        loner = as_user("u-lead3", Role.LEAD)
        assert loner.get(f"{LEAVE}/requests").json() == []
        assert loner.post(f"{LEAVE}/requests/{request_id}/approve").status_code == 404

    def test_an_unmanaged_person_is_decided_by_planners_and_admins_only(
        self, teams: dict[str, Any]
    ) -> None:
        teams["a"].manager = None
        teams["a"].save(update_fields=["manager"])
        request_id = ask_leave(as_user("u-agent", Role.AGENT), MON)
        assert (
            as_user("u-lead", Role.LEAD).post(f"{LEAVE}/requests/{request_id}/approve").status_code
            == 404
        )
        assert login(Role.PLANNER).post(f"{LEAVE}/requests/{request_id}/approve").status_code == 200

    def test_a_lead_sees_their_own_request_but_cannot_decide_it(
        self, teams: dict[str, Any]
    ) -> None:
        request_id = ask_leave(as_user("u-lead", Role.LEAD), MON)
        lead = as_user("u-lead", Role.LEAD)
        assert [r["id"] for r in lead.get(f"{LEAVE}/requests").json()] == [request_id]
        assert lead.post(f"{LEAVE}/requests/{request_id}/approve").status_code == 403
        assert login(Role.ADMIN).post(f"{LEAVE}/requests/{request_id}/approve").status_code == 200

    def test_a_lead_cannot_read_another_teams_balances_or_ask_on_their_behalf(
        self, teams: dict[str, Any]
    ) -> None:
        lead = as_user("u-lead", Role.LEAD)
        own_team = lead.get(f"{LEAVE}/balances", {"year": 2026, "employee_id": teams["a"].pk})
        assert own_team.status_code == 200
        other = lead.get(f"{LEAVE}/balances", {"year": 2026, "employee_id": teams["b"].pk})
        assert other.status_code == 404


class TestSwapsAreScopedToTheTeam:
    def offered(self, teams: dict[str, Any]) -> int:
        give = ShiftAssignment.objects.get(employee=teams["a"], day=MON)
        take = ShiftAssignment.objects.get(employee=teams["b"], day=TUE)
        response = as_user("u-agent", Role.AGENT).post(
            SW, {"giveAssignmentId": give.pk}, content_type="application/json"
        )
        assert response.status_code == 201, response.content
        swap_id = int(response.json()["id"])
        taken = as_user("u-colleague", Role.AGENT).post(
            f"{SW}/{swap_id}/accept", {"assignmentId": take.pk}, content_type="application/json"
        )
        assert taken.status_code == 200, taken.content
        return swap_id

    def test_both_teams_leads_can_see_a_swap_between_the_teams_and_either_may_decide(
        self, teams: dict[str, Any]
    ) -> None:
        swap_id = self.offered(teams)
        for lead in ("u-lead", "u-lead2"):
            listed = as_user(lead, Role.LEAD).get(SW).json()
            assert [s["id"] for s in listed] == [swap_id]
        assert as_user("u-lead2", Role.LEAD).post(f"{SW}/{swap_id}/approve").status_code == 200

    def test_a_lead_with_neither_person_in_their_team_cannot_see_or_decide_it(
        self, teams: dict[str, Any]
    ) -> None:
        swap_id = self.offered(teams)
        outsider = as_user("u-lead3", Role.LEAD)
        assert outsider.get(SW).json() == []
        for what in ("approve", "reject"):
            assert (
                outsider.post(
                    f"{SW}/{swap_id}/{what}", {}, content_type="application/json"
                ).status_code
                == 404
            )


class TestAvailabilityIsScopedToTheTeam:
    def test_a_lead_reads_their_teams_availability_and_not_another_teams(
        self, teams: dict[str, Any]
    ) -> None:
        lead = as_user("u-lead", Role.LEAD)
        assert lead.get(AV, {"employee_id": teams["a"].pk}).status_code == 200
        assert lead.get(AV, {"employee_id": teams["b"].pk}).status_code == 404


class TestSettingAManager:
    def body(self, employee: Employee, **extra: Any) -> dict[str, Any]:
        return {
            "empNo": employee.emp_no,
            "name": employee.name,
            "contractType": "permanent",
            "workMode": "office",
            "weeklyHours": 40,
            "skills": [{"queueId": queue().pk, "level": 1}],
            **extra,
        }

    def put(self, employee: Employee, client: Client | None = None, **extra: Any) -> Any:
        return (client or login(Role.PLANNER)).put(
            f"{EMPLOYEES}/{employee.pk}",
            self.body(employee, **extra),
            content_type="application/json",
        )

    def test_a_planner_names_a_lead_as_manager_and_the_list_says_who(
        self, teams: dict[str, Any]
    ) -> None:
        response = self.put(teams["b"], managerId=teams["l1"].pk)
        assert response.status_code == 200, response.content
        body = response.json()
        assert (body["managerId"], body["manager"]) == (teams["l1"].pk, "Person L001")
        listed = {e["empNo"]: e for e in login(Role.PLANNER).get(EMPLOYEES).json()}
        assert listed["L001"]["canManage"] is True
        assert listed["E001"]["canManage"] is False

    def test_a_change_that_leaves_the_manager_out_keeps_it_and_null_clears_it(
        self, teams: dict[str, Any]
    ) -> None:
        # Failure caught: an older form without managerId must not silently wipe the team.
        assert self.put(teams["a"]).json()["managerId"] == teams["l1"].pk
        assert self.put(teams["a"], managerId=None).json()["managerId"] is None

    @pytest.mark.parametrize(
        ("who", "code"),
        [
            ("self", "employee.manager_self"),
            ("agent", "employee.manager_cannot"),  # a person with a login that cannot approve
            ("nobody", "employee.manager_unknown"),
        ],
    )
    def test_a_manager_must_be_someone_who_can_approve(
        self, teams: dict[str, Any], who: str, code: str
    ) -> None:
        wanted = {"self": teams["a"].pk, "agent": teams["b"].pk, "nobody": 999999}[who]
        response = self.put(teams["a"], managerId=wanted)
        assert (response.status_code, response.json()["code"]) == (422, code)
        teams["a"].refresh_from_db()
        assert teams["a"].manager_id == teams["l1"].pk

    def test_a_manager_without_a_login_is_refused(self, teams: dict[str, Any]) -> None:
        nobody = person("E050")
        response = self.put(teams["a"], managerId=nobody.pk)
        assert (response.status_code, response.json()["code"]) == (422, "employee.manager_cannot")

    def test_only_planners_and_admins_set_it(self, teams: dict[str, Any]) -> None:
        for role in (Role.LEAD, Role.AGENT, Role.EXECUTIVE):
            assert self.put(teams["b"], login(role), managerId=teams["l1"].pk).status_code == 403
        assert self.put(teams["b"], login(Role.ADMIN), managerId=teams["l1"].pk).status_code == 200

    def test_the_change_is_audited_by_employee_number_not_name(self, teams: dict[str, Any]) -> None:
        self.put(teams["b"], managerId=teams["l1"].pk)
        event = AuditEvent.objects.filter(action=Action.EMPLOYEE_CHANGED).latest("chain_seq")
        changes = {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }
        assert changes["manager"] == ("L002", "L001")
