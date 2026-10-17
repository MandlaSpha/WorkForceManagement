"""Reconciling worked against approved overtime (OT-03), the month summary, rates and budget, and
the standby rota with call-outs (OT-02): who may do what, that money is worked out once and never
leaks, and that the rules around it cannot be bypassed."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.notifications.models import Notification
from wfm.overtime.models import (
    EmployeePay,
    OvertimeBudget,
    OvertimeRequest,
    StandbyShift,
    StandbyStatus,
)
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import Employee
from wfm.scheduling.tests.helpers import person, standard_shifts

from .test_overtime_api import REQUESTS, SALARY, act, ask, client, pay

pytestmark = pytest.mark.django_db

SUMMARY = "/api/v1/overtime/summary"
RATES = "/api/v1/overtime/rates"
STANDBY = "/api/v1/overtime/standby"
ALL_ROLES = [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS, Role.LEAD]


@pytest.fixture(autouse=True)
def _shifts() -> None:
    standard_shifts()


def a_weekday_back(days: int = 3) -> date:
    """A Monday to Friday that is not a public holiday, a few days ago (so it has happened)."""
    from wfm.people.calendar import public_holidays

    day = timezone.localdate() - timedelta(days=days)
    while day.weekday() > 4 or day in public_holidays(day, day):
        day -= timedelta(days=1)
    return day


def approved_past(employee: Employee, day: date | None = None) -> OvertimeRequest:
    """Two hours of overtime on a day that has passed, asked for and approved."""
    day = day or a_weekday_back()
    made = ask(client(Role.PLANNER), employee, day)
    assert made.status_code == 201, made.content
    assert act(client(Role.ADMIN), made.json()["id"], "approve").status_code == 200
    return OvertimeRequest.objects.get(pk=made.json()["id"])


def cost_of(r: OvertimeRequest) -> Decimal:
    assert r.approved_cost is not None
    return Decimal(r.approved_cost)


def worked(c: Any, request_id: int, minutes: int) -> Any:
    return c.post(
        f"{REQUESTS}/{request_id}/worked", {"minutes": minutes}, content_type="application/json"
    )


def put(c: Any, path: str, body: dict[str, Any]) -> Any:
    return c.put(path, body, content_type="application/json")


class TestRecordingWhatWasWorked:
    def test_worked_time_is_paid_in_proportion_to_the_approved_price(self) -> None:
        # Failure caught: paying the whole approval for part of the time, or re-pricing it.
        e1 = person("E001")
        pay(e1)
        r = approved_past(e1)
        body = worked(client(Role.PLANNER), r.pk, 90).json()
        assert (body["workedMinutes"], body["paidMinutes"], body["extraMinutes"]) == (90, 90, 0)
        expected = (cost_of(r) * 90 / 120).quantize(Decimal("0.01"))
        assert Decimal(str(body["workedCostRands"])) == expected

    def test_time_beyond_the_approval_is_shown_but_not_paid(self) -> None:
        # Failure caught: overtime nobody approved being paid because somebody typed it in.
        e1 = person("E001")
        pay(e1)
        r = approved_past(e1)
        body = worked(client(Role.PLANNER), r.pk, 150).json()
        assert (body["workedMinutes"], body["paidMinutes"], body["extraMinutes"]) == (150, 120, 30)
        assert Decimal(str(body["workedCostRands"])) == cost_of(r)

    def test_a_later_change_of_pay_does_not_reprice_what_was_approved(self) -> None:
        # Failure caught: a raise applied backwards to overtime already agreed at the old rate.
        e1 = person("E001")
        pay(e1)
        r = approved_past(e1)
        EmployeePay.objects.filter(employee=e1).update(monthly_salary=SALARY * 3)
        body = worked(client(Role.PLANNER), r.pk, 120).json()
        assert Decimal(str(body["workedCostRands"])) == cost_of(r)

    def test_it_can_be_corrected_and_the_audit_event_holds_no_money(self) -> None:
        e1 = person("E001")
        pay(e1)
        r = approved_past(e1)
        worked(client(Role.PLANNER), r.pk, 60)
        worked(client(Role.ADMIN), r.pk, 100)
        r.refresh_from_db()
        assert r.worked_minutes == 100
        events = AuditEvent.objects.filter(action=Action.OVERTIME_WORKED_RECORDED).order_by(
            "chain_seq"
        )
        assert events.count() == 2
        changes = list(
            AuditChange.objects.filter(event__in=events).values_list("old_value", "new_value")
        )
        assert changes == [(None, "60"), ("60", "100")]
        everything = " ".join(str(c) for c in AuditChange.objects.all().values())
        assert str(cost_of(r)) not in everything

    def test_only_approved_overtime_that_has_happened_can_be_reconciled(self) -> None:
        # Failure caught: worked time recorded for overtime that was never approved, or has not
        # happened yet.
        e1 = person("E001")
        pay(e1)
        waiting = ask(client(Role.PLANNER), e1, a_weekday_back(5)).json()
        assert worked(client(Role.PLANNER), waiting["id"], 60).status_code == 409
        future = approved_past(e1, a_weekday_back(1) + timedelta(days=14))
        r = worked(client(Role.PLANNER), future.pk, 60)
        assert (r.status_code, r.json()["code"]) == (409, "overtime.not_yet")

    @pytest.mark.parametrize("minutes", [-1, 721])
    def test_a_silly_duration_is_refused(self, minutes: int) -> None:
        e1 = person("E001")
        pay(e1)
        r = approved_past(e1)
        assert worked(client(Role.PLANNER), r.pk, minutes).status_code == 422

    def test_nobody_records_their_own(self) -> None:
        # Failure caught: a person marking their own overtime as fully worked.
        user = User.objects.create(username="u-planner-self", role=Role.PLANNER)
        mine = person("E001", user=user)
        pay(mine)
        r = approved_past(mine)
        c = client(Role.PLANNER, "u-planner-self")
        refused = worked(c, r.pk, 60)
        assert (refused.status_code, refused.json()["code"]) == (403, "overtime.own_request")

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_other_roles_cannot_record(self, role: Role) -> None:
        e1 = person("E001")
        pay(e1)
        r = approved_past(e1)
        assert worked(client(role), r.pk, 60).status_code == 403
        r.refresh_from_db()
        assert r.worked_minutes is None

    def test_a_lead_sees_the_worked_time_but_never_the_rands(self) -> None:
        e1 = person("E001")
        pay(e1)
        lead_of(e1)
        r = approved_past(e1)
        worked(client(Role.PLANNER), r.pk, 90)
        row = client(Role.LEAD).get(REQUESTS).json()[0]
        assert (row["workedMinutes"], row["workedCostRands"], row["costRands"]) == (90, None, None)


class TestMonthSummaryRatesAndBudget:
    def test_the_month_adds_up_overtime_standby_and_call_outs(self) -> None:
        # Failure caught: a total that double counts, or counts approved time that was later
        # reconciled to less.
        admin = client(Role.ADMIN)
        put(admin, RATES, {"standbyAllowance": 150})
        e1, e2 = person("E001"), person("E002")
        pay(e1)
        pay(e2)
        day = a_weekday_back()
        done = approved_past(e1, day)
        worked(client(Role.PLANNER), done.pk, 60)  # half of it
        open_ = approved_past(e2, day)  # approved, not yet reconciled
        stand = (
            client(Role.PLANNER)
            .post(STANDBY, {"employeeId": e1.pk, "day": str(day)}, content_type="application/json")
            .json()
        )
        client(Role.PLANNER).post(
            f"{STANDBY}/{stand['id']}/call-out", {"minutes": 30}, content_type="application/json"
        )
        s = client(Role.PLANNER).get(SUMMARY, {"month": str(day.replace(day=1))}).json()
        half = (cost_of(done) / 2).quantize(Decimal("0.01"))
        call_out = StandbyShift.objects.get().call_out_cost or Decimal(0)
        assert (s["approved"], s["unreconciled"], s["workedMinutes"]) == (2, 1, 60)
        assert Decimal(str(s["overtimeCostRands"])) == half + cost_of(open_)
        assert (s["standbyDays"], s["standbyAllowancesRands"], s["callOutMinutes"]) == (1, 150, 30)
        assert Decimal(str(s["callOutCostRands"])) == call_out
        assert Decimal(str(s["totalRands"])) == half + cost_of(open_) + Decimal(150) + call_out

    def test_the_budget_shows_beside_the_total_and_only_the_admin_sets_it(self) -> None:
        day = a_weekday_back()
        month = str(day.replace(day=1))
        admin = client(Role.ADMIN)
        assert put(admin, f"/api/v1/overtime/budget/{month}", {"amount": 5000}).status_code == 200
        assert client(Role.PLANNER).get(SUMMARY, {"month": month}).json()["budgetRands"] == 5000
        refused = put(client(Role.PLANNER), f"/api/v1/overtime/budget/{month}", {"amount": 1})
        assert refused.status_code == 403
        assert OvertimeBudget.objects.get().amount == Decimal("5000.00")
        put(admin, f"/api/v1/overtime/budget/{month}", {"amount": None})
        assert not OvertimeBudget.objects.exists()
        assert put(admin, f"/api/v1/overtime/budget/{month}", {"amount": -5}).status_code == 422

    def test_a_budget_change_is_audited_without_the_amount(self) -> None:
        month = str(a_weekday_back().replace(day=1))
        put(client(Role.ADMIN), f"/api/v1/overtime/budget/{month}", {"amount": 123456})
        event = AuditEvent.objects.get(action=Action.OVERTIME_BUDGET_CHANGED)
        assert "123456" not in " ".join(
            str(c) for c in AuditChange.objects.filter(event=event).values()
        )

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_only_planner_and_admin_read_the_summary(self, role: Role) -> None:
        # Failure caught: pay totals visible to a lead, an agent or a customer.
        assert client(role).get(SUMMARY, {"month": "2031-03-01"}).status_code == 403
        assert client(Role.PLANNER).get(SUMMARY, {"month": "2031-03-01"}).status_code == 200
        assert client(Role.ADMIN).get(SUMMARY, {"month": "2031-03-01"}).status_code == 200

    def test_the_standby_rate_is_the_admins_and_must_be_sensible(self) -> None:
        assert put(client(Role.PLANNER), RATES, {"standbyAllowance": 100}).status_code == 403
        assert put(client(Role.ADMIN), RATES, {"standbyAllowance": -1}).status_code == 422
        assert put(client(Role.ADMIN), RATES, {"standbyAllowance": 100}).status_code == 200

    def test_a_missing_salary_is_counted_not_priced_as_zero(self) -> None:
        # Failure caught: an unpriced overtime quietly adding R0 and looking cheaper than it is.
        e1 = person("E001")
        r = ask(client(Role.PLANNER), e1, a_weekday_back())
        act(client(Role.ADMIN), r.json()["id"], "approve")
        s = client(Role.PLANNER).get(SUMMARY, {"month": str(a_weekday_back().replace(day=1))})
        assert s.json()["missingPrices"] == 1


def book(c: Any, employee: Employee, day: date) -> Any:
    return c.post(
        STANDBY, {"employeeId": employee.pk, "day": str(day)}, content_type="application/json"
    )


def tomorrow() -> date:
    return timezone.localdate() + timedelta(days=1)


class TestStandby:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planner_and_admin_can_put_anyone_on_standby(self, role: Role) -> None:
        e1 = person("E001")
        assert book(client(role), e1, tomorrow()).status_code == 201

    def test_a_lead_books_their_own_team_and_nobody_else(self) -> None:
        # Failure caught: a lead rostering standby for another lead's people.
        mine, other = person("E001"), person("E002")
        lead_of(mine)
        assert book(client(Role.LEAD), mine, tomorrow()).status_code == 201
        assert book(client(Role.LEAD), other, tomorrow()).status_code == 404

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_cannot(self, role: Role) -> None:
        e1 = person("E001")
        assert book(client(role), e1, tomorrow()).status_code == 403
        assert not StandbyShift.objects.exists()
        assert client(role).get(STANDBY).status_code == 403

    def test_one_booking_a_day_but_a_cancelled_one_can_be_booked_again(self) -> None:
        # Failure caught: two allowances for the same day.
        e1 = person("E001")
        first = book(client(Role.PLANNER), e1, tomorrow())
        again = book(client(Role.PLANNER), e1, tomorrow())
        assert (again.status_code, again.json()["code"]) == (409, "standby.already_booked")
        client(Role.PLANNER).post(f"{STANDBY}/{first.json()['id']}/cancel")
        assert book(client(Role.PLANNER), e1, tomorrow()).status_code == 201
        assert StandbyShift.objects.filter(status=StandbyStatus.BOOKED).count() == 1

    def test_leave_employment_and_the_date_range_are_respected(self) -> None:
        e1 = person("E001", start_date=tomorrow() + timedelta(days=5))
        too_early = book(client(Role.PLANNER), e1, tomorrow())
        assert (too_early.status_code, too_early.json()["code"]) == (422, "standby.not_employed")
        e2 = person("E002")
        LeaveRequest.objects.create(
            employee=e2,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=tomorrow(),
            end_date=tomorrow(),
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=User.objects.get_or_create(
                username="u-admin", defaults={"role": Role.ADMIN}
            )[0],
        )
        assert book(client(Role.PLANNER), e2, tomorrow()).json()["code"] == "standby.on_leave"
        far = timezone.localdate() + timedelta(days=1000)
        assert book(client(Role.PLANNER), e2, far).status_code == 422

    def test_the_allowance_is_fixed_when_booked(self) -> None:
        # Failure caught: a raised allowance rewriting standby already rostered.
        e1 = person("E001")
        put(client(Role.ADMIN), RATES, {"standbyAllowance": 100})
        first = book(client(Role.PLANNER), e1, tomorrow()).json()
        put(client(Role.ADMIN), RATES, {"standbyAllowance": 500})
        second = book(client(Role.PLANNER), e1, tomorrow() + timedelta(days=1)).json()
        assert (first["allowanceRands"], second["allowanceRands"]) == (100, 500)

    def test_only_those_who_see_pay_see_the_allowance(self) -> None:
        # Failure caught: a lead reading what standby pays.
        e1 = person("E001")
        lead_of(e1)
        put(client(Role.ADMIN), RATES, {"standbyAllowance": 100})
        book(client(Role.PLANNER), e1, tomorrow())
        seen_by_lead = client(Role.LEAD).get(STANDBY).json()[0]
        assert (seen_by_lead["allowanceRands"], seen_by_lead["callOutCostRands"]) == (None, None)
        assert client(Role.PLANNER).get(STANDBY).json()[0]["allowanceRands"] == 100

    def test_booking_and_cancelling_notify_the_person_without_money(self) -> None:
        user = User.objects.create(username="u-agent-sb", role=Role.AGENT)
        e1 = person("E001", user=user)
        put(client(Role.ADMIN), RATES, {"standbyAllowance": 987})
        made = book(client(Role.PLANNER), e1, tomorrow()).json()
        client(Role.PLANNER).post(f"{STANDBY}/{made['id']}/cancel")
        messages = list(
            Notification.objects.filter(recipient=user).values_list("message", flat=True)
        )
        assert len(messages) == 2
        assert not any("987" in m or "R " in m for m in messages)

    def test_cancelling_belongs_to_whoever_booked_or_a_planner(self) -> None:
        e1 = person("E001")
        lead_of(e1)
        made = book(client(Role.LEAD), e1, tomorrow()).json()
        other_lead = client(Role.LEAD, "u-lead-other")
        assert other_lead.post(f"{STANDBY}/{made['id']}/cancel").status_code == 404
        assert client(Role.AGENT).post(f"{STANDBY}/{made['id']}/cancel").status_code == 403
        assert client(Role.PLANNER).post(f"{STANDBY}/{made['id']}/cancel").status_code == 200


class TestCallOuts:
    def test_a_call_out_is_priced_like_overtime_on_that_day(self) -> None:
        # Failure caught: a call-out priced at a different rate from overtime for the same hour.
        e1 = person("E001")
        pay(e1)
        day = a_weekday_back()
        stand = book(client(Role.PLANNER), e1, day).json()
        done = (
            client(Role.PLANNER)
            .post(
                f"{STANDBY}/{stand['id']}/call-out",
                {"minutes": 120},
                content_type="application/json",
            )
            .json()
        )
        overtime = approved_past(e1, day - timedelta(days=1) if day.weekday() else day)
        assert done["callOutMinutes"] == 120
        if overtime.day.weekday() < 5:
            assert Decimal(str(done["callOutCostRands"])) == cost_of(overtime)

    def test_it_waits_for_the_day_and_cannot_be_recorded_for_oneself(self) -> None:
        e1 = person("E001")
        pay(e1)
        future = book(client(Role.PLANNER), e1, tomorrow()).json()
        r = client(Role.PLANNER).post(
            f"{STANDBY}/{future['id']}/call-out", {"minutes": 30}, content_type="application/json"
        )
        assert (r.status_code, r.json()["code"]) == (409, "standby.not_yet")
        user = User.objects.create(username="u-planner-me", role=Role.PLANNER)
        mine = person("E002", user=user)
        stand = book(client(Role.PLANNER), mine, a_weekday_back()).json()
        own = client(Role.PLANNER, "u-planner-me").post(
            f"{STANDBY}/{stand['id']}/call-out", {"minutes": 30}, content_type="application/json"
        )
        assert (own.status_code, own.json()["code"]) == (403, "overtime.own_request")

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_other_roles_cannot_record_one(self, role: Role) -> None:
        e1 = person("E001")
        stand = book(client(Role.PLANNER), e1, a_weekday_back()).json()
        r = client(role).post(
            f"{STANDBY}/{stand['id']}/call-out", {"minutes": 30}, content_type="application/json"
        )
        assert r.status_code == 403
        assert StandbyShift.objects.get().call_out_minutes is None

    def test_zero_clears_it_and_a_missing_salary_is_said_not_priced_as_nothing(self) -> None:
        e1 = person("E001")
        stand = book(client(Role.PLANNER), e1, a_weekday_back()).json()
        url = f"{STANDBY}/{stand['id']}/call-out"
        done = (
            client(Role.PLANNER).post(url, {"minutes": 45}, content_type="application/json").json()
        )
        assert (done["callOutCostRands"], done["callOutCostMissing"]) == (None, True)
        cleared = (
            client(Role.PLANNER).post(url, {"minutes": 0}, content_type="application/json").json()
        )
        assert (cleared["callOutMinutes"], cleared["callOutCostMissing"]) == (None, False)

    def test_a_call_out_cannot_be_longer_than_twelve_hours_and_a_standby_with_one_stays(
        self,
    ) -> None:
        e1 = person("E001")
        pay(e1)
        stand = book(client(Role.PLANNER), e1, a_weekday_back()).json()
        url = f"{STANDBY}/{stand['id']}/call-out"
        too_long = client(Role.PLANNER).post(url, {"minutes": 721}, content_type="application/json")
        assert too_long.status_code == 422
        client(Role.PLANNER).post(url, {"minutes": 30}, content_type="application/json")
        # Failure caught: standby that already had a call-out dropped, losing the pay it earned.
        gone = client(Role.PLANNER).post(f"{STANDBY}/{stand['id']}/cancel")
        assert gone.status_code == 409

    def test_no_audit_event_holds_a_rand_figure(self) -> None:
        e1 = person("E001")
        pay(e1)
        put(client(Role.ADMIN), RATES, {"standbyAllowance": 777})
        stand = book(client(Role.PLANNER), e1, a_weekday_back()).json()
        done = (
            client(Role.PLANNER)
            .post(
                f"{STANDBY}/{stand['id']}/call-out",
                {"minutes": 60},
                content_type="application/json",
            )
            .json()
        )
        text = " ".join(str(c) for c in AuditChange.objects.all().values())
        assert "777" not in text
        assert str(done["callOutCostRands"]) not in text
        assert AuditEvent.objects.filter(action=Action.STANDBY_CALL_OUT_RECORDED).count() == 1
