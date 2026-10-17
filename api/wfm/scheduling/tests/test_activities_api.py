"""Breaks and activities inside shifts (SCH-03) and coverage on the phones (ENG-03)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftActivity, ShiftAssignment
from wfm.scheduling.selectors import week_plan

from .helpers import MON, assign, login, person, queue, standard_shifts

pytestmark = pytest.mark.django_db

URL = "/api/v1/scheduling/roster/activities"


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


def add(
    c: Any, assignment: ShiftAssignment, kind: str = "break", offset: int = 6, slots: int = 1
) -> Any:
    """Add by clock time: `offset` half-hours after the shift starts, `slots` half-hours long."""
    began = datetime.combine(assignment.day, assignment.template.start_time) + timedelta(
        minutes=30 * offset
    )
    return c.post(
        URL,
        {
            "queueId": assignment.roster_week.queue_id,
            "employeeId": assignment.employee_id,
            "day": str(assignment.day),
            "kind": kind,
            "startTime": f"{began:%H:%M}",
            "minutes": 30 * slots,
        },
        content_type="application/json",
    )


def on_shift(shifts: dict[str, Any], code: str = "D1") -> ShiftAssignment:
    e1 = person("E001")
    assign(login(), queue(), e1, MON, shifts[code])
    return ShiftAssignment.objects.get(employee=e1, day=MON)


def planner() -> User:
    return User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]


class TestWhoMayDoWhat:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planner_and_admin_can_add_and_remove(self, role: Role, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        made = add(login(role), a)
        assert made.status_code == 201, made.content
        assert login(role).delete(f"{URL}/{made.json()['id']}").status_code == 204
        assert not ShiftActivity.objects.exists()

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_change_them(self, role: Role, shifts: dict[str, Any]) -> None:
        # Failure caught: a lead or an agent taking people off the phones.
        a = on_shift(shifts)
        assert add(login(role), a).status_code == 403
        mine = add(login(), a).json()
        assert login(role).delete(f"{URL}/{mine['id']}").status_code == 403
        assert ShiftActivity.objects.count() == 1

    def test_a_lead_can_read_them_and_an_agent_cannot(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        add(login(), a)
        params = {"queue_id": str(queue().pk), "week_start": str(MON)}
        assert len(login(Role.LEAD).get(URL, params).json()) == 1
        assert login(Role.AGENT).get(URL, params).status_code == 403

    def test_an_unknown_shift_or_queue_is_not_found(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        body = {
            "queueId": a.roster_week.queue_id,
            "employeeId": a.employee_id,
            "day": str(a.day + timedelta(days=1)),  # no shift that day
            "kind": "break",
            "startTime": "12:00",
            "minutes": 30,
        }
        assert login().post(URL, body, content_type="application/json").status_code == 404
        r = login().get(URL, {"queue_id": "99999", "week_start": str(MON)})
        assert r.status_code == 404


class TestWhereItMayGo:
    def test_it_must_sit_inside_the_shift_and_not_overlap_another(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a lunch after the shift has ended, or two breaks on the same half-hour.
        a = on_shift(shifts)  # 09:00 to 17:30: 17 half-hours
        assert add(login(), a, offset=17).json()["code"] == "activity.outside_shift"
        assert add(login(), a, offset=16, slots=2).json()["code"] == "activity.outside_shift"
        assert add(login(), a, slots=0).json()["code"] == "activity.no_length"
        assert add(login(), a, offset=16, slots=1).status_code == 201  # the very last half-hour
        assert add(login(), a, offset=4, slots=2).status_code == 201
        assert add(login(), a, offset=5, slots=2).json()["code"] == "activity.overlap"
        assert add(login(), a, offset=6, slots=1).status_code == 201  # touching is fine

    def test_the_time_must_be_on_the_half_hour_and_in_half_hours(
        self, shifts: dict[str, Any]
    ) -> None:
        a = on_shift(shifts)
        body = {
            "queueId": a.roster_week.queue_id,
            "employeeId": a.employee_id,
            "day": str(a.day),
            "kind": "break",
            "startTime": "12:10",
            "minutes": 30,
        }
        r = login().post(URL, body, content_type="application/json")
        assert (r.status_code, r.json()["code"]) == (422, "activity.not_on_grid")
        r = login().post(
            URL, {**body, "startTime": "12:00", "minutes": 45}, content_type="application/json"
        )
        assert r.json()["code"] == "activity.not_on_grid"

    def test_a_time_before_the_shift_starts_is_outside_it(self, shifts: dict[str, Any]) -> None:
        # Failure caught: 08:00 read as inside a 09:00 shift by wrapping round the clock.
        a = on_shift(shifts)
        body = {
            "queueId": a.roster_week.queue_id,
            "employeeId": a.employee_id,
            "day": str(a.day),
            "kind": "break",
            "startTime": "08:00",
            "minutes": 30,
        }
        r = login().post(URL, body, content_type="application/json")
        assert r.json()["code"] == "activity.outside_shift"

    def test_an_unknown_kind_is_refused(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        assert add(login(), a, kind="nap").json()["code"] == "activity.unknown_kind"

    def test_one_shift_cannot_collect_endless_activities(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        for n in range(12):
            assert add(login(), a, offset=n, slots=1).status_code == 201
        assert add(login(), a, offset=14, slots=1).json()["code"] == "activity.too_many"

    def test_an_overnight_shift_places_by_half_hours_from_its_start(
        self, shifts: dict[str, Any]
    ) -> None:
        a = on_shift(shifts, "N1")  # 22:00 to 06:00
        made = add(login(), a, offset=4, slots=1).json()
        assert (made["startTime"], made["endTime"]) == ("00:00", "00:30")
        assert add(login(), a, offset=16).json()["code"] == "activity.outside_shift"


class TestCoverageOnThePhones:
    def test_an_activity_takes_the_person_out_of_coverage_for_those_half_hours(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a person in training still counted as answering calls.
        a = on_shift(shifts)
        before = week_plan(planner(), queue().pk, MON).cells[MON]
        add(login(), a, kind="training", offset=6, slots=2)  # 12:00 and 12:30
        after = week_plan(planner(), queue().pk, MON).cells[MON]
        assert [before[k].scheduled for k in (23, 24, 25, 26)] == [1, 1, 1, 1]
        assert [after[k].scheduled for k in (23, 24, 25, 26)] == [1, 0, 0, 1]
        assert [after[k].off_phone for k in (23, 24, 25, 26)] == [0, 1, 1, 0]

    def test_removing_it_puts_them_back(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        made = add(login(), a, offset=6, slots=2).json()
        login().delete(f"{URL}/{made['id']}")
        cells = week_plan(planner(), queue().pk, MON).cells[MON]
        assert [cells[k].scheduled for k in (24, 25)] == [1, 1]
        assert [cells[k].off_phone for k in (24, 25)] == [0, 0]

    def test_a_gap_it_opens_shows_in_the_plan(self, shifts: dict[str, Any]) -> None:
        from .helpers import publish_forecast

        a = on_shift(shifts)
        publish_forecast(queue(), {(MON, slot): 1 for slot in range(18, 35)})
        add(login(), a, offset=6, slots=1)
        cell = week_plan(planner(), queue().pk, MON).cells[MON][24]
        assert (cell.scheduled, cell.required, cell.state) == (0, 1, "under")


class TestTheShiftOwnsThem:
    def test_changing_the_shift_clears_activities_measured_from_the_old_one(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a lunch at 12:00 left standing in a shift that now starts at 13:00.
        a = on_shift(shifts)
        add(login(), a)
        assign(login(), queue(), a.employee, MON, shifts["L1"])
        assert not ShiftActivity.objects.exists()

    def test_putting_the_same_shift_back_keeps_them(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        add(login(), a)
        assign(login(), queue(), a.employee, MON, shifts["D1"])
        assert ShiftActivity.objects.count() == 1

    def test_clearing_the_shift_removes_them(self, shifts: dict[str, Any]) -> None:
        a = on_shift(shifts)
        add(login(), a)
        assign(login(), queue(), a.employee, MON, None)
        assert not ShiftActivity.objects.exists()

    def test_they_can_be_changed_in_a_published_week(self, shifts: dict[str, Any]) -> None:
        # Breaks get moved on the day, after the roster is final.
        a = on_shift(shifts)
        RosterWeek.objects.filter(pk=a.roster_week_id).update(status=RosterStatus.PUBLISHED)
        assert add(login(), a).status_code == 201


class TestAudit:
    def test_adding_and_removing_are_audited_against_the_person(
        self, shifts: dict[str, Any]
    ) -> None:
        a = on_shift(shifts)
        made = add(login(), a, kind="coaching", slots=2).json()
        login().delete(f"{URL}/{made['id']}")
        added = AuditEvent.objects.get(action=Action.ROSTER_ACTIVITY_ADDED)
        removed = AuditEvent.objects.get(action=Action.ROSTER_ACTIVITY_REMOVED)
        assert added.subject_employee_id == removed.subject_employee_id == a.employee_id
        assert added.actor_role == "planner"


def test_the_list_shows_when_in_clock_time(shifts: dict[str, Any]) -> None:
    a = on_shift(shifts)
    add(login(), a, kind="lunch", offset=6, slots=2)
    row = login().get(URL, {"queue_id": str(queue().pk), "week_start": str(MON)}).json()[0]
    assert (row["shift"], row["kind"], row["startTime"], row["endTime"]) == (
        "D1",
        "lunch",
        "12:00",
        "13:00",
    )
    # Only that week's shifts are listed.
    later = login().get(
        URL, {"queue_id": str(queue().pk), "week_start": str(MON + timedelta(days=7))}
    )
    assert later.json() == []


def post_move(c: Any, activity_id: int, start: str) -> Any:
    return c.post(
        f"{URL}/{activity_id}/move", {"startTime": start}, content_type="application/json"
    )


class TestMovingOne:
    """INT-04: move a break in one audited step."""

    def test_a_move_replaces_the_old_place_and_is_audited_last(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: a move that leaves both places (double absence) or neither, or audits
        # before the write.
        a = on_shift(shifts)  # 09:00 to 17:30
        made = add(login(), a, offset=2, slots=2).json()  # 10:00 to 11:00
        r = post_move(login(), made["id"], "12:00")
        assert r.status_code == 200, r.content
        (only,) = ShiftActivity.objects.all()
        assert (only.offset_slots, only.slots, only.kind) == (6, 2, "break")
        newest = AuditEvent.objects.order_by("-pk")[:2]
        assert {e.action for e in newest} == {
            Action.ROSTER_ACTIVITY_ADDED,
            Action.ROSTER_ACTIVITY_REMOVED,
        }
        assert newest[0].action == Action.ROSTER_ACTIVITY_ADDED  # the last write

    def test_a_refused_move_changes_nothing(self, shifts: dict[str, Any]) -> None:
        # Failure caught: the old break deleted and the new one refused, leaving nothing.
        a = on_shift(shifts)
        first = add(login(), a, offset=2).json()
        add(login(), a, offset=6)
        events = AuditEvent.objects.count()
        for start, code in (
            ("12:00", "activity.overlap"),
            ("18:00", "activity.outside_shift"),
            ("12:15", "activity.not_on_grid"),
        ):
            r = post_move(login(), first["id"], start)
            assert (r.status_code, r.json()["code"]) == (422, code)
        assert sorted(ShiftActivity.objects.values_list("offset_slots", flat=True)) == [2, 6]
        assert AuditEvent.objects.count() == events

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_only_planner_and_admin_can_move(self, role: Role, shifts: dict[str, Any]) -> None:
        # Failure caught: a lead moving people off the phones.
        made = add(login(), on_shift(shifts), offset=2).json()
        assert post_move(login(role), made["id"], "12:00").status_code == 403
        assert ShiftActivity.objects.get().offset_slots == 2

    def test_admin_can_move_and_an_unknown_one_is_not_found(self, shifts: dict[str, Any]) -> None:
        made = add(login(), on_shift(shifts), offset=2).json()
        assert post_move(login(Role.ADMIN), made["id"], "12:00").status_code == 200
        assert post_move(login(), 99999, "12:00").status_code == 404
