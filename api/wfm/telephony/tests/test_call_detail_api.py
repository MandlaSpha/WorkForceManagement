"""The Call detail screen's API (DAT-01): the figures, honest gaps, and who sees which rows."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import AgentLogin
from wfm.scheduling.tests.helpers import person
from wfm.telephony.models import Queue

from . import factories as f

pytestmark = pytest.mark.django_db

URL = "/api/v1/telephony/call-detail"
INC1, INC2 = "INC000000000101", "INC000000000202"
ALLOWED = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE]
REFUSED = [Role.AGENT, Role.CUSTOMER_OPS]


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def ask(role: Role, month: str = "2031-03") -> dict[str, Any]:
    response = client(role).get(URL, {"month": month})
    assert response.status_code == 200, response.content
    return dict(response.json())


def world() -> Queue:
    """Two agents in the lead's team, one agent in nobody's team, one login mapped to no one."""
    lead = lead_of()
    mine = person("E010", name="Mia Team")
    mine.manager = lead
    mine.save()
    other = person("E020", name="Otto Elsewhere")
    AgentLogin.objects.create(login="Agent010", employee=mine)
    AgentLogin.objects.create(login="Agent020", employee=other)
    q = Queue.objects.create(name="Support")
    c1 = f.call(q, agent="Agent010", hour=9)
    f.offer(c1, "Agent020", answered=False, ring_s=20)
    f.offer(c1, "Agent999", answered=False, ring_s=30)
    f.offer(c1, "Agent010", answered=True, ring_s=10)
    c2 = f.call(q, agent="Agent020", day=4)
    f.offer(c2, "Agent020", answered=True, ring_s=4)
    f.offer(c2, "Agent010", answered=False, ring_s=16)
    f.transfer(c1, "Agent010", answer_s=4, duration_s=60)
    f.pause(c1, "hold", 30)
    f.pause(c2, "hold", 50)
    f.pause(c2, "mute", 10)
    f.disposition(c1, INC1)
    f.disposition(c2, INC1)
    f.disposition(c2, INC2)
    # An IVR path: two calls, one of which never reached the queue.
    c1.queue_at = c1.start_at
    c1.save()
    f.ivr(c1, 1, "1", "Support menu")
    d1 = f.call(q, day=5, status="Abandoned")
    d1.queue_at = d1.start_at
    d1.save()
    f.ivr(d1, 1, "1", "Support menu")
    d2 = f.call(q, day=5, status="Abandoned")
    f.ivr(d2, 1, "1", "Support menu")
    # A call in another month must not count.
    gone = f.call(q, agent="Agent010")
    gone.start_at = gone.start_at.replace(month=2)
    gone.save()
    f.offer(gone, "Agent010", answered=False)
    return q


class TestWhoMayAsk:
    @pytest.mark.parametrize("role", ALLOWED)
    def test_these_roles_can_open_it(self, role: Role) -> None:
        world()
        assert ask(role)["month"] == "2031-03"

    @pytest.mark.parametrize("role", REFUSED)
    def test_an_agent_and_customer_ops_are_refused(self, role: Role) -> None:
        world()
        assert client(role).get(URL, {"month": "2031-03"}).status_code == 403

    def test_signed_out_is_refused(self) -> None:
        assert Client().get(URL, {"month": "2031-03"}).status_code in (401, 403)

    @pytest.mark.parametrize("bad", ["2031-13", "2031-3", "march", "2031-03-01", ""])
    def test_a_bad_month_is_refused(self, bad: str) -> None:
        assert client(Role.PLANNER).get(URL, {"month": bad}).status_code == 422


class TestRingNoAnswer:
    def test_admin_sees_each_login_in_employee_number_order_unmapped_last(self) -> None:
        world()
        agents = ask(Role.PLANNER)["agents"]
        assert [(a["login"], a["employeeNumber"]) for a in agents] == [
            ("Agent010", "E010"),
            ("Agent020", "E020"),
            ("Agent999", None),
        ]
        mia = agents[0]
        assert (mia["offers"], mia["answered"], mia["ringNoAnswer"]) == (2, 1, 1)
        assert float(mia["ringNoAnswerPct"]) == 50.0
        assert float(mia["avgRingS"]) == 13.0  # last month's offer (ring unknown) is not in March

    def test_no_rank_and_no_team_average_beside_a_person(self) -> None:
        # Failure caught: a league table or a "vs team" figure shown to peers.
        world()
        body = ask(Role.PLANNER)
        assert set(body["agents"][0]) == {
            "login",
            "employeeNumber",
            "employeeName",
            "offers",
            "answered",
            "ringNoAnswer",
            "ringNoAnswerPct",
            "avgRingS",
        }
        assert not any("rank" in k.lower() or "average" in k.lower() for k in body)

    def test_a_lead_sees_only_their_own_teams_agents(self) -> None:
        # Failure caught: a lead reading a colleague team's ring-no-answer, or unmapped logins.
        world()
        agents = ask(Role.LEAD)["agents"]
        assert [a["login"] for a in agents] == ["Agent010"]
        assert ask(Role.LEAD)["scope"] == "team"
        text = client(Role.LEAD).get(URL, {"month": "2031-03"}).content.decode()
        for hidden in ("Agent020", "Agent999", "Otto Elsewhere", "E020"):
            assert hidden not in text

    def test_an_executive_gets_no_per_agent_rows(self) -> None:
        # Failure caught: executives reading logins or names.
        world()
        body = ask(Role.EXECUTIVE)
        assert body["agents"] is None
        assert body["agentsAllowed"] is False
        assert body["scope"] == "aggregate"
        text = client(Role.EXECUTIVE).get(URL, {"month": "2031-03"}).content.decode()
        for hidden in ("Agent010", "Agent020", "Mia Team", "E010"):
            assert hidden not in text

    def test_no_offers_sheet_is_no_data_not_an_empty_table(self) -> None:
        world()
        f.only_sheets("Call Record Report", "Call IVR Details")
        body = ask(Role.PLANNER)
        assert body["sheets"]["ring"] is False
        assert body["agents"] is None


class TestIvr:
    def test_calls_per_step_and_drop_off_per_queue(self) -> None:
        world()
        (q,) = ask(Role.EXECUTIVE)["ivr"]
        assert q["queue"] == "Support"
        assert (q["calls"], q["reachedQueue"], q["endedInIvr"], q["abandonedAfterIvr"]) == (
            3,
            2,
            1,
            1,
        )
        assert q["steps"] == [
            {"step": 1, "digit": "1", "activity": "Support menu", "calls": 3, "endedHere": 1}
        ]

    def test_no_ivr_sheet_is_no_data(self) -> None:
        world()
        f.only_sheets("Call Record Report")
        body = ask(Role.PLANNER)
        assert body["ivr"] is None
        assert body["sheets"]["ivr"] is False


class TestTransfersHoldsMutes:
    def test_counts_and_averages_per_queue_and_day(self) -> None:
        world()
        body = ask(Role.LEAD)
        (total,) = [e for e in body["eventsByQueue"] if e["day"] is None]
        assert (total["transfers"], total["holds"], total["mutes"]) == (1, 2, 1)
        assert float(total["avgHoldS"]) == 40.0
        assert float(total["avgTransferS"]) == 60.0
        days = {e["day"]: e for e in body["eventsByDay"]}
        assert days["2031-03-03"]["holds"] == 1
        assert days["2031-03-04"]["mutes"] == 1

    def test_a_missing_sheet_is_null_not_zero(self) -> None:
        # Failure caught: "0 transfers" shown when the transfer sheet was never imported.
        world()
        f.only_sheets("Call Record Report", "Call Hold Details")
        (total,) = [e for e in ask(Role.PLANNER)["eventsByQueue"] if e["day"] is None]
        assert total["transfers"] is None
        assert total["avgTransferS"] is None
        assert total["mutes"] is None
        assert total["holds"] == 2

    def test_a_queue_with_calls_but_no_events_shows_real_zeros(self) -> None:
        world()
        Queue.objects.create(name="Quiet")
        f.call(Queue.objects.get(name="Quiet"))
        rows = {e["queue"]: e for e in ask(Role.PLANNER)["eventsByQueue"] if e["day"] is None}
        assert (rows["Quiet"]["transfers"], rows["Quiet"]["holds"]) == (0, 0)


class TestIncidentLinks:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_admin_and_planner_see_the_numbers(self, role: Role) -> None:
        world()
        body = ask(role)
        assert body["incidents"] == [
            {"queue": "Support", "callsWithIncident": 2, "incidents": [INC1, INC2]}
        ]

    @pytest.mark.parametrize("role", [Role.LEAD, Role.EXECUTIVE])
    def test_a_lead_and_an_executive_get_no_incident_numbers(self, role: Role) -> None:
        # Failure caught: incident numbers (a link to tickets) leaking to roles that may not
        # open them.
        world()
        body = ask(role)
        assert body["incidents"] is None
        assert body["incidentsAllowed"] is False
        assert INC1 not in client(role).get(URL, {"month": "2031-03"}).content.decode()

    def test_no_disposition_sheet_is_no_data(self) -> None:
        world()
        f.only_sheets("Call Record Report")
        body = ask(Role.ADMIN)
        assert body["incidents"] is None
        assert body["sheets"]["incidents"] is False


def test_a_month_no_import_covers_is_no_data_everywhere() -> None:
    # Failure caught: a month nobody imported shown as a screen of zeros.
    world()
    body = ask(Role.PLANNER, "2031-04")
    assert set(body["sheets"].values()) == {False}
    assert body["agents"] is None
    assert body["ivr"] is None
    assert body["incidents"] is None
    assert body["eventsByQueue"] is None
