"""Attendance: the state-file import, a queue day's adherence, and a person's own day (ATT-01).

All data is a few synthetic lines of CSV text. Monday 25 May 2026 is "today" for the date window.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.attendance.models import AgentStateImport, AgentStateInterval
from wfm.audit.models import Action, AuditEvent
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import (
    ActivityKind,
    AgentLogin,
    Employee,
    RosterStatus,
    RosterWeek,
    ShiftActivity,
    ShiftAssignment,
)
from wfm.scheduling.tests.helpers import MON, assign, login, person, queue, standard_shifts

pytestmark = pytest.mark.django_db

IMPORT = "/api/v1/attendance/imports"
ADHERENCE = "/api/v1/attendance/adherence"
MINE = "/api/v1/attendance/mine"
HEADER = "login,state,from,to\n"
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("wfm.attendance.api.timezone.localdate", lambda: MON)


def as_role(role: Role) -> Client:
    return login(role)


def line(who: str, state: str, start: str, end: str, day: str = "2026-05-25") -> str:
    return f"{who},{state},{day}T{start}:00,{day}T{end}:00\n"


def upload(client: Client, text: str | bytes, name: str = "states.csv") -> Any:
    data = text.encode() if isinstance(text, str) else text
    return client.post(IMPORT, {"file": SimpleUploadedFile(name, data, "text/csv")})


class World:
    """Two people on the 09:00 to 17:30 shift on Monday, lunch 12:00 to 12:30, published. Ann is
    in the lead's team and the agent user; Bob is nobody's."""

    def __init__(self) -> None:
        shifts = standard_shifts()
        self.ann = person("E001", user=User.objects.create(username="u-agent", role=Role.AGENT))
        self.bob = person("E002")
        AgentLogin.objects.create(login="ann1", employee=self.ann)
        AgentLogin.objects.create(login="bob1", employee=self.bob)
        self.lead = lead_of(self.ann)
        planner = as_role(Role.PLANNER)
        for p in (self.ann, self.bob):
            assign(planner, queue(), p, MON, shifts["D1"])
        self.planner_user = User.objects.get(username="u-planner")
        for a in ShiftAssignment.objects.all():
            ShiftActivity.objects.create(
                assignment=a,
                kind=ActivityKind.LUNCH,
                offset_slots=6,
                slots=1,
                created_by=self.planner_user,
            )
        RosterWeek.objects.update(status=RosterStatus.PUBLISHED)


@pytest.fixture
def world() -> World:
    return World()


# Ann: 60 minutes away mid-afternoon. Scheduled 480 (510 less the 30 minute lunch), in 420.
ANN_DAY = (
    line("ann1", "available", "09:00", "12:00")
    + line("ann1", "lunch", "12:00", "12:30")
    + line("ann1", "available", "12:30", "14:00")
    + line("ann1", "away", "14:00", "15:00")
    + line("ann1", "on_call", "15:00", "17:30")
)


class TestImportRoles:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_admin_and_planner_can_import(self, world: World, role: Role) -> None:
        assert upload(as_role(role), HEADER + ANN_DAY).status_code == 201

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_import(self, world: World, role: Role) -> None:
        # Failure caught: a lead or agent loading attendance data, or rewriting their own day.
        assert upload(as_role(role), HEADER + ANN_DAY).status_code == 403
        assert not AgentStateInterval.objects.exists()

    def test_signed_out_is_refused(self, world: World) -> None:
        assert upload(Client(), HEADER + ANN_DAY).status_code == 401


class TestImport:
    def test_rows_are_mapped_through_the_agent_login_and_stored_in_utc(self, world: World) -> None:
        body = upload(as_role(Role.PLANNER), HEADER + ANN_DAY).json()
        assert (body["rowsRead"], body["rowsInserted"], body["rowsDuplicate"]) == (5, 5, 0)
        first = AgentStateInterval.objects.order_by("start_at").first()
        assert first is not None
        assert first.employee_id == world.ann.pk
        assert first.start_at.isoformat() == "2026-05-25T07:00:00+00:00"  # 09:00 in Johannesburg

    def test_an_unmapped_login_is_reported_and_never_guessed_or_stored(self, world: World) -> None:
        # Failure caught: "ANN1" or an unknown login attached to the nearest person.
        text = HEADER + line("ANN1", "available", "09:00", "10:00")
        text += line("ghost", "available", "09:00", "10:00") + line(
            "ann1", "break", "10:00", "10:15"
        )
        body = upload(as_role(Role.PLANNER), text).json()
        assert body["unmappedLogins"] == ["ANN1", "ghost"]
        assert (body["rowsUnmapped"], body["rowsInserted"]) == (2, 1)
        assert set(AgentStateInterval.objects.values_list("login", flat=True)) == {"ann1"}

    def test_bad_rows_are_reported_with_a_reason_and_not_stored(self, world: World) -> None:
        # Failure caught: a malformed row stored, aborting the file, or quoted back in the error.
        text = HEADER + "ann1,dancing,2026-05-25T09:00,2026-05-25T10:00\n"
        text += "ann1,available,2026-05-25T10:00,2026-05-25T09:00\n"
        text += line("ann1", "available", "09:00", "10:00")
        body = upload(as_role(Role.PLANNER), text).json()
        assert (body["rowsRejected"], body["rowsInserted"]) == (2, 1)
        assert [e["row"] for e in body["errors"]] == [2, 3]
        assert "ann1" not in str(body["errors"])
        assert AgentStateInterval.objects.count() == 1

    def test_the_same_interval_twice_is_skipped_in_a_file_and_across_files(
        self, world: World
    ) -> None:
        # Failure caught: loading a file twice (or a feed overlap) doubling the minutes.
        once = line("ann1", "available", "09:00", "10:00")
        first = upload(as_role(Role.PLANNER), HEADER + once + once).json()
        assert (first["rowsInserted"], first["rowsDuplicate"]) == (1, 1)
        again = upload(as_role(Role.PLANNER), HEADER + once).json()
        assert (again["rowsInserted"], again["rowsDuplicate"]) == (0, 1)
        assert AgentStateInterval.objects.count() == 1

    def test_an_oversize_file_is_refused_and_nothing_is_stored(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Failure caught: an unbounded upload read into memory and parsed.
        monkeypatch.setattr("wfm.attendance.api.MAX_UPLOAD_BYTES", 100)
        response = upload(as_role(Role.PLANNER), HEADER + ANN_DAY)
        assert response.status_code == 413
        assert response.json()["code"] == "attendance.too_large"
        assert not AgentStateImport.objects.exists()

    def test_a_file_that_is_not_the_agreed_layout_or_not_text_is_refused(
        self, world: World
    ) -> None:
        # Failure caught: a different vendor layout, or a binary file, read as states.
        client = as_role(Role.PLANNER)
        wrong = upload(client, "agent,status,start,stop\na,available,x,y\n")
        assert (wrong.status_code, wrong.json()["code"]) == (422, "attendance.bad_header")
        binary = upload(client, b"\xff\xfe\x00\x01")
        assert (binary.status_code, binary.json()["code"]) == (422, "attendance.not_utf8")
        empty = upload(client, HEADER)
        assert (empty.status_code, empty.json()["code"]) == (422, "attendance.empty")
        assert not AgentStateImport.objects.exists()

    def test_the_audit_event_holds_counts_and_no_login_or_time(self, world: World) -> None:
        # Failure caught: attendance data (who, when) leaking into the audit trail.
        upload(as_role(Role.PLANNER), HEADER + ANN_DAY)
        event = AuditEvent.objects.get(action=Action.ATTENDANCE_IMPORTED)
        assert event.actor_role == "planner"
        values = {c.field: c.new_value for c in event.changes.all()}
        assert values == {
            "rows_read": "5",
            "rows_inserted": "5",
            "rows_duplicate": "0",
            "rows_rejected": "0",
            "rows_unmapped": "0",
        }
        assert "ann1" not in repr(list(event.changes.values()))


class TestQueueAdherence:
    def get(self, client: Client, day: date = MON, queue_id: int | None = None) -> Any:
        return client.get(ADHERENCE, {"queue_id": str(queue_id or queue().pk), "day": str(day)})

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_admin_planner_and_lead_can_read(self, world: World, role: Role) -> None:
        assert self.get(as_role(role)).status_code == 200

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_everyone_else_is_refused(self, world: World, role: Role) -> None:
        # Failure caught: an agent reading colleagues' adherence.
        assert self.get(as_role(role)).status_code == 403

    def test_signed_out_is_refused(self, world: World) -> None:
        assert self.get(Client()).status_code == 401

    def test_the_figures_are_worked_by_hand_and_a_person_without_data_claims_nothing(
        self, world: World
    ) -> None:
        # Failure caught: a person whose feed is not loaded shown as 0% (a no-show), or the lunch
        # counted as time that should be on the phones.
        upload(as_role(Role.PLANNER), HEADER + ANN_DAY)
        body = self.get(as_role(Role.PLANNER)).json()
        people = {p["empNo"]: p for p in body["people"]}
        ann, bob = people["E001"], people["E002"]
        assert (ann["scheduledMin"], ann["inAdherenceMin"], ann["outOfAdherenceMin"]) == (
            480,
            420,
            60,
        )
        assert ann["adherencePct"] == 87.5
        assert ann["exceptions"] == ["out_of_adherence"]
        assert (ann["lateStartMin"], ann["earlyFinishMin"]) == (0, 0)
        assert (bob["hasData"], bob["adherencePct"], bob["exceptions"]) == (False, None, [])
        assert (body["withData"], body["withoutData"], body["teamAdherencePct"]) == (1, 1, 87.5)

    def test_a_lead_sees_only_their_own_team(self, world: World) -> None:
        # Failure caught: a lead reading adherence of people who do not report to them.
        upload(as_role(Role.PLANNER), HEADER + ANN_DAY + line("bob1", "away", "09:00", "17:30"))
        body = self.get(as_role(Role.LEAD)).json()
        assert [p["empNo"] for p in body["people"]] == ["E001"]
        assert "E002" not in str(body)

    def test_a_lead_with_no_team_sees_nobody(self, world: World) -> None:
        Employee.objects.update(manager=None)
        assert self.get(as_role(Role.LEAD)).json()["people"] == []

    def test_a_draft_roster_is_not_the_plan(self, world: World) -> None:
        # Failure caught: adherence measured against a roster that was never published.
        RosterWeek.objects.update(status=RosterStatus.DRAFT)
        assert self.get(as_role(Role.PLANNER)).json()["people"] == []

    def test_an_unknown_queue_is_404_and_a_day_out_of_range_is_422(self, world: World) -> None:
        client = as_role(Role.PLANNER)
        assert self.get(client, queue_id=99999).status_code == 404
        too_old = self.get(client, day=date(2026, 1, 1))
        assert (too_old.status_code, too_old.json()["code"]) == (
            422,
            "attendance.date_out_of_range",
        )


class TestMyAttendance:
    def get(self, client: Client, day: date = MON) -> Any:
        return client.get(MINE, {"day": str(day)})

    def test_an_agent_sees_their_own_planned_and_actual_day(self, world: World) -> None:
        upload(as_role(Role.PLANNER), HEADER + ANN_DAY)
        body = self.get(as_role(Role.AGENT)).json()
        assert (body["hasShift"], body["shiftCode"], body["adherencePct"]) == (True, "D1", 87.5)
        # The plan is the shift less the lunch: two pieces, in local time.
        assert [(s["start"][11:16], s["end"][11:16]) for s in body["planned"]] == [
            ("09:00", "12:00"),
            ("12:30", "17:30"),
        ]
        assert body["planned"][0]["start"].endswith("+02:00")
        assert [a["state"] for a in body["actual"]][:2] == ["available", "lunch"]

    def test_an_agent_never_sees_a_colleagues_day(self, world: World) -> None:
        # Failure caught: the own-day endpoint leaking another person's states or identity.
        upload(as_role(Role.PLANNER), HEADER + line("bob1", "away", "09:00", "17:30"))
        body = self.get(as_role(Role.AGENT)).json()
        assert body["actual"] == []
        assert body["hasData"] is False
        assert "E002" not in str(body)

    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_roles_with_no_roster_are_refused(self, world: World, role: Role) -> None:
        assert self.get(as_role(role)).status_code == 403

    def test_signed_out_is_refused(self, world: World) -> None:
        assert self.get(Client()).status_code == 401

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_staff_without_an_employee_record_get_a_plain_refusal(
        self, world: World, role: Role
    ) -> None:
        # Failure caught: a person with no record being shown somebody else's day.
        if role == Role.LEAD:
            Employee.objects.filter(user__username="u-lead").update(user=None)
        response = self.get(as_role(role))
        assert response.status_code == 422
        assert response.json()["code"] == "attendance.no_employee_record"

    def test_a_day_without_a_shift_says_so(self, world: World) -> None:
        body = self.get(as_role(Role.AGENT), day=date(2026, 5, 26)).json()
        assert (body["hasShift"], body["planned"], body["adherencePct"]) == (False, [], None)

    def test_an_unpublished_shift_is_not_shown(self, world: World) -> None:
        # Failure caught: an agent seeing (and being measured against) a draft roster.
        RosterWeek.objects.update(status=RosterStatus.DRAFT)
        assert self.get(as_role(Role.AGENT)).json()["hasShift"] is False
