"""The events calendar (FC-04) on a real PostgreSQL: who may change it, what it refuses, how it
reaches a forecast, and what it leaves in the audit trail.

The forecast numbers are the hand-worked ones of test_forecast_api: history at 10:00 on the three
Mondays before 25 May of 40, 20 and 10 calls gives 19.909 expected calls at 10:00 on 25 May.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.forecasting.models import ForecastEvent, ForecastInterval
from wfm.telephony.models import Queue

from .helpers import MON_4, MON_11, MON_18, MON_25, add_days, import_mondays, login

pytestmark = pytest.mark.django_db

EVENTS = "/api/v1/forecasting/events"
VERSIONS = "/api/v1/forecasting/versions"
HAND_VOLUME = (10 + 0.7 * 20 + 0.49 * 40) / 2.19  # 19.909 calls at 10:00 on 25 May


@pytest.fixture
def history() -> None:
    import_mondays({MON_4: 40, MON_11: 20, MON_18: 10})
    # Five calls a day spread over five half-hours: one call in the 10:00 half-hour each Monday.
    add_days("QueueB", {MON_4: 5, MON_11: 5, MON_18: 5})


def queue_id(name: str = "QueueA") -> int:
    return Queue.objects.get(name=name).pk


def body(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "Payment run",
        "queueId": None,
        "dateFrom": str(MON_25),
        "dateTo": str(MON_25),
        "upliftPct": 50,
    }
    return {**base, **overrides}


def add(client: Client, **overrides: Any) -> Any:
    return client.post(EVENTS, body(**overrides), content_type="application/json")


def ten_am(version_id: str) -> ForecastInterval:
    """The 10:00 half-hour (the database is queried in South African time)."""
    return ForecastInterval.objects.get(
        version__pk=version_id,
        interval_start__date=MON_25,
        interval_start__hour=10,
        interval_start__minute=0,
    )


def run(client: Client, name: str = "QueueA") -> dict[str, Any]:
    payload = {"queueId": queue_id(name), "dateFrom": str(MON_25), "dateTo": str(MON_25)}
    return client.post(VERSIONS, payload, content_type="application/json").json()  # type: ignore[no-any-return]


@pytest.mark.usefixtures("history")
class TestWhoMay:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_these_roles_read_the_calendar(self, role: Role) -> None:
        assert login(role).get(EVENTS).status_code == 200

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_cannot_read_it(self, role: Role) -> None:
        assert login(role).get(EVENTS).status_code == 403

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planners_and_admins_change_it(self, role: Role) -> None:
        client = login(role)
        created = add(client)
        assert created.status_code == 201
        event_id = created.json()["id"]
        changed = client.put(
            f"{EVENTS}/{event_id}", body(upliftPct=10), content_type="application/json"
        )
        assert changed.status_code == 200
        assert client.delete(f"{EVENTS}/{event_id}").status_code == 200

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_changes_it(self, role: Role) -> None:
        event_id = add(login(Role.PLANNER)).json()["id"]
        client = login(role)
        assert add(client).status_code == 403
        put = client.put(f"{EVENTS}/{event_id}", body(), content_type="application/json")
        assert put.status_code == 403
        assert client.delete(f"{EVENTS}/{event_id}").status_code == 403
        assert ForecastEvent.objects.count() == 1  # untouched


@pytest.mark.usefixtures("history")
class TestWhatIsRefused:
    @pytest.mark.parametrize(
        ("overrides", "code"),
        [
            ({"name": "   "}, "event.name_invalid"),
            ({"dateTo": str(date(2026, 5, 24))}, "event.range_invalid"),
            ({"dateTo": str(date(2027, 5, 26))}, "event.range_too_long"),  # 367 days
            ({"upliftPct": -101}, "event.uplift_invalid"),
            ({"upliftPct": 501}, "event.uplift_invalid"),
        ],
    )
    def test_bad_events_are_refused_with_a_reason_and_nothing_is_stored(
        self, overrides: dict[str, Any], code: str
    ) -> None:
        response = add(login(), **overrides)
        assert response.status_code == 422
        assert response.json()["code"] == code
        assert ForecastEvent.objects.count() == 0

    def test_the_limits_themselves_are_allowed(self) -> None:
        client = login()
        assert add(client, upliftPct=-100).status_code == 201
        assert add(client, upliftPct=500).status_code == 201
        assert add(client, dateTo=str(date(2027, 5, 25))).status_code == 201  # exactly 366 days

    def test_an_unknown_queue_is_not_found(self) -> None:
        assert add(login(), queueId=999_999).status_code == 404

    def test_changing_or_removing_an_event_that_does_not_exist_is_not_found(self) -> None:
        client = login()
        assert (
            client.put(f"{EVENTS}/999999", body(), content_type="application/json").status_code
            == 404
        )
        assert client.delete(f"{EVENTS}/999999").status_code == 404


@pytest.mark.usefixtures("history")
class TestTheCalendar:
    def test_lists_soonest_first_and_says_which_queue(self) -> None:
        client = login()
        add(client, name="Later", dateFrom="2026-07-01", dateTo="2026-07-02", queueId=queue_id())
        add(client, name="Sooner")
        events = client.get(EVENTS).json()
        assert [e["name"] for e in events] == ["Sooner", "Later"]
        assert (events[0]["queue"], events[1]["queue"]) == (None, "QueueA")

    def test_a_queue_filter_keeps_its_own_events_and_the_all_queue_ones(self) -> None:
        client = login()
        add(client, name="For A", queueId=queue_id("QueueA"))
        add(client, name="For B", queueId=queue_id("QueueB"))
        add(client, name="For all")
        names = {e["name"] for e in client.get(f"{EVENTS}?queue_id={queue_id('QueueA')}").json()}
        assert names == {"For A", "For all"}


@pytest.mark.usefixtures("history")
class TestEffectOnForecasts:
    def test_an_event_scales_the_forecast_it_covers(self) -> None:
        add(login(), upliftPct=50, queueId=queue_id())
        version = run(login())

        assert ten_am(version["id"]).volume == pytest.approx(HAND_VOLUME * 1.5)
        applied = version["params"]["events"]
        assert [(e["name"], e["upliftPct"], e["days"]) for e in applied] == [
            ("Payment run", 50, [str(MON_25)])
        ]

    def test_staffing_follows_the_adjusted_volume(self) -> None:
        before = ten_am(run(login())["id"]).required_raw
        add(login(), upliftPct=100)
        after = ten_am(run(login())["id"]).required_raw
        assert before is not None
        assert after is not None
        assert after > before

    def test_an_event_for_all_queues_applies_to_each_queue(self) -> None:
        add(login(), upliftPct=100)
        a = ten_am(run(login(), "QueueA")["id"]).volume
        b = ten_am(run(login(), "QueueB")["id"]).volume
        assert a == pytest.approx(HAND_VOLUME * 2)
        assert b == pytest.approx(1 * 2)  # QueueB: one call at 10:00 on each Monday

    def test_an_event_for_another_queue_is_ignored(self) -> None:
        add(login(), upliftPct=100, queueId=queue_id("QueueB"))
        version = run(login(), "QueueA")
        assert ten_am(version["id"]).volume == pytest.approx(HAND_VOLUME)
        assert "events" not in version["params"]

    def test_overlapping_events_compound(self) -> None:
        add(login(), name="Campaign", upliftPct=20)
        add(login(), name="Outage", upliftPct=-50)
        version = run(login())
        assert ten_am(version["id"]).volume == pytest.approx(HAND_VOLUME * 0.6)

    def test_minus_100_percent_closes_the_queue_for_the_day(self) -> None:
        add(login(), name="Public closure", upliftPct=-100)
        row = ten_am(run(login())["id"])
        assert (row.volume, row.required, row.required_raw) == (0, 0, 0)

    def test_an_event_on_other_days_changes_nothing(self) -> None:
        add(login(), dateFrom="2026-06-01", dateTo="2026-06-02")
        version = run(login())
        assert ten_am(version["id"]).volume == pytest.approx(HAND_VOLUME)
        assert "events" not in version["params"]

    def test_a_forecast_already_run_keeps_what_it_used(self) -> None:
        old = run(login())
        event_id = add(login(), upliftPct=100).json()["id"]
        assert ten_am(old["id"]).volume == pytest.approx(HAND_VOLUME)  # not rewritten

        new = run(login())
        assert ten_am(new["id"]).volume == pytest.approx(HAND_VOLUME * 2)
        login().delete(f"{EVENTS}/{event_id}")
        assert ten_am(new["id"]).volume == pytest.approx(HAND_VOLUME * 2)  # kept after removal
        assert new["params"]["events"][0]["id"] == event_id  # and says what it used
        assert ten_am(run(login())["id"]).volume == pytest.approx(HAND_VOLUME)


@pytest.mark.usefixtures("history")
class TestAudit:
    @staticmethod
    def changes(action: Action) -> dict[str, tuple[str | None, str | None]]:
        event = AuditEvent.objects.filter(action=action).latest("chain_seq")
        rows = AuditChange.objects.filter(event=event)
        return {c.field: (c.old_value, c.new_value) for c in rows}

    def test_creating_says_who_and_what(self) -> None:
        created = add(login(), queueId=queue_id()).json()
        event = AuditEvent.objects.get(action=Action.FORECAST_EVENT_CREATED)
        assert (event.actor_role, event.entity_id) == (Role.PLANNER, str(created["id"]))
        assert self.changes(Action.FORECAST_EVENT_CREATED) == {
            "name": (None, "Payment run"),
            "queue": (None, "QueueA"),
            "range": (None, "2026-05-25..2026-05-25"),
            "uplift_pct": (None, "+50.00"),
        }

    def test_changing_records_only_what_changed_with_before_and_after(self) -> None:
        client = login()
        event_id = add(client).json()["id"]
        client.put(f"{EVENTS}/{event_id}", body(upliftPct=80), content_type="application/json")
        assert self.changes(Action.FORECAST_EVENT_CHANGED) == {"uplift_pct": ("+50.00", "+80.00")}

    def test_saving_without_changing_anything_records_nothing(self) -> None:
        client = login()
        event_id = add(client).json()["id"]
        client.put(f"{EVENTS}/{event_id}", body(), content_type="application/json")
        assert not AuditEvent.objects.filter(action=Action.FORECAST_EVENT_CHANGED).exists()

    def test_removing_keeps_what_was_removed(self) -> None:
        client = login()
        event_id = add(client, name="Gone").json()["id"]
        client.delete(f"{EVENTS}/{event_id}")
        assert self.changes(Action.FORECAST_EVENT_DELETED)["name"] == ("Gone", None)

    def test_a_refused_event_leaves_no_audit_event_for_a_change(self) -> None:
        add(login(), upliftPct=900)
        assert not AuditEvent.objects.filter(action=Action.FORECAST_EVENT_CREATED).exists()
