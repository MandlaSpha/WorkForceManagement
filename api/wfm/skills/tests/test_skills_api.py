"""Credentials, queue requirements and skill gaps (SKL-01, WEL-02). Synthetic data only."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.people.tests.team import lead_of
from wfm.scheduling.models import RosterWeek, ShiftAssignment
from wfm.scheduling.tests.helpers import EMPLOYEES, MON, login, person, queue, standard_shifts
from wfm.skills.models import EmployeeCredential, QueueRequirement

pytestmark = pytest.mark.django_db

CREDENTIALS = "/api/v1/skills/credentials"
REQUIREMENTS = "/api/v1/skills/requirements"
GAPS = "/api/v1/skills/gaps"
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
WRITERS = [Role.ADMIN, Role.PLANNER]
NON_WRITERS = [r for r in ALL_ROLES if r not in WRITERS]


def planner_user() -> User:
    return User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]


def put(client: Client, url: str, body: dict[str, Any]) -> Any:
    return client.put(url, body, content_type="application/json")


def cred(kind: str, name: str, expires: str | None = None) -> dict[str, Any]:
    return {"kind": kind, "name": name, "expiresOn": expires}


class World:
    """Ann (the agent login, in the lead's team) and Bob (nobody's team), both on QueueA."""

    def __init__(self) -> None:
        self.ann = person("E001", user=User.objects.create(username="u-agent", role=Role.AGENT))
        self.bob = person("E002")
        self.lead = lead_of(self.ann)
        self.q = queue()

    def creds_url(self, who: Any) -> str:
        return f"/api/v1/skills/employees/{who.pk}/credentials"


@pytest.fixture
def world() -> World:
    return World()


class TestWritingCredentials:
    @pytest.mark.parametrize("role", WRITERS)
    def test_planner_and_admin_replace_the_set(self, world: World, role: Role) -> None:
        client = login(role)
        r = put(
            client,
            world.creds_url(world.ann),
            {
                "credentials": [
                    cred("language", "Afrikaans"),
                    cred("clearance", "Secret", "2027-01-31"),
                ]
            },
        )
        assert r.status_code == 200
        assert [(c["kind"], c["name"]) for c in r.json()] == [
            ("clearance", "Secret"),
            ("language", "Afrikaans"),
        ]
        again = put(client, world.creds_url(world.ann), {"credentials": [cred("language", "Zulu")]})
        assert [c["name"] for c in again.json()] == ["Zulu"]
        assert EmployeeCredential.objects.filter(employee=world.ann).count() == 1

    @pytest.mark.parametrize("role", NON_WRITERS)
    def test_everyone_else_is_refused_and_nothing_changes(self, world: World, role: Role) -> None:
        r = put(login(role), world.creds_url(world.ann), {"credentials": [cred("language", "X")]})
        assert r.status_code == 403
        assert not EmployeeCredential.objects.exists()

    def test_unknown_employee_is_404(self, world: World) -> None:
        r = put(
            login(Role.PLANNER), "/api/v1/skills/employees/99999/credentials", {"credentials": []}
        )
        assert r.status_code == 404

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            ([cred("hobby", "Chess")], "skills.kind_invalid"),
            ([cred("language", "  ")], "skills.name_invalid"),
            ([cred("language", "Zulu"), cred("language", " zulu ")], "skills.duplicate"),
        ],
    )
    def test_bad_input_is_refused(self, world: World, body: list[Any], code: str) -> None:
        r = put(login(Role.PLANNER), world.creds_url(world.ann), {"credentials": body})
        assert r.status_code == 422
        assert r.json()["code"] == code

    def test_the_change_is_audited_once_with_before_and_after(self, world: World) -> None:
        client = login(Role.PLANNER)
        url = world.creds_url(world.ann)
        put(client, url, {"credentials": [cred("language", "Zulu")]})
        put(client, url, {"credentials": [cred("language", "Zulu")]})  # no change: no event
        events = AuditEvent.objects.filter(action=Action.CREDENTIALS_SET)
        assert events.count() == 1
        assert events.get().subject_employee_id == world.ann.pk

    def test_filtering_the_employee_list_by_credential(self, world: World) -> None:
        client = login(Role.PLANNER)
        put(
            client,
            world.creds_url(world.ann),
            {
                "credentials": [
                    cred("language", "Afrikaans"),
                    cred("certification", "ITIL", "2000-01-01"),
                ]
            },
        )
        found = client.get(EMPLOYEES, {"credential": "language:afrikaans"})
        assert [e["empNo"] for e in found.json()] == ["E001"]
        assert client.get(EMPLOYEES, {"credential": "language:Zulu"}).json() == []
        # an expired credential no longer counts
        assert client.get(EMPLOYEES, {"credential": "certification:ITIL"}).json() == []
        assert client.get(EMPLOYEES, {"credential": "nonsense"}).status_code == 422
        assert len(client.get(EMPLOYEES).json()) == 3  # no filter: Ann, Bob and the lead


class TestReadingCredentials:
    @pytest.fixture(autouse=True)
    def _held(self, world: World) -> None:
        for who, name in ((world.ann, "Afrikaans"), (world.bob, "Zulu"), (world.lead, "Xhosa")):
            EmployeeCredential.objects.create(
                employee=who,
                kind="language",
                name=name,
                updated_by=User.objects.create(username=f"x{who.pk}"),
            )

    def names(self, role: Role) -> list[str]:
        r = login(role).get(CREDENTIALS)
        assert r.status_code == 200
        return sorted(c["name"] for c in r.json())

    @pytest.mark.parametrize("role", WRITERS)
    def test_planner_and_admin_see_everybody(self, role: Role) -> None:
        assert self.names(role) == ["Afrikaans", "Xhosa", "Zulu"]

    def test_a_lead_sees_their_team_and_themselves_not_other_teams(self) -> None:
        assert self.names(Role.LEAD) == ["Afrikaans", "Xhosa"]

    def test_an_agent_sees_only_their_own(self) -> None:
        assert self.names(Role.AGENT) == ["Afrikaans"]

    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_others_are_refused(self, role: Role) -> None:
        assert login(role).get(CREDENTIALS).status_code == 403

    def test_asking_for_somebody_out_of_scope_is_404(self, world: World) -> None:
        for role in (Role.LEAD, Role.AGENT):
            r = login(role).get(CREDENTIALS, {"employee_id": world.bob.pk})
            assert r.status_code == 404
        ok = login(Role.LEAD).get(CREDENTIALS, {"employee_id": world.ann.pk})
        assert [c["name"] for c in ok.json()] == ["Afrikaans"]

    def test_an_expired_credential_is_marked(self, world: World) -> None:
        EmployeeCredential.objects.filter(employee=world.ann).update(expires_on=date(2000, 1, 1))
        row = login(Role.PLANNER).get(CREDENTIALS, {"employee_id": world.ann.pk}).json()[0]
        assert row["expired"] is True


class TestRequirements:
    def url(self, world: World) -> str:
        return f"/api/v1/skills/queues/{world.q.pk}/requirements"

    @pytest.mark.parametrize("role", WRITERS)
    def test_planner_and_admin_set_and_read(self, world: World, role: Role) -> None:
        client = login(role)
        r = put(
            client,
            self.url(world),
            {"requirements": [{"kind": "language", "name": "Afrikaans", "minPeople": 2}]},
        )
        assert r.status_code == 200
        assert r.json()[0]["minPeople"] == 2
        assert AuditEvent.objects.filter(action=Action.QUEUE_REQUIREMENTS_SET).count() == 1
        assert len(client.get(REQUIREMENTS).json()) == 1

    @pytest.mark.parametrize("role", NON_WRITERS)
    def test_others_cannot_write(self, world: World, role: Role) -> None:
        r = put(login(role), self.url(world), {"requirements": []})
        assert r.status_code == 403

    @pytest.mark.parametrize(
        ("role", "status"),
        [(Role.LEAD, 200), (Role.AGENT, 403), (Role.EXECUTIVE, 403), (Role.CUSTOMER_OPS, 403)],
    )
    def test_read_roles(self, world: World, role: Role, status: int) -> None:
        assert login(role).get(REQUIREMENTS).status_code == status

    def test_unknown_queue_is_404_and_zero_people_refused(self, world: World) -> None:
        client = login(Role.PLANNER)
        assert (
            put(client, "/api/v1/skills/queues/9999/requirements", {"requirements": []}).status_code
            == 404
        )
        r = put(
            client,
            self.url(world),
            {"requirements": [{"kind": "language", "name": "Zulu", "minPeople": 0}]},
        )
        assert r.status_code == 422
        assert not QueueRequirement.objects.exists()


class TestSkillGaps:
    @pytest.fixture
    def roster(self, world: World) -> dict[str, Any]:
        shifts = standard_shifts()
        week = RosterWeek.objects.create(queue=world.q, week_start=MON)
        for who in (world.ann, world.bob):
            ShiftAssignment.objects.create(
                roster_week=week, employee=who, day=MON, template=shifts["D1"]
            )
        ShiftAssignment.objects.create(
            roster_week=week, employee=world.bob, day=MON + timedelta(days=1), template=shifts["D1"]
        )
        QueueRequirement.objects.create(
            queue=world.q, kind="language", name="Afrikaans", min_people=1
        )
        return shifts

    def gaps(self, role: Role = Role.PLANNER) -> Any:
        return login(role).get(GAPS, {"start": str(MON), "days": "7"})

    def test_a_shift_with_nobody_holding_the_skill_is_a_gap(
        self, world: World, roster: Any
    ) -> None:
        rows = self.gaps().json()
        assert [(g["day"], g["shiftCode"], g["required"], g["present"]) for g in rows] == [
            ("2026-05-25", "D1", 1, 0),
            ("2026-05-26", "D1", 1, 0),
        ]

    def test_holding_it_closes_the_gap_on_the_days_the_person_works(
        self, world: World, roster: Any
    ) -> None:
        user = planner_user()
        EmployeeCredential.objects.create(
            employee=world.ann, kind="language", name="afrikaans", updated_by=user
        )
        assert [g["day"] for g in self.gaps().json()] == ["2026-05-26"]  # Ann is off on Tuesday

    def test_an_expired_credential_does_not_count_on_the_day(
        self, world: World, roster: Any
    ) -> None:
        user = planner_user()
        EmployeeCredential.objects.create(
            employee=world.bob, kind="language", name="Afrikaans", expires_on=MON, updated_by=user
        )
        assert [g["day"] for g in self.gaps().json()] == ["2026-05-26"]  # held on Monday only

    def test_more_people_required_than_hold_it(self, world: World, roster: Any) -> None:
        QueueRequirement.objects.update(min_people=2)
        user = planner_user()
        EmployeeCredential.objects.create(
            employee=world.ann, kind="language", name="Afrikaans", updated_by=user
        )
        first = self.gaps().json()[0]
        assert (first["required"], first["present"]) == (2, 1)

    def test_no_requirement_means_no_gaps(self, world: World, roster: Any) -> None:
        QueueRequirement.objects.all().delete()
        assert self.gaps().json() == []

    @pytest.mark.parametrize(
        ("role", "status"),
        [
            (Role.ADMIN, 200),
            (Role.PLANNER, 200),
            (Role.LEAD, 403),
            (Role.AGENT, 403),
            (Role.EXECUTIVE, 403),
            (Role.CUSTOMER_OPS, 403),
        ],
    )
    def test_roles(self, world: World, roster: Any, role: Role, status: int) -> None:
        assert self.gaps(role).status_code == status

    def test_window_is_bounded(self, world: World) -> None:
        r = login(Role.PLANNER).get(GAPS, {"start": str(MON), "days": "90"})
        assert r.status_code == 422
