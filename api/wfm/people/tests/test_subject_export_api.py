"""Subject-access export (NFR-03): only the admin; it holds the person's own data and nobody
else's; it never carries a salary; and taking it is audited without its contents."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.notifications.models import Notification
from wfm.overtime.models import EmployeePay
from wfm.people.models import LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.tests.helpers import person

from .team import lead_of

pytestmark = pytest.mark.django_db

SECRET_SALARY = Decimal("98765.43")


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def url(employee_id: int) -> str:
    return f"/api/v1/people/employees/{employee_id}/data-export"


def leave_for(employee: Any, first: date) -> None:
    LeaveRequest.objects.create(
        employee=employee,
        leave_type=LeaveType.objects.get(code="annual"),
        start_date=first,
        end_date=first,
        days=1,
        status=LeaveStatus.APPROVED,
        requested_by=User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[
            0
        ],
    )


def export(employee_id: int) -> dict[str, Any]:
    response = client(Role.ADMIN).get(url(employee_id))
    assert response.status_code == 200, response.content
    return dict(json.loads(response.content))


class TestWhoMayTakeIt:
    @pytest.mark.parametrize(
        "role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
    )
    def test_nobody_but_the_admin(self, role: Role) -> None:
        # Failure caught: a planner or the person's own lead pulling a full file on someone.
        e1 = person("E001")
        assert client(role).get(url(e1.pk)).status_code == 403
        assert not AuditEvent.objects.filter(action=Action.SUBJECT_EXPORTED).exists()

    def test_signed_out_is_refused(self) -> None:
        e1 = person("E001")
        assert Client().get(url(e1.pk)).status_code in (401, 403)

    def test_an_unknown_employee_is_not_found(self) -> None:
        assert client(Role.ADMIN).get(url(99999)).status_code == 404

    def test_the_file_is_a_download_and_is_not_cached(self) -> None:
        e1 = person("E001")
        r = client(Role.ADMIN).get(url(e1.pk))
        assert r["Cache-Control"] == "no-store"
        assert r["Content-Disposition"].startswith("attachment;")
        assert r["Content-Type"].startswith("application/json")


class TestWhatIsInIt:
    def test_it_holds_the_persons_record_leave_and_what_was_done_to_them(self) -> None:
        lead = lead_of(person("E002", name="Team Lead"))
        e1 = person("E001", name="Pat Subject")
        e1.manager = lead
        e1.save()
        leave_for(e1, date(2031, 3, 4))
        data = export(e1.pk)
        assert data["person"]["name"] == "Pat Subject"
        assert data["person"]["teamLead"] == "Person L001"
        assert [r["from"] for r in data["leave"]] == ["2031-03-04"]
        assert data["person"]["skills"][0]["queue"] == "QueueA"

    def test_it_holds_nothing_about_other_people(self) -> None:
        # Failure caught: another person's leave, name or shifts leaking into a subject's file.
        e1 = person("E001", name="Pat Subject")
        other = person("E002", name="Olly Other")
        leave_for(other, date(2031, 3, 4))
        text = client(Role.ADMIN).get(url(e1.pk)).content.decode()
        assert "Olly Other" not in text
        assert "E002" not in text
        assert export(e1.pk)["leave"] == []

    def test_notifications_are_only_the_persons_own(self) -> None:
        user = User.objects.create(username="u-sub", role=Role.AGENT)
        other = User.objects.create(username="u-other", role=Role.AGENT)
        e1 = person("E001", user=user)
        Notification.objects.create(recipient=user, kind="x", message="for the subject")
        Notification.objects.create(recipient=other, kind="x", message="for somebody else")
        messages = [n["message"] for n in export(e1.pk)["notifications"]]
        assert messages == ["for the subject"]

    def test_the_audit_trail_about_them_is_included_without_hashes(self) -> None:
        e1 = person("E001", name="Pat Subject")
        leave_for(e1, date(2031, 3, 4))
        client(Role.ADMIN).put(
            f"/api/v1/overtime/pay/{e1.pk}",
            {
                "monthlySalary": float(SECRET_SALARY),
                "ordinarilyWorksSundays": False,
                "clear": False,
            },
            content_type="application/json",
        )
        text = client(Role.ADMIN).get(url(e1.pk)).content.decode()
        trail = json.loads(text)["auditTrail"]
        assert any(t["action"] == "overtime.pay_changed" for t in trail)
        assert "hash" not in text.lower()


class TestPayIsNotRead:
    def test_a_salary_is_never_in_the_file_only_that_pay_exists(self) -> None:
        # Failure caught: the export becoming a way to read a salary back out of the system.
        e1 = person("E001")
        EmployeePay.objects.create(employee=e1, monthly_salary=SECRET_SALARY)
        text = client(Role.ADMIN).get(url(e1.pk)).content.decode()
        assert "98765" not in text
        assert json.loads(text)["pay"]["onFile"] is True

    def test_overtime_is_in_minutes_and_status_with_no_rand_amounts(self) -> None:
        from wfm.overtime.models import OvertimeRequest

        e1 = person("E001")
        admin = User.objects.get_or_create(username="u-admin", defaults={"role": Role.ADMIN})[0]
        OvertimeRequest.objects.create(
            employee=e1,
            day=date(2031, 3, 5),
            start_time="18:00",
            end_time="20:00",
            minutes=120,
            status="approved",
            approved_cost=Decimal("300.00"),
            requested_by=admin,
        )
        text = client(Role.ADMIN).get(url(e1.pk)).content.decode()
        assert "300" not in text.replace("120", "")
        assert json.loads(text)["overtime"][0]["approvedMinutes"] == 120


class TestTheExportIsAudited:
    def test_who_whose_and_how_many_records_but_never_the_contents(self) -> None:
        e1 = person("E001", name="Pat Subject")
        leave_for(e1, date(2031, 3, 4))
        export(e1.pk)
        event = AuditEvent.objects.get(action=Action.SUBJECT_EXPORTED)
        assert (event.actor_role, event.subject_employee_id) == ("admin", e1.pk)
        changes = list(AuditChange.objects.filter(event=event).values_list("field", "new_value"))
        assert changes[0][0] == "records"
        assert int(changes[0][1] or 0) >= 2
        assert "Pat Subject" not in " ".join(
            str(c) for c in AuditChange.objects.filter(event=event).values()
        )

    def test_every_export_is_a_separate_event(self) -> None:
        e1 = person("E001")
        export(e1.pk)
        export(e1.pk)
        assert AuditEvent.objects.filter(action=Action.SUBJECT_EXPORTED).count() == 2


def test_the_service_itself_refuses_anyone_but_the_admin() -> None:
    # Failure caught: the admin check living only in the endpoint, so a new caller of the
    # service (a job, another view) could pull a full file on a person.
    from wfm.core.errors import ApiError
    from wfm.people import subject_export

    e1 = person("E001")
    for role in (Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
        who = User.objects.create(username=f"u-svc-{role.value}", role=role)
        with pytest.raises(ApiError) as refused:
            subject_export.export(who, e1.pk)
        assert refused.value.status == 404
    assert not AuditEvent.objects.filter(action=Action.SUBJECT_EXPORTED).exists()
