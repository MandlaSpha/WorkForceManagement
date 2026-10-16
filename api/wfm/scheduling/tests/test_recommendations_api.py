"""Recommendations (REC-01): who may use them, that they never suggest what the roster would
refuse, and that applying one cannot be forced, replayed or forged."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftAssignment

from .helpers import (
    MON,
    TUE,
    assign,
    login,
    params,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)

pytestmark = pytest.mark.django_db

RECS = "/api/v1/scheduling/recommendations"
AUTO = "/api/v1/scheduling/roster/auto-schedule"


def need(
    day: date, first: int = 18, last: int = 34, people: int = 1
) -> dict[tuple[date, int], int | None]:
    return {(day, slot): people for slot in range(first, last + 1)}


def listing(client: Any, week: date = MON, q: Any = None) -> Any:
    return client.get(RECS, params(q or queue(), week))


def apply_body(
    employee: Any, day: date, shift: Any, week: date = MON, q: Any = None
) -> dict[str, Any]:
    return {
        "queueId": (q or queue()).pk,
        "weekStart": str(week),
        "employeeId": employee.pk,
        "day": str(day),
        "templateId": shift.pk,
    }


def apply(client: Any, body: dict[str, Any]) -> Any:
    return client.post(f"{RECS}/apply", body, content_type="application/json")


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


def admin() -> User:
    return User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[0]


class TestWhoMayUseThem:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_can_list_and_apply(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        publish_forecast(queue(), need(MON))
        assert listing(login(role)).status_code == 200
        assert apply(login(role), apply_body(e1, MON, shifts["D1"])).status_code == 200

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_even_with_a_valid_request(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a lead or an agent rostering through the back door of a suggestion.
        e1 = person()
        publish_forecast(queue(), need(MON))
        assert listing(login(role)).status_code == 403
        assert apply(login(role), apply_body(e1, MON, shifts["D1"])).status_code == 403
        assert ShiftAssignment.objects.count() == 0

    def test_a_switched_off_optimisation_feature_refuses_recommendations_and_auto_schedule(
        self, settings: Any, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a customer who has not paid for optimisation still getting it.
        person()
        publish_forecast(queue(), need(MON))
        settings.WFM_FEATURES = "telephony,forecasting,scheduling"
        admin_client = login(Role.ADMIN)
        for response in (
            listing(admin_client),
            admin_client.post(
                f"{AUTO}/preview",
                {"queueId": queue().pk, "weekStart": str(MON)},
                content_type="application/json",
            ),
        ):
            assert (response.status_code, response.json()["code"]) == (403, "feature.disabled")


class TestWhatTheyAre:
    def test_a_gap_with_a_free_person_gives_a_concrete_sentence(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person(name="Pat Example")
        publish_forecast(queue(), need(MON))
        body = listing(login()).json()
        top = body[0]
        assert (top["kind"], top["employeeId"], top["day"], top["shift"]) == (
            "add",
            e1.pk,
            str(MON),
            "D1",
        )
        assert (top["closes"], top["addsOver"]) == (17, 0)
        assert top["text"] == "Add Pat Example to D1 on Mon 25 May: closes 17 half-hours short."

    def test_listing_changes_nothing(self, shifts: dict[str, Any]) -> None:
        person()
        publish_forecast(queue(), need(MON))
        before = AuditEvent.objects.count()
        listing(login())
        assert ShiftAssignment.objects.count() == 0
        assert AuditEvent.objects.count() == before

    def test_no_gap_no_suggestions(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        person("E002")
        publish_forecast(queue(), need(MON))
        assign(login(), queue(), e1, MON, shifts["D1"])
        assert listing(login()).json() == []

    def test_a_shift_on_the_queue_can_be_changed_to_close_more(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["E1"])  # 07:00 to 15:30
        publish_forecast(queue(), need(MON))  # the demand runs to 17:30
        change = next(r for r in listing(login()).json() if r["kind"] == "change")
        assert (change["employeeId"], change["replaces"], change["shift"]) == (e1.pk, "E1", "D1")
        assert change["closes"] == 4

    def test_it_never_suggests_somebody_the_roster_would_refuse(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: suggesting somebody on leave, not skilled, or on another queue that day.
        on_leave = person("E001")
        LeaveRequest.objects.create(
            employee=on_leave,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=MON,
            end_date=MON,
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=admin(),
        )
        person("E002", queues=("Other",))
        elsewhere = person("E003", queues=("QueueA", "QueueB"))
        assign(login(), queue("QueueB"), elsewhere, MON, shifts["D1"])
        publish_forecast(queue(), need(MON))
        assert listing(login()).json() == []

    def test_the_rest_rule_is_respected(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])  # ends 22:00
        publish_forecast(queue(), need(TUE, 14, 17))  # 07:00 to 09:00: only E1 would cover it
        assert [r for r in listing(login()).json() if r["shift"] == "E1"] == []


class TestApplying:
    def test_applying_closes_the_gap_by_what_it_said_and_is_audited(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        publish_forecast(queue(), need(MON))
        plan_url = "/api/v1/scheduling/plan"
        gap_before = login().get(plan_url, params(queue(), MON)).json()["summary"]["gap"]
        top = listing(login()).json()[0]
        response = apply(login(), apply_body(e1, MON, shifts["D1"]))
        assert response.json() == {"applied": True, "closes": top["closes"]}
        gap_after = login().get(plan_url, params(queue(), MON)).json()["summary"]["gap"]
        assert gap_before - gap_after == top["closes"]
        event = AuditEvent.objects.get(action=Action.ROSTER_ASSIGNED)
        assert event.actor_role == Role.PLANNER

    def test_applying_a_change_swaps_the_shift(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["E1"])
        publish_forecast(queue(), need(MON))
        assert apply(login(), apply_body(e1, MON, shifts["D1"])).status_code == 200
        assert ShiftAssignment.objects.get().template_id == shifts["D1"].pk

    def test_applying_the_same_suggestion_twice_is_refused_as_stale(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a double click adding the shift twice, or a replay of an old list.
        e1 = person()
        publish_forecast(queue(), need(MON))
        body = apply_body(e1, MON, shifts["D1"])
        assert apply(login(), body).status_code == 200
        again = apply(login(), body)
        assert (again.status_code, again.json()["code"]) == (409, "recommendation.stale")
        assert ShiftAssignment.objects.count() == 1

    def test_a_forged_suggestion_is_refused_and_writes_nothing(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: the apply endpoint taking its authority from the request: somebody on
        # leave, or a shift that was never suggested.
        e1 = person()
        LeaveRequest.objects.create(
            employee=e1,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=MON,
            end_date=MON,
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=admin(),
        )
        publish_forecast(queue(), need(MON))
        forged = apply(login(), apply_body(e1, MON, shifts["D1"]))
        assert (forged.status_code, forged.json()["code"]) == (409, "recommendation.stale")
        never_suggested = apply(login(), apply_body(e1, TUE, shifts["D1"]))
        assert never_suggested.json()["code"] == "recommendation.stale"
        assert ShiftAssignment.objects.count() == 0

    def test_a_refusal_after_the_list_was_read_is_stale_not_forced(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        publish_forecast(queue(), need(MON))
        listing(login())
        RosterWeek.objects.create(queue=queue(), week_start=MON, status=RosterStatus.PUBLISHED)
        response = apply(login(), apply_body(e1, MON, shifts["D1"]))
        assert response.status_code == 409
        assert ShiftAssignment.objects.count() == 0


class TestRefusals:
    def test_a_queue_that_does_not_exist_is_a_404(self, shifts: dict[str, Any]) -> None:
        response = login().get(RECS, {"queue_id": "999999", "week_start": MON.isoformat()})
        assert response.status_code == 404

    def test_a_week_must_start_on_a_monday(self, shifts: dict[str, Any]) -> None:
        response = listing(login(), TUE)
        assert (response.status_code, response.json()["code"]) == (422, "roster.not_a_monday")

    def test_without_a_published_forecast_it_says_so(self, shifts: dict[str, Any]) -> None:
        person()
        response = listing(login())
        assert (response.status_code, response.json()["code"]) == (409, "autoschedule.no_forecast")
