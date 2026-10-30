"""A customer operations manager is held to the customers an admin assigned to them.

Two customers, each with a contract holding one queue. `u-customer_ops` is assigned to Acme only,
so Bravo (and its contract and queue) must never reach them, by any road.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.contracts.models import Contract, ContractQueue, Customer, CustomerAssignment
from wfm.scheduling.tests.helpers import login, queue
from wfm.telephony.models import Queue

pytestmark = pytest.mark.django_db

C = "/api/v1/contracts"
ALL_ROLES = list(Role)


def world() -> dict[str, Any]:
    acme, bravo = Customer.objects.create(name="Acme"), Customer.objects.create(name="Bravo")
    out: dict[str, Any] = {"acme": acme, "bravo": bravo}
    for key, customer in (("a", acme), ("b", bravo)):
        contract = Contract.objects.create(customer=customer, name=f"Gold {key}")
        q = queue(f"Queue {key}")
        ContractQueue.objects.create(contract=contract, queue=q)
        out[f"contract_{key}"], out[f"queue_{key}"] = contract, q
    return out


def ops(w: dict[str, Any], *, assign: bool = True) -> tuple[Client, User]:
    client = login(Role.CUSTOMER_OPS)
    user = User.objects.get(username="u-customer_ops")
    if assign:
        CustomerAssignment.objects.create(customer=w["acme"], user=user)
    return client, user


def put(client: Client, customer: Customer, ids: list[int]) -> Any:
    return client.put(
        f"{C}/customers/{customer.pk}/assignees", {"userIds": ids}, content_type="application/json"
    )


def test_an_assigned_manager_sees_only_their_customer_contract_and_queue() -> None:
    w = world()
    client, user = ops(w)
    assert [c["name"] for c in client.get(f"{C}/customers").json()] == ["Acme"]
    assert [c["name"] for c in client.get(C).json()] == ["Gold a"]
    assert list(Contract.objects.for_user(user)) == [w["contract_a"]]
    assert list(ContractQueue.objects.for_user(user)) == [w["queue_a"].contract_link]
    assert list(Queue.objects.for_user(user)) == [w["queue_a"]]


def test_an_unassigned_manager_sees_nothing() -> None:
    w = world()
    client, user = ops(w, assign=False)
    assert client.get(f"{C}/customers").json() == []
    assert client.get(C).json() == []
    assert not Queue.objects.for_user(user).exists()


def test_other_roles_keep_their_reach() -> None:
    world()
    for role in (Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.LEAD):
        user = login(role) and User.objects.get(username=f"u-{role.value}")
        assert Customer.objects.for_user(user).count() == 2, role


def test_the_assignment_list_is_the_admins_alone() -> None:
    w = world()
    _, user = ops(w)
    assert CustomerAssignment.objects.for_user(user).count() == 0
    admin = login(Role.ADMIN) and User.objects.get(username="u-admin")
    assert CustomerAssignment.objects.for_user(admin).count() == 1


@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_the_admin_reads_or_sets_assignees(role: Role) -> None:
    w = world()
    _, user = ops(w, assign=False)
    client = login(role)
    got = client.get(f"{C}/customers/{w['acme'].pk}/assignees")
    wrote = put(client, w["acme"], [user.pk])
    if role == Role.ADMIN:
        assert got.status_code == 200
        assert wrote.status_code == 200
        assert [u["username"] for u in wrote.json()] == ["u-customer_ops"]
    else:
        assert got.status_code == 403
        assert wrote.status_code == 403
        assert not CustomerAssignment.objects.exists()


def test_an_unknown_customer_is_404_for_the_admin() -> None:
    world()
    admin = login(Role.ADMIN)
    assert admin.get(f"{C}/customers/99999/assignees").status_code == 404
    response = admin.put(
        f"{C}/customers/99999/assignees", {"userIds": []}, content_type="application/json"
    )
    assert response.status_code == 404


def test_only_active_customer_ops_accounts_can_be_assigned() -> None:
    w = world()
    login(Role.PLANNER)
    planner = User.objects.get(username="u-planner")
    admin = login(Role.ADMIN)
    refused = put(admin, w["acme"], [planner.pk])
    assert (refused.status_code, refused.json()["code"]) == (422, "customer.assignee_invalid")
    _, user = ops(w, assign=False)
    User.objects.filter(pk=user.pk).update(is_active=False)
    assert put(admin, w["acme"], [user.pk]).status_code == 422
    assert put(admin, w["acme"], [424242]).status_code == 422
    assert not CustomerAssignment.objects.exists()


def test_setting_replaces_the_set_and_the_manager_gains_and_loses_sight() -> None:
    w = world()
    client, user = ops(w, assign=False)
    admin = login(Role.ADMIN)
    assert put(admin, w["bravo"], [user.pk]).status_code == 200
    assert [c["name"] for c in client.get(C).json()] == ["Gold b"]
    assert put(admin, w["bravo"], []).status_code == 200
    assert client.get(C).json() == []


def test_a_change_is_audited_with_ids_only_as_the_last_write_and_no_change_is_not() -> None:
    w = world()
    _, user = ops(w, assign=False)
    admin = login(Role.ADMIN)
    put(admin, w["acme"], [user.pk])
    put(admin, w["acme"], [user.pk])  # unchanged: no second event
    events = AuditEvent.objects.filter(action=Action.CUSTOMER_ASSIGNED)
    assert events.count() == 1
    event = events.get()
    change = AuditChange.objects.get(event=event)
    assert (change.field, change.old_value, change.new_value) == ("assignees", "", str(user.pk))
    assert "u-customer_ops" not in json.dumps([event.entity_id, event.reason or ""])
    assert AuditEvent.objects.order_by("chain_seq").last() == event
