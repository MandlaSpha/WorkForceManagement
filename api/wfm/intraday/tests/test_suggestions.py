"""Acting on a short half-hour (INT-04): who could cover it as overtime, and which breaks could
move. Read only; the writes are the overtime and activity services."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.intraday import suggestions
from wfm.overtime.models import OvertimeRequest
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import Employee, ShiftActivity, ShiftAssignment
from wfm.scheduling.tests.helpers import (
    assign,
    login,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/intraday/suggestions"
SLOT = 20  # 10:00


def the_day() -> date:
    return timezone.localdate() + timedelta(days=3)


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def ask(role: Role, queue_id: int | None = None, slot: int = SLOT) -> Any:
    return client(role).get(
        URL, {"queue_id": str(queue_id or queue().pk), "day": str(the_day()), "slot": str(slot)}
    )


def planner() -> User:
    return User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]


def names(r: Any) -> list[str]:
    return [p["name"] for p in r.json()["people"]]


@pytest.fixture
def shifts() -> dict[str, Any]:
    found = standard_shifts()
    publish_forecast(queue(), {(the_day(), s): 1 for s in range(48)})
    return found


class TestPeopleForOvertime:
    def test_only_people_who_pass_every_rule_are_suggested(self, shifts: dict[str, Any]) -> None:
        # Failure caught: a person already on shift, on leave, unskilled for the queue, or short of
        # rest being offered, so the planner's one click produces a refusal.
        day = the_day()
        free = person("E001", name="Free")
        working = person("E002", name="Working")
        on_leave = person("E003", name="On leave")
        tired = person("E004", name="Tired")
        person("E005", queues=("QueueB",), name="Other queue")
        assign(login(), queue(), working, day, shifts["D1"])
        LeaveRequest.objects.create(
            employee=on_leave,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=day,
            end_date=day,
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=planner(),
        )
        # Finished at 22:00 the day before: 12 hours of rest before 10:00, 7 before 05:00.
        assign(login(), queue(), tired, day - timedelta(days=1), shifts["L1"])
        assert names(ask(Role.PLANNER)) == ["Free", "Tired"]
        early = ask(Role.PLANNER, slot=10)  # 05:00
        assert names(early) == ["Free"]
        assert early.json()["people"][0]["employeeId"] == free.pk

    def test_the_lightest_week_comes_first_and_at_most_five(self, shifts: dict[str, Any]) -> None:
        # Failure caught: the busiest person asked first, or an unbounded list.
        day = the_day()
        monday = day - timedelta(days=day.weekday())
        others = [
            d for d in (monday + timedelta(days=n) for n in range(7)) if abs((d - day).days) > 1
        ]
        heavy = person("E001", name="Heavy")
        light = person("E002", name="Light")
        for i in range(3, 8):
            person(f"E00{i}", name=f"Same {i}")
        for d in others[:2]:
            assign(login(), queue(), heavy, d, shifts["D1"])
        assign(login(), queue(), light, others[0], shifts["D1"])
        found = ask(Role.PLANNER).json()["people"]
        assert [p["name"] for p in found] == [f"Same {i}" for i in range(3, 8)]
        assert {p["weekMinutes"] for p in found} == {0}  # Light and Heavy are left out

    def test_waiting_overtime_counts_toward_the_week(self, shifts: dict[str, Any]) -> None:
        # Failure caught: suggesting someone with a full week of approved overtime as "light".
        day = the_day()
        busy = person("E001", name="Busy")
        person("E002", name="Idle")
        OvertimeRequest.objects.create(
            employee=busy,
            day=day - timedelta(days=day.weekday()) if day.weekday() else day + timedelta(days=1),
            start_time="18:00",
            end_time="22:00",
            minutes=240,
            requested_by=planner(),
        )
        assert names(ask(Role.PLANNER))[0] == "Idle"

    def test_the_overtime_span_is_the_half_hour(self) -> None:
        # Failure caught: a prefilled form that does not cover the short half-hour.
        assert [f"{t:%H:%M}" for t in suggestions.overtime_span(20)] == ["10:00", "10:30"]
        assert [f"{t:%H:%M}" for t in suggestions.overtime_span(47)] == ["23:30", "23:59"]


class TestBreakMoves:
    def test_a_break_in_the_short_half_hour_is_offered_a_covered_place(
        self, shifts: dict[str, Any]
    ) -> None:
        # Failure caught: no way to see that the short half-hour is a break, or a move to a place
        # that is itself short.
        day = the_day()
        a, b = person("E001", name="Ann"), person("E002", name="Bea")
        assign(login(), queue(), a, day, shifts["D1"])  # 09:00 to 17:30
        assign(login(), queue(), b, day, shifts["D1"])
        mine = ShiftAssignment.objects.get(employee=a, day=day)
        ShiftActivity.objects.create(
            assignment=mine, kind="break", offset_slots=2, slots=1, created_by=planner()
        )  # 10:00
        ShiftActivity.objects.create(
            assignment=ShiftAssignment.objects.get(employee=b, day=day),
            kind="break",
            offset_slots=3,
            slots=1,
            created_by=planner(),
        )  # Bea's 10:30
        found = ask(Role.PLANNER).json()["breaks"]
        assert [(m["employee"], m["start"], m["end"]) for m in found] == [("Ann", "10:00", "10:30")]
        # One is needed on the phones. 10:30 is Bea's break (moving there leaves nobody); 09:30
        # is the nearest place that keeps one person on the phones.
        assert found[0]["moveTo"] == "09:30"

    def test_a_break_that_cannot_move_anywhere_is_not_offered(self, shifts: dict[str, Any]) -> None:
        # Failure caught: a move suggested where every other place leaves the phones uncovered.
        day = the_day()
        a = person("E001", name="Ann")
        assign(login(), queue(), a, day, shifts["P1"])  # alone, 10:00 to 14:00
        ShiftActivity.objects.create(
            assignment=ShiftAssignment.objects.get(employee=a, day=day),
            kind="break",
            offset_slots=0,
            slots=1,
            created_by=planner(),
        )
        assert ask(Role.PLANNER).json()["breaks"] == []


class TestWhoMayAsk:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planner_and_admin_get_names(self, role: Role, shifts: dict[str, Any]) -> None:
        person("E001", name="Free")
        r = ask(role)
        assert r.status_code == 200, r.content
        assert names(r) == ["Free"]

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_everyone_else_is_refused(self, role: Role, shifts: dict[str, Any]) -> None:
        # Failure caught: a lead (who sees the alerts) or an outsider reading staff names and
        # their week loads through the suggestions.
        person("E001", name="Free")
        r = ask(role)
        assert r.status_code == 403
        assert "Free" not in r.content.decode()

    def test_signed_out_and_unknown_queue_and_bad_slot(self, shifts: dict[str, Any]) -> None:
        assert Client().get(URL).status_code in (401, 403)
        assert ask(Role.PLANNER, queue_id=99999).status_code == 404
        assert ask(Role.PLANNER, slot=48).status_code == 422


def test_asking_writes_nothing(shifts: dict[str, Any]) -> None:
    # Failure caught: the suggestion read writing a request or a notification.
    person("E001")
    ask(Role.PLANNER)
    assert not OvertimeRequest.objects.exists()
    assert Employee.objects.count() == 1
