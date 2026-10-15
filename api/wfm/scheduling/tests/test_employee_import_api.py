"""Importing the employee master (DAT-06) and mapping ACD logins (DAT-05), on PostgreSQL.

The synthetic file used throughout has a header row and two people:

    E100  Pat One  permanent  40 hours   office  starts 2026-01-05  QueueA, QueueB level 2
          ACD logins pone and p.one
    E101  Sam Two  seasonal   no hours   remote  starts 01/06/2026, ends 30/09/2026  QueueA
          ACD login stwo
    plus a column (Favourite colour) that is not one of ours.

Two people are created; E101 has no hours, so the default 40 is stored FLAGGED as a default; the
day-first dates are read; three ACD logins are mapped; the unknown column is named but not stored.
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.scheduling.models import AgentLogin, Employee
from wfm.scheduling.tests.helpers import login, person, queue
from wfm.telephony.models import CallRecord, ImportBatch

pytestmark = pytest.mark.django_db

IMPORT = "/api/v1/scheduling/employees/import"
HEADER = (
    "Employee No,Name,Contract,Weekly Hours,Work Mode,Start Date,End Date,Manager,Queues,"
    "ACD Logins,Favourite colour\n"
)
GOOD = (
    HEADER
    + "E100,Pat One,permanent,40,office,2026-01-05,,,QueueA;QueueB:2,pone;p.one,blue\n"
    + "E101,Sam Two,seasonal,,remote,01/06/2026,30/09/2026,,QueueA,stwo,red\n"
)


@pytest.fixture(autouse=True)
def queues() -> None:
    queue("QueueA")
    queue("QueueB")


def send(
    csv: str | bytes, client: Client | None = None, *, dry_run: bool = False, name: str = "e.csv"
) -> Any:
    body = csv.encode("utf-8") if isinstance(csv, str) else csv
    file = SimpleUploadedFile(name, body, content_type="text/csv")
    return (client or login(Role.PLANNER)).post(
        f"{IMPORT}?dry_run={str(dry_run).lower()}", {"file": file}
    )


def one_row(row: str, **kw: Any) -> Any:
    return send(HEADER + row + "\n", **kw)


class TestAGoodFile:
    def test_it_creates_people_with_flagged_defaults_dates_skills_and_logins(self) -> None:
        response = send(GOOD)
        assert response.status_code == 200, response.content
        body = response.json()
        assert (body["created"], body["updated"], body["unchanged"], body["loginsMapped"]) == (
            2,
            0,
            0,
            3,
        )
        assert body["ignoredColumns"] == ["Favourite colour"]
        assert body["rejected"] == {}
        pat, sam = Employee.objects.get(emp_no="E100"), Employee.objects.get(emp_no="E101")
        assert (pat.name, float(pat.weekly_hours), pat.weekly_hours_is_default) == (
            "Pat One",
            40.0,
            False,
        )
        # Failure caught: a made-up figure passed off as a contract fact (DAT-10).
        assert (float(sam.weekly_hours), sam.weekly_hours_is_default) == (40.0, True)
        assert (sam.contract_type, sam.work_mode) == ("seasonal", "remote")
        assert (sam.start_date, sam.end_date) == (date(2026, 6, 1), date(2026, 9, 30))
        assert {(s.queue.name, s.level) for s in pat.skills.select_related("queue")} == {
            ("QueueA", 1),
            ("QueueB", 2),
        }
        assert sorted(a.login for a in AgentLogin.objects.filter(employee=pat)) == ["p.one", "pone"]

    def test_a_dry_run_reports_the_same_and_changes_nothing(self) -> None:
        body = send(GOOD, dry_run=True).json()
        assert (body["dryRun"], body["created"], body["loginsMapped"]) == (True, 2, 3)
        assert Employee.objects.count() == 0
        assert AgentLogin.objects.count() == 0
        assert not AuditEvent.objects.filter(action=Action.EMPLOYEES_IMPORTED).exists()

    def test_the_preview_is_the_default_so_a_slip_changes_nothing(self) -> None:
        file = SimpleUploadedFile("e.csv", GOOD.encode(), content_type="text/csv")
        body = login(Role.PLANNER).post(IMPORT, {"file": file}).json()
        assert body["dryRun"] is True
        assert Employee.objects.count() == 0

    def test_importing_the_same_file_again_changes_nothing(self) -> None:
        send(GOOD)
        body = send(GOOD).json()
        assert (body["created"], body["updated"], body["unchanged"], body["loginsMapped"]) == (
            0,
            0,
            2,
            0,
        )

    def test_a_changed_cell_updates_that_person_only_and_a_blank_cell_wipes_nothing(self) -> None:
        send(GOOD)
        changed = GOOD.replace("Pat One", "Patricia One").replace("seasonal,,remote", "seasonal,,")
        body = send(changed).json()
        assert (body["created"], body["updated"], body["unchanged"]) == (0, 1, 1)
        assert Employee.objects.get(emp_no="E100").name == "Patricia One"
        # Sam's work mode cell was blanked in the file; blank means "no change", not "erase".
        assert Employee.objects.get(emp_no="E101").work_mode == "remote"

    def test_a_manager_who_can_approve_is_linked(self) -> None:
        lead_user = User.objects.create(username="lee", role=Role.LEAD)
        lead = person("L001", user=lead_user)
        body = one_row("E200,New Person,,,,,,L001,,,").json()
        assert (body["created"], body["rejected"]) == (1, {})
        assert Employee.objects.get(emp_no="E200").manager_id == lead.pk

    def test_an_excel_file_is_read_like_a_csv_including_date_cells(self) -> None:
        from openpyxl import Workbook

        book = Workbook()
        sheet = book.active
        assert sheet is not None
        sheet.append(["Employee No", "Name", "Contract", "Weekly Hours", "Start Date", "Queues"])
        sheet.append(["X1", "Xavier", "permanent", 37.5, datetime(2026, 2, 2), "QueueA"])
        buffer = io.BytesIO()
        book.save(buffer)
        body = send(buffer.getvalue(), name="e.xlsx").json()
        assert body["created"] == 1
        xavier = Employee.objects.get(emp_no="X1")
        assert (float(xavier.weekly_hours), xavier.start_date) == (37.5, date(2026, 2, 2))


class TestRowsThatAreRefused:
    @pytest.mark.parametrize(
        ("row", "reason"),
        [
            (",Nobody,,,,,,,,,", "emp_no_invalid"),
            ("E1,,,,,,,,,,", "name_missing"),
            ("E1,A,temp,,,,,,,,", "contract_invalid"),
            ("E1,A,,,home,,,,,,", "work_mode_invalid"),
            ("E1,A,,0,,,,,,,", "hours_invalid"),
            ("E1,A,,70,,,,,,,", "hours_invalid"),
            ("E1,A,,lots,,,,,,,", "hours_invalid"),
            ("E1,A,,,,31-12-2026,,,,,", "date_invalid"),
            ("E1,A,,,,2026-06-01,2026-05-01,,,,", "dates_invalid"),
            ("E1,A,,,,,,,NoSuchQueue,,", "queue_unknown"),
            ("E1,A,,,,,,,QueueA:4,,", "skill_level_invalid"),
            ("E1,A,,,,,,,QueueA;QueueA,,", "queue_repeated"),
            ("E1,A,,,,,,GHOST,,,", "manager_unknown"),
        ],
    )
    def test_each_reason_is_named_and_the_row_creates_nothing(self, row: str, reason: str) -> None:
        body = one_row(row).json()
        assert body["rejected"] == {reason: 1}, body
        assert body["created"] == 0
        assert Employee.objects.count() == 0

    def test_a_manager_without_a_login_that_can_approve_is_refused(self) -> None:
        person("L001")  # an employee, but no login
        assert one_row("E1,A,,,,,,L001,,,").json()["rejected"] == {"manager_cannot": 1}
        agent_user = User.objects.create(username="amy", role=Role.AGENT)
        person("L002", user=agent_user)
        assert one_row("E2,B,,,,,,L002,,,").json()["rejected"] == {"manager_cannot": 1}

    def test_the_same_number_twice_in_one_file_only_counts_the_first(self) -> None:
        body = send(HEADER + "E1,First,,,,,,,,,\nE1,Second,,,,,,,,,\n").json()
        assert (body["created"], body["rejected"]) == (1, {"duplicate_in_file": 1})
        assert Employee.objects.get(emp_no="E1").name == "First"

    def test_an_acd_login_that_is_someone_elses_refuses_the_row_and_leaves_no_half_person(
        self,
    ) -> None:
        send(HEADER + "E1,Owner,,,,,,,,shared,\n")
        body = one_row("E2,Thief,,,,,,,QueueA,shared;other,").json()
        assert body["rejected"] == {"login_taken": 1}
        assert not Employee.objects.filter(emp_no="E2").exists()
        assert not AgentLogin.objects.filter(login="other").exists()

    def test_good_rows_still_go_in_when_another_row_is_bad(self) -> None:
        body = send(HEADER + "E1,Good,,,,,,,,,\nE2,Bad,temp,,,,,,,,\nE3,Fine,,,,,,,,,\n").json()
        assert (body["created"], body["rejected"]) == (2, {"contract_invalid": 1})

    def test_the_report_never_repeats_what_was_in_the_file(self) -> None:
        response = send(HEADER + "E1,Secret Name,temp,,,,,,,,\n")
        # Failure caught: a name or number from the file written into a response that gets logged.
        assert "Secret Name" not in response.content.decode()
        assert "E1" not in response.content.decode()


class TestFilesThatCannotBeRead:
    @pytest.mark.parametrize(
        ("content", "name"),
        [
            (b"just text", "notes.txt"),
            (b"", "empty.csv"),
            (b"Name,Contract\nA,permanent\n", "no-number.csv"),  # no employee number column
            (b"Employee No,Contract\nE1,permanent\n", "no-name.csv"),
            (b"\xff\xfe\x00bad", "binary.csv"),
            (b"not a workbook", "broken.xlsx"),
        ],
    )
    def test_they_are_refused_with_one_reason_and_the_refusal_is_audited(
        self, content: bytes, name: str
    ) -> None:
        response = send(content, name=name)
        assert (response.status_code, response.json()["code"]) == (422, "employees.unreadable")
        assert Employee.objects.count() == 0
        assert AuditEvent.objects.filter(action=Action.EMPLOYEES_IMPORT_REFUSED).count() == 1

    def test_a_file_with_too_many_rows_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("wfm.scheduling.employee_import.MAX_ROWS", 2)
        rows = "".join(f"E{n},Person {n},,,,,,,,,\n" for n in range(3))
        assert send(HEADER + rows).status_code == 422
        assert Employee.objects.count() == 0


class TestWhoMayImport:
    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_only_planners_and_admins(self, role: Role) -> None:
        assert send(GOOD, login(role)).status_code == 403
        assert Employee.objects.count() == 0

    def test_an_admin_may(self) -> None:
        assert send(GOOD, login(Role.ADMIN)).status_code == 200

    def test_an_anonymous_caller_is_turned_away(self) -> None:
        file = SimpleUploadedFile("e.csv", GOOD.encode(), content_type="text/csv")
        assert Client().post(IMPORT, {"file": file}).status_code == 401


class TestTheAuditTrail:
    def test_one_event_with_counts_and_no_names(self) -> None:
        send(GOOD)
        event = AuditEvent.objects.get(action=Action.EMPLOYEES_IMPORTED)
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes == {"created": "2", "updated": "0", "rejected": "0"}
        text = " ".join(
            f"{c.old_value}{c.new_value}" for c in AuditChange.objects.filter(event=event)
        )
        assert "Pat" not in text
        assert "Sam" not in text


class TestMappingAcdLogins:
    def batch(self) -> ImportBatch:
        now = timezone.now()
        return ImportBatch.objects.create(
            file_name="synthetic.xlsx",
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            uploaded_by=User.objects.create(username="importer", role=Role.PLANNER),
            source_timezone="Africa/Johannesburg",
            period_start=now,
            period_end=now,
            rows_read=0,
            rows_inserted=0,
            rows_duplicate=0,
            rows_rejected=0,
        )

    def calls(self, logins: list[str]) -> None:
        batch, q = self.batch(), queue()
        for n, name in enumerate(logins):
            CallRecord.objects.create(
                call_id=1000 + n,
                batch=batch,
                queue=q,
                call_type="INBOUND",
                status="ANSWERED",
                agent_login=name,
                start_at=timezone.now(),
            )

    def test_unmapped_logins_are_listed_busiest_first_and_mapped_ones_are_not(self) -> None:
        owner = person("E1")
        AgentLogin.objects.create(login="mapped", employee=owner)
        self.calls(["a", "a", "a", "b", "mapped", "mapped", ""])
        listed = login(Role.PLANNER).get("/api/v1/scheduling/agent-logins/unmapped").json()
        assert [(x["login"], x["calls"]) for x in listed] == [("a", 3), ("b", 1)]

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_others_cannot_list_or_set_logins(self, role: Role) -> None:
        owner = person("E1")
        client = login(role)
        assert client.get("/api/v1/scheduling/agent-logins/unmapped").status_code == 403
        response = client.put(
            f"/api/v1/scheduling/employees/{owner.pk}/agent-logins",
            {"logins": ["a"]},
            content_type="application/json",
        )
        assert response.status_code == 403

    def put(self, employee: Employee, logins: list[str], role: Role = Role.PLANNER) -> Any:
        return login(role).put(
            f"/api/v1/scheduling/employees/{employee.pk}/agent-logins",
            {"logins": logins},
            content_type="application/json",
        )

    def test_several_logins_can_be_one_person_and_setting_replaces_the_set(self) -> None:
        owner = person("E1")
        assert sorted(self.put(owner, ["a", "b", " b ", ""]).json()["agentLogins"]) == ["a", "b"]
        assert self.put(owner, ["c"]).json()["agentLogins"] == ["c"]
        assert sorted(AgentLogin.objects.values_list("login", flat=True)) == ["c"]

    def test_a_login_belongs_to_one_person_only(self) -> None:
        first, second = person("E1"), person("E2")
        self.put(first, ["shared"])
        response = self.put(second, ["shared"])
        assert (response.status_code, response.json()["code"]) == (409, "logins.taken")
        assert AgentLogin.objects.get(login="shared").employee_id == first.pk

    def test_unknown_employee_and_overlong_login(self) -> None:
        assert (
            login(Role.PLANNER)
            .put(
                "/api/v1/scheduling/employees/999999/agent-logins",
                {"logins": ["a"]},
                content_type="application/json",
            )
            .status_code
            == 404
        )
        owner = person("E1")
        assert self.put(owner, ["x" * 101]).status_code == 422

    def test_the_audit_trail_counts_logins_and_does_not_repeat_them(self) -> None:
        owner = person("E1")
        self.put(owner, ["jane.private"])
        event = AuditEvent.objects.get(action=Action.AGENT_LOGINS_SET)
        change = AuditChange.objects.get(event=event)
        assert (change.old_value, change.new_value) == ("0", "1")
        assert "jane" not in f"{change.old_value}{change.new_value}"
