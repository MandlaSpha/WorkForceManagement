"""The audit log viewer (AUD-11, AUD-12): admin only, filters, paging, the CSV, and that looking at
the log is itself on the log without ever storing what was seen."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.audit import services
from wfm.audit.models import Action, AuditEvent, Outcome
from wfm.scheduling.tests.helpers import login

pytestmark = pytest.mark.django_db

EVENTS = "/api/v1/audit/events"
CSV = "/api/v1/audit/events.csv"
OPTIONS = "/api/v1/audit/options"
CHAIN = "/api/v1/audit/chain"
URLS = [EVENTS, CSV, OPTIONS, CHAIN]
REFUSED = [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS]


def seed() -> User:
    actor = User.objects.create(username="amy-actor", role=Role.PLANNER)
    other = User.objects.create(username="bob-other", role=Role.LEAD)
    services.record(
        actor=actor,
        action=Action.LEAVE_APPROVED,
        entity_type="leave",
        entity_id="7",
        changes=[services.FieldChange("leave", "7", "status", "pending", "approved")],
    )
    services.record(
        actor=other, action=Action.ROSTER_REFUSED, outcome=Outcome.DENIED, entity_type="roster"
    )
    services.record(actor=None, action=Action.REPORT_SENT, entity_type="report")
    return actor


@pytest.mark.parametrize("url", URLS)
@pytest.mark.parametrize("role", REFUSED)
def test_every_other_role_is_refused_and_the_attempt_is_audited(role: Role, url: str) -> None:
    response = login(role).get(url)
    assert response.status_code == 403
    assert AuditEvent.objects.filter(action=Action.ACCESS_DENIED).count() == 1


@pytest.mark.parametrize("url", URLS)
def test_anonymous_is_refused(client: Any, url: str) -> None:
    assert client.get(url).status_code == 401


@pytest.mark.parametrize("url", URLS)
def test_admin_may_read(url: str) -> None:
    assert login(Role.ADMIN).get(url).status_code == 200


def test_for_user_shows_nothing_to_anyone_but_an_admin() -> None:
    seed()
    for role in REFUSED:
        user = User.objects.create(username=f"x-{role.value}", role=role)
        assert not AuditEvent.objects.for_user(user).exists()
    admin = User.objects.create(username="x-admin", role=Role.ADMIN)
    assert AuditEvent.objects.for_user(admin).exists()


def test_lists_newest_first_with_actor_and_old_new_values() -> None:
    seed()
    body = login(Role.ADMIN).get(EVENTS, {"action": Action.LEAVE_APPROVED}).json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["actor"] == "amy-actor"
    assert item["changes"] == [
        {
            "entityType": "leave",
            "entityId": "7",
            "field": "status",
            "old": "pending",
            "new": "approved",
        }
    ]
    everything = login(Role.ADMIN).get(EVENTS).json()["items"]
    assert [e["seq"] for e in everything] == sorted((e["seq"] for e in everything), reverse=True)


def test_filters_by_actor_action_entity_outcome_and_time() -> None:
    seed()
    admin = login(Role.ADMIN)

    def total(**q: str) -> int:
        return int(admin.get(EVENTS, q).json()["total"])

    assert total(actor="amy") == 1
    assert total(actor="system") == 1  # no user: the job
    assert total(action=Action.ROSTER_REFUSED) == 1
    assert total(entityType="leave") == 1
    assert total(outcome="denied") == 1
    future = (timezone.now() + timedelta(days=1)).isoformat()
    past = (timezone.now() - timedelta(days=1)).isoformat()
    assert total(since=future) == 0
    assert total(until=past) == 0
    assert total(since=past, until=future, action=Action.REPORT_SENT) == 1


def test_a_range_that_ends_before_it_starts_is_refused() -> None:
    now = timezone.now()
    response = login(Role.ADMIN).get(
        EVENTS, {"since": now.isoformat(), "until": (now - timedelta(hours=1)).isoformat()}
    )
    assert response.status_code == 422
    assert response.json()["code"] == "audit.bad_range"


def test_pages_and_caps_the_page_size() -> None:
    for i in range(5):
        services.record(actor=None, action="test.event", reason=str(i))
    admin = login(Role.ADMIN)
    first = admin.get(EVENTS, {"action": "test.event", "pageSize": "2"}).json()
    second = admin.get(EVENTS, {"action": "test.event", "pageSize": "2", "page": "2"}).json()
    assert first["total"] == 5
    assert len(first["items"]) == 2
    assert len(second["items"]) == 2
    assert not {e["id"] for e in first["items"]} & {e["id"] for e in second["items"]}
    assert admin.get(EVENTS, {"pageSize": "100000"}).json()["pageSize"] == 200


def test_viewing_is_audited_with_the_shape_of_the_search_and_never_its_values() -> None:
    seed()
    login(Role.ADMIN).get(EVENTS, {"actor": "amy-actor", "outcome": "success"})
    event = AuditEvent.objects.filter(action=Action.AUDIT_VIEWED).latest("chain_seq")
    assert event.reason == "filters: actor,outcome; page 1"
    assert "amy" not in event.reason
    assert event.actor_role == Role.ADMIN
    assert not event.changes.exists()


def test_the_csv_is_audited_last_and_counts_rows() -> None:
    seed()
    response = login(Role.ADMIN).get(CSV, {"action": Action.LEAVE_APPROVED})
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    assert response["Cache-Control"] == "no-store"
    rows = list(csv.DictReader(io.StringIO(response.content.decode())))
    assert len(rows) == 1
    assert rows[0]["Who"] == "amy-actor"
    event = AuditEvent.objects.get(action=Action.AUDIT_EXPORTED)
    assert event.reason == "filters: action; 1 rows"
    assert event.chain_seq == AuditEvent.objects.latest("chain_seq").chain_seq


def test_the_csv_cannot_run_as_a_formula() -> None:
    evil = User.objects.create(username="=cmd|calc", role=Role.PLANNER)
    services.record(actor=evil, action="test.event", reason="@SUM(1)")
    text = login(Role.ADMIN).get(CSV, {"action": "test.event"}).content.decode()
    row = next(csv.DictReader(io.StringIO(text)))
    assert row["Who"] == "'=cmd|calc"
    assert row["Reason"] == "'@SUM(1)"


def test_options_list_actions_entities_and_outcomes() -> None:
    seed()
    body = login(Role.ADMIN).get(OPTIONS).json()
    assert {"value": "leave.approved", "label": "Leave approved"} in body["actions"]
    assert {"value": "leave", "label": "leave"} in body["entityTypes"]
    assert [o["value"] for o in body["outcomes"]] == ["success", "denied", "failed"]


def test_chain_status_reports_intact_and_never_writes() -> None:
    seed()
    before = AuditEvent.objects.count()
    body = login(Role.ADMIN).get(CHAIN).json()
    assert body["intact"] is True
    assert body["problemCount"] == 0
    assert body["events"] == before
    assert AuditEvent.objects.count() == before


def test_the_viewer_has_no_write_routes() -> None:
    admin = login(Role.ADMIN)
    for url in (EVENTS, CSV, OPTIONS, CHAIN):
        assert admin.post(url).status_code == 405
        assert admin.delete(url).status_code == 405
