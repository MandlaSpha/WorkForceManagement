"""Quality results (QUA-01): the file import, a team's people, one person, and your own.

All data is a few synthetic lines of CSV text. Monday 25 May 2026 is "today". The rules that
matter most: a lead sees their own team only, an agent only themselves, nobody sees a ranking, and
the file's comment column never reaches the database.
"""

from __future__ import annotations

import io
from datetime import date
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from openpyxl import Workbook

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent, Outcome
from wfm.people.tests.team import lead_of
from wfm.quality.models import QualityImport, QualityResult
from wfm.scheduling.models import AgentLogin
from wfm.scheduling.tests.helpers import MON, login, person

pytestmark = pytest.mark.django_db

IMPORT = "/api/v1/quality/imports"
TEAM = "/api/v1/quality/team"
MINE = "/api/v1/quality/mine"
HEADER = "login,date,score,kind,ref,csat,coaching_due\n"
ALL_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]
REVIEW_ROLES = [Role.ADMIN, Role.PLANNER, Role.LEAD]


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: MON)


def as_role(role: Role) -> Client:
    return login(role)


def upload(client: Client, data: str | bytes, name: str = "quality.csv") -> Any:
    raw = data.encode() if isinstance(data, str) else data
    return client.post(IMPORT, {"file": SimpleUploadedFile(name, raw)})


def row(who: str, day: str, score: str, **extra: str) -> str:
    return (
        f"{who},{day},{score},{extra.get('kind', '')},{extra.get('ref', '')},"
        f"{extra.get('csat', '')},{extra.get('due', '')}\n"
    )


class World:
    """Ann (the agent user) is in the lead's team; Bob is nobody's."""

    def __init__(self) -> None:
        self.ann = person("E001", user=User.objects.create(username="u-agent", role=Role.AGENT))
        self.bob = person("E002")
        AgentLogin.objects.create(login="ann1", employee=self.ann)
        AgentLogin.objects.create(login="bob1", employee=self.bob)
        self.lead = lead_of(self.ann)


@pytest.fixture
def world() -> World:
    return World()


FILE = (
    HEADER
    + row("ann1", "2026-05-04", "80", ref="c1", csat="4")
    + row("ann1", "2026-05-18", "90", ref="c2", csat="5", due="2026-06-01")
    + row("bob1", "2026-05-11", "55", ref="c3", due="2026-05-20")
)


@pytest.fixture
def loaded(world: World) -> World:
    assert upload(as_role(Role.PLANNER), FILE).status_code == 201
    return world


class TestImportRoles:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_admin_and_planner_can_import(self, world: World, role: Role) -> None:
        assert upload(as_role(role), FILE).status_code == 201

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_can_import(self, world: World, role: Role) -> None:
        # Failure caught: a lead or agent loading (or rewriting their own) quality results.
        assert upload(as_role(role), FILE).status_code == 403
        assert not QualityResult.objects.exists()

    def test_signed_out_is_refused(self, world: World) -> None:
        assert upload(Client(), FILE).status_code == 401


class TestImport:
    def test_results_are_mapped_through_the_agent_login(self, world: World) -> None:
        body = upload(as_role(Role.PLANNER), FILE).json()
        assert (body["rowsRead"], body["rowsCreated"], body["rowsRejected"]) == (3, 3, 0)
        first = QualityResult.objects.get(ref="c2")
        assert first.employee_id == world.ann.pk
        assert (first.kind, first.csat, first.coaching_due) == ("call", 5, date(2026, 6, 1))

    def test_an_unmapped_login_is_reported_and_never_guessed_or_stored(self, world: World) -> None:
        # Failure caught: "ANN1" or an unknown login attached to the nearest person.
        text = HEADER + row("ANN1", "2026-05-04", "70") + row("ghost", "2026-05-04", "70")
        text += row("ann1", "2026-05-04", "70")
        body = upload(as_role(Role.PLANNER), text).json()
        assert body["unmappedLogins"] == ["ANN1", "ghost"]
        assert (body["rowsUnmapped"], body["rowsCreated"]) == (2, 1)
        assert QualityResult.objects.count() == 1

    def test_bad_rows_get_a_line_number_and_a_reason_and_are_not_quoted(self, world: World) -> None:
        # Failure caught: a bad row stored, aborting the file, or its content echoed back.
        text = HEADER + row("ann1", "2026-05-04", "banana-secret")
        text += row("ann1", "2026-06-30", "70")  # in the future
        text += row("ann1", "2026-05-04", "101")
        text += row("ann1", "2026-05-04", "70", csat="9")
        text += row("ann1", "2026-05-04", "70", kind="email")
        text += row("ann1", "2026-05-04", "70", ref="x", due="not-a-date")
        text += row("ann1", "2026-05-04", "60")
        body = upload(as_role(Role.PLANNER), text).json()
        assert (body["rowsRejected"], body["rowsCreated"]) == (6, 1)
        assert [e["row"] for e in body["errors"]] == [2, 3, 4, 5, 6, 7]
        assert all(e["reason"] for e in body["errors"])
        assert "banana-secret" not in str(body)

    def test_a_repeat_in_the_file_is_rejected_with_its_line(self, world: World) -> None:
        text = (
            HEADER
            + row("ann1", "2026-05-04", "70", ref="a")
            + row("ann1", "2026-05-04", "99", ref="a")
        )
        body = upload(as_role(Role.PLANNER), text).json()
        assert (body["rowsCreated"], body["rowsRejected"]) == (1, 1)
        assert body["errors"][0]["row"] == 3
        assert float(QualityResult.objects.get().score_pct) == 70

    def test_a_later_file_corrects_a_result_and_counts_unchanged(self, loaded: World) -> None:
        # Failure caught: a corrected score in the quality tool never reaching this system, or a
        # second upload duplicating rows.
        again = FILE.replace(",80,", ",85,")
        body = upload(as_role(Role.PLANNER), again).json()
        assert (body["rowsCreated"], body["rowsUpdated"], body["rowsUnchanged"]) == (0, 1, 2)
        assert QualityResult.objects.count() == 3
        assert float(QualityResult.objects.get(ref="c1").score_pct) == 85

    def test_other_columns_are_named_and_never_stored(self, world: World) -> None:
        text = "login,date,score,comment\nann1,2026-05-04,70,rude-to-the-customer-secret\n"
        body = upload(as_role(Role.PLANNER), text).json()
        assert body["ignoredColumns"] == ["comment"]
        stored = " ".join(str(v) for v in QualityResult.objects.values().get().values())
        assert "secret" not in stored

    def test_an_excel_workbook_is_read_like_a_csv(self, world: World) -> None:
        book = Workbook()
        sheet = book.active
        assert sheet is not None
        sheet.append(["Agent login", "Evaluation date", "QA score", "Type"])
        sheet.append(["ann1", date(2026, 5, 4), 88.5, "Ticket"])
        out = io.BytesIO()
        book.save(out)
        body = upload(as_role(Role.PLANNER), out.getvalue(), "quality.xlsx").json()
        assert body["rowsCreated"] == 1
        stored = QualityResult.objects.get()
        assert (stored.kind, float(stored.score_pct)) == ("ticket", 88.5)

    @pytest.mark.parametrize(
        ("data", "name"),
        [
            ("login,date\nann1,2026-05-04\n", "q.csv"),  # no score column
            ("", "q.csv"),
            (b"\xff\xfe\x00", "q.csv"),
            ("login,date,score\n", "q.pdf"),
        ],
    )
    def test_an_unusable_file_is_refused_and_audited(
        self, world: World, data: str | bytes, name: str
    ) -> None:
        response = upload(as_role(Role.PLANNER), data, name)
        assert response.status_code == 422
        assert not QualityResult.objects.exists()
        assert AuditEvent.objects.filter(
            action=Action.QUALITY_IMPORT_REFUSED, outcome=Outcome.FAILED
        ).exists()

    def test_a_file_with_only_a_header_is_refused(self, world: World) -> None:
        assert upload(as_role(Role.PLANNER), HEADER).status_code == 422

    def test_the_audit_event_carries_counts_and_nothing_personal(self, world: World) -> None:
        upload(as_role(Role.PLANNER), FILE)
        event = AuditEvent.objects.get(action=Action.QUALITY_IMPORTED)
        assert event.entity_type == "quality_import"
        batch = QualityImport.objects.get()
        assert event.entity_id == str(batch.pk)
        written = " ".join(f"{c.field} {c.old_value} {c.new_value}" for c in event.changes.all())
        for secret in ("ann1", "bob1", "E001", "Person", "2026-05", "c1", "quality.csv"):
            assert secret not in written
        assert {c.field for c in event.changes.all()} >= {"rows_read", "rows_created"}


def team(role: Role, **params: Any) -> Any:
    return as_role(role).get(TEAM, params)


class TestTeam:
    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_peers_and_non_reviewers_are_refused(self, loaded: World, role: Role) -> None:
        # Failure caught: an agent, an executive or customer operations browsing named results.
        assert team(role).status_code == 403

    def test_signed_out_is_refused(self, loaded: World) -> None:
        assert Client().get(TEAM).status_code == 401

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planner_and_admin_see_everyone_in_employee_number_order(
        self, loaded: World, role: Role
    ) -> None:
        body = team(role).json()
        assert [p["empNo"] for p in body["people"]] == ["E001", "E002"]
        ann = body["people"][0]
        assert (ann["evaluations"], ann["averageScorePct"], ann["latestScorePct"]) == (
            2,
            85.0,
            90.0,
        )
        assert ann["csatAverage"] == 4.5
        assert ann["coachingDue"] == "2026-06-01"
        assert ann["coachingIsDue"] is False
        assert body["people"][1]["coachingIsDue"] is True  # due 20 May, today is 25 May

    def test_a_lead_sees_only_their_own_team(self, loaded: World) -> None:
        # Failure caught: a lead reading another team's quality results.
        body = team(Role.LEAD).json()
        assert [p["empNo"] for p in body["people"]] == ["E001"]
        assert "E002" not in str(body)

    def test_the_window_limits_what_is_summarised(self, loaded: World) -> None:
        body = team(Role.PLANNER, days=10).json()  # 16 May onwards: only Ann's 18 May result
        assert [(p["empNo"], p["evaluations"]) for p in body["people"]] == [("E001", 1)]

    @pytest.mark.parametrize("days", [0, 367])
    def test_a_silly_window_is_refused(self, loaded: World, days: int) -> None:
        assert team(Role.PLANNER, days=days).status_code == 422

    def test_there_is_no_rank_and_no_team_average_anywhere(self, loaded: World) -> None:
        # Failure caught: a league table creeping in as a "position" or an "average of the team".
        text = team(Role.PLANNER).content.decode().lower()
        for word in ("rank", "position", "percentile", "best", "worst", "league", "teamaverage"):
            assert word not in text


class TestPerson:
    def url(self, employee_id: int) -> str:
        return f"/api/v1/quality/people/{employee_id}"

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_reviewers_read_a_person_in_scope(self, loaded: World, role: Role) -> None:
        body = as_role(role).get(self.url(loaded.ann.pk)).json()
        assert [r["ref"] for r in body["results"]] == ["c2", "c1"]  # newest first
        assert body["empNo"] == "E001"

    def test_a_lead_asking_for_someone_outside_the_team_gets_404(self, loaded: World) -> None:
        # Failure caught: a lead reading a person from another team by id.
        assert as_role(Role.LEAD).get(self.url(loaded.bob.pk)).status_code == 404

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_others_are_refused(self, loaded: World, role: Role) -> None:
        assert as_role(role).get(self.url(loaded.ann.pk)).status_code == 403

    def test_an_unknown_person_is_404(self, loaded: World) -> None:
        assert as_role(Role.PLANNER).get(self.url(999_999)).status_code == 404


class TestMine:
    def test_an_agent_sees_only_their_own_results(self, loaded: World) -> None:
        # Failure caught: a colleague's results leaking into the agent's own view.
        body = as_role(Role.AGENT).get(MINE).json()
        assert body["empNo"] == "E001"
        assert [r["ref"] for r in body["results"]] == ["c2", "c1"]
        assert "E002" not in str(body)
        assert "55" not in [r["scorePct"] for r in body["results"]]

    @pytest.mark.parametrize("role", [Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_executives_and_customer_operations_are_refused(
        self, loaded: World, role: Role
    ) -> None:
        assert as_role(role).get(MINE).status_code == 403

    def test_someone_not_on_the_employee_list_gets_a_plain_message(self, loaded: World) -> None:
        response = as_role(Role.PLANNER).get(MINE)
        assert response.status_code == 422
        assert response.json()["code"] == "quality.no_employee_record"

    def test_a_lead_sees_their_own_results_only(self, loaded: World) -> None:
        AgentLogin.objects.create(login="lead1", employee=loaded.lead)
        upload(as_role(Role.PLANNER), HEADER + row("lead1", "2026-05-04", "77"))
        body = as_role(Role.LEAD).get(MINE).json()
        assert [r["scorePct"] for r in body["results"]] == [77.0]
        # ...and their own result is not in the list of their team.
        assert [p["empNo"] for p in team(Role.LEAD).json()["people"]] == ["E001"]


class TestScopeOfTheTable:
    def test_the_scoped_manager_itself_never_shows_a_peer(self, loaded: World) -> None:
        # Failure caught: a future view reading `QualityResult.objects.for_user(...)` and getting
        # colleagues' rows, even though today's endpoints add their own filter as well.
        agent = User.objects.get(username="u-agent")
        scoped = QualityResult.objects.for_user(agent)
        assert set(scoped.values_list("employee_id", flat=True)) == {loaded.ann.pk}
        lead = User.objects.get(username="u-lead")
        assert QualityResult.objects.for_user(lead).filter(employee=loaded.bob).count() == 0
        for role in (Role.EXECUTIVE, Role.CUSTOMER_OPS):
            user = User.objects.create(username=f"x-{role.value}", role=role)
            assert not QualityResult.objects.for_user(user).exists()
