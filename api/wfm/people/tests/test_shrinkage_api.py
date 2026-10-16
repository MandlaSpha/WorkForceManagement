"""Planned shrinkage from approved leave (SHR-01): the numbers, and who may see them."""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import Employee
from wfm.scheduling.tests.helpers import person

from .team import lead_of

pytestmark = pytest.mark.django_db

URL = "/api/v1/people/shrinkage"
MARCH = "2031-03-01"  # 20 working days: 21 weekdays less Human Rights Day on Friday the 21st


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def leave(
    employee: Employee, first: str, last: str, status: str = LeaveStatus.APPROVED
) -> LeaveRequest:
    admin, _ = User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})
    kind, _ = LeaveType.objects.get_or_create(code="annual", defaults={"name": "Annual"})
    return LeaveRequest.objects.create(
        employee=employee,
        leave_type=kind,
        start_date=date.fromisoformat(first),
        end_date=date.fromisoformat(last),
        days=1,
        status=status,
        requested_by=admin,
    )


def teams(c: Client, month: str = MARCH) -> list[dict[str, Any]]:
    response = c.get(URL, {"month": month})
    assert response.status_code == 200, response.content
    return list(response.json()["teams"])


def lead_team() -> dict[str, Any]:
    """The team led by `lead_of` (the lead herself has no lead, so she is in 'No lead')."""
    return next(t for t in teams(client(Role.PLANNER)) if t["team"] == "Person L001")


class TestTheNumbers:
    def test_two_days_of_leave_in_twenty_working_days_is_ten_percent(self) -> None:
        # Failure caught: leave hours divided by the wrong base (calendar days, or all weekdays).
        e = person("E001")
        lead_of(e)
        leave(e, "2031-03-03", "2031-03-04")
        team = lead_team()
        assert (team["contractedHours"], team["awayHours"], team["plannedPct"]) == (
            "160.0",
            "16.0",
            "10.0",
        )
        assert team["assumedPct"] == "30.00"  # the queue's own planning assumption

    def test_only_approved_leave_counts(self) -> None:
        # Failure caught: leave still waiting, rejected or cancelled counted as time away.
        e = person("E001")
        lead_of(e)
        for status in (LeaveStatus.PENDING, LeaveStatus.REJECTED, LeaveStatus.CANCELLED):
            leave(e, "2031-03-03", "2031-03-04", status)
        assert lead_team()["plannedPct"] == "0.0"

    def test_weekends_and_public_holidays_are_not_time_away(self) -> None:
        # Failure caught: leave over a holiday charged against the team.
        e = person("E001")
        lead_of(e)
        leave(e, "2031-03-21", "2031-03-23")  # the holiday, then the weekend
        assert lead_team()["awayHours"] == "0.0"

    def test_leave_across_a_month_boundary_counts_only_the_days_inside(self) -> None:
        # Failure caught: a whole request charged to every month it touches.
        e = person("E001")
        lead_of(e)
        leave(e, "2031-02-27", "2031-03-04")  # Thu 27, Fri 28 are February; Mon 3, Tue 4 March
        assert lead_team()["awayHours"] == "16.0"

    def test_somebody_who_joined_mid_month_is_only_counted_from_then(self) -> None:
        # Failure caught: contracted hours for days before they were employed, understating it.
        e = person("E001", start_date=date(2031, 3, 17))
        lead_of(e)
        assert lead_team()["contractedHours"] == "80.0"

    def test_part_time_hours_scale_the_hours_not_the_share(self) -> None:
        # Failure caught: 40 hours assumed for everybody.
        e = person("E001", hours=20)
        lead_of(e)
        leave(e, "2031-03-03", "2031-03-04")
        team = lead_team()
        assert (team["awayHours"], team["plannedPct"]) == ("8.0", "10.0")

    def test_unplanned_shrinkage_is_never_claimed_to_be_measured(self) -> None:
        # Failure caught: an attendance figure invented where there is no feed.
        person("E001")
        body = client(Role.PLANNER).get(URL, {"month": MARCH}).json()
        assert body["unplannedMeasured"] is False


class TestWhoSeesWhat:
    def test_a_lead_sees_only_their_own_team(self) -> None:
        # Failure caught: a lead reading another team's absence.
        mine = person("E001")
        other = person("E002")
        lead_of(mine)
        other_lead_user = User.objects.create(username="u-lead2", role=Role.LEAD)
        other.manager = person("L002", user=other_lead_user)
        other.save(update_fields=["manager"])
        leave(other, "2031-03-03", "2031-03-04")
        rows = teams(client(Role.LEAD))
        assert [t["team"] for t in rows] == ["Person L001"]
        assert rows[0]["awayHours"] == "0.0"

    def test_planner_and_admin_see_every_team_and_people_with_no_lead(self) -> None:
        lead_of(person("E001"))
        person("E002")  # no lead
        for role in (Role.PLANNER, Role.ADMIN):
            assert {t["team"] for t in teams(client(role))} >= {"Person L001", "No lead"}

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role) -> None:
        assert client(role).get(URL, {"month": MARCH}).status_code == 403

    def test_signed_out_is_refused(self) -> None:
        assert Client().get(URL).status_code in (401, 403)
