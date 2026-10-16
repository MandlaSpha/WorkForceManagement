"""Auto-schedule a week (SCH-05): who may use it, that it never breaks a rule or trusts the client,
and that what it does is recorded."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any

import pytest

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.core.errors import ApiError
from wfm.people.models import (
    Availability,
    AvailabilityKind,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
)
from wfm.scheduling import autoschedule_services
from wfm.scheduling.models import ComplianceRuleVersion, RosterStatus, RosterWeek, ShiftAssignment

from .helpers import (
    FRI,
    MON,
    TUE,
    WED,
    assign,
    login,
    params,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)

pytestmark = pytest.mark.django_db

AUTO = "/api/v1/scheduling/roster/auto-schedule"
LONG_AGO = date(2026, 1, 1)


def need(
    day: date, first: int = 18, last: int = 34, people: int = 1
) -> dict[tuple[date, int], int | None]:
    """A requirement of `people` for half-hours first..last: by default 09:00 to 17:30."""
    return {(day, slot): people for slot in range(first, last + 1)}


def post(client: Any, path: str = "", *, q: Any = None, week: date = MON, **extra: Any) -> Any:
    body = {"queueId": (q or queue()).pk, "weekStart": str(week), **extra}
    return client.post(f"{AUTO}{path}", body, content_type="application/json")


def preview(client: Any, **kw: Any) -> Any:
    return post(client, "/preview", **kw)


def admin() -> User:
    return User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[0]


def approved_leave(employee: Any, day: date) -> None:
    LeaveRequest.objects.create(
        employee=employee,
        leave_type=LeaveType.objects.get(code="annual"),
        start_date=day,
        end_date=day,
        days=1,
        status=LeaveStatus.APPROVED,
        requested_by=admin(),
    )


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


class TestWhoMayUseIt:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_can_preview_and_apply(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        person()
        publish_forecast(queue(), need(MON))
        assert preview(login(role)).status_code == 200
        assert post(login(role)).status_code == 200

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_even_with_a_valid_request(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a lead or an agent filling the roster.
        person()
        publish_forecast(queue(), need(MON))
        assert preview(login(role)).status_code == 403
        assert post(login(role)).status_code == 403
        assert ShiftAssignment.objects.count() == 0
        assert not AuditEvent.objects.filter(action=Action.ROSTER_AUTO_SCHEDULED).exists()


class TestWhatItDoes:
    def test_a_preview_changes_nothing(self, shifts: dict[str, Any]) -> None:
        # Failure caught: a "preview" that quietly writes.
        person()
        publish_forecast(queue(), need(MON))
        before = AuditEvent.objects.count()
        body = preview(login()).json()
        assert body["status"] == "optimal"
        assert [p["day"] for p in body["placements"]] == [str(MON)]
        assert (body["shortBefore"], body["shortAfter"]) == (17, 0)
        assert ShiftAssignment.objects.count() == 0
        assert AuditEvent.objects.count() == before

    def test_applying_fills_the_gap_and_the_roster_shows_it(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        publish_forecast(queue(), need(MON))
        body = post(login()).json()
        assert (body["placed"], body["skipped"], body["shortAfter"]) == (1, {}, 0)
        assignment = ShiftAssignment.objects.get()
        assert (assignment.employee_id, assignment.day) == (e1.pk, MON)
        plan = login().get("/api/v1/scheduling/plan", params(queue(), MON)).json()
        assert plan["summary"]["gap"] == 0

    def test_it_does_not_add_people_nobody_needs(self, shifts: dict[str, Any]) -> None:
        for n in range(1, 5):
            person(f"E00{n}")
        publish_forecast(queue(), need(MON, people=2))
        post(login())
        assert ShiftAssignment.objects.count() == 2  # two needed, four available

    def test_a_second_run_adds_nothing(self, shifts: dict[str, Any]) -> None:
        person()
        person("E002")
        publish_forecast(queue(), need(MON))
        post(login())
        again = post(login()).json()
        assert again["placed"] == 0
        assert ShiftAssignment.objects.count() == 1

    def test_what_is_already_rostered_is_kept_and_counted(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        person("E002")
        publish_forecast(queue(), need(MON))
        assign(login(), queue(), e1, MON, shifts["D1"])
        body = post(login()).json()
        assert (body["placed"], body["kept"], body["shortAfter"]) == (0, 1, 0)
        assert ShiftAssignment.objects.get().employee_id == e1.pk

    def test_every_shift_goes_through_assign_and_the_run_is_summarised_last(
        self, shifts: dict[str, Any]
    ) -> None:
        person()
        publish_forecast(queue(), need(MON))
        post(login())
        events = list(AuditEvent.objects.order_by("id").values_list("action", flat=True))
        assert events.count(Action.ROSTER_ASSIGNED) == 1
        assert events[-1] == Action.ROSTER_AUTO_SCHEDULED
        summary = AuditEvent.objects.get(action=Action.ROSTER_AUTO_SCHEDULED)
        assert "1 placed" in (summary.changes.get().new_value or "")

    def test_no_name_reaches_the_audit_trail(self, shifts: dict[str, Any]) -> None:
        person(name="Zanele Testperson")
        publish_forecast(queue(), need(MON))
        post(login())
        text = " ".join(
            f"{e.reason} {e.entity_id} {e.entity_type}" for e in AuditEvent.objects.all()
        ) + " ".join(f"{c.old_value} {c.new_value}" for c in AuditChange.objects.all())
        assert "Zanele" not in text


class TestItNeverBreaksARule:
    def test_somebody_on_approved_leave_is_not_rostered(self, shifts: dict[str, Any]) -> None:
        # Failure caught: filling the roster with a person who is away.
        e1 = person()
        approved_leave(e1, MON)
        publish_forecast(queue(), need(MON))
        assert preview(login()).json()["placements"] == []

    def test_a_cannot_work_window_is_respected(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        Availability.objects.create(
            employee=e1,
            weekday=0,
            start_time=time(8, 0),
            end_time=time(12, 0),
            kind=AvailabilityKind.UNAVAILABLE,
            created_by=admin(),
        )
        publish_forecast(queue(), need(MON, 18, 23))  # 09:00 to 12:00
        assert preview(login()).json()["placements"] == []

    def test_somebody_not_skilled_on_the_queue_is_never_used(self, shifts: dict[str, Any]) -> None:
        person(queues=("Other",))
        publish_forecast(queue(), need(MON))
        assert preview(login()).json()["placements"] == []

    def test_somebody_not_yet_employed_is_not_used(self, shifts: dict[str, Any]) -> None:
        person(start_date=MON + timedelta(days=3))
        publish_forecast(queue(), need(MON))
        assert preview(login()).json()["placements"] == []

    def test_a_shift_on_another_queue_that_day_blocks_the_person(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person(queues=("QueueA", "QueueB"))
        assign(login(), queue("QueueB"), e1, MON, shifts["D1"])
        publish_forecast(queue(), need(MON))
        assert preview(login()).json()["placements"] == []

    def test_the_rest_rule_against_a_neighbouring_shift(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])  # ends 22:00
        publish_forecast(queue(), need(TUE, 14, 17))  # 07:00 to 09:00: only E1 covers it
        assert preview(login()).json()["placements"] == []

    def test_the_compliance_rules_in_force_are_the_ones_used(self, shifts: dict[str, Any]) -> None:
        # Failure caught: the optimiser ignoring the editable rules the roster enforces.
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])
        publish_forecast(queue(), need(TUE))  # 09:00 to 17:30: D1, 11 h after L1, fits exactly

        def tuesday_shifts() -> list[str]:
            found = preview(login()).json()["placements"]
            return [p["shift"] for p in found if p["day"] == str(TUE)]

        assert "D1" in tuesday_shifts()
        ComplianceRuleVersion.objects.create(
            effective_from=LONG_AGO, min_rest_hours=12, max_consecutive_days=6
        )
        assert "D1" not in tuesday_shifts()  # 11 hours is no longer enough

    def test_contract_hours_are_a_limit(self, shifts: dict[str, Any]) -> None:
        person(hours=16)
        publish_forecast(queue(), {**need(MON), **need(TUE), **need(WED)})
        assert len(preview(login()).json()["placements"]) == 2

    def test_whatever_it_applies_the_roster_would_also_accept(self, shifts: dict[str, Any]) -> None:
        # Failure caught: the optimiser's idea of a rule drifting from the roster's. Applying goes
        # through assign, so a disagreement shows as a skip; there must be none.
        for n in range(1, 4):
            person(f"E00{n}")
        publish_forecast(queue(), {**need(MON, people=2), **need(TUE, people=2), **need(FRI)})
        body = post(login()).json()
        assert body["skipped"] == {}
        assert body["placed"] > 0


class TestItNeverTrustsTheClient:
    def test_a_forged_list_of_placements_is_ignored(self, shifts: dict[str, Any]) -> None:
        # Failure caught: the apply endpoint taking its shifts from the request.
        e1 = person()
        approved_leave(e1, MON)
        publish_forecast(queue(), need(MON))
        post(
            login(),
            placements=[{"employeeId": e1.pk, "day": str(MON), "shift": "D1"}],
        )
        assert ShiftAssignment.objects.count() == 0

    def test_a_refusal_while_applying_is_skipped_and_counted_not_forced(
        self, shifts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        person()
        publish_forecast(queue(), need(MON))

        def refuse(**kwargs: Any) -> None:
            raise ApiError(422, "roster.over_hours", "Refused", "no")

        monkeypatch.setattr(autoschedule_services, "assign", refuse)
        body = post(login()).json()
        assert (body["placed"], body["skipped"]) == (0, {"roster.over_hours": 1})
        assert ShiftAssignment.objects.count() == 0


class TestRefusals:
    def test_a_queue_that_does_not_exist_is_a_404(self, shifts: dict[str, Any]) -> None:
        assert post(login(), q=type("Q", (), {"pk": 999999})()).status_code == 404

    def test_a_week_must_start_on_a_monday(self, shifts: dict[str, Any]) -> None:
        response = post(login(), week=TUE)
        assert response.status_code == 422
        assert response.json()["code"] == "roster.not_a_monday"

    def test_without_a_published_forecast_it_says_so(self, shifts: dict[str, Any]) -> None:
        person()
        queue()
        response = post(login())
        assert response.status_code == 409
        assert response.json()["code"] == "autoschedule.no_forecast"
        assert ShiftAssignment.objects.count() == 0

    def test_a_published_week_is_left_alone(self, shifts: dict[str, Any]) -> None:
        person()
        publish_forecast(queue(), need(MON))
        RosterWeek.objects.create(queue=queue(), week_start=MON, status=RosterStatus.PUBLISHED)
        response = post(login())
        assert response.status_code == 409
        assert response.json()["code"] == "autoschedule.published"
        assert ShiftAssignment.objects.count() == 0

    def test_an_empty_shift_library_says_so(self) -> None:
        person()
        publish_forecast(queue(), need(MON))
        assert post(login()).json()["code"] == "autoschedule.no_shifts"
