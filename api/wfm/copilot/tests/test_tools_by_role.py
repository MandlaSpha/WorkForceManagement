"""AI-03: a fixed list of read tools; every tool x every role. Allowed roles get data, every other
role cannot call it (the same error whether the tool exists or not)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pytest

from wfm.accounts.models import Role, User
from wfm.copilot import tools

from .helpers import REFUSAL, USERNAMES, ask, client_for

pytestmark = pytest.mark.django_db

ALL_TOOLS = sorted(tools.REGISTRY)
EXPECTED_ROLES = {
    "coverage_gaps": {Role.PLANNER, Role.ADMIN},
    "why_short": {Role.PLANNER, Role.ADMIN},
    "forecast_status": {Role.PLANNER, Role.ADMIN},
    "team_pending_leave": {Role.LEAD},
    "team_on_shift": {Role.LEAD},
    "team_open_swaps": {Role.LEAD},
    "my_schedule": {Role.AGENT},
    "my_leave_balance": {Role.AGENT},
    "my_open_swaps": {Role.AGENT},
    "coverage_summary": {Role.EXECUTIVE, Role.PLANNER, Role.ADMIN},
    "absence_rate": {Role.EXECUTIVE, Role.PLANNER, Role.ADMIN},
    "my_contracts_capacity": {Role.CUSTOMER_OPS},
}


def user_of(role: Role) -> User:
    client_for(role)
    return User.objects.get(username=USERNAMES[role])


def test_the_registry_is_exactly_the_agreed_list() -> None:
    # Failure caught: a tool added (or a role widened) without a decision and without a test row.
    assert set(tools.REGISTRY) == set(EXPECTED_ROLES)
    for name, roles in EXPECTED_ROLES.items():
        assert set(tools.REGISTRY[name].roles) == roles, name


def test_no_tool_takes_a_person_or_record_id_and_none_is_about_pay() -> None:
    # Failure caught: a tool that lets the question choose whose data to read, or a money tool.
    for tool in tools.REGISTRY.values():
        names = {p.name for p in tool.params}
        assert not names & {"user", "user_id", "employee", "employee_id", "id", "role"}, tool.name
        assert not any(w in tool.name for w in ("pay", "salary", "overtime", "rate_of")), tool.name


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("name", ALL_TOOLS)
def test_every_tool_by_every_role(name: str, role: Role, seeded: dict[str, Any]) -> None:
    user = user_of(role)
    params: dict[str, Any] = (
        {"day": date(2026, 5, 26)}
        if any(p.name == "day" for p in tools.REGISTRY[name].params)
        else {}
    )
    if role in EXPECTED_ROLES[name]:
        result = tools.call_tool(user, name, params)
        assert result.tool == name
        assert isinstance(result.row_count, int)
        json.dumps(result.facts)  # plain JSON-safe data
    else:
        with pytest.raises(tools.ToolNotAllowedError):
            tools.call_tool(user, name, params)


def test_an_unknown_tool_and_a_forbidden_tool_raise_the_same_error(seeded: dict[str, Any]) -> None:
    user = user_of(Role.AGENT)
    with pytest.raises(tools.ToolNotAllowedError) as unknown:
        tools.call_tool(user, "no_such_tool", {})
    with pytest.raises(tools.ToolNotAllowedError) as forbidden:
        tools.call_tool(user, "coverage_gaps", {})
    assert type(unknown.value) is type(forbidden.value)


def test_a_tool_refuses_a_parameter_it_did_not_declare(seeded: dict[str, Any]) -> None:
    # Failure caught: a forged employee id slipped in as an extra argument.
    with pytest.raises(tools.ToolParamsError):
        tools.call_tool(user_of(Role.AGENT), "my_schedule", {"employee_id": 1})
    with pytest.raises(tools.ToolParamsError):
        tools.call_tool(user_of(Role.AGENT), "my_leave_balance", {"user_id": 99})


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("name", ALL_TOOLS)
def test_a_role_is_answered_by_its_tool_through_the_api_and_never_by_anothers(
    name: str, role: Role, seeded: dict[str, Any]
) -> None:
    tool = tools.REGISTRY[name]
    response = ask(client_for(role), tool.example)
    assert response.status_code == 200
    body = response.json()
    used = {s["tool"] for s in body["sources"]}
    if role in EXPECTED_ROLES[name]:
        # The example may be answered by a neighbouring tool the role also has (a planner's
        # "coverage" questions), but it must be answered and must not be refused.
        assert not body["refused"], (name, role, body["answer"])
        assert used, (name, role)
    else:
        assert name not in used, f"{role.value} was answered from {name}"
        if not used:
            assert body["refused"] or body["answer"].startswith("I can't answer that yet")
            if body["refused"]:
                assert body["answer"] == REFUSAL


def test_the_day_defaults_to_today(seeded: dict[str, Any]) -> None:
    from django.utils import timezone

    result = tools.call_tool(user_of(Role.LEAD), "team_on_shift", {})
    assert result.facts["day"] == timezone.localdate().isoformat()


def test_customer_ops_count_only_their_assigned_customers_contracts(
    seeded: dict[str, Any],
) -> None:
    # Failure caught: a customer operations manager counting a contract of a customer nobody
    # assigned to them (the canary contract exists, held by another customer).
    from wfm.contracts.models import Contract, Customer, CustomerAssignment

    user = user_of(Role.CUSTOMER_OPS)
    assert tools.call_tool(user, "my_contracts_capacity", {}).facts == {"contracts": 0, "active": 0}
    own = Customer.objects.create(name="Own Customerco")
    Contract.objects.create(customer=own, name="Own Contract", sl_target_pct=80, sl_threshold_s=20)
    CustomerAssignment.objects.create(customer=own, user=user)
    facts = tools.call_tool(user, "my_contracts_capacity", {}).facts
    assert facts == {"contracts": 1, "active": 1}
