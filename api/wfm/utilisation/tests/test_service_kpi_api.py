"""Service metrics from imported tickets, beside staffing (KPI-01).

Synthetic tickets only. "Now" is Monday 25 May 2026 12:00 South African time, so May is the month
in progress and April is over.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role
from wfm.overtime.models import EmployeePay
from wfm.scheduling.models import RosterStatus, RosterWeek
from wfm.scheduling.tests.helpers import MON, assign, login, person, queue, standard_shifts
from wfm.servicedesk.models import ServicePool, WorkItem

pytestmark = pytest.mark.django_db

REPORT = "/api/v1/service-kpis/report"
MONTH = "2026-05-01"
NOW = datetime(2026, 5, 25, 10, 0, tzinfo=UTC)
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
ALLOWED = [Role.ADMIN, Role.PLANNER, Role.CUSTOMER_OPS]
PAY_ROLES = [Role.ADMIN, Role.PLANNER]


@pytest.fixture(autouse=True)
def _now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.utilisation.kpi_api.timezone.now", lambda: NOW)


def at(day: int, hour: int = 8, month: int = 5) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


def item(
    ref: str, pool: ServicePool, opened: datetime, closed: datetime | None = None, **kw: Any
) -> None:
    WorkItem.objects.create(ref=ref, pool=pool, opened_at=opened, closed_at=closed, **kw)


@pytest.fixture
def desk() -> ServicePool:
    pool = ServicePool.objects.create(name="Desk")
    item("A1", pool, at(4), at(5), first_contact_resolved=True, csat=5, nps=10, effort_minutes=60)
    item("A2", pool, at(4), at(6), first_contact_resolved=False, csat=2, nps=3, effort_minutes=30)
    item("A3", pool, at(4), at(5, 20), first_contact_resolved=True, effort_minutes=None)
    item("A4", pool, at(20, 8), effort_minutes=120)  # open since 20 May, 5 days before now
    item("OLD", pool, at(1, month=4), at(2, month=4), csat=1, nps=0)  # closed in April
    noc = ServicePool.objects.create(name="NOC")
    item("N1", noc, at(10), at(11), csat=4)
    return pool


def get(role: Role, month: str = MONTH) -> Any:
    return login(role).get(REPORT, {"month": month})


class TestRoles:
    @pytest.mark.parametrize("role", ALLOWED)
    def test_the_service_desk_roles_can_read(self, desk: ServicePool, role: Role) -> None:
        assert get(role).status_code == 200

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE])
    def test_everyone_else_is_refused(self, desk: ServicePool, role: Role) -> None:
        assert get(role).status_code == 403

    def test_signed_out_is_refused(self, desk: ServicePool) -> None:
        assert Client().get(REPORT, {"month": MONTH}).status_code == 401

    def test_a_month_starts_on_the_first(self, desk: ServicePool) -> None:
        assert get(Role.PLANNER, "2026-05-02").status_code == 422


class TestFigures:
    def figures(self, body: dict[str, Any], name: str) -> dict[str, Any]:
        return next(p for p in body["pools"] if p["pool"] == name)

    def test_the_pool_figures_are_counted_from_the_tickets_closed_in_the_month(
        self, desk: ServicePool
    ) -> None:
        body = get(Role.PLANNER).json()
        d = self.figures(body, "Desk")
        assert d["closed"] == 3  # the April ticket is not counted
        assert d["mttrH"] == round((24 + 48 + 36) / 3, 1)
        assert (d["fcrKnown"], d["fcrPct"]) == (3, 66.7)
        assert (d["csatCount"], d["csatAverage"], d["csatSatisfiedPct"]) == (2, 3.5, 50.0)
        assert (d["npsCount"], d["nps"]) == (2, 0.0)
        assert body["basis"] == "measured"

    def test_backlog_age_is_the_open_tickets_at_now(self, desk: ServicePool) -> None:
        d = self.figures(get(Role.PLANNER).json(), "Desk")
        assert d["backlogCount"] == 1
        assert d["backlogOldestAgeDays"] == 5.1  # 20 May 08:00 to 25 May 10:00 UTC

    def test_a_pool_with_no_survey_answers_says_so_rather_than_zero(
        self, desk: ServicePool
    ) -> None:
        noc = self.figures(get(Role.PLANNER).json(), "NOC")
        assert (noc["npsCount"], noc["nps"], noc["fcrPct"]) == (0, None, None)

    def test_the_total_row_covers_every_pool(self, desk: ServicePool) -> None:
        total = get(Role.PLANNER).json()["total"]
        assert total["closed"] == 4
        assert total["csatCount"] == 3

    def test_a_past_month_has_its_own_figures(self, desk: ServicePool) -> None:
        body = get(Role.PLANNER, "2026-04-01").json()
        d = self.figures(body, "Desk")
        assert (d["closed"], d["csatAverage"], d["nps"]) == (1, 1.0, -100.0)

    def test_staffing_is_the_service_desk_workload_of_the_next_seven_days(
        self, desk: ServicePool
    ) -> None:
        # Failure caught: a second sizing of the pool that disagrees with the Service desk screen.
        sized = login(Role.PLANNER).get(
            "/api/v1/service-desk/demand", {"as_of": "2026-05-25", "days": "7"}
        )
        want = {p["pool"]: p["requiredFte"] for p in sized.json()["pools"]}
        got = {p["pool"]: p["requiredFte"] for p in get(Role.PLANNER).json()["pools"]}
        assert got == want
        assert want["Desk"] is not None

    def test_an_empty_system_is_an_empty_report(self) -> None:
        body = get(Role.PLANNER).json()
        assert body["pools"] == []
        assert body["total"]["closed"] == 0


class TestCostPerTicket:
    def test_pay_roles_get_the_price_from_the_utilisation_cost_code(
        self, desk: ServicePool
    ) -> None:
        # Failure caught: a second, different price of a ticket than the one the cost report shows.
        who = person("E001")
        EmployeePay.objects.create(employee=who, monthly_salary=20000)
        assign(login(Role.PLANNER), queue(), who, MON, standard_shifts()["D1"])
        RosterWeek.objects.update(status=RosterStatus.PUBLISHED)
        costs = login(Role.ADMIN).get("/api/v1/utilisation/costs", {"month": MONTH}).json()
        priced = next(p for p in costs["pools"] if p["pool"] == "Desk")
        for role in PAY_ROLES:
            d = next(p for p in get(role).json()["pools"] if p["pool"] == "Desk")
            assert d["costPerTicketRands"] == priced["perTicketRands"]
            assert d["costPerTicketRands"] is not None
            assert d["ticketsPriced"] == 2
        assert Decimal(str(priced["perTicketRands"])) > 0

    def test_no_rand_figure_reaches_customer_operations(self, desk: ServicePool) -> None:
        EmployeePay.objects.create(employee=person("E001"), monthly_salary=98765)
        response = get(Role.CUSTOMER_OPS)
        body = response.json()
        assert body["costVisible"] is False
        assert all(p["costPerTicketRands"] is None for p in body["pools"])
        assert body["total"]["costPerTicketRands"] is None
        assert "98765" not in response.content.decode()
