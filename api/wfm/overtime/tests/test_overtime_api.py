"""Overtime (OT-01): who may ask, decide, cancel and see rands; that the roster's rules still hold;
that it is priced from the rules and pay on file; and that no salary leaks anywhere."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.notifications.models import Notification
from wfm.overtime.models import EmployeePay, OvertimeRequest, OvertimeStatus
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import ComplianceRuleVersion, Employee
from wfm.scheduling.tests.helpers import assign, person, queue, standard_shifts

pytestmark = pytest.mark.django_db

REQUESTS = "/api/v1/overtime/requests"
PAY = "/api/v1/overtime/pay"
SALARY = Decimal("17332")  # with 40 contract hours: R100 an hour


def client(role: Role, username: str | None = None) -> Client:
    user, _ = User.objects.get_or_create(
        username=username or f"u-{role.value}", defaults={"role": role}
    )
    c = Client()
    c.force_login(user)
    return c


def monday(weeks: int = 1) -> date:
    today = timezone.localdate()
    return today - timedelta(days=today.weekday()) + timedelta(weeks=weeks)


def sunday(weeks: int = 1) -> date:
    return monday(weeks) + timedelta(days=6)


def ask(
    c: Client, employee: Employee, day: date, start: str = "18:00", end: str = "20:00", **kw: Any
) -> Any:
    body = {
        "employeeId": employee.pk,
        "day": str(day),
        "startTime": start,
        "endTime": end,
        "reason": "",
        **kw,
    }
    return c.post(REQUESTS, body, content_type="application/json")


def act(c: Client, request_id: int, what: str) -> Any:
    return c.post(f"{REQUESTS}/{request_id}/{what}")


def pay(employee: Employee, salary: Decimal = SALARY, sundays: bool = False) -> None:
    EmployeePay.objects.create(
        employee=employee, monthly_salary=salary, ordinarily_works_sundays=sundays
    )


def admin() -> User:
    return User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[0]


def team() -> tuple[Client, Employee, Employee]:
    """A lead (who has an employee record) and one person in their team."""
    lead_client = client(Role.LEAD)
    lead_user = User.objects.get(username="u-lead")
    boss = person("L001", user=lead_user)
    member = person("E001", manager=boss)
    return lead_client, boss, member


@pytest.fixture
def shifts() -> dict[str, Any]:
    return standard_shifts()


class TestWhoMayAsk:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planners_and_admins_ask_for_anybody(self, role: Role) -> None:
        e1 = person()
        response = ask(client(role), e1, monday())
        assert response.status_code == 201, response.content
        assert response.json()["status"] == "pending"

    def test_a_lead_asks_for_their_own_team(self) -> None:
        lead_client, _, member = team()
        assert ask(lead_client, member, monday()).status_code == 201

    def test_a_lead_cannot_ask_for_somebody_outside_their_team(self) -> None:
        # Failure caught: a lead booking overtime (and cost) for another lead's people.
        lead_client, _, _ = team()
        outsider = person("E002")
        response = ask(lead_client, outsider, monday())
        assert response.status_code == 404
        assert OvertimeRequest.objects.count() == 0

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_ask_even_with_a_valid_request(self, role: Role) -> None:
        e1 = person()
        assert ask(client(role), e1, monday()).status_code == 403
        assert OvertimeRequest.objects.count() == 0


class TestWhoSeesWhat:
    def test_a_planner_sees_every_request_with_its_cost(self) -> None:
        e1 = person()
        pay(e1)
        ask(client(Role.PLANNER), e1, monday())
        (row,) = client(Role.PLANNER).get(REQUESTS).json()
        assert row["costRands"] == 300.0  # 2 hours x R100 x 1.5

    def test_a_lead_sees_their_team_only_and_never_a_cost(self) -> None:
        lead_client, _, member = team()
        outsider = person("E002")
        pay(member)
        ask(lead_client, member, monday())
        ask(client(Role.PLANNER), outsider, monday())
        rows = lead_client.get(REQUESTS).json()
        assert [r["empNo"] for r in rows] == ["E001"]
        assert rows[0]["costRands"] is None
        assert rows[0]["costMissing"] is False

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_others_cannot_read_overtime(self, role: Role) -> None:
        assert client(role).get(REQUESTS).status_code == 403

    def test_no_salary_on_file_is_said_not_shown_as_zero(self) -> None:
        # Failure caught: a missing salary priced as R0.
        e1 = person()
        ask(client(Role.PLANNER), e1, monday())
        (row,) = client(Role.PLANNER).get(REQUESTS).json()
        assert (row["costRands"], row["costMissing"]) == (None, True)


class TestPricing:
    def test_weekday_sunday_and_holiday_rates(self) -> None:
        e1 = person()
        pay(e1)
        planner = client(Role.PLANNER)
        ask(planner, e1, monday(), "08:00", "09:00")
        ask(planner, e1, sunday(), "08:00", "09:00")
        today = timezone.localdate()
        holiday = date(today.year, 12, 16)  # Day of Reconciliation
        if holiday < today:
            holiday = date(today.year + 1, 12, 16)
        ask(planner, e1, holiday, "08:00", "09:00")
        rows = {r["kind"]: r["costRands"] for r in planner.get(REQUESTS).json()}
        # Failure caught: the wrong multiplier for the kind of day.
        assert rows == {"weekday": 150.0, "sunday": 200.0, "holiday": 200.0}

    def test_somebody_who_ordinarily_works_sundays_is_paid_the_ordinary_rate(self) -> None:
        e1 = person()
        pay(e1, sundays=True)
        ask(client(Role.PLANNER), e1, sunday(), "08:00", "09:00")
        (row,) = client(Role.PLANNER).get(REQUESTS).json()
        assert row["costRands"] == 150.0

    def test_the_rates_come_from_the_rules_in_force(self) -> None:
        # Failure caught: multipliers hard-coded instead of read from the editable rules.
        e1 = person()
        pay(e1)
        ComplianceRuleVersion.objects.create(
            effective_from=date(2026, 1, 1),
            min_rest_hours=11,
            max_consecutive_days=6,
            overtime_multiplier=Decimal("1.75"),
        )
        ask(client(Role.PLANNER), e1, monday(), "08:00", "09:00")
        (row,) = client(Role.PLANNER).get(REQUESTS).json()
        assert row["costRands"] == 175.0

    def test_part_time_hours_change_the_rate(self) -> None:
        e1 = person(hours=20)
        pay(e1, Decimal("8666"))
        ask(client(Role.PLANNER), e1, monday(), "08:00", "09:00")
        (row,) = client(Role.PLANNER).get(REQUESTS).json()
        assert row["costRands"] == 150.0

    def test_the_price_it_was_approved_at_does_not_change_later(self) -> None:
        # Failure caught: a later change of rules or salary rewriting what was agreed.
        e1 = person()
        pay(e1)
        planner = client(Role.PLANNER)
        created = ask(planner, e1, monday(), "08:00", "09:00").json()
        assert act(planner, created["id"], "approve").json()["costRands"] == 150.0
        ComplianceRuleVersion.objects.create(
            effective_from=date(2026, 1, 1),
            min_rest_hours=11,
            max_consecutive_days=6,
            overtime_multiplier=Decimal("3"),
        )
        EmployeePay.objects.update(monthly_salary=Decimal("99999"))
        (row,) = planner.get(REQUESTS).json()
        assert row["costRands"] == 150.0


class TestRosterRulesStillHold:
    def test_overtime_beside_a_shift_is_fine_but_not_on_top_of_it(
        self, shifts: dict[str, Any]
    ) -> None:
        e1 = person()
        day = monday()
        assign(client(Role.PLANNER), queue(), e1, day, shifts["D1"])  # 09:00 to 17:30
        planner = client(Role.PLANNER)
        assert ask(planner, e1, day, "17:30", "19:30").status_code == 201  # extends the day
        overlap = ask(planner, e1, day, "16:00", "18:00")
        assert (overlap.status_code, overlap.json()["code"]) == (409, "overtime.overlap")

    def test_overlapping_other_overtime_is_refused(self) -> None:
        e1 = person()
        planner = client(Role.PLANNER)
        ask(planner, e1, monday(), "18:00", "20:00")
        assert ask(planner, e1, monday(), "19:00", "21:00").json()["code"] == "overtime.overlap"

    def test_the_rest_between_days_is_kept(self, shifts: dict[str, Any]) -> None:
        # Failure caught: overtime late one night and a shift early the next morning.
        e1 = person()
        day = monday()
        assign(client(Role.PLANNER), queue(), e1, day + timedelta(days=1), shifts["E1"])  # 07:00
        response = ask(client(Role.PLANNER), e1, day, "18:00", "23:00")  # 8 h before 07:00
        assert (response.status_code, response.json()["code"]) == (409, "overtime.rest_period")

    def test_a_person_on_approved_leave_is_refused(self) -> None:
        e1 = person()
        LeaveRequest.objects.create(
            employee=e1,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=monday(),
            end_date=monday(),
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=admin(),
        )
        response = ask(client(Role.PLANNER), e1, monday())
        assert (response.status_code, response.json()["code"]) == (409, "overtime.on_leave")

    def test_a_seventh_day_in_a_row_is_refused(self, shifts: dict[str, Any]) -> None:
        e1 = person(hours=60)
        start = monday()
        for n in range(6):
            assign(client(Role.PLANNER), queue(), e1, start + timedelta(days=n), shifts["D1"])
        response = ask(client(Role.PLANNER), e1, start + timedelta(days=6), "08:00", "10:00")
        assert response.json()["code"] == "overtime.too_many_days"

    def test_the_weekly_cap_in_the_rules_limits_overtime(self, shifts: dict[str, Any]) -> None:
        e1 = person()
        start = monday()
        for n in range(5):
            assign(client(Role.PLANNER), queue(), e1, start + timedelta(days=n), shifts["D1"])
        # 40 h rostered, no cap: overtime on the weekend is fine.
        assert (
            ask(client(Role.PLANNER), e1, start + timedelta(days=5), "08:00", "10:00").status_code
            == 201
        )
        ComplianceRuleVersion.objects.create(
            effective_from=date(2026, 1, 1),
            min_rest_hours=11,
            max_consecutive_days=6,
            max_weekly_hours=41,
        )
        refused = ask(client(Role.PLANNER), e1, start + timedelta(days=5), "12:00", "13:30")
        assert refused.json()["code"] == "overtime.over_weekly_cap"

    @pytest.mark.parametrize(
        ("kwargs", "code"),
        [
            ({"start": "20:00", "end": "18:00"}, "overtime.times_invalid"),
            ({"start": "06:00", "end": "20:00"}, "overtime.too_long"),
            ({"reason": "x" * 201}, "overtime.reason_too_long"),
        ],
    )
    def test_nonsense_is_refused_and_stores_nothing(
        self, kwargs: dict[str, str], code: str
    ) -> None:
        e1 = person()
        response = ask(client(Role.PLANNER), e1, monday(), **kwargs)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert OvertimeRequest.objects.count() == 0

    @pytest.mark.parametrize("offset", [-60, 400])
    def test_days_too_far_back_or_ahead_are_refused(self, offset: int) -> None:
        e1 = person()
        day = timezone.localdate() + timedelta(days=offset)
        assert ask(client(Role.PLANNER), e1, day).json()["code"] == "overtime.date_out_of_range"

    def test_somebody_not_yet_employed_is_refused(self) -> None:
        e1 = person(start_date=monday() + timedelta(days=30))
        assert ask(client(Role.PLANNER), e1, monday()).json()["code"] == "overtime.not_employed"


class TestDeciding:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planners_and_admins_approve_and_reject(self, role: Role) -> None:
        e1 = person()
        first = ask(client(Role.PLANNER), e1, monday(), "08:00", "09:00").json()
        second = ask(client(Role.PLANNER), e1, monday(), "18:00", "19:00").json()
        assert act(client(role), first["id"], "approve").json()["status"] == "approved"
        assert act(client(role), second["id"], "reject").json()["status"] == "rejected"

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_decides(self, role: Role) -> None:
        # Failure caught: a lead approving the overtime (and cost) they asked for themselves.
        e1 = person()
        created = ask(client(Role.PLANNER), e1, monday()).json()
        assert act(client(role), created["id"], "approve").status_code == 403
        assert OvertimeRequest.objects.get().status == OvertimeStatus.PENDING

    def test_nobody_decides_their_own_overtime(self) -> None:
        mine = person(
            "E001",
            user=User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[
                0
            ],
        )
        created = ask(client(Role.ADMIN), mine, monday()).json()
        response = act(client(Role.PLANNER), created["id"], "approve")
        assert (response.status_code, response.json()["code"]) == (403, "overtime.own_request")

    def test_a_request_is_decided_once(self) -> None:
        e1 = person()
        created = ask(client(Role.PLANNER), e1, monday()).json()
        act(client(Role.PLANNER), created["id"], "approve")
        again = act(client(Role.PLANNER), created["id"], "reject")
        assert (again.status_code, again.json()["code"]) == (409, "overtime.not_pending")

    def test_approval_checks_the_rules_again(self) -> None:
        # Failure caught: leave approved after the request was made, and overtime approved anyway.
        e1 = person()
        created = ask(client(Role.PLANNER), e1, monday()).json()
        LeaveRequest.objects.create(
            employee=e1,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=monday(),
            end_date=monday(),
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=admin(),
        )
        response = act(client(Role.PLANNER), created["id"], "approve")
        assert (response.status_code, response.json()["code"]) == (409, "overtime.on_leave")
        assert OvertimeRequest.objects.get().status == OvertimeStatus.PENDING

    def test_an_unknown_request_is_a_404(self) -> None:
        assert act(client(Role.PLANNER), 999999, "approve").status_code == 404


class TestCancelling:
    def test_whoever_asked_can_cancel_and_others_cannot(self) -> None:
        lead_client, _, member = team()
        created = ask(lead_client, member, monday()).json()
        other_lead = client(Role.LEAD, "other-lead")
        assert act(other_lead, created["id"], "cancel").status_code == 404
        assert act(lead_client, created["id"], "cancel").json()["status"] == "cancelled"

    def test_a_planner_can_cancel_an_approved_request(self) -> None:
        e1 = person()
        pay(e1)
        created = ask(client(Role.PLANNER), e1, monday()).json()
        act(client(Role.PLANNER), created["id"], "approve")
        done = act(client(Role.ADMIN), created["id"], "cancel").json()
        assert (done["status"], done["costRands"]) == ("cancelled", None)

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_cancel(self, role: Role) -> None:
        e1 = person()
        created = ask(client(Role.PLANNER), e1, monday()).json()
        assert act(client(role), created["id"], "cancel").status_code == 403

    def test_overtime_that_has_happened_cannot_be_cancelled(self) -> None:
        e1 = person()
        yesterday = timezone.localdate() - timedelta(days=1)
        past = OvertimeRequest.objects.create(
            employee=e1,
            day=yesterday,
            start_time="18:00",
            end_time="20:00",
            minutes=120,
            status=OvertimeStatus.APPROVED,
            requested_by=admin(),
        )
        response = act(client(Role.PLANNER), past.pk, "cancel")
        assert (response.status_code, response.json()["code"]) == (409, "overtime.past")


class TestPay:
    def test_only_the_admin_sets_pay_even_with_a_valid_request(self) -> None:
        e1 = person()
        body = {"monthlySalary": 17332, "ordinarilyWorksSundays": False}
        for role in (Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
            response = client(role).put(f"{PAY}/{e1.pk}", body, content_type="application/json")
            assert response.status_code == 403
            assert client(role).get(PAY).status_code == 403
        assert EmployeePay.objects.count() == 0

    def test_the_admin_sets_and_clears_it_and_the_figure_is_never_returned(self) -> None:
        # Failure caught: a salary readable through the API.
        e1 = person()
        admin_client = client(Role.ADMIN)
        body = {"monthlySalary": 17332.55, "ordinarilyWorksSundays": True}
        put = admin_client.put(f"{PAY}/{e1.pk}", body, content_type="application/json")
        assert put.json() == {
            "employeeId": e1.pk,
            "employee": e1.name,
            "empNo": e1.emp_no,
            "hasSalary": True,
            "ordinarilyWorksSundays": True,
        }
        assert "17332" not in put.content.decode()
        assert "17332" not in admin_client.get(PAY).content.decode()
        assert EmployeePay.objects.get().monthly_salary == Decimal("17332.55")
        # Leaving the salary out changes only the Sunday flag: it never wipes the salary.
        flag = admin_client.put(
            f"{PAY}/{e1.pk}", {"ordinarilyWorksSundays": False}, content_type="application/json"
        )
        assert (flag.json()["hasSalary"], flag.json()["ordinarilyWorksSundays"]) == (True, False)
        assert EmployeePay.objects.get().monthly_salary == Decimal("17332.55")
        cleared = admin_client.put(
            f"{PAY}/{e1.pk}", {"clear": True}, content_type="application/json"
        )
        assert cleared.json()["hasSalary"] is False
        assert EmployeePay.objects.count() == 0

    def test_changing_the_flag_with_no_salary_on_file_is_refused(self) -> None:
        e1 = person()
        response = client(Role.ADMIN).put(
            f"{PAY}/{e1.pk}", {"ordinarilyWorksSundays": True}, content_type="application/json"
        )
        assert (response.status_code, response.json()["code"]) == (422, "pay.no_salary")

    @pytest.mark.parametrize("bad", [0, -5, 2_000_000])
    def test_a_nonsense_salary_is_refused(self, bad: float) -> None:
        e1 = person()
        response = client(Role.ADMIN).put(
            f"{PAY}/{e1.pk}", {"monthlySalary": bad}, content_type="application/json"
        )
        assert (response.status_code, response.json()["code"]) == (422, "pay.invalid")

    def test_an_unknown_employee_is_a_404(self) -> None:
        response = client(Role.ADMIN).put(
            f"{PAY}/999999", {"monthlySalary": 1000}, content_type="application/json"
        )
        assert response.status_code == 404


class TestNothingLeaks:
    def test_no_salary_or_rand_figure_reaches_the_audit_trail_or_notifications(self) -> None:
        # Failure caught: a pay figure copied into an audit change, a notification or a reason.
        client(Role.AGENT)
        e1 = person("E001", user=User.objects.get(username="u-agent"))
        client(Role.ADMIN).put(
            f"{PAY}/{e1.pk}",
            {"monthlySalary": 12345.67},
            content_type="application/json",
        )
        planner = client(Role.PLANNER)
        created = ask(planner, e1, monday(), "08:00", "09:00").json()
        act(planner, created["id"], "approve")
        text = " ".join(f"{c.old_value} {c.new_value} {c.field}" for c in AuditChange.objects.all())
        text += " ".join(f"{e.reason} {e.entity_id}" for e in AuditEvent.objects.all())
        text += " ".join(n.message for n in Notification.objects.all())
        for secret in ("12345", "12 345", "185", "R1"):  # the salary and the cost, however written
            assert secret not in text

    def test_every_change_is_audited_with_who(self) -> None:
        e1 = person()
        planner = client(Role.PLANNER)
        created = ask(planner, e1, monday()).json()
        act(planner, created["id"], "approve")
        actions = list(AuditEvent.objects.order_by("id").values_list("action", flat=True))
        assert actions == [Action.OVERTIME_REQUESTED, Action.OVERTIME_APPROVED]
        assert AuditEvent.objects.get(action=Action.OVERTIME_APPROVED).actor_role == Role.PLANNER


class TestNotifications:
    def test_approvers_are_told_a_request_is_waiting_but_not_the_one_who_asked(self) -> None:
        e1 = person()
        planner_client = client(Role.PLANNER)
        client(Role.ADMIN)
        ask(planner_client, e1, monday())
        told = {
            n.recipient.username for n in Notification.objects.filter(kind="overtime.requested")
        }
        assert told == {"u-admin"}
        assert Notification.objects.get().message == "An overtime request is waiting for approval."

    def test_the_person_is_told_of_the_decision_without_a_name_or_an_amount(self) -> None:
        client(Role.AGENT)
        e1 = person("E001", user=User.objects.get(username="u-agent"))
        pay(e1)
        planner = client(Role.PLANNER)
        created = ask(planner, e1, monday(), "08:00", "09:00").json()
        act(planner, created["id"], "approve")
        mine = Notification.objects.get(recipient__username="u-agent", kind="overtime.approved")
        assert mine.message == f"Your overtime on {monday():%a %d %b} was approved."
        assert mine.link == ""  # an agent has no overtime screen to open
