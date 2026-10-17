"""Hiring plans (CAP-01): the numbers come from the engine, who may see and change them, and that
a cost per person never leaves the roles that see pay."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.capacity.models import HiringPlan

pytestmark = pytest.mark.django_db

PLANS = "/api/v1/capacity/hiring-plans"


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def body(**over: Any) -> dict[str, Any]:
    return {
        "name": "FY plan",
        "startMonth": "2031-03-01",
        "incumbents": 100,
        "attritionPctPerMonth": 0,
        "ramp": [0.0, 0.5, 1.0],
        "required": [100.0] * 6 + [110.0] * 6,
        "costPerPersonMonth": 20000,
        **over,
    }


def make(role: Role = Role.PLANNER, **over: Any) -> dict[str, Any]:
    r = client(role).post(PLANS, body(**over), content_type="application/json")
    assert r.status_code == 201, r.content
    return dict(r.json())


class TestTheNumbers:
    def test_a_rise_in_need_is_hired_for_two_months_ahead_and_costed(self) -> None:
        # Failure caught: hiring in the month the people are needed, or a cost that ignores
        # the months a new hire is paid but still learning.
        plan = make()
        assert [r["hires"] for r in plan["rows"]] == [0, 0, 0, 0, 10, 0, 0, 0, 0, 0, 0, 0]
        assert plan["totalHires"] == 10
        assert plan["rows"][6]["gap"] == 0
        assert plan["rows"][4]["headcount"] == 110  # paid from the month hired
        assert plan["rows"][4]["effective"] == 100  # not yet at full strength
        assert plan["rows"][4]["costRands"] == 110 * 20000
        assert plan["totalCostRands"] == 100 * 4 * 20000 + 110 * 8 * 20000
        assert plan["rows"][0]["month"] == "2031-03-01"
        assert plan["rows"][11]["month"] == "2032-02-01"

    def test_months_roll_over_a_year(self) -> None:
        plan = make(startMonth="2031-11-01", required=[100.0] * 14)
        assert [r["month"] for r in plan["rows"]][1:4] == ["2031-12-01", "2032-01-01", "2032-02-01"]

    def test_attrition_is_replaced_and_a_shortfall_in_the_lead_time_is_flagged(self) -> None:
        plan = make(attritionPctPerMonth=2, required=[110.0] * 12)
        assert plan["totalHires"] > 0
        assert plan["rows"][0]["unavoidable"] is True  # 110 needed now, 100 here, none can arrive
        assert plan["unavoidableMonths"] >= 1
        assert plan["rows"][5]["unavoidable"] is False

    def test_reading_it_again_gives_the_same_plan(self) -> None:
        plan = make()
        again = client(Role.PLANNER).get(f"{PLANS}/{plan['id']}").json()
        assert again["rows"] == plan["rows"]


class TestWhatIsRefused:
    @pytest.mark.parametrize(
        ("over", "code"),
        [
            ({"required": [100.0] * 11}, "hiring.invalid"),
            ({"required": [100.0] * 19}, "hiring.invalid"),
            ({"attritionPctPerMonth": 100}, "hiring.invalid"),
            ({"ramp": [0.5, 0.9]}, "hiring.invalid"),
            ({"ramp": [0.9, 0.2, 1.0]}, "hiring.invalid"),
            ({"incumbents": -1}, "hiring.invalid"),
            ({"startMonth": "2031-03-15"}, "hiring.bad_start"),
            ({"name": "  "}, "hiring.bad_name"),
            ({"costPerPersonMonth": -5}, "hiring.bad_cost"),
        ],
    )
    def test_nonsense_is_refused_with_a_reason(self, over: dict[str, Any], code: str) -> None:
        r = client(Role.PLANNER).post(PLANS, body(**over), content_type="application/json")
        assert (r.status_code, r.json()["code"]) == (422, code)
        assert not HiringPlan.objects.exists()

    def test_not_endless_plans(self) -> None:
        for n in range(20):
            make(name=f"p{n}")
        r = client(Role.PLANNER).post(PLANS, body(), content_type="application/json")
        assert r.status_code == 409


class TestWhoMayDoWhat:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planner_and_admin_make_change_and_delete(self, role: Role) -> None:
        plan = make(role)
        changed = client(role).put(
            f"{PLANS}/{plan['id']}", body(name="Renamed"), content_type="application/json"
        )
        assert changed.json()["name"] == "Renamed"
        assert client(role).delete(f"{PLANS}/{plan['id']}").status_code == 204

    def test_an_executive_reads_but_never_changes(self) -> None:
        plan = make()
        exec_ = client(Role.EXECUTIVE)
        assert exec_.get(f"{PLANS}/{plan['id']}").status_code == 200
        assert exec_.post(PLANS, body(), content_type="application/json").status_code == 403
        r = exec_.put(f"{PLANS}/{plan['id']}", body(), content_type="application/json")
        assert r.status_code == 403
        assert exec_.delete(f"{PLANS}/{plan['id']}").status_code == 403
        assert HiringPlan.objects.count() == 1

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.CUSTOMER_OPS])
    def test_others_cannot_even_read(self, role: Role) -> None:
        plan = make()
        assert client(role).get(PLANS).status_code == 403
        assert client(role).get(f"{PLANS}/{plan['id']}").status_code == 403

    def test_an_unknown_plan_is_not_found(self) -> None:
        assert client(Role.PLANNER).get(f"{PLANS}/99999").status_code == 404
        assert client(Role.PLANNER).delete(f"{PLANS}/99999").status_code == 404
        r = client(Role.PLANNER).put(f"{PLANS}/99999", body(), content_type="application/json")
        assert r.status_code == 404

    def test_the_cost_per_person_never_reaches_an_executive(self) -> None:
        # Failure caught: pay read by a role that is kept away from it.
        plan = make()
        seen = client(Role.EXECUTIVE).get(f"{PLANS}/{plan['id']}").json()
        assert seen["costPerPersonMonth"] is None
        assert seen["totalCostRands"] is None
        assert all(r["costRands"] is None for r in seen["rows"])
        assert "20000" not in str(seen)


def test_the_list_names_the_plans() -> None:
    make(name="B plan")
    make(name="A plan")
    got = client(Role.EXECUTIVE).get(PLANS).json()
    assert [p["name"] for p in got] == ["A plan", "B plan"]
    assert got[0]["months"] == 12


def test_changes_are_audited_by_name_and_never_carry_a_cost() -> None:
    plan = make(costPerPersonMonth=98765)
    client(Role.PLANNER).put(
        f"{PLANS}/{plan['id']}", body(name="Renamed"), content_type="application/json"
    )
    client(Role.PLANNER).delete(f"{PLANS}/{plan['id']}")
    for action in (
        Action.HIRING_PLAN_CREATED,
        Action.HIRING_PLAN_CHANGED,
        Action.HIRING_PLAN_DELETED,
    ):
        assert AuditEvent.objects.filter(action=action).count() == 1
    assert "98765" not in " ".join(str(c) for c in AuditChange.objects.all().values())
