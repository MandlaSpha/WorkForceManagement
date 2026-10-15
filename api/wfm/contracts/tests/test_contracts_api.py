"""Customers, contracts and the risk view, on PostgreSQL with the numbers worked out by hand.

Today is frozen at Wednesday 27 May 2026, so the measured window is 29 April to 26 May and the week
is Monday 25 May.

Measured service level (over OFFERED calls, as everywhere in the app):
    QueueA: 100 offered, 70 answered inside the threshold
    QueueB: 100 offered, 90 answered inside the threshold
    contract service level = (70 + 90) / (100 + 100) = 80.0%
Move QueueA to 60 inside the threshold and it is (60 + 90) / 200 = 75.0%, below an 80% promise.

Coverage: QueueA needs 2 people at each of the 17 half-hours of 09:00-17:30 on Monday and has one
person on D1, so it is short by 1 in each: 17 half-hours short, gap 17.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.contracts.models import ContractQueue, Customer
from wfm.scheduling.tests.helpers import (
    MON,
    assign,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)
from wfm.scheduling.tests.helpers import login as scheduling_login
from wfm.telephony.models import IntervalActual, Queue

pytestmark = pytest.mark.django_db

C = "/api/v1/contracts"
TODAY = date(2026, 5, 27)
SAST = ZoneInfo("Africa/Johannesburg")


@pytest.fixture(autouse=True)
def today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.contracts.selectors.timezone.localdate", lambda: TODAY)


def login(role: Role = Role.ADMIN) -> Client:
    return scheduling_login(role)


def customer(name: str = "Acme") -> int:
    response = login().post(f"{C}/customers", {"name": name}, content_type="application/json")
    assert response.status_code == 201, response.content
    return int(response.json()["id"])


def body(**over: Any) -> dict[str, Any]:
    return {"name": "Gold", "slTargetPct": 80, "slThresholdS": 20, "queueIds": [], **over}


def make(client: Client | None = None, *, customer_id: int | None = None, **over: Any) -> Any:
    owner = customer_id or Customer.objects.get_or_create(name="Acme")[0].pk
    return (client or login()).post(
        C,
        {"customerId": owner, **body(**over)},
        content_type="application/json",
    )


def calls(q: Queue, hour: int, offered: int, in_sl: int, day: int = 20) -> None:
    IntervalActual.objects.create(
        queue=q,
        interval_start=datetime(2026, 5, day, hour, 0, tzinfo=SAST),
        offered=offered,
        answered=offered,
        abandoned=0,
        answered_in_sl=in_sl,
        sum_wait_s=0,
        sum_handle_s=offered * 300,
    )


def row(client: Client, contract_id: int) -> dict[str, Any]:
    return next(r for r in client.get(C).json() if r["id"] == contract_id)


class TestCustomers:
    def test_the_admin_adds_one_and_the_list_shows_it(self) -> None:
        customer("Acme")
        assert [c["name"] for c in login(Role.PLANNER).get(f"{C}/customers").json()] == ["Acme"]

    def test_a_name_is_needed_and_unique(self) -> None:
        customer("Acme")
        again = login().post(f"{C}/customers", {"name": "Acme"}, content_type="application/json")
        assert (again.status_code, again.json()["code"]) == (409, "customer.name_taken")
        blank = login().post(f"{C}/customers", {"name": "  "}, content_type="application/json")
        assert (blank.status_code, blank.json()["code"]) == (422, "customer.name_invalid")


class TestAContractHoldsItsQueuesToItsTarget:
    def test_the_target_and_threshold_are_written_onto_each_queue_and_nothing_else(self) -> None:
        a, b = queue("QueueA"), queue("QueueB")
        response = make(slTargetPct=90, slThresholdS=30, queueIds=[a.pk, b.pk])
        assert response.status_code == 201, response.content
        for q in (a, b):
            q.refresh_from_db()
            assert (q.sl_target_pct, q.sl_threshold_s) == (Decimal("90.00"), 30)
            # Failure caught: a contract quietly confirming shrinkage and occupancy nobody checked.
            assert (q.shrinkage_pct, q.occupancy_ceiling_pct) == (Decimal("30"), Decimal("85"))
            assert q.settings_confirmed is False

    def test_changing_the_target_changes_every_queue_it_holds_and_audits_each(self) -> None:
        a, b = queue("QueueA"), queue("QueueB")
        contract_id = make(queueIds=[a.pk, b.pk]).json()["id"]
        before = AuditEvent.objects.filter(action=Action.QUEUE_SETTINGS_CHANGED).count()
        changed = login().put(
            f"{C}/{contract_id}",
            body(slTargetPct=85, slThresholdS=20, queueIds=[a.pk, b.pk]),
            content_type="application/json",
        )
        assert changed.status_code == 200, changed.content
        a.refresh_from_db()
        assert a.sl_target_pct == Decimal("85.00")
        events = AuditEvent.objects.filter(action=Action.QUEUE_SETTINGS_CHANGED).order_by(
            "chain_seq"
        )
        assert events.count() - before == 2
        newest = events.last()
        assert newest is not None
        last = AuditChange.objects.get(event=newest)
        assert (last.field, last.old_value, last.new_value) == ("sl_target_pct", "80.00", "85")
        assert newest.reason == "contract"

    def test_a_queue_already_at_the_target_is_not_touched_or_audited(self) -> None:
        a = queue("QueueA")  # the defaults are 80% in 20 seconds, which is what the contract says
        make(queueIds=[a.pk])
        assert not AuditEvent.objects.filter(action=Action.QUEUE_SETTINGS_CHANGED).exists()

    def test_taking_a_queue_out_leaves_it_where_it_was_left(self) -> None:
        a, b = queue("QueueA"), queue("QueueB")
        contract_id = make(slTargetPct=90, queueIds=[a.pk, b.pk]).json()["id"]
        login().put(
            f"{C}/{contract_id}",
            body(slTargetPct=95, queueIds=[a.pk]),
            content_type="application/json",
        )
        a.refresh_from_db()
        b.refresh_from_db()
        assert (a.sl_target_pct, b.sl_target_pct) == (Decimal("95.00"), Decimal("90.00"))
        assert not ContractQueue.objects.filter(queue=b).exists()

    def test_a_queue_is_under_one_contract_at_most(self) -> None:
        a = queue("QueueA")
        make(queueIds=[a.pk])
        other = make(name="Silver", queueIds=[a.pk], customer_id=customer("Beta"))
        assert (other.status_code, other.json()["code"]) == (409, "contract.queue_taken")
        assert ContractQueue.objects.count() == 1

    @pytest.mark.parametrize(
        ("over", "code"),
        [
            ({"name": ""}, "contract.name_invalid"),
            ({"slTargetPct": 0}, "contract.sl_target_invalid"),
            ({"slTargetPct": 101}, "contract.sl_target_invalid"),
            ({"slThresholdS": 0}, "contract.sl_threshold_invalid"),
            ({"slThresholdS": 601}, "contract.sl_threshold_invalid"),
            ({"queueIds": [999999]}, "contract.queue_unknown"),
        ],
    )
    def test_nonsense_is_refused_with_a_reason_and_nothing_is_written(
        self, over: dict[str, Any], code: str
    ) -> None:
        response = make(**over)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert ContractQueue.objects.count() == 0

    def test_names_are_unique_per_customer_but_can_repeat_across_customers(self) -> None:
        acme = customer("Acme")
        assert make(customer_id=acme).status_code == 201
        assert make(customer_id=acme).json()["code"] == "contract.name_taken"
        assert make(customer_id=customer("Beta")).status_code == 201

    def test_the_audit_trail_says_which_queues_and_what_target(self) -> None:
        a = queue("QueueA")
        make(slTargetPct=90, queueIds=[a.pk])
        event = AuditEvent.objects.get(action=Action.CONTRACT_CREATED)
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes == {"sl_target_pct": "90", "queues": "QueueA"}

    def test_an_inactive_contract_is_still_listed_so_history_is_kept(self) -> None:
        contract_id = make().json()["id"]
        login().put(
            f"{C}/{contract_id}", {**body(), "active": False}, content_type="application/json"
        )
        assert row(login(), contract_id)["active"] is False

    def test_an_unknown_contract_is_not_found(self) -> None:
        assert (
            login().put(f"{C}/999999", body(), content_type="application/json").status_code == 404
        )


class TestHowEachContractIsDoing:
    def make_pair(self) -> tuple[int, Queue, Queue]:
        a, b = queue("QueueA"), queue("QueueB")
        return make(queueIds=[a.pk, b.pk]).json()["id"], a, b

    def test_a_contract_that_meets_its_promise_is_not_at_risk(self) -> None:
        contract_id, a, b = self.make_pair()
        calls(a, 10, 100, 70)
        calls(b, 10, 100, 90)
        shown = row(login(), contract_id)
        assert (shown["offered"], shown["measuredSlPct"], shown["atRisk"]) == (200, 80.0, False)

    def test_one_queue_falling_behind_pulls_the_contract_below_its_promise(self) -> None:
        contract_id, a, b = self.make_pair()
        calls(a, 10, 100, 60)
        calls(b, 10, 100, 90)
        shown = row(login(), contract_id)
        assert shown["measuredSlPct"] == 75.0
        assert shown["atRisk"] is True
        assert shown["risks"] == [
            "service level 75.0% over the last 28 days is below the 80% promised"
        ]

    def test_calls_outside_the_28_days_do_not_count(self) -> None:
        contract_id, a, _ = self.make_pair()
        calls(a, 10, 100, 100, day=20)  # inside
        IntervalActual.objects.create(  # 30 days ago: outside, and terrible
            queue=a,
            interval_start=datetime(2026, 4, 27, 10, 0, tzinfo=SAST),
            offered=1000,
            answered=1000,
            abandoned=0,
            answered_in_sl=0,
            sum_wait_s=0,
            sum_handle_s=0,
        )
        assert row(login(), contract_id)["measuredSlPct"] == 100.0

    def test_no_calls_means_no_figure_never_a_made_up_zero(self) -> None:
        contract_id, _, _ = self.make_pair()
        shown = row(login(), contract_id)
        assert (shown["offered"], shown["measuredSlPct"], shown["atRisk"]) == (0, None, False)

    def test_a_week_short_of_people_puts_the_contract_at_risk_with_the_count(self) -> None:
        contract_id, a, _ = self.make_pair()
        shifts = standard_shifts()
        publish_forecast(a, {(MON, s): 2 for s in range(18, 35)})
        one = person("E001")
        assign(login(Role.PLANNER), a, one, MON, shifts["D1"])
        shown = row(login(), contract_id)
        # The whole Monday has a known requirement (48 half-hours), 17 of which need two people.
        assert (shown["gap"], shown["underIntervals"], shown["intervalsKnown"]) == (17, 17, 48)
        assert shown["atRisk"] is True
        assert shown["risks"] == ["17 half-hours of the week are short of the people needed"]

    def test_a_queue_with_no_forecast_has_no_known_gap(self) -> None:
        contract_id, _, _ = self.make_pair()
        shown = row(login(), contract_id)
        assert (shown["intervalsKnown"], shown["gap"], shown["atRisk"]) == (0, 0, False)

    def test_queues_not_in_any_contract_are_not_counted_against_one(self) -> None:
        contract_id, a, _ = self.make_pair()
        outside = queue("QueueC")
        calls(a, 10, 100, 100)
        calls(outside, 10, 1000, 0)  # a disaster, but not this contract's
        assert row(login(), contract_id)["measuredSlPct"] == 100.0


class TestRoles:
    @pytest.mark.parametrize(
        "role", [Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS, Role.LEAD]
    )
    def test_these_roles_read_contracts_and_customers(self, role: Role) -> None:
        make()
        assert login(role).get(C).status_code == 200
        assert login(role).get(f"{C}/customers").status_code == 200

    def test_an_agent_reads_nothing(self) -> None:
        assert login(Role.AGENT).get(C).status_code == 403
        assert login(Role.AGENT).get(f"{C}/customers").status_code == 403

    @pytest.mark.parametrize(
        "role", [Role.PLANNER, Role.LEAD, Role.EXECUTIVE, Role.CUSTOMER_OPS, Role.AGENT]
    )
    def test_only_the_admin_changes_what_a_contract_promises(self, role: Role) -> None:
        contract_id = make().json()["id"]
        client = login(role)
        assert (
            client.post(
                f"{C}/customers", {"name": "X"}, content_type="application/json"
            ).status_code
            == 403
        )
        assert make(client).status_code == 403
        assert (
            client.put(f"{C}/{contract_id}", body(), content_type="application/json").status_code
            == 403
        )
