"""A small world for the Copilot tests, with CANARY values in data the asker must not see.

Today is frozen at Wednesday 20 May 2026 (Johannesburg). Two teams:

- team one: lead `u-lead` (Lena Leadone) manages the agent `u-agent` (Alice Ownerson)
- team two: lead `u-lead2` (Mpho Leadtwo) manages the agent `Zandile Qwertyuiop` (the canary)

On Tuesday 26 May the queue needs 3 people from 09:00 to 15:00. Alice (D1 09:00-17:30) and Zandile
(L1 13:00-22:00) are rostered, so 09:00-13:00 is 2 short (8 half-hours, 16 people-half-hours) and
13:00-15:00 is 1 short (4 half-hours, 4): a gap of 20 people-half-hours over 12 half-hours.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import AuditChange, AuditEvent
from wfm.contracts.models import Contract, ContractQueue, Customer
from wfm.overtime.models import EmployeePay
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType, SwapRequest, SwapStatus
from wfm.scheduling.tests.helpers import (
    MON,
    TUE,
    assign,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)

ASK = "/api/v1/copilot/ask"
TODAY = date(2026, 5, 20)
REFUSAL = "I can't share that for your role."

# Values the asker must never see. Each is distinct and would be easy to spot in any output.
C_NAME = "Zandile Qwertyuiop"  # an agent on the OTHER team
C_LEAD2 = "Mpho Leadtwo"  # the other team's lead
C_QUEUE = "QueueSecretOmega"  # a queue only a planner may see
C_CUSTOMER = "Vantage Canaryco"
C_CONTRACT = "Canary Contract Platinum"
C_SALARY = "98765.43"
C_REMARK = "CANARYREMARK-7731"
CANARIES = (C_NAME, "Qwertyuiop", C_LEAD2, "Leadtwo", C_CUSTOMER, C_CONTRACT, C_SALARY, C_REMARK)


def as_user(username: str, role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=username, defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


USERNAMES = {
    Role.AGENT: "u-agent",
    Role.LEAD: "u-lead",
    Role.PLANNER: "u-planner",
    Role.ADMIN: "u-admin",
    Role.EXECUTIVE: "u-executive",
    Role.CUSTOMER_OPS: "u-customer_ops",
}


def client_for(role: Role) -> Client:
    return as_user(USERNAMES[role], role)


def ask(client: Client, question: str) -> Any:
    return client.post(ASK, {"question": question}, content_type="application/json")


def world() -> dict[str, Any]:
    """Build the data. Called once per test through the `seeded` fixture."""
    shifts = standard_shifts()
    client_for(Role.AGENT)
    client_for(Role.LEAD)
    agent_user = User.objects.get(username="u-agent")
    lead_user = User.objects.get(username="u-lead")
    lead2_user = User.objects.create(username="u-lead2", role=Role.LEAD)
    for role in (Role.PLANNER, Role.ADMIN, Role.EXECUTIVE, Role.CUSTOMER_OPS):
        client_for(role)

    q = queue("QueueAlpha")
    lead = person("L001", queues=(), name="Lena Leadone", user=lead_user)
    lead2 = person("L002", queues=(), name=C_LEAD2, user=lead2_user)
    alice = person(
        "E001", queues=("QueueAlpha",), name="Alice Ownerson", user=agent_user, manager=lead
    )
    zandile = person("E002", queues=("QueueAlpha",), name=C_NAME, manager=lead2)
    third = person("E003", queues=("QueueAlpha",), name="Thomas Thirdwheel", manager=lead)
    secret_q = queue(C_QUEUE)

    planner = client_for(Role.PLANNER)
    for who, day, code in ((alice, TUE, "D1"), (zandile, TUE, "L1"), (alice, MON, "D1")):
        done = assign(planner, q, who, day, shifts[code])
        assert done.status_code == 200, done.content
    publish_forecast(q, {(TUE, s): (3 if 18 <= s < 30 else 0) for s in range(48)})

    annual = LeaveType.objects.get(code="annual")
    LeaveRequest.objects.create(  # Alice: 2 approved days of annual leave this year
        employee=alice,
        leave_type=annual,
        start_date=date(2026, 3, 2),
        end_date=date(2026, 3, 3),
        days=2,
        days_by_year={"2026": 2},
        status=LeaveStatus.APPROVED,
        requested_by=agent_user,
    )
    LeaveRequest.objects.create(  # Alice: one pending request (own team)
        employee=alice,
        leave_type=annual,
        start_date=date(2026, 7, 6),
        end_date=date(2026, 7, 7),
        days=2,
        days_by_year={"2026": 2},
        status=LeaveStatus.PENDING,
        requested_by=agent_user,
    )
    LeaveRequest.objects.create(  # Zandile: pending, other team: must stay out of u-lead's view
        employee=zandile,
        leave_type=annual,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 4),
        days=2,
        days_by_year={"2026": 2},
        status=LeaveStatus.PENDING,
        requested_by=lead2_user,
    )
    LeaveRequest.objects.create(  # Zandile: away yesterday (approved): who-was-absent canary
        employee=zandile,
        leave_type=annual,
        start_date=date(2026, 5, 19),
        end_date=date(2026, 5, 19),
        days=1,
        days_by_year={"2026": 1},
        status=LeaveStatus.APPROVED,
        requested_by=lead2_user,
    )
    LeaveRequest.objects.create(  # Thomas: approved leave on Tuesday 26 May: counts in why_short
        employee=third,
        leave_type=annual,
        start_date=TUE,
        end_date=TUE,
        days=1,
        days_by_year={"2026": 1},
        status=LeaveStatus.APPROVED,
        requested_by=lead_user,
    )
    SwapRequest.objects.create(
        queue=q,
        from_employee=alice,
        from_day=MON,
        from_template=shifts["D1"],
        status=SwapStatus.OPEN,
        requested_by=agent_user,
    )
    SwapRequest.objects.create(  # the other team's open swap: canary
        queue=q,
        from_employee=zandile,
        from_day=TUE,
        from_template=shifts["L1"],
        status=SwapStatus.OPEN,
        requested_by=lead2_user,
    )
    EmployeePay.objects.create(employee=zandile, monthly_salary=Decimal(C_SALARY))
    customer = Customer.objects.create(name=C_CUSTOMER)
    contract = Contract.objects.create(
        customer=customer, name=C_CONTRACT, sl_target_pct=80, sl_threshold_s=20
    )
    ContractQueue.objects.create(contract=contract, queue=secret_q)
    return {"q": q, "alice": alice, "zandile": zandile, "lead": lead, "shifts": shifts}


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.copilot.adapter.sast_today", lambda: TODAY)
    monkeypatch.setattr("wfm.people.services.timezone.localdate", lambda: TODAY)


@pytest.fixture
def seeded() -> dict[str, Any]:
    return world()


def audit_text(user_id: int, *, skip_reason: bool = True) -> str:
    """Everything the audit trail holds about this user's Copilot questions, as one string. The
    reason (the question as typed) is left out by default: the asker typed it themselves."""
    rows = []
    for e in AuditEvent.objects.filter(actor_user_id=user_id):
        row = {
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "outcome": e.outcome,
            "role": e.actor_role,
        }
        if not skip_reason:
            row["reason"] = e.reason
        rows.append(row)
    for c in AuditChange.objects.filter(event__actor_user_id=user_id):
        rows.append({"f": c.field, "o": c.old_value, "n": c.new_value, "t": c.entity_type})
    return json.dumps(rows, default=str)
