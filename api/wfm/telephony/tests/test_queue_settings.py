"""Confirming a queue's staffing assumptions turns the "unconfirmed defaults" warning off."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.telephony.models import Queue

pytestmark = pytest.mark.django_db

GOOD = {
    "slTargetPct": 85,
    "slThresholdS": 30,
    "occupancyCeilingPct": 80,
    "shrinkagePct": 25,
}


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def put(role: Role, queue_id: int, body: dict[str, Any]) -> Any:
    return client(role).put(
        f"/api/v1/telephony/queues/{queue_id}/settings", body, content_type="application/json"
    )


@pytest.fixture
def q() -> Queue:
    return Queue.objects.create(name="QueueA")


def test_an_admin_sets_and_confirms_the_assumptions(q: Queue) -> None:
    response = put(Role.ADMIN, q.pk, GOOD)
    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["slTargetPct"], body["slThresholdS"]) == (85, 30)
    assert (body["occupancyCeilingPct"], body["shrinkagePct"]) == (80, 25)
    assert body["settingsConfirmed"] is True
    q.refresh_from_db()
    assert q.settings_confirmed is True


@pytest.mark.parametrize("role", [Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE])
def test_only_an_admin_may_do_it_even_with_a_valid_request(role: Role, q: Queue) -> None:
    assert put(role, q.pk, GOOD).status_code == 403
    q.refresh_from_db()
    assert (q.settings_confirmed, float(q.sl_target_pct)) == (False, 80.0)


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"slTargetPct": 0}, "queue.sl_target_invalid"),
        ({"slTargetPct": 101}, "queue.sl_target_invalid"),
        ({"slThresholdS": 0}, "queue.sl_threshold_invalid"),
        ({"slThresholdS": 601}, "queue.sl_threshold_invalid"),
        ({"occupancyCeilingPct": 0}, "queue.occupancy_invalid"),
        ({"shrinkagePct": 100}, "queue.shrinkage_invalid"),
        ({"shrinkagePct": -1}, "queue.shrinkage_invalid"),
    ],
)
def test_refuses_values_that_cannot_be_staffed_to(
    override: dict[str, Any], code: str, q: Queue
) -> None:
    response = put(Role.ADMIN, q.pk, {**GOOD, **override})
    assert (response.status_code, response.json()["code"]) == (422, code)
    q.refresh_from_db()
    assert q.settings_confirmed is False


def test_a_hundred_percent_target_and_zero_shrinkage_are_allowed(q: Queue) -> None:
    assert put(Role.ADMIN, q.pk, {**GOOD, "slTargetPct": 100, "shrinkagePct": 0}).status_code == 200


def test_an_unknown_queue_is_a_404() -> None:
    assert put(Role.ADMIN, 99999, GOOD).status_code == 404


def test_the_change_is_audited_with_old_and_new_values(q: Queue) -> None:
    put(Role.ADMIN, q.pk, GOOD)
    event = AuditEvent.objects.get(action=Action.QUEUE_SETTINGS_CHANGED)
    assert event.actor_role == Role.ADMIN
    changes = {c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)}
    assert changes["sl_target_pct"] == ("80.00", "85")
    assert changes["shrinkage_pct"] == ("30.00", "25")
    assert changes["settings_confirmed"] == ("False", "True")


def test_a_forecast_run_afterwards_records_the_confirmed_values(q: Queue) -> None:
    # The version carries the assumptions it was made with, so an old forecast is never
    # re-described by later settings.
    from wfm.forecasting.tests.helpers import MON_4, MON_11, MON_25, import_mondays

    import_mondays({MON_4: 10, MON_11: 10}, queue="QueueA")
    q = Queue.objects.get(name="QueueA")
    run = {"queueId": q.pk, "dateFrom": str(MON_25), "dateTo": str(MON_25)}
    before = (
        client(Role.PLANNER)
        .post("/api/v1/forecasting/versions", run, content_type="application/json")
        .json()
    )
    put(Role.ADMIN, q.pk, GOOD)
    after = (
        client(Role.PLANNER)
        .post("/api/v1/forecasting/versions", run, content_type="application/json")
        .json()
    )

    assert (before["assumptionsConfirmed"], before["params"]["slTargetPct"]) == (False, 80)
    assert (after["assumptionsConfirmed"], after["params"]["slTargetPct"]) == (True, 85)
