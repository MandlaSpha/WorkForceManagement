"""Backup teams and the mobilise view (BCP-01), on PostgreSQL.

Monday 25 May 2026 is the day. QueueA's published roster holds two office people (R1, R2) and one
remote person (R3). The backup team "Alpha" holds one person of each kind of answer: free (hybrid),
rostered on another queue, office-only, on approved leave, and unavailable all day.
"""

from __future__ import annotations

from datetime import time
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.continuity.models import BackupMember, BackupTeam
from wfm.people.models import Availability, AvailabilityKind, LeaveRequest, LeaveStatus, LeaveType
from wfm.scheduling.models import Employee, RosterStatus, RosterWeek
from wfm.scheduling.tests.helpers import MON, assign, login, person, queue, standard_shifts

pytestmark = pytest.mark.django_db

TEAMS = "/api/v1/continuity/teams"
MOBILISE = "/api/v1/continuity/mobilise"
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
WRITERS = [Role.ADMIN, Role.PLANNER]
NAMED_READERS = [Role.ADMIN, Role.PLANNER, Role.LEAD]
REFUSED_READ = [Role.AGENT, Role.CUSTOMER_OPS]
REFUSED_WRITE = [Role.LEAD, Role.EXECUTIVE, Role.AGENT, Role.CUSTOMER_OPS]


class World:
    def __init__(self) -> None:
        shifts = standard_shifts()
        qa, qb = queue("QueueA"), queue("QueueB")
        planner = login(Role.PLANNER)
        for emp_no, mode in (("R1", "office"), ("R2", "office"), ("R3", "remote")):
            assign(planner, qa, person(emp_no, work_mode=mode), MON, shifts["D1"])
        self.free = person("B1", work_mode="hybrid")
        self.elsewhere = person("B2", work_mode="remote", queues=("QueueB",))
        assign(planner, qb, self.elsewhere, MON, shifts["D1"])
        self.office = person("B3", work_mode="office")
        self.leave = person("B4", work_mode="remote")
        self.unavailable = person("B5", work_mode="remote")
        RosterWeek.objects.update(status=RosterStatus.PUBLISHED)

        admin = User.objects.create(username="u-setup", role=Role.ADMIN)
        kind = LeaveType.objects.first()
        assert kind is not None
        LeaveRequest.objects.create(
            employee=self.leave,
            leave_type=kind,
            start_date=MON,
            end_date=MON,
            days=1,
            status=LeaveStatus.APPROVED,
            requested_by=admin,
        )
        Availability.objects.create(
            employee=self.unavailable,
            weekday=MON.weekday(),
            start_time=time(0, 0),
            end_time=time(0, 0),
            kind=AvailabilityKind.UNAVAILABLE,
            created_by=admin,
        )
        self.queue = qa
        self.team = BackupTeam.objects.create(queue=qa, name="Alpha", created_by=admin)
        for e in (self.free, self.elsewhere, self.office, self.leave, self.unavailable):
            BackupMember.objects.create(team=self.team, employee=e, added_by=admin)


@pytest.fixture
def world() -> World:
    return World()


def get(role: Role, path: str, **params: Any) -> Any:
    return login(role).get(path, params)


def send(role: Role, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    client: Client = login(role)
    return getattr(client, method)(path, body, content_type="application/json")


def mob(role: Role, w: World, **extra: Any) -> Any:
    return get(role, MOBILISE, queue_id=w.queue.pk, day=str(MON), **extra)


# ---- mobilise: the answer --------------------------------------------------------------------


@pytest.mark.parametrize("role", NAMED_READERS)
def test_site_failure_lists_who_can_cover_and_the_roster_impact(role: Role, world: World) -> None:
    r = mob(role, world, scenario="site")
    assert r.status_code == 200
    body = r.json()
    assert body["impact"] == {
        "rostered": 3,
        "lost": 2,
        "remaining": 1,
        "recovered": 2,
        "coveredAfter": 3,
        "shortfall": 0,
        "coveragePct": 100.0,
    }
    assert body["rosteredByMode"] == {"office": 2, "remote": 1}
    assert body["byStatus"] == {
        "free": 1,
        "rostered_elsewhere": 1,
        "needs_office": 1,
        "on_leave": 1,
        "unavailable": 1,
    }
    assert body["usableDistinct"] == 2
    team = body["teams"][0]
    assert (team["name"], team["memberCount"], team["usableCount"]) == ("Alpha", 5, 2)
    by_no = {c["empNo"]: c for c in team["candidates"]}
    assert by_no["B1"]["status"] == "free"
    assert by_no["B1"]["usable"] is True
    assert by_no["B1"]["workMode"] == "hybrid"
    assert by_no["B1"]["remoteCapable"] is True
    assert by_no["B2"]["status"] == "rostered_elsewhere"
    assert by_no["B2"]["usable"] is True
    assert by_no["B3"]["status"] == "needs_office"
    assert by_no["B3"]["usable"] is False
    assert by_no["B4"]["status"] == "on_leave"
    assert by_no["B5"]["status"] == "unavailable"


def test_an_office_person_counts_as_cover_in_an_outbreak(world: World) -> None:
    body = mob(Role.PLANNER, world, scenario="outbreak", lost_pct=100).json()
    assert body["impact"]["lost"] == 3
    assert body["byStatus"]["free"] == 2  # the hybrid person and the office-only person
    assert body["impact"]["recovered"] == 3
    assert body["impact"]["shortfall"] == 0


def test_shortfall_when_the_backups_run_out(world: World) -> None:
    BackupMember.objects.filter(team=world.team).exclude(employee=world.free).delete()
    body = mob(Role.PLANNER, world, scenario="site").json()
    assert body["impact"]["recovered"] == 1
    assert body["impact"]["shortfall"] == 1
    assert body["impact"]["coveragePct"] == 66.7


def test_a_person_on_two_teams_is_counted_once(world: World) -> None:
    admin = User.objects.get(username="u-setup")
    second = BackupTeam.objects.create(queue=world.queue, name="Beta", created_by=admin)
    BackupMember.objects.create(team=second, employee=world.free, added_by=admin)
    body = mob(Role.PLANNER, world, scenario="site").json()
    assert body["usableDistinct"] == 2
    assert [t["name"] for t in body["teams"]] == ["Alpha", "Beta"]


def test_a_draft_roster_is_not_the_roster_impact(world: World) -> None:
    RosterWeek.objects.update(status=RosterStatus.DRAFT)
    assert mob(Role.PLANNER, world).json()["impact"]["rostered"] == 0


def test_executive_gets_numbers_and_no_names(world: World) -> None:
    r = mob(Role.EXECUTIVE, world, scenario="site")
    assert r.status_code == 200
    body = r.json()
    assert body["impact"]["recovered"] == 2
    assert body["usableDistinct"] == 2
    assert body["teams"][0]["usableCount"] == 2
    assert body["teams"][0]["candidates"] == []
    assert "B1" not in r.content.decode()
    assert "Person" not in r.content.decode()


def test_bad_scenario_and_percentage_are_refused(world: World) -> None:
    assert mob(Role.PLANNER, world, scenario="flood").status_code == 422
    assert mob(Role.PLANNER, world, scenario="outbreak", lost_pct=101).status_code == 422


def test_unknown_queue_is_404(world: World) -> None:
    r = get(Role.PLANNER, MOBILISE, queue_id=9999, day=str(MON))
    assert r.status_code == 404


@pytest.mark.parametrize("role", REFUSED_READ)
def test_mobilise_refused_roles(role: Role, world: World) -> None:
    assert mob(role, world).status_code == 403


def test_mobilise_needs_a_login(world: World) -> None:
    assert (
        Client().get(MOBILISE, {"queue_id": str(world.queue.pk), "day": str(MON)}).status_code
        == 401
    )


# ---- teams: read ------------------------------------------------------------------------------


@pytest.mark.parametrize("role", NAMED_READERS)
def test_named_readers_list_teams_with_members(role: Role, world: World) -> None:
    r = get(role, TEAMS, queue_id=world.queue.pk)
    assert r.status_code == 200
    team = r.json()[0]
    assert team["memberCount"] == 5
    assert {m["empNo"] for m in team["members"]} == {"B1", "B2", "B3", "B4", "B5"}


def test_executive_lists_teams_without_names(world: World) -> None:
    r = get(Role.EXECUTIVE, TEAMS)
    assert r.status_code == 200
    assert r.json()[0]["memberCount"] == 5
    assert r.json()[0]["members"] == []


@pytest.mark.parametrize("role", REFUSED_READ)
def test_list_teams_refused_roles(role: Role, world: World) -> None:
    assert get(role, TEAMS).status_code == 403


def test_list_teams_for_an_unknown_queue_is_404(world: World) -> None:
    assert get(Role.PLANNER, TEAMS, queue_id=9999).status_code == 404


# ---- teams: write -----------------------------------------------------------------------------


@pytest.mark.parametrize("role", WRITERS)
def test_writers_create_a_team_and_it_is_audited(role: Role, world: World) -> None:
    r = send(role, "post", TEAMS, {"queueId": world.queue.pk, "name": "  Gamma  "})
    assert r.status_code == 201
    assert r.json()["name"] == "Gamma"
    event = AuditEvent.objects.get(action=Action.BACKUP_TEAM_CREATED)
    assert event.entity_id == str(r.json()["id"])


def test_duplicate_team_name_conflicts(world: World) -> None:
    r = send(Role.PLANNER, "post", TEAMS, {"queueId": world.queue.pk, "name": "Alpha"})
    assert r.status_code == 409


def test_blank_team_name_is_refused(world: World) -> None:
    assert (
        send(Role.PLANNER, "post", TEAMS, {"queueId": world.queue.pk, "name": " "}).status_code
        == 422
    )


def test_create_team_on_unknown_queue_is_404(world: World) -> None:
    assert send(Role.PLANNER, "post", TEAMS, {"queueId": 9999, "name": "X"}).status_code == 404


@pytest.mark.parametrize("role", REFUSED_WRITE)
def test_write_refused_roles(role: Role, world: World) -> None:
    team = f"{TEAMS}/{world.team.pk}"
    assert send(role, "post", TEAMS, {"queueId": world.queue.pk, "name": "Z"}).status_code == 403
    assert send(role, "delete", team).status_code == 403
    assert send(role, "post", f"{team}/members", {"employeeId": world.free.pk}).status_code == 403
    assert send(role, "delete", f"{team}/members/{world.free.pk}").status_code == 403
    assert BackupTeam.objects.count() == 1
    assert BackupMember.objects.count() == 5


@pytest.mark.parametrize("role", WRITERS)
def test_writers_add_and_remove_a_member_audited(role: Role, world: World) -> None:
    spare = person("B9", work_mode="remote")
    team = f"{TEAMS}/{world.team.pk}"
    added = send(role, "post", f"{team}/members", {"employeeId": spare.pk})
    assert added.status_code == 201
    assert added.json()["memberCount"] == 6
    ev = AuditEvent.objects.get(action=Action.BACKUP_MEMBER_ADDED)
    assert ev.subject_employee_id == spare.pk
    removed = send(role, "delete", f"{team}/members/{spare.pk}")
    assert removed.status_code == 200
    assert AuditEvent.objects.filter(action=Action.BACKUP_MEMBER_REMOVED).count() == 1
    assert BackupMember.objects.filter(employee=spare).count() == 0


def test_adding_twice_conflicts_and_unknowns_are_404(world: World) -> None:
    team = f"{TEAMS}/{world.team.pk}"
    assert (
        send(Role.PLANNER, "post", f"{team}/members", {"employeeId": world.free.pk}).status_code
        == 409
    )
    assert send(Role.PLANNER, "post", f"{team}/members", {"employeeId": 9999}).status_code == 404
    assert (
        send(
            Role.PLANNER, "post", f"{TEAMS}/9999/members", {"employeeId": world.free.pk}
        ).status_code
        == 404
    )
    assert send(Role.PLANNER, "delete", f"{team}/members/9999").status_code == 404


@pytest.mark.parametrize("role", WRITERS)
def test_writers_delete_a_team_audited(role: Role, world: World) -> None:
    assert send(role, "delete", f"{TEAMS}/{world.team.pk}").status_code == 200
    assert BackupTeam.objects.count() == 0
    assert BackupMember.objects.count() == 0
    assert AuditEvent.objects.filter(action=Action.BACKUP_TEAM_DELETED).count() == 1
    assert send(role, "delete", f"{TEAMS}/{world.team.pk}").status_code == 404


def test_audit_never_holds_a_name(world: World) -> None:
    send(Role.PLANNER, "post", f"{TEAMS}/{world.team.pk}/members", {"employeeId": person("B8").pk})
    dumped = " ".join(
        f"{c.field} {c.old_value} {c.new_value}"
        for e in AuditEvent.objects.all()
        for c in e.changes.all()
    )
    assert "Person B8" not in dumped
    assert Employee.objects.filter(emp_no="B8").exists()
