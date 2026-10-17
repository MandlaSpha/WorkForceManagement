"""Right to erasure (POPIA): admin only, two steps, refuses anyone still working or waiting,
removes what identifies a person and keeps what the aggregates need. Audit rows stay untouched."""

from __future__ import annotations

import json
from datetime import date, time
from typing import Any

import pytest
from django.apps import apps
from django.db import models
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.integrity import verify_chain
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.notifications.models import Notification
from wfm.overtime.models import EmployeePay, OvertimeRequest, StandbyShift
from wfm.people.models import (
    Availability,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    SwapRequest,
    SwapStatus,
)
from wfm.scheduling.models import AgentLogin, Employee, RosterWeek, ShiftAssignment, ShiftTemplate
from wfm.scheduling.tests.helpers import person, queue, standard_shifts

pytestmark = pytest.mark.django_db

NAME = "Pat Leaverson"
NUMBER = "E777"
LOGIN = "pleaverson"
USERNAME = "pat.leaverson"
REASON = "Pat needs the money for a wedding"
PAST = date(2025, 1, 6)  # a Monday long gone
FUTURE = date(2099, 1, 5)


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def preview_url(pk: int) -> str:
    return f"/api/v1/people/employees/{pk}/erasure-request"


def anonymise_url(pk: int) -> str:
    return f"/api/v1/people/employees/{pk}/anonymise"


def confirm(pk: int, typed: str, role: Role = Role.ADMIN) -> Any:
    return client(role).post(
        anonymise_url(pk), {"employeeNumber": typed}, content_type="application/json"
    )


def admin() -> User:
    return User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[0]


def leaver(**fields: Any) -> Employee:
    """Someone who left in 2025, with a login and a little of everything held about them."""
    user = User.objects.create(
        username=USERNAME, first_name="Pat", last_name="Leaverson", email="pat@example.test"
    )
    user.set_password("a-long-secret-password")
    user.save()
    e = person(NUMBER, name=NAME, user=user, end_date=date(2025, 1, 31), **fields)
    shifts = standard_shifts()
    week = RosterWeek.objects.create(queue=queue(), week_start=PAST)
    ShiftAssignment.objects.create(roster_week=week, employee=e, day=PAST, template=shifts["D1"])
    AgentLogin.objects.create(login=LOGIN, employee=e)
    Availability.objects.create(
        employee=e,
        weekday=0,
        start_time=time(8),
        end_time=time(12),
        kind="unavailable",
        created_by=admin(),
    )
    Notification.objects.create(recipient=user, kind="x", message="Hello Pat Leaverson")
    EmployeePay.objects.create(employee=e, monthly_salary=12345)
    OvertimeRequest.objects.create(
        employee=e,
        day=PAST,
        start_time=time(18),
        end_time=time(20),
        minutes=120,
        reason=REASON,
        status="approved",
        approved_cost=300,
        worked_minutes=90,
        requested_by=admin(),
    )
    StandbyShift.objects.create(
        employee=e, day=PAST, status="booked", call_out_minutes=45, booked_by=admin()
    )
    LeaveRequest.objects.create(
        employee=e,
        leave_type=LeaveType.objects.get(code="annual"),
        start_date=PAST,
        end_date=PAST,
        days=1,
        status=LeaveStatus.APPROVED,
        requested_by=admin(),
    )
    return e


def anonymised(e: Employee) -> Employee:
    assert confirm(e.pk, NUMBER).status_code == 200
    return Employee.objects.get(pk=e.pk)


def every_text_in_the_database() -> str:
    """All text columns of all tables (sessions aside), as one string to search."""
    parts: list[str] = []
    for model in apps.get_models():
        if model._meta.label == "sessions.Session":
            continue
        names = [
            f.name
            for f in model._meta.get_fields()
            if isinstance(f, (models.CharField, models.TextField))
        ]
        for name in names:
            parts.extend(str(v) for v in model._default_manager.values_list(name, flat=True) if v)
    return "\n".join(parts)


class TestWhoMayDoIt:
    @pytest.mark.parametrize(
        "role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
    )
    def test_nobody_but_the_admin(self, role: Role) -> None:
        # Failure caught: a planner or the person's lead erasing a colleague's record.
        e = leaver()
        assert client(role).post(preview_url(e.pk)).status_code == 403
        assert confirm(e.pk, NUMBER, role).status_code == 403
        assert client(role).get("/api/v1/people/retention").status_code == 403
        assert Employee.objects.get(pk=e.pk).name == NAME

    def test_signed_out_is_refused(self) -> None:
        e = leaver()
        assert Client().post(preview_url(e.pk)).status_code in (401, 403)

    def test_an_unknown_employee_is_not_found(self) -> None:
        # Failure caught: telling an admin whether an id exists elsewhere / a 500.
        assert client(Role.ADMIN).post(preview_url(99999)).status_code == 404
        assert confirm(99999, NUMBER).status_code == 404


class TestTheTwoSteps:
    def test_the_request_says_what_goes_and_what_stays_and_changes_nothing(self) -> None:
        e = leaver()
        r = client(Role.ADMIN).post(preview_url(e.pk))
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["removes"] == {
            "agentLogins": 1,
            "callRecordLogins": 0,
            "offerLogins": 0,
            "transferLogins": 0,
            "availabilityWindows": 1,
            "credentials": 0,
            "notifications": 1,
            "overtimeReasons": 1,
            "payRecords": 1,
            "qualityResults": 0,
            "signInLinks": 1,
        }
        assert body["keeps"] == {
            "shifts": 1,
            "leaveRequests": 1,
            "overtimeRequests": 1,
            "standbyShifts": 1,
        }
        assert NAME not in r.content.decode()
        assert Employee.objects.get(pk=e.pk).name == NAME
        assert not AuditEvent.objects.filter(action=Action.EMPLOYEE_ANONYMISED).exists()

    def test_a_wrong_typed_number_does_nothing(self) -> None:
        # Failure caught: anonymising by accident, or a confirm that ignores the typed number.
        e = leaver()
        r = confirm(e.pk, "E778")
        assert r.status_code == 422
        assert r.json()["code"] == "erasure.confirmation_mismatch"
        assert confirm(e.pk, "").status_code == 422
        assert Employee.objects.get(pk=e.pk).name == NAME
        assert AgentLogin.objects.filter(login=LOGIN).exists()

    def test_a_second_call_is_a_clear_conflict(self) -> None:
        # Failure caught: anonymising twice, giving the same person a second audit event.
        e = leaver()
        anonymised(e)
        again = confirm(e.pk, NUMBER)
        assert again.status_code == 409
        assert again.json()["code"] == "erasure.already_anonymised"
        assert client(Role.ADMIN).post(preview_url(e.pk)).status_code == 409
        assert AuditEvent.objects.filter(action=Action.EMPLOYEE_ANONYMISED).count() == 1


class TestRefusals:
    def test_someone_still_employed_is_refused(self) -> None:
        # Failure caught: erasing a current employee.
        e = leaver()
        e.end_date = None
        e.save()
        r = confirm(e.pk, NUMBER)
        assert (r.status_code, r.json()["code"]) == (409, "erasure.not_left")
        e.end_date = date(2099, 1, 1)
        e.save()
        assert confirm(e.pk, NUMBER).json()["code"] == "erasure.not_left"
        assert Employee.objects.get(pk=e.pk).name == NAME

    def test_a_future_shift_is_refused_with_a_reason(self) -> None:
        # Failure caught: erasing someone who is still on the roster.
        e = leaver()
        week = RosterWeek.objects.create(queue=queue(), week_start=FUTURE)
        ShiftAssignment.objects.create(
            roster_week=week, employee=e, day=FUTURE, template=ShiftTemplate.objects.get(code="D1")
        )
        r = confirm(e.pk, NUMBER)
        assert (r.status_code, r.json()["code"]) == (409, "erasure.future_work")
        assert "future" in r.json()["detail"]

    def test_future_leave_is_refused(self) -> None:
        e = leaver()
        LeaveRequest.objects.create(
            employee=e,
            leave_type=LeaveType.objects.get(code="annual"),
            start_date=FUTURE,
            end_date=FUTURE,
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=admin(),
        )
        assert confirm(e.pk, NUMBER).json()["code"] == "erasure.future_work"

    def test_a_pending_request_is_refused(self) -> None:
        # Failure caught: erasing someone whose request a lead is about to decide.
        e = leaver()
        OvertimeRequest.objects.create(
            employee=e,
            day=PAST,
            start_time=time(6),
            end_time=time(7),
            minutes=60,
            status="pending",
            requested_by=admin(),
        )
        assert confirm(e.pk, NUMBER).json()["code"] == "erasure.pending_requests"

    def test_an_open_swap_is_refused(self) -> None:
        e = leaver()
        other = person("E002")
        SwapRequest.objects.create(
            queue=queue(),
            from_employee=other,
            from_day=PAST,
            from_template=ShiftTemplate.objects.get(code="D1"),
            to_employee=e,
            status=SwapStatus.OPEN,
            requested_by=admin(),
        )
        assert confirm(e.pk, NUMBER).json()["code"] == "erasure.pending_requests"

    def test_the_admin_cannot_anonymise_their_own_login(self) -> None:
        # Failure caught: an admin locking themselves out of the system.
        me = admin()
        e = person("E900", name="Admin Self", user=me, end_date=date(2025, 1, 1))
        r = confirm(e.pk, "E900")
        assert (r.status_code, r.json()["code"]) == (409, "erasure.own_login")
        me.refresh_from_db()
        assert me.is_active


class TestWhatItDoes:
    def test_nothing_of_the_old_identity_is_left_anywhere(self) -> None:
        # Failure caught: a name, number, username or login surviving in a table, a list or the
        # subject-access file after the person was anonymised.
        e = leaver()
        before = every_text_in_the_database()
        for needle in (NAME, NUMBER, LOGIN, USERNAME, REASON, "Leaverson", "pat@example.test"):
            assert needle in before  # the check can see them
        e = anonymised(e)
        after = every_text_in_the_database()
        for needle in (NAME, NUMBER, LOGIN, USERNAME, REASON, "Leaverson", "pat@example.test"):
            assert needle not in after, needle
        listing = client(Role.ADMIN).get("/api/v1/scheduling/employees").content.decode()
        export = client(Role.ADMIN).get(f"/api/v1/people/employees/{e.pk}/data-export").content
        for needle in (NAME, NUMBER, LOGIN, USERNAME, REASON):
            assert needle not in listing
            assert needle not in export.decode()

    def test_the_record_is_neutral_and_the_login_cannot_sign_in(self) -> None:
        e = leaver()
        user_id = e.user_id or 0
        e = anonymised(e)
        assert e.emp_no.startswith("ERASED-")
        assert e.name == f"Former employee {e.emp_no.removeprefix('ERASED-')}"
        assert e.user_id is None
        user = User.objects.get(pk=user_id)
        assert not user.is_active
        assert not user.has_usable_password()
        assert (user.first_name, user.last_name, user.email) == ("", "", "")
        assert user.username == f"erased-user-{user_id}"
        assert not Client().login(username=user.username, password="a-long-secret-password")

    def test_history_and_aggregates_are_unchanged(self) -> None:
        # Failure caught: erasing a person also rewriting service level, hours or payroll history.
        e = leaver()
        assert anonymised(e)
        assert ShiftAssignment.objects.filter(employee=e).count() == 1
        assert LeaveRequest.objects.filter(employee=e).count() == 1
        ot = OvertimeRequest.objects.get(employee=e)
        assert (ot.minutes, ot.worked_minutes, ot.reason) == (120, 90, "")
        assert ot.approved_cost == 300
        assert StandbyShift.objects.get(employee=e).call_out_minutes == 45
        assert Employee.objects.get(pk=e.pk).weekly_hours == 40

    def test_pay_logins_availability_and_notifications_are_deleted(self) -> None:
        e = leaver()
        user_id = e.user_id or 0
        anonymised(e)
        assert not EmployeePay.objects.filter(employee=e).exists()
        assert not AgentLogin.objects.filter(employee=e).exists()
        assert not Availability.objects.filter(employee=e).exists()
        assert not Notification.objects.filter(recipient_id=user_id).exists()

    def test_other_peoples_records_are_untouched(self) -> None:
        # Failure caught: a filter that is too wide wiping someone else's logins or notifications.
        other_user = User.objects.create(username="other.person", role=Role.AGENT)
        other = person("E002", name="Olly Other", user=other_user)
        AgentLogin.objects.create(login="olly", employee=other)
        Notification.objects.create(recipient=other_user, kind="x", message="for Olly")
        anonymised(leaver())
        other.refresh_from_db()
        assert (other.name, other.emp_no) == ("Olly Other", "E002")
        assert AgentLogin.objects.filter(login="olly").exists()
        assert Notification.objects.filter(recipient=other_user).count() == 1

    def test_a_leaver_with_no_login_can_be_anonymised(self) -> None:
        e = person("E300", name="No Login", end_date=date(2025, 1, 1))
        assert confirm(e.pk, "E300").status_code == 200

    def test_the_old_number_can_be_used_again(self) -> None:
        # Failure caught: the unique employee number staying taken by an anonymised record.
        e = leaver()
        anonymised(e)
        assert not Employee.objects.filter(emp_no=NUMBER).exists()
        person(NUMBER, name="New Hire")


class TestAudit:
    def test_one_event_with_counts_only_and_the_chain_still_verifies(self) -> None:
        # Failure caught: names in the trail, or the erasure breaking the tamper-evident chain.
        e = leaver()
        anonymised(e)
        event = AuditEvent.objects.get(action=Action.EMPLOYEE_ANONYMISED)
        assert (event.actor_role, event.subject_employee_id) == ("admin", e.pk)
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes["removed_agentLogins"] == "1"
        assert changes["kept_shifts"] == "1"
        assert all(v is not None and v.isdigit() for v in changes.values())
        assert verify_chain() == []

    def test_the_old_audit_rows_are_left_exactly_as_they_were(self) -> None:
        e = leaver()
        client(Role.ADMIN).put(
            f"/api/v1/overtime/pay/{e.pk}",
            {"monthlySalary": 1000, "ordinarilyWorksSundays": False, "clear": False},
            content_type="application/json",
        )
        before = list(AuditEvent.objects.order_by("chain_seq").values("id", "hash", "prev_hash"))
        anonymised(e)
        after = list(
            AuditEvent.objects.order_by("chain_seq")
            .filter(id__in=[b["id"] for b in before])
            .values("id", "hash", "prev_hash")
        )
        assert after == before

    def test_a_refusal_writes_no_event(self) -> None:
        e = leaver()
        confirm(e.pk, "wrong")
        assert not AuditEvent.objects.filter(action=Action.EMPLOYEE_ANONYMISED).exists()


class TestAuditNeverStoresNamesOrNumbers:
    def test_creating_and_changing_an_employee_keep_names_and_numbers_out_of_the_trail(
        self,
    ) -> None:
        # Failure caught: the (uneditable) audit trail holding an employee number or name that an
        # erasure request could then never remove.
        planner = client(Role.PLANNER)
        q = queue()
        made = planner.post(
            "/api/v1/scheduling/employees",
            {
                "empNo": "E555",
                "name": "Trail Tester",
                "contractType": "permanent",
                "workMode": "office",
                "weeklyHours": 40,
                "skills": [{"queueId": q.pk, "level": 1}],
            },
            content_type="application/json",
        )
        assert made.status_code in (200, 201), made.content
        pk = made.json()["id"]
        planner.put(
            f"/api/v1/scheduling/employees/{pk}",
            {
                "empNo": "E556",
                "name": "Trail Renamed",
                "contractType": "permanent",
                "workMode": "office",
                "weeklyHours": 40,
                "skills": [{"queueId": q.pk, "level": 1}],
            },
            content_type="application/json",
        )
        text = json.dumps(list(AuditChange.objects.values()), default=str)
        for needle in ("E555", "E556", "Trail Tester", "Trail Renamed"):
            assert needle not in text


class TestRetentionList:
    def test_lists_only_those_gone_longer_than_the_period(self) -> None:
        # Failure caught: listing current staff or recent leavers for review, or leaking names.
        old = person("E100", name="Long Gone", end_date=date(2015, 1, 1))
        person("E101", name="Recent", end_date=date(2026, 6, 1))
        person("E102", name="Still Here")
        r = client(Role.ADMIN).get("/api/v1/people/retention")
        assert r.status_code == 200
        body = r.json()
        assert body["months"] == 60
        assert [(p["employeeId"], p["employeeNumber"]) for p in body["employees"]] == [
            (old.pk, "E100")
        ]
        assert "Long Gone" not in r.content.decode()

    def test_the_period_is_configurable_and_anonymised_people_drop_off(self, settings: Any) -> None:
        e = person("E100", end_date=date(2025, 1, 1))
        settings.WFM_RETENTION_MONTHS = 6
        listed = client(Role.ADMIN).get("/api/v1/people/retention").json()
        assert [p["employeeNumber"] for p in listed["employees"]] == ["E100"]
        assert confirm(e.pk, "E100").status_code == 200
        assert client(Role.ADMIN).get("/api/v1/people/retention").json()["employees"] == []
        assert Employee.objects.count() == 1  # listing never acts by itself
