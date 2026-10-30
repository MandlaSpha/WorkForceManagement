"""Utilisation, cost and workload balance (UTL-01, UTL-02, WLB-01) through the API.

Synthetic data only. Two people on the 09:00 to 17:30 shift (480 paid minutes) on Monday
25 May 2026; Ann is on QueueA, which the "Acme" contract holds; Bob is on QueueB (no contract)
unless a test moves him.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from wfm_engine import overtime as pricing

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.contracts.models import Contract, ContractQueue, Customer, CustomerAssignment
from wfm.overtime.models import EmployeePay, OvertimeRequest, OvertimeStatus
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import (
    ActivityKind,
    RosterStatus,
    RosterWeek,
    ShiftActivity,
    ShiftAssignment,
    ShiftTemplate,
)
from wfm.scheduling.tests.helpers import (
    MON,
    assign,
    login,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)
from wfm.servicedesk.models import ServicePool, WorkItem
from wfm.utilisation import selectors as util_selectors

pytestmark = pytest.mark.django_db

REPORT = "/api/v1/utilisation/report"
COSTS = "/api/v1/utilisation/costs"
BALANCE = "/api/v1/utilisation/balance"
MONTH = "2026-05-01"
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]


def terms_url(contract: Contract) -> str:
    return f"/api/v1/utilisation/contracts/{contract.pk}/terms"


class World:
    def __init__(self) -> None:
        shifts = standard_shifts()
        self.ann = person("E001", queues=("QueueA",))
        self.bob = person("E002", queues=("QueueA", "QueueB"))
        self.lead = lead_of(self.ann)
        planner = login(Role.PLANNER)
        self.planner_user = User.objects.get(username="u-planner")
        assign(planner, queue("QueueA"), self.ann, MON, shifts["D1"])
        assign(planner, queue("QueueB"), self.bob, MON, shifts["D1"])
        RosterWeek.objects.update(status=RosterStatus.PUBLISHED)
        customer = Customer.objects.create(name="Acme")
        self.contract = Contract.objects.create(customer=customer, name="Support")
        ContractQueue.objects.create(contract=self.contract, queue=queue("QueueA"))

    def away(self, who: Any, kind: str, slots: int) -> None:
        ShiftActivity.objects.create(
            assignment=ShiftAssignment.objects.get(employee=who),
            kind=kind,
            offset_slots=4,
            slots=slots,
            created_by=self.planner_user,
        )


@pytest.fixture
def world() -> World:
    return World()


def get(role: Role, url: str, **params: str) -> Any:
    return login(role).get(url, params)


# --- UTL-01 -------------------------------------------------------------------------------------


def test_utilisation_over_the_roles(world: World) -> None:
    for role in (Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS, Role.LEAD):
        assert get(role, REPORT, month=MONTH).status_code == 200, role
    assert get(Role.AGENT, REPORT, month=MONTH).status_code == 403


def test_worked_billable_target_and_gap_per_group(world: World) -> None:
    world.away(world.ann, ActivityKind.LUNCH, 1)  # lunch is not paid time: it changes nothing
    world.away(world.bob, ActivityKind.TRAINING, 2)
    body = get(Role.PLANNER, REPORT, month=MONTH).json()
    assert body["basis"] == "modelled"
    [contract] = body["contracts"]
    assert contract["name"] == "Support"
    assert contract["customer"] == "Acme"
    assert (contract["workedMin"], contract["billableMin"]) == (480, 480)
    assert contract["utilisationPct"] == 100.0
    assert contract["targetPct"] == 75.0
    assert contract["targetIsDefault"] is True
    assert contract["gapPct"] == 25.0
    [customer] = body["customers"]
    assert customer["name"] == "Acme"
    # Bob's queue is under no contract, so his time is worked but never billable, and has no target.
    [team] = [t for t in body["teams"] if t["name"] == "No team"]
    assert (team["workedMin"], team["billableMin"]) == (480, 0)
    assert team["targetPct"] is None
    assert team["gapPct"] is None


def test_non_customer_activity_lowers_billable_time(world: World) -> None:
    world.away(world.ann, ActivityKind.TRAINING, 3)  # 90 minutes
    [contract] = get(Role.ADMIN, REPORT, month=MONTH).json()["contracts"]
    assert contract["billableMin"] == 390
    assert contract["utilisationPct"] == 81.2


def test_draft_rosters_are_not_counted(world: World) -> None:
    RosterWeek.objects.update(status=RosterStatus.DRAFT)
    body = get(Role.ADMIN, REPORT, month=MONTH).json()
    assert body["contracts"] == []
    assert body["people"] == []


def test_people_rows_for_planners_in_number_order_and_never_ranked(world: World) -> None:
    people = get(Role.PLANNER, REPORT, month=MONTH).json()["people"]
    assert [p["empNo"] for p in people] == ["E001", "E002"]
    assert all("rank" not in p for p in people)


@pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
def test_executives_and_customer_operations_see_groups_but_no_named_person(
    world: World, role: Role
) -> None:
    unassigned = get(role, REPORT, month=MONTH).json()
    if role == Role.CUSTOMER_OPS:  # no customer assigned yet: no contract is theirs
        assert unassigned["contracts"] == []
        user = User.objects.get(username=f"u-{role.value}")
        CustomerAssignment.objects.create(customer=Customer.objects.get(name="Acme"), user=user)
    body = get(role, REPORT, month=MONTH).json()
    assert body["people"] == []
    assert body["contracts"], "they still see the aggregate"
    assert "Person E001" not in str(body)


def test_a_lead_sees_their_own_team_only(world: World) -> None:
    body = get(Role.LEAD, REPORT, month=MONTH).json()
    assert [p["empNo"] for p in body["people"]] == ["E001"]
    assert [t["name"] for t in body["teams"]] == ["Team L001"]
    assert "Person E002" not in str(body)


def test_month_must_start_on_the_first(world: World) -> None:
    assert get(Role.ADMIN, REPORT, month="2026-05-15").status_code == 422


# --- the target and revenue ---------------------------------------------------------------------


def put_terms(role: Role, contract: Contract, target: object = 60, revenue: object = 20000) -> Any:
    return login(role).put(
        terms_url(contract),
        {"utilisationTargetPct": target, "monthlyRevenueRands": revenue},
        content_type="application/json",
    )


def test_only_the_admin_sets_terms_and_it_is_audited_without_the_revenue(world: World) -> None:
    for role in (Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
        assert put_terms(role, world.contract).status_code == 403, role
    response = put_terms(Role.ADMIN, world.contract, target=60, revenue=20000)
    assert response.status_code == 200
    assert response.json() == {
        "contractId": world.contract.pk,
        "utilisationTargetPct": 60.0,
        "hasRevenue": True,
    }
    event = AuditEvent.objects.get(action=Action.UTILISATION_TERMS_CHANGED)
    assert "20000" not in str([(c.field, c.old_value, c.new_value) for c in event.changes.all()])
    [contract] = get(Role.ADMIN, REPORT, month=MONTH).json()["contracts"]
    assert contract["targetPct"] == 60.0
    assert contract["targetIsDefault"] is False
    assert contract["gapPct"] == 40.0


def test_terms_for_an_unknown_contract_and_bad_values(world: World) -> None:
    bad = Contract(pk=987654)
    assert put_terms(Role.ADMIN, bad).status_code == 404
    assert put_terms(Role.ADMIN, world.contract, target=0).status_code == 422
    assert put_terms(Role.ADMIN, world.contract, target=101).status_code == 422
    assert put_terms(Role.ADMIN, world.contract, revenue=-1).status_code == 422
    assert not AuditEvent.objects.filter(action=Action.UTILISATION_TERMS_CHANGED).exists()


# --- UTL-02 -------------------------------------------------------------------------------------


def salary(who: Any, amount: int = 20000) -> Decimal:
    EmployeePay.objects.create(employee=who, monthly_salary=amount)
    return pricing.hourly_rate(Decimal(amount), who.weekly_hours)


def test_costs_are_for_the_roles_that_see_pay(world: World) -> None:
    for role in (Role.ADMIN, Role.PLANNER):
        assert get(role, COSTS, month=MONTH).status_code == 200, role
    for role in (Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
        assert get(role, COSTS, month=MONTH).status_code == 403, role


def test_cost_per_engineer_and_overtime_against_contract_revenue(world: World) -> None:
    rate = salary(world.ann)
    put_terms(Role.ADMIN, world.contract, target=60, revenue=10000)
    OvertimeRequest.objects.create(
        employee=world.ann,
        day=MON,
        start_time=time(18, 0),
        end_time=time(19, 0),
        minutes=60,
        status=OvertimeStatus.APPROVED,
        requested_by=world.planner_user,
        approved_cost=Decimal("300.00"),
    )
    body = get(Role.PLANNER, COSTS, month=MONTH).json()
    ordinary = float((rate * 480 / 60).quantize(Decimal("0.01")))
    ann = next(e for e in body["engineers"] if e["empNo"] == "E001")
    assert ann["ordinaryRands"] == ordinary
    assert ann["overtimeRands"] == 300.0
    assert ann["totalRands"] == round(ordinary + 300, 2)
    bob = next(e for e in body["engineers"] if e["empNo"] == "E002")
    assert bob["ordinaryRands"] is None  # no salary on file: nothing is invented
    assert bob["totalRands"] is None
    assert body["engineersWithoutSalary"] == 1
    contract = next(c for c in body["contracts"] if c["name"] == "Support")
    assert contract["overtimeRands"] == 300.0
    assert contract["revenueRands"] == 10000.0
    assert contract["overtimePctOfRevenue"] == 3.0
    assert contract["incomplete"] is False
    nowhere = next(c for c in body["contracts"] if c["contractId"] is None)
    assert nowhere["incomplete"] is True  # Bob's time has no salary to price it from
    assert body["basis"] == "modelled"


def test_cost_per_ticket_from_effort_at_the_blended_rate(world: World) -> None:
    rate = salary(world.ann)
    pool = ServicePool.objects.create(name="Desk")
    for ref, effort in (("INC1", 60), ("INC2", 30), ("INC3", None)):
        WorkItem.objects.create(
            ref=ref,
            pool=pool,
            opened_at=datetime(2026, 5, 4, 8, tzinfo=UTC),
            closed_at=datetime(2026, 5, 12, 8, tzinfo=UTC),
            effort_minutes=effort,
        )
    WorkItem.objects.create(  # closed in another month: not counted
        ref="INC4",
        pool=pool,
        opened_at=datetime(2026, 4, 4, 8, tzinfo=UTC),
        closed_at=datetime(2026, 4, 12, 8, tzinfo=UTC),
        effort_minutes=600,
    )
    [row] = get(Role.ADMIN, COSTS, month=MONTH).json()["pools"]
    assert (row["closed"], row["estimated"], row["effortMin"]) == (3, 2, 90)
    total = (rate * 90 / 60).quantize(Decimal("0.01"))
    assert row["costRands"] == float(total)
    assert row["perTicketRands"] == float(
        (total / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def test_no_rates_known_means_no_ticket_cost(world: World) -> None:
    pool = ServicePool.objects.create(name="Desk")
    WorkItem.objects.create(
        ref="INC1",
        pool=pool,
        opened_at=datetime(2026, 5, 4, 8, tzinfo=UTC),
        closed_at=datetime(2026, 5, 12, 8, tzinfo=UTC),
        effort_minutes=60,
    )
    [row] = get(Role.ADMIN, COSTS, month=MONTH).json()["pools"]
    assert row["costRands"] is None
    assert row["perTicketRands"] is None


def test_no_pay_figure_reaches_a_role_that_may_not_see_one(world: World) -> None:
    salary(world.ann, 98765)
    for role in (Role.LEAD, Role.EXECUTIVE, Role.CUSTOMER_OPS):
        text = get(role, REPORT, month=MONTH).content.decode()
        assert "98765" not in text
        assert "Rands" not in text


# --- WLB-01 -------------------------------------------------------------------------------------


def stretched_world(world: World) -> None:
    """QueueA needs 3 people all day and has Ann; QueueB needs 1 and has Bob and Carl."""
    carl = person("E003", queues=("QueueB",))
    ShiftAssignment.objects.create(  # the roster is published, so not through the roster API
        roster_week=RosterWeek.objects.get(queue=queue("QueueB")),
        employee=carl,
        day=MON,
        template=ShiftTemplate.objects.get(code="D1"),
    )
    slots = range(18, 35)
    publish_forecast(queue("QueueA"), {(MON, s): 3 for s in slots})
    publish_forecast(queue("QueueB"), {(MON, s): 1 for s in slots})


def test_balance_is_for_planners_admins_and_leads(world: World) -> None:
    for role in (Role.ADMIN, Role.PLANNER, Role.LEAD):
        assert get(role, BALANCE, day=str(MON)).status_code == 200, role
    for role in (Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
        assert get(role, BALANCE, day=str(MON)).status_code == 403, role


def test_balance_names_stretched_and_slack_queues_and_suggests_a_move(world: World) -> None:
    stretched_world(world)
    body = get(Role.PLANNER, BALANCE, day=str(MON)).json()
    states = {q["queue"]: q["state"] for q in body["queues"]}
    assert states == {"QueueA": "stretched", "QueueB": "slack"}
    assert body["queues"][0]["queue"] == "QueueA"  # most stretched first
    assert "suggestions" in body["note"]
    [move] = body["suggestions"]
    assert (move["empNo"], move["fromQueue"], move["toQueue"]) == ("E002", "QueueB", "QueueA")


def test_balance_never_moves_anyone(world: World) -> None:
    stretched_world(world)
    before = list(ShiftAssignment.objects.values_list("employee_id", "roster_week__queue_id"))
    get(Role.ADMIN, BALANCE, day=str(MON))
    assert before == list(
        ShiftAssignment.objects.values_list("employee_id", "roster_week__queue_id")
    )


def test_a_lead_is_offered_only_their_own_team(world: World) -> None:
    stretched_world(world)  # the lead leads Ann; the person who could move is Bob
    assert get(Role.LEAD, BALANCE, day=str(MON)).json()["suggestions"] == []
    lead_of(world.bob)
    [move] = get(Role.LEAD, BALANCE, day=str(MON)).json()["suggestions"]
    assert move["empNo"] == "E002"


def test_a_queue_without_a_forecast_is_unknown_not_balanced(world: World) -> None:
    states = {
        q["queue"]: q["state"] for q in get(Role.ADMIN, BALANCE, day=str(MON)).json()["queues"]
    }
    assert set(states.values()) <= {"unknown"}


def test_balance_day_is_a_date(world: World) -> None:
    assert get(Role.ADMIN, BALANCE, day="nope").status_code == 422
    assert isinstance(
        date.fromisoformat(get(Role.ADMIN, BALANCE, day=str(MON)).json()["day"]), date
    )


# --- Service-level checks: the API guard is not the only one ------------------------------------


def test_the_terms_audit_names_the_fields_and_records_the_revenue_as_on_file(world: World) -> None:
    # Failure caught: the terms audit event written with no field changes, so the trail cannot
    # say which terms moved
    assert put_terms(Role.ADMIN, world.contract, target=60, revenue=20000).status_code == 200
    event = AuditEvent.objects.get(action=Action.UTILISATION_TERMS_CHANGED)
    changes = {c.field: (c.old_value, c.new_value) for c in event.changes.all()}
    assert set(changes) == {"utilisation_target_pct", "monthly_revenue"}
    assert changes["monthly_revenue"] == ("none", "on file")


def test_a_target_of_exactly_100_is_accepted(world: World) -> None:
    # Failure caught: the target's upper bound made exclusive, so a 100% target is refused
    assert put_terms(Role.ADMIN, world.contract, target=100).status_code == 200


@pytest.mark.parametrize("role", [Role.LEAD, Role.EXECUTIVE, Role.CUSTOMER_OPS])
def test_the_cost_service_itself_refuses_roles_that_do_not_see_pay(
    world: World, role: Role
) -> None:
    # Failure caught: the service's own pay check widened to the group roles. The API guard
    # would still stop the request, so only a direct call to the service shows the gap.
    login(role)
    user = User.objects.get(username=f"u-{role.value}")
    with pytest.raises(PermissionError):
        util_selectors.costs(user, date(2026, 5, 1))
