"""Cross-queue flexing (SCH-09): who may use it, that it only lends what a donor can spare, and
that applying one cannot be forced or forged."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditEvent
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftAssignment

from .helpers import MON, assign, login, params, person, publish_forecast, queue, standard_shifts

pytestmark = pytest.mark.django_db

FLEX = "/api/v1/scheduling/flex"


def need(
    day: date, people: int, first: int = 18, last: int = 34
) -> dict[tuple[date, int], int | None]:
    return {(day, slot): people for slot in range(first, last + 1)}


def listing(client: Any, q: Any = None) -> Any:
    return client.get(FLEX, params(q or queue("QueueA"), MON))


def apply_body(employee: Any, q: Any = None) -> dict[str, Any]:
    return {
        "queueId": (q or queue("QueueA")).pk,
        "weekStart": str(MON),
        "employeeId": employee.pk,
        "day": str(MON),
    }


def apply(client: Any, body: dict[str, Any]) -> Any:
    return client.post(f"{FLEX}/apply", body, content_type="application/json")


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


def lender(shifts: dict[str, Any], donor_needs: int = 0) -> Any:
    """A person skilled on A and B, rostered on B, with A short and B needing `donor_needs`."""
    a, b = queue("QueueA"), queue("QueueB")
    flexer = person("F001", queues=("QueueA", "QueueB"))
    publish_forecast(a, need(MON, 1))
    publish_forecast(b, need(MON, donor_needs))
    assert assign(login(Role.PLANNER), b, flexer, MON, shifts["D1"]).status_code == 200
    return flexer


class TestWhoMayUseIt:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_can_list_and_apply(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        flexer = lender(shifts)
        assert listing(login(role)).status_code == 200
        assert apply(login(role), apply_body(flexer)).status_code == 200

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_even_with_a_valid_request(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a lead or an agent moving people between queues by a back door.
        flexer = lender(shifts)
        assert listing(login(role)).status_code == 403
        assert apply(login(role), apply_body(flexer)).status_code == 403
        assert ShiftAssignment.objects.get().roster_week.queue.name == "QueueB"


class TestWhatItOffers:
    def test_a_spare_person_is_offered_with_a_sentence(self, shifts: dict[str, Any]) -> None:
        lender(shifts)
        (item,) = listing(login()).json()
        assert item["fromQueue"] == "QueueB"
        assert item["shift"] == "D1"
        assert item["closes"] > 0
        assert "Borrow Person F001" in item["text"]

    def test_nobody_is_offered_when_the_donor_would_be_left_short(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: fixing one queue by breaking another.
        lender(shifts, donor_needs=1)
        assert listing(login()).json() == []

    def test_a_person_not_skilled_on_the_short_queue_is_not_offered(
        self, shifts: dict[str, Any]
    ) -> None:
        b = queue("QueueB")
        queue("QueueA")
        only_b = person("F002", queues=("QueueB",))
        publish_forecast(queue("QueueA"), need(MON, 1))
        publish_forecast(b, need(MON, 0))
        assign(login(), b, only_b, MON, shifts["D1"])
        assert listing(login()).json() == []

    def test_a_published_donor_week_cannot_lend(self, shifts: dict[str, Any]) -> None:
        lender(shifts)
        RosterWeek.objects.filter(queue__name="QueueB").update(status=RosterStatus.PUBLISHED)
        assert listing(login()).json() == []


class TestApplying:
    def test_moves_the_shift_and_audits_it(self, shifts: dict[str, Any]) -> None:
        flexer = lender(shifts)
        response = apply(login(), apply_body(flexer))
        assert response.status_code == 200
        assert response.json()["closes"] > 0
        moved = ShiftAssignment.objects.get(employee=flexer)
        assert moved.roster_week.queue.name == "QueueA"
        assert moved.template == shifts["D1"]
        assert AuditEvent.objects.filter(action=Action.ROSTER_ASSIGNED).exists()
        assert listing(login()).json() == []  # the gap is closed; nothing more to borrow

    def test_a_suggestion_that_is_not_on_the_list_is_refused_as_stale(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: forging a body for someone the list never offered.
        flexer = lender(shifts, donor_needs=1)
        response = apply(login(), apply_body(flexer))
        assert (response.status_code, response.json()["code"]) == (409, "flex.stale")
        assert ShiftAssignment.objects.get().roster_week.queue.name == "QueueB"

    def test_applying_twice_is_refused_the_second_time(self, shifts: dict[str, Any]) -> None:
        flexer = lender(shifts)
        assert apply(login(), apply_body(flexer)).status_code == 200
        assert apply(login(), apply_body(flexer)).status_code == 409

    def test_a_published_borrowing_week_refuses_the_move(self, shifts: dict[str, Any]) -> None:
        flexer = lender(shifts)
        body = apply_body(flexer)
        RosterWeek.objects.create(
            queue=queue("QueueA"), week_start=MON, status=RosterStatus.PUBLISHED
        )
        response = apply(login(), body)
        assert response.status_code in (409, 422)
        assert ShiftAssignment.objects.get().roster_week.queue.name == "QueueB"
