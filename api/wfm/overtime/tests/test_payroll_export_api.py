"""The payroll file (RPT-08): who may take it, what is in it, that it cannot run as a formula, and
that taking it is audited without its contents."""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftAssignment
from wfm.scheduling.tests.helpers import person, queue, standard_shifts

from .test_overtime_api import client, pay
from .test_reconcile_standby_api import (
    RATES,
    STANDBY,
    a_weekday_back,
    approved_past,
    cost_of,
    put,
    worked,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/overtime/payroll.csv"


def month_of(day: date) -> str:
    return str(day.replace(day=1))


def file(role: Role, month: str) -> Any:
    return client(role).get(URL, {"month": month})


def rows(role: Role, month: str) -> list[dict[str, str]]:
    response = file(role, month)
    assert response.status_code == 200, response.content
    return list(csv.DictReader(io.StringIO(response.content.decode())))


class TestWhoMayTakeIt:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planner_and_admin_get_a_csv_download_that_is_not_cached(self, role: Role) -> None:
        response = file(role, "2031-03-01")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert response["Content-Disposition"] == 'attachment; filename="payroll-2031-03.csv"'
        assert response["Cache-Control"] == "no-store"

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_and_nothing_is_recorded_as_exported(self, role: Role) -> None:
        # Failure caught: names and pay handed to a lead, an agent or a customer.
        assert file(role, "2031-03-01").status_code == 403
        assert not AuditEvent.objects.filter(action=Action.PAYROLL_EXPORTED).exists()

    def test_signed_out_is_refused(self) -> None:
        from django.test import Client

        assert Client().get(URL, {"month": "2031-03-01"}).status_code in (401, 403)


class TestWhatIsInIt:
    def test_overtime_standby_and_call_outs_are_added_up_per_person(self) -> None:
        # Failure caught: payroll paid for time that was never worked, or for a missing salary as 0.
        put(client(Role.ADMIN), RATES, {"standbyAllowance": 150})
        e1 = person("E001", name="Pat Payroll")
        pay(e1)
        day = a_weekday_back()
        r = approved_past(e1, day)
        worked(client(Role.PLANNER), r.pk, 60)  # half of the two hours approved
        stand = (
            client(Role.PLANNER)
            .post(STANDBY, {"employeeId": e1.pk, "day": str(day)}, content_type="application/json")
            .json()
        )
        client(Role.PLANNER).post(
            f"{STANDBY}/{stand['id']}/call-out", {"minutes": 30}, content_type="application/json"
        )
        got = rows(Role.PLANNER, month_of(day))
        assert len(got) == 1
        row = got[0]
        half = (cost_of(r) / 2).quantize(Decimal("0.01"))
        assert (row["Employee number"], row["Name"]) == ("E001", "Pat Payroll")
        assert (row["Overtime approved hours"], row["Overtime paid hours"]) == ("2.00", "1.00")
        assert Decimal(row["Overtime amount (R)"]) == half
        assert (row["Standby days"], row["Standby allowance (R)"]) == ("1", "150.00")
        assert row["Call-out hours"] == "0.50"
        total = Decimal(row["Total extra pay (R)"])
        assert total == half + Decimal("150.00") + Decimal(row["Call-out amount (R)"])

    def test_overtime_not_yet_reconciled_is_flagged_and_paid_as_approved(self) -> None:
        e1 = person("E001")
        pay(e1)
        day = a_weekday_back()
        r = approved_past(e1, day)
        row = rows(Role.PLANNER, month_of(day))[0]
        assert (row["Overtime not yet reconciled"], row["Overtime paid hours"]) == ("1", "2.00")
        assert Decimal(row["Overtime amount (R)"]) == cost_of(r)

    def test_a_missing_salary_is_counted_not_paid_as_nothing_silently(self) -> None:
        e1 = person("E001")
        day = a_weekday_back()
        approved_past(e1, day)
        row = rows(Role.PLANNER, month_of(day))[0]
        assert row["Overtime without a salary on file"] == "1"
        assert row["Overtime amount (R)"] == "0.00"

    def test_rostered_hours_come_from_published_rosters_only(self) -> None:
        # Failure caught: a draft roster paid as if it had been worked.
        e1 = person("E001")
        d1 = standard_shifts()["D1"]
        day = a_weekday_back()
        week = RosterWeek.objects.create(
            queue=queue(), week_start=day - timedelta(days=day.weekday()), status=RosterStatus.DRAFT
        )
        ShiftAssignment.objects.create(roster_week=week, employee=e1, day=day, template=d1)
        assert rows(Role.PLANNER, month_of(day)) == []
        RosterWeek.objects.filter(pk=week.pk).update(status=RosterStatus.PUBLISHED)
        assert rows(Role.PLANNER, month_of(day))[0]["Rostered hours"] == "8.00"

    def test_leave_is_counted_in_working_days_by_kind_inside_the_month(self) -> None:
        # Failure caught: a request across two months charged wholly to one, or weekends counted.
        e1 = person("E001")
        admin = User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[0]
        LeaveRequest.objects.create(
            employee=e1,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=date(2031, 2, 27),  # Thursday
            end_date=date(2031, 3, 4),  # Tuesday
            days=4,
            status=LeaveStatus.APPROVED,
            requested_by=admin,
        )
        row = rows(Role.PLANNER, "2031-03-01")[0]
        assert row["Leave: Annual leave (days)"] == "2"  # Mon 3 and Tue 4 March
        assert rows(Role.PLANNER, "2031-02-01")[0]["Leave: Annual leave (days)"] == "2"

    def test_people_with_nothing_in_the_month_are_left_out(self) -> None:
        person("E001")
        assert rows(Role.PLANNER, "2031-03-01") == []


class TestSafety:
    def test_a_name_that_is_a_formula_cannot_run_in_a_spreadsheet(self) -> None:
        # Failure caught: a person named "=HYPERLINK(...)" executing when payroll opens the file.
        e1 = person("E001", name='=HYPERLINK("http://evil")')
        pay(e1)
        day = a_weekday_back()
        approved_past(e1, day)
        text = file(Role.PLANNER, month_of(day)).content.decode()
        assert "'=HYPERLINK" in text
        assert ",=HYPERLINK" not in text

    def test_the_export_is_audited_with_a_row_count_and_no_contents(self) -> None:
        e1 = person("E001", name="Pat Payroll")
        pay(e1)
        day = a_weekday_back()
        r = approved_past(e1, day)
        file(Role.ADMIN, month_of(day))
        event = AuditEvent.objects.get(action=Action.PAYROLL_EXPORTED)
        changes = list(AuditChange.objects.filter(event=event).values_list("field", "new_value"))
        assert changes == [("rows", "1")]
        everything = " ".join(str(c) for c in AuditChange.objects.filter(event=event).values())
        assert "Pat Payroll" not in everything
        assert str(cost_of(r)) not in everything
        assert event.actor_role == "admin"

    def test_a_bad_month_is_refused_not_guessed(self) -> None:
        assert client(Role.PLANNER).get(URL, {"month": "March"}).status_code == 422
        assert client(Role.PLANNER).get(URL).status_code == 422


def test_today_is_a_sane_default_month_to_ask_for() -> None:
    # The screen asks for the current month first; it must work on an empty database.
    assert file(Role.PLANNER, month_of(timezone.localdate())).status_code == 200
