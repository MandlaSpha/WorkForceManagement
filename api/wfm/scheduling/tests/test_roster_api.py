"""Building the roster: every rule, and every way round it, on a real PostgreSQL."""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any

import pytest
from django.db import IntegrityError, transaction

from wfm.accounts.models import Role
from wfm.audit import services as audit_services
from wfm.audit.models import Action, AuditChange, AuditEvent, Outcome
from wfm.scheduling import roster_services
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftAssignment

from .helpers import (
    FRI,
    MON,
    NEXT_MON,
    ROSTER,
    SAT,
    SUN,
    THU,
    TUE,
    WED,
    assign,
    login,
    params,
    person,
    queue,
    standard_shifts,
)

pytestmark = pytest.mark.django_db


def refused(response: Any, code: str) -> None:
    assert response.status_code in (409, 422), response.content
    assert response.json()["code"] == code


def stored() -> int:
    return ShiftAssignment.objects.count()


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


def grid(day: date = MON, q: str = "QueueA", role: Role = Role.PLANNER) -> dict[str, Any]:
    response = login(role).get(ROSTER, params(queue(q), day))
    assert response.status_code == 200, response.content
    return response.json()  # type: ignore[no-any-return]


class TestAssigning:
    def test_puts_a_person_on_a_shift_in_a_draft_week(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        response = assign(login(), queue(), e1, MON, shifts["D1"])
        assert response.status_code == 200
        assert response.json() == {
            "employeeId": e1.pk,
            "day": "2026-05-25",
            "shiftId": shifts["D1"].pk,
            "code": "D1",
            "weekStatus": "draft",
        }

    def test_the_grid_shows_the_shift_and_how_many_are_on(self, shifts: dict[str, Any]) -> None:
        a, b = person("E001"), person("E002")
        assign(login(), queue(), a, MON, shifts["D1"])
        assign(login(), queue(), b, MON, shifts["E1"])
        assign(login(), queue(), b, TUE, shifts["E1"])

        body = grid()
        rows = {r["empNo"]: r for r in body["rows"]}
        assert [c["code"] for c in rows["E002"]["cells"]] == ["E1", "E1"]
        assert rows["E002"]["daysWorked"] == 2
        assert rows["E002"]["paidMinutes"] == 960
        assert body["onCounts"]["2026-05-25"] == 2  # "2 on" on Monday
        assert body["onCounts"]["2026-05-26"] == 1

    def test_the_grid_lists_the_people_skilled_on_the_queue_and_nobody_else(
        self, shifts: dict[str, Any]
    ) -> None:
        person("E001", queues=("QueueA",))
        person("E002", queues=("QueueB",))
        assert [r["empNo"] for r in grid()["rows"]] == ["E001"]

    def test_a_second_shift_on_the_same_day_replaces_the_first(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        response = assign(login(), queue(), e1, MON, shifts["E1"])
        assert response.json()["code"] == "E1"
        assert stored() == 1  # replaced, not added

    def test_clearing_removes_the_shift(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        response = assign(login(), queue(), e1, MON, None)
        assert (response.status_code, response.json()["code"]) == (200, None)
        assert stored() == 0

    def test_clearing_nothing_is_harmless_and_leaves_no_audit_noise(self) -> None:
        e1 = person()
        assert assign(login(), queue(), e1, MON, None).status_code == 200
        assert not AuditEvent.objects.filter(action=Action.ROSTER_CLEARED).exists()

    def test_unknown_people_shifts_and_queues_are_404s(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        planner = login()
        body = {"queueId": queue().pk, "employeeId": e1.pk, "day": str(MON)}
        assert (
            planner.put(
                "/api/v1/scheduling/roster/assignments",
                {**body, "employeeId": 99999, "templateId": shifts["D1"].pk},
                content_type="application/json",
            ).status_code
            == 404
        )
        assert (
            planner.put(
                "/api/v1/scheduling/roster/assignments",
                {**body, "templateId": 99999},
                content_type="application/json",
            ).status_code
            == 404
        )
        assert (
            planner.put(
                "/api/v1/scheduling/roster/assignments",
                {**body, "queueId": 99999, "templateId": shifts["D1"].pk},
                content_type="application/json",
            ).status_code
            == 404
        )


class TestTheElevenHourRest:
    def test_a_late_shift_then_an_early_one_is_refused(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])  # ends 22:00
        response = assign(login(), queue(), e1, TUE, shifts["E1"])  # starts 07:00: only 9 hours
        refused(response, "roster.rest_period")
        assert stored() == 1

    def test_exactly_eleven_hours_is_allowed(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])  # ends 22:00
        assert assign(login(), queue(), e1, TUE, shifts["D1"]).status_code == 200  # 09:00

    def test_the_rule_works_whichever_shift_is_added_first(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, TUE, shifts["E1"])
        refused(assign(login(), queue(), e1, MON, shifts["L1"]), "roster.rest_period")

    def test_a_night_shift_leaves_no_room_for_a_morning_one(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["N1"])  # 22:00 Monday to 06:00 Tuesday
        refused(assign(login(), queue(), e1, TUE, shifts["D1"]), "roster.rest_period")
        refused(assign(login(), queue(), e1, TUE, shifts["L1"]), "roster.rest_period")
        assert assign(login(), queue(), e1, WED, shifts["D1"]).status_code == 200

    def test_it_holds_across_the_week_boundary(self, shifts: dict[str, Any]) -> None:
        # Sunday night to Monday morning sit in different roster weeks; the rule must still see it.
        e1 = person()
        assign(login(), queue(), e1, SUN, shifts["L1"])
        refused(assign(login(), queue(), e1, NEXT_MON, shifts["E1"]), "roster.rest_period")
        assert stored() == 1  # only Sunday's shift exists; the refused Monday left no trace

    def test_changing_a_shift_is_checked_against_the_neighbours_not_itself(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])
        assign(login(), queue(), e1, TUE, shifts["D1"])
        # Tuesday E1 would start 9h after Monday's L1 ends: refused, and Tuesday is left as it was.
        refused(assign(login(), queue(), e1, TUE, shifts["E1"]), "roster.rest_period")
        assert ShiftAssignment.objects.get(day=TUE).template.code == "D1"


class TestDaysInARowAndContractHours:
    def test_a_seventh_day_in_a_row_is_refused(self, shifts: dict[str, Any]) -> None:
        e1 = person(hours=60)
        for day in (MON, TUE, WED, THU, FRI, SAT):
            assert assign(login(), queue(), e1, day, shifts["D1"]).status_code == 200
        refused(assign(login(), queue(), e1, SUN, shifts["D1"]), "roster.too_many_days")

    def test_a_day_off_breaks_the_run(self, shifts: dict[str, Any]) -> None:
        e1 = person(hours=60)
        for day in (MON, TUE, WED, THU, FRI):
            assign(login(), queue(), e1, day, shifts["D1"])
        # Saturday off, Sunday and next Monday fine: the run is Sun-Mon only.
        assert assign(login(), queue(), e1, SUN, shifts["D1"]).status_code == 200
        assert assign(login(), queue(), e1, NEXT_MON, shifts["D1"]).status_code == 200

    def test_a_sixth_shift_over_contract_hours_is_refused(self, shifts: dict[str, Any]) -> None:
        e1 = person(hours=40)  # five 8-hour shifts is exactly 40 hours
        for day in (MON, TUE, WED, THU, FRI):
            assert assign(login(), queue(), e1, day, shifts["D1"]).status_code == 200
        refused(assign(login(), queue(), e1, SAT, shifts["D1"]), "roster.over_hours")

    def test_a_shorter_shift_that_still_fits_is_allowed(self, shifts: dict[str, Any]) -> None:
        e1 = person(hours=42)  # 40 h used, 2 h left
        for day in (MON, TUE, WED, THU, FRI):
            assign(login(), queue(), e1, day, shifts["D1"])
        refused(assign(login(), queue(), e1, SAT, shifts["P1"]), "roster.over_hours")  # 4 h
        e2 = person("E002", hours=44)
        for day in (MON, TUE, WED, THU, FRI):
            assign(login(), queue(), e2, day, shifts["D1"])
        assert assign(login(), queue(), e2, SAT, shifts["P1"]).status_code == 200  # 4 h fits

    def test_hours_are_counted_per_calendar_week(self, shifts: dict[str, Any]) -> None:
        e1 = person(hours=40)
        for day in (MON, TUE, WED, THU, FRI):
            assign(login(), queue(), e1, day, shifts["D1"])
        # The next Monday is a new week with a fresh allowance.
        assert assign(login(), queue(), e1, NEXT_MON, shifts["D1"]).status_code == 200


class TestWhoMayBeRostered:
    def test_only_people_skilled_on_the_queue(self, shifts: dict[str, Any]) -> None:
        e1 = person(queues=("QueueB",))
        queue("QueueA")
        refused(assign(login(), queue("QueueA"), e1, MON, shifts["D1"]), "roster.not_skilled")

    def test_not_before_they_start_or_after_they_leave(self, shifts: dict[str, Any]) -> None:
        e1 = person(start_date=TUE, end_date=THU)
        refused(assign(login(), queue(), e1, MON, shifts["D1"]), "roster.not_employed")
        assert assign(login(), queue(), e1, TUE, shifts["D1"]).status_code == 200
        refused(assign(login(), queue(), e1, FRI, shifts["D1"]), "roster.not_employed")

    def test_one_person_cannot_be_on_two_queues_on_the_same_day(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person(queues=("QueueA", "QueueB"))
        assign(login(), queue("QueueA"), e1, MON, shifts["D1"])
        refused(assign(login(), queue("QueueB"), e1, MON, shifts["E1"]), "roster.already_rostered")
        assert stored() == 1

    def test_the_database_itself_allows_one_shift_per_person_per_day(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        first = ShiftAssignment.objects.get()
        with pytest.raises(IntegrityError), transaction.atomic():
            ShiftAssignment.objects.create(
                roster_week=first.roster_week, employee=e1, day=MON, template=shifts["E1"]
            )


class TestTheWeek:
    def test_a_week_starts_on_a_monday(self, shifts: dict[str, Any]) -> None:
        person()
        response = login().get(ROSTER, params(queue(), TUE))
        refused(response, "roster.not_a_monday")

    def test_publishing_locks_the_week(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        published = login().post(f"{ROSTER}/publish", body, content_type="application/json")
        assert published.json()["status"] == "published"

        refused(assign(login(), queue(), e1, TUE, shifts["D1"]), "roster.published")
        refused(assign(login(), queue(), e1, MON, None), "roster.published")  # clearing too
        assert stored() == 1

    def test_reopening_makes_it_editable_again(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        login().post(f"{ROSTER}/publish", body, content_type="application/json")
        reopened = login().post(f"{ROSTER}/reopen", body, content_type="application/json")
        assert reopened.json()["status"] == "draft"
        assert assign(login(), queue(), e1, TUE, shifts["D1"]).status_code == 200

    def test_publishing_twice_changes_and_audits_nothing_more(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        login().post(f"{ROSTER}/publish", body, content_type="application/json")
        login().post(f"{ROSTER}/publish", body, content_type="application/json")
        assert AuditEvent.objects.filter(action=Action.ROSTER_PUBLISHED).count() == 1

    def test_an_empty_roster_cannot_be_published(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        assign(login(), queue(), e1, MON, None)  # the week exists but holds nothing
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        response = login().post(f"{ROSTER}/publish", body, content_type="application/json")
        refused(response, "roster.empty")
        assert RosterWeek.objects.get().status == RosterStatus.DRAFT

    def test_a_week_nobody_was_rostered_for_is_a_404(self) -> None:
        person()
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        assert (
            login().post(f"{ROSTER}/publish", body, content_type="application/json").status_code
            == 404
        )

    def test_publishing_records_who_and_when(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        out = login().post(f"{ROSTER}/publish", body, content_type="application/json").json()
        week = RosterWeek.objects.get()
        assert week.published_by is not None
        assert out["publishedAt"] is not None
        event = AuditEvent.objects.get(action=Action.ROSTER_PUBLISHED)
        assert (event.actor_role, event.entity_id) == (Role.PLANNER, str(week.pk))


class TestAudit:
    def test_an_assignment_says_who_what_and_for_whom(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        assign(login(), queue(), e1, MON, shifts["E1"])
        events = AuditEvent.objects.filter(action=Action.ROSTER_ASSIGNED).order_by("chain_seq")
        assert [e.subject_employee_id for e in events] == [e1.pk, e1.pk]
        second = AuditChange.objects.get(event=events[1])
        assert (second.old_value, second.new_value) == ("D1", "E1")

    def test_a_refusal_is_audited_even_though_the_change_rolled_back(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["L1"])
        assign(login(), queue(), e1, TUE, shifts["E1"])  # refused: 9 hours of rest
        event = AuditEvent.objects.get(action=Action.ROSTER_REFUSED)
        assert (event.outcome, event.reason) == (Outcome.FAILED, "roster.rest_period")
        assert event.actor_role == Role.PLANNER

    def test_staff_names_never_reach_the_audit_trail(self, shifts: dict[str, Any]) -> None:
        name = "Zanele Testperson"
        e1 = person(name=name)
        assign(login(), queue(), e1, MON, shifts["D1"])
        assign(login(), queue(), e1, MON, None)
        assign(login(), queue(), e1, TUE, shifts["L1"])
        assign(login(), queue(), e1, WED, shifts["E1"])  # refused
        login().get(f"{ROSTER}/export.csv", params(queue(), MON))
        text = " ".join(
            f"{e.reason} {e.entity_id} {e.entity_type}" for e in AuditEvent.objects.all()
        ) + " ".join(
            f"{c.old_value} {c.new_value} {c.entity_id}" for c in AuditChange.objects.all()
        )
        assert "Zanele" not in text
        assert "Testperson" not in text


class TestNothingHalfDone:
    def test_an_assignment_whose_audit_event_cannot_be_written_is_not_made(
        self, shifts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        e1 = person()

        def refuse(**kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_services, "record", refuse)
        with pytest.raises(RuntimeError):
            assign(login(), queue(), e1, MON, shifts["D1"])
        assert (stored(), RosterWeek.objects.count()) == (0, 0)

    def test_two_planners_at_once_get_one_winner_and_a_clear_conflict(
        self, shifts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        e1 = person()

        def lose_the_race(*args: Any, **kwargs: Any) -> None:
            raise IntegrityError("duplicate key value violates scheduling_one_shift_per_day")

        monkeypatch.setattr(ShiftAssignment.objects, "create", lose_the_race)
        response = assign(login(), queue(), e1, MON, shifts["D1"])
        refused(response, "roster.conflict")
        assert AuditEvent.objects.filter(action=Action.ROSTER_REFUSED).count() == 1


class TestWhoMayDoWhat:
    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_only_planners_and_admins_change_the_roster_even_with_a_valid_request(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assert assign(login(role), queue(), e1, MON, shifts["D1"]).status_code == 403
        assert (stored(), RosterWeek.objects.count()) == (0, 0)

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT])
    def test_publishing_is_for_planners_and_admins_only(
        self, role: Role, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        body = {"queueId": queue().pk, "weekStart": str(MON)}
        assert (
            login(role).post(f"{ROSTER}/publish", body, content_type="application/json").status_code
            == 403
        )
        assert RosterWeek.objects.get().status == RosterStatus.DRAFT

    def test_a_lead_may_read_the_roster_but_an_agent_may_not(self, shifts: dict[str, Any]) -> None:
        person()
        assert login(Role.LEAD).get(ROSTER, params(queue(), MON)).status_code == 200
        assert login(Role.AGENT).get(ROSTER, params(queue(), MON)).status_code == 403


class TestExport:
    def export(self, role: Role = Role.PLANNER, day: date = MON) -> Any:
        return login(role).get(f"{ROSTER}/export.csv", params(queue(), day))

    def rows(self, response: Any) -> list[list[str]]:
        return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))

    def test_lists_each_shift_with_its_times(self, shifts: dict[str, Any]) -> None:
        e1 = person("E001", name="Test One")
        assign(login(), queue(), e1, MON, shifts["D1"])
        assign(login(), queue(), e1, TUE, shifts["N1"])
        response = self.export()
        assert response["Content-Type"].startswith("text/csv")
        assert "attachment" in response["Content-Disposition"]
        assert self.rows(response) == [
            ["Employee no", "Name", "Date", "Shift", "Start", "End", "Paid minutes"],
            ["E001", "Test One", "2026-05-25", "D1", "09:00", "17:30", "480"],
            ["E001", "Test One", "2026-05-26", "N1", "22:00", "06:00", "480"],
        ]

    def test_a_week_with_no_roster_exports_just_the_header(self) -> None:
        person()
        assert len(self.rows(self.export())) == 1

    def test_a_name_that_looks_like_a_formula_cannot_run_in_a_spreadsheet(
        self, shifts: dict[str, Any]
    ) -> None:
        # Opened in a spreadsheet, a cell starting with = + - or @ is run as a formula.
        evil = person("+E002", name='=HYPERLINK("http://evil.example","click")')
        assign(login(), queue(), evil, MON, shifts["D1"])
        row = self.rows(self.export())[1]
        assert row[0] == "'+E002"
        assert row[1].startswith("'=HYPERLINK")
        assert not any(cell.startswith(("=", "+", "-", "@")) for cell in row)

    def test_every_export_is_audited_with_how_many_rows(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        assign(login(), queue(), e1, MON, shifts["D1"])
        self.export()
        event = AuditEvent.objects.get(action=Action.ROSTER_EXPORTED)
        assert (event.actor_role, event.reason) == (Role.PLANNER, "1 rows")

    def test_a_lead_may_export_and_an_agent_may_not(self, shifts: dict[str, Any]) -> None:
        person()
        assert self.export(Role.LEAD).status_code == 200
        assert self.export(Role.AGENT).status_code == 403
        assert AuditEvent.objects.filter(action=Action.ROSTER_EXPORTED).count() == 1


def test_the_service_helper_finds_the_monday() -> None:
    assert roster_services.week_start_of(SUN) == MON
    assert roster_services.week_start_of(MON) == MON
    assert roster_services.week_start_of(NEXT_MON) == NEXT_MON
