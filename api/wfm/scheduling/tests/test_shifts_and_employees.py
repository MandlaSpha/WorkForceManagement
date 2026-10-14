"""The shift library and the employee directory: validation, ownership of changes, privacy."""

from __future__ import annotations

from typing import Any

import pytest
from django.db import IntegrityError, transaction

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.scheduling.models import Employee, ShiftTemplate

from .helpers import EMPLOYEES, MON, SHIFTS, assign, login, person, queue, shift

pytestmark = pytest.mark.django_db


def new_shift(client: Any, **overrides: Any) -> Any:
    body = {"code": "D1", "startTime": "09:00", "endTime": "17:30", "paidMinutes": 480, **overrides}
    return client.post(SHIFTS, body, content_type="application/json")


class TestShiftLibrary:
    def test_an_admin_adds_a_shift_and_it_is_described_for_the_roster_legend(self) -> None:
        response = new_shift(login(Role.ADMIN))
        assert response.status_code == 201
        assert response.json() | {"id": 0} == {
            "id": 0,
            "code": "D1",
            "startTime": "09:00",
            "endTime": "17:30",
            "paidMinutes": 480,
            "minutes": 510,
            "overnight": False,
            "kind": "day",
        }

    def test_a_night_shift_is_flagged_overnight(self) -> None:
        body = new_shift(login(Role.ADMIN), code="N1", startTime="22:00", endTime="06:00").json()
        assert (body["overnight"], body["kind"], body["minutes"]) == (True, "night", 480)

    @pytest.mark.parametrize("role", [Role.PLANNER, Role.LEAD, Role.AGENT])
    def test_only_an_admin_changes_the_library_even_with_a_valid_request(self, role: Role) -> None:
        assert new_shift(login(role)).status_code == 403
        assert ShiftTemplate.objects.count() == 0

    def test_planners_and_leads_can_read_it(self) -> None:
        shift("D1", "09:00", "17:30", 480)
        assert len(login(Role.PLANNER).get(SHIFTS).json()) == 1
        assert len(login(Role.LEAD).get(SHIFTS).json()) == 1
        assert login(Role.AGENT).get(SHIFTS).status_code == 403

    @pytest.mark.parametrize(
        ("overrides", "code"),
        [
            ({"startTime": "09:15"}, "shift.not_on_grid"),
            ({"endTime": "17:10"}, "shift.not_on_grid"),
            ({"startTime": "09:00", "endTime": "09:00"}, "shift.no_length"),
            (
                {"paidMinutes": 600},
                "shift.paid_minutes_invalid",
            ),  # longer than the 510 on the clock
            ({"paidMinutes": 0}, "shift.paid_minutes_invalid"),
            ({"code": "   "}, "shift.code_invalid"),
        ],
    )
    def test_refuses_a_shift_that_cannot_be_rostered(
        self, overrides: dict[str, Any], code: str
    ) -> None:
        response = new_shift(login(Role.ADMIN), **overrides)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert ShiftTemplate.objects.count() == 0

    def test_a_code_is_used_once(self) -> None:
        new_shift(login(Role.ADMIN))
        response = new_shift(login(Role.ADMIN), startTime="10:00", endTime="18:00")
        assert (response.status_code, response.json()["code"]) == (409, "shift.code_taken")

    def test_the_database_itself_refuses_a_repeated_code(self) -> None:
        shift("D1", "09:00", "17:30", 480)
        with pytest.raises(IntegrityError), transaction.atomic():
            shift("D1", "10:00", "18:00", 480)

    def test_an_unused_shift_can_be_changed_and_deleted(self) -> None:
        template = shift("D1", "09:00", "17:30", 480)
        changed = login(Role.ADMIN).put(
            f"{SHIFTS}/{template.pk}",
            {"code": "D2", "startTime": "09:30", "endTime": "18:00", "paidMinutes": 480},
            content_type="application/json",
        )
        assert (changed.status_code, changed.json()["code"], changed.json()["startTime"]) == (
            200,
            "D2",
            "09:30",
        )
        assert login(Role.ADMIN).delete(f"{SHIFTS}/{template.pk}").status_code == 200
        assert ShiftTemplate.objects.count() == 0

    def test_once_people_are_rostered_the_times_are_fixed_but_the_name_can_change(self) -> None:
        template = shift("D1", "09:00", "17:30", 480)
        queue()
        assign(login(), queue(), person(), MON, template)

        def put(body: dict[str, Any]) -> Any:
            return login(Role.ADMIN).put(
                f"{SHIFTS}/{template.pk}", body, content_type="application/json"
            )

        times = put({"code": "D1", "startTime": "08:00", "endTime": "16:30", "paidMinutes": 480})
        assert (times.status_code, times.json()["code"]) == (409, "shift.in_use")

        rename = put({"code": "DAY", "startTime": "09:00", "endTime": "17:30", "paidMinutes": 480})
        assert (rename.status_code, rename.json()["code"]) == (200, "DAY")

    def test_a_shift_in_use_cannot_be_deleted(self) -> None:
        template = shift("D1", "09:00", "17:30", 480)
        assign(login(), queue(), person(), MON, template)
        response = login(Role.ADMIN).delete(f"{SHIFTS}/{template.pk}")
        assert (response.status_code, response.json()["code"]) == (409, "shift.in_use")
        assert ShiftTemplate.objects.count() == 1

    def test_changes_are_audited_with_who_and_what(self) -> None:
        template = shift("D1", "09:00", "17:30", 480)
        login(Role.ADMIN).put(
            f"{SHIFTS}/{template.pk}",
            {"code": "D1", "startTime": "09:00", "endTime": "18:00", "paidMinutes": 480},
            content_type="application/json",
        )
        event = AuditEvent.objects.get(action=Action.SHIFT_CHANGED)
        assert event.actor_role == Role.ADMIN
        change = AuditChange.objects.get(event=event)
        assert (change.field, change.old_value, change.new_value) == (
            "end_time",
            "17:30:00",
            "18:00:00",
        )

    def test_unknown_shift_is_a_404(self) -> None:
        body = {"code": "X", "startTime": "09:00", "endTime": "10:00", "paidMinutes": 60}
        assert (
            login(Role.ADMIN)
            .put(f"{SHIFTS}/9999", body, content_type="application/json")
            .status_code
            == 404
        )
        assert login(Role.ADMIN).delete(f"{SHIFTS}/9999").status_code == 404


def new_employee(client: Any, **overrides: Any) -> Any:
    body = {
        "empNo": "E001",
        "name": "Test Person",
        "skills": [{"queueId": queue().pk, "level": 2}],
        **overrides,
    }
    return client.post(EMPLOYEES, body, content_type="application/json")


class TestEmployees:
    def test_a_planner_adds_a_person_with_a_skill(self) -> None:
        response = new_employee(login(), weeklyHours=45, workMode="hybrid")
        assert response.status_code == 201, response.content
        body = response.json()
        assert (body["empNo"], body["weeklyHours"], body["weeklyHoursIsDefault"]) == (
            "E001",
            45,
            False,
        )
        assert body["skills"] == [{"queueId": queue().pk, "queue": "QueueA", "level": 2}]

    def test_hours_nobody_entered_are_a_visible_default(self) -> None:
        body = new_employee(login()).json()
        assert (body["weeklyHours"], body["weeklyHoursIsDefault"]) == (40, True)

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_only_planners_and_admins_add_people_even_with_a_valid_request(
        self, role: Role
    ) -> None:
        assert new_employee(login(role)).status_code == 403
        assert Employee.objects.count() == 0

    @pytest.mark.parametrize(
        ("overrides", "code"),
        [
            ({"empNo": " "}, "employee.emp_no_invalid"),
            ({"name": " "}, "employee.name_missing"),
            ({"contractType": "casual"}, "employee.contract_invalid"),
            ({"workMode": "moon"}, "employee.work_mode_invalid"),
            ({"weeklyHours": 0}, "employee.hours_invalid"),
            ({"weeklyHours": 80}, "employee.hours_invalid"),
            ({"startDate": "2026-06-01", "endDate": "2026-05-01"}, "employee.dates_invalid"),
            ({"skills": [{"queueId": 99999, "level": 1}]}, "employee.skill_queue_unknown"),
        ],
    )
    def test_refuses_nonsense_and_stores_nothing(
        self, overrides: dict[str, Any], code: str
    ) -> None:
        queue()
        response = new_employee(login(), **overrides)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert Employee.objects.count() == 0

    def test_a_skill_level_is_one_to_three_and_a_queue_is_listed_once(self) -> None:
        q = queue().pk
        bad_level = new_employee(login(), skills=[{"queueId": q, "level": 4}])
        assert bad_level.json()["code"] == "employee.skill_level_invalid"
        twice = new_employee(login(), skills=[{"queueId": q}, {"queueId": q, "level": 2}])
        assert twice.json()["code"] == "employee.skill_duplicate"

    def test_an_employee_number_is_used_once(self) -> None:
        new_employee(login())
        again = new_employee(login(), name="Someone Else")
        assert (again.status_code, again.json()["code"]) == (409, "employee.emp_no_taken")

    def test_changing_a_person_keeps_their_hours_unless_new_ones_are_entered(self) -> None:
        created = new_employee(login()).json()
        body = {
            "empNo": "E001",
            "name": "Renamed",
            "skills": created["skills"]
            and [{"queueId": s["queueId"], "level": s["level"]} for s in created["skills"]],
        }
        kept = login().put(f"{EMPLOYEES}/{created['id']}", body, content_type="application/json")
        assert (kept.json()["name"], kept.json()["weeklyHoursIsDefault"]) == ("Renamed", True)
        entered = login().put(
            f"{EMPLOYEES}/{created['id']}",
            {**body, "weeklyHours": 36},
            content_type="application/json",
        )
        assert (entered.json()["weeklyHours"], entered.json()["weeklyHoursIsDefault"]) == (
            36,
            False,
        )

    def test_a_skill_cannot_be_removed_while_the_person_is_rostered_on_that_queue(self) -> None:
        created = new_employee(login()).json()
        template = shift("D1", "09:00", "17:30", 480)
        assign(login(), queue(), Employee.objects.get(pk=created["id"]), MON, template)
        body = {"empNo": "E001", "name": "Test Person", "skills": []}
        response = login().put(
            f"{EMPLOYEES}/{created['id']}", body, content_type="application/json"
        )
        assert (response.status_code, response.json()["code"]) == (409, "employee.skill_in_use")

    def test_unknown_employee_is_a_404(self) -> None:
        body = {"empNo": "E9", "name": "X", "skills": []}
        assert (
            login().put(f"{EMPLOYEES}/9999", body, content_type="application/json").status_code
            == 404
        )


class TestPrivacyOfStaffData:
    def test_staff_names_are_in_the_directory_but_never_in_the_audit_trail(self) -> None:
        name = "Zanele Testperson"
        created = new_employee(login(), name=name).json()
        login().put(
            f"{EMPLOYEES}/{created['id']}",
            {"empNo": "E001", "name": "Renamed Person", "skills": []},
            content_type="application/json",
        )
        text = " ".join(f"{e.reason} {e.entity_id}" for e in AuditEvent.objects.all()) + " ".join(
            f"{c.old_value} {c.new_value}" for c in AuditChange.objects.all()
        )
        for forbidden in ("Zanele", "Testperson", "Renamed"):
            assert forbidden not in text
        change = AuditChange.objects.get(field="name")
        assert (change.old_value, change.new_value) == (None, "changed")

    def test_an_agent_can_see_only_their_own_record(self) -> None:
        mine = person("E001")
        theirs = person("E002")
        agent = User.objects.create_user(username="agent1", password="x", role=Role.AGENT)
        mine.user = agent
        mine.save()
        visible = list(Employee.objects.for_user(agent))
        assert visible == [mine]
        assert theirs not in visible

    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_roles_with_no_business_here_see_no_staff(self, role: Role) -> None:
        person("E001")
        user = User.objects.create_user(username=f"x-{role}", password="x", role=role)
        assert Employee.objects.for_user(user).count() == 0

    def test_the_directory_is_not_readable_by_an_agent(self) -> None:
        person("E001")
        assert login(Role.AGENT).get(EMPLOYEES).status_code == 403
