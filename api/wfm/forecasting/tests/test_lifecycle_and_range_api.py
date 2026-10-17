"""Discarding a draft, withdrawing the live forecast, and reading a forecast over a week or month.

Numbers worked by hand, as in test_forecast_api: 10:00 on Monday 25 May 2026 forecasts 19.909 calls
at 180 s, which needs 4 on the phones and 6 to roster; no other half-hour has calls, so the day
needs 6 at its peak and 6 x 0.5 = 3 agent-hours.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit import services as audit_services
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.forecasting.models import ForecastEvent, ForecastInterval, ForecastStatus, ForecastVersion
from wfm.scheduling.selectors import week_plan

from .helpers import MON_4, MON_11, MON_18, MON_25, import_mondays, login
from .test_forecast_api import HAND_VOLUME, VERSIONS, queue_id, run

pytestmark = pytest.mark.django_db

REASON = {"reason": "Built on the wrong week"}
UNKNOWN = "00000000-0000-4000-8000-000000000000"


@pytest.fixture(autouse=True)
def history() -> None:
    import_mondays({MON_4: 40, MON_11: 20, MON_18: 10})


def post(client: Client, path: str, body: dict[str, Any] | None = None) -> Any:
    return client.post(path, body if body is not None else REASON, content_type="application/json")


def live_version() -> dict[str, Any]:
    version = run(login()).json()
    assert login().post(f"{VERSIONS}/{version['id']}/publish").status_code == 200
    return version  # type: ignore[no-any-return]


class TestDiscardingADraft:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_delete_a_draft_and_its_half_hours(self, role: Role) -> None:
        draft = run(login()).json()
        response = post(login(role), f"{VERSIONS}/{draft['id']}/discard")
        assert response.status_code == 200, response.content
        assert ForecastVersion.objects.count() == 0
        assert ForecastInterval.objects.count() == 0

    def test_the_reason_is_audited_as_the_last_write(self) -> None:
        draft = run(login()).json()
        post(login(), f"{VERSIONS}/{draft['id']}/discard")

        event = AuditEvent.objects.get(action=Action.FORECAST_DISCARDED)
        assert (event.entity_id, event.reason, event.actor_role) == (
            draft["id"],
            REASON["reason"],
            Role.PLANNER,
        )
        assert event == AuditEvent.objects.latest("chain_seq")
        changes = {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }
        assert changes["status"] == ("draft", "discarded")
        assert changes["range"] == ("2026-05-25..2026-05-25", None)

    # Failure caught: a discard that deletes the draft but loses the audit event (or the reverse).
    def test_a_discard_whose_audit_event_cannot_be_written_leaves_the_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        draft = run(login()).json()

        def refuse(**kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_services, "record", refuse)
        with pytest.raises(RuntimeError):
            post(login(), f"{VERSIONS}/{draft['id']}/discard")
        assert ForecastVersion.objects.filter(pk=draft["id"]).exists()
        assert ForecastInterval.objects.count() == 48

    def test_a_published_forecast_cannot_be_discarded(self) -> None:
        live = live_version()
        response = post(login(), f"{VERSIONS}/{live['id']}/discard")
        assert (response.status_code, response.json()["code"]) == (409, "forecast.not_draft")
        assert ForecastVersion.objects.get(pk=live["id"]).status == ForecastStatus.PUBLISHED

    def test_an_archived_forecast_cannot_be_discarded(self) -> None:
        live = live_version()
        post(login(), f"{VERSIONS}/{live['id']}/archive")
        response = post(login(), f"{VERSIONS}/{live['id']}/discard")
        assert (response.status_code, response.json()["code"]) == (409, "forecast.not_draft")
        assert ForecastVersion.objects.filter(pk=live["id"]).exists()

    def test_an_unknown_version_is_a_404(self) -> None:
        assert post(login(), f"{VERSIONS}/{UNKNOWN}/discard").status_code == 404

    def test_a_reason_is_required(self) -> None:
        draft = run(login()).json()
        for body in ({}, {"reason": ""}, {"reason": "  "}, {"reason": "x" * 201}):
            assert post(login(), f"{VERSIONS}/{draft['id']}/discard", body).status_code in (
                400,
                422,
            )
        assert ForecastVersion.objects.filter(pk=draft["id"]).exists()

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_every_other_role_is_refused_and_nothing_is_deleted(self, role: Role) -> None:
        draft = run(login()).json()
        assert post(login(role), f"{VERSIONS}/{draft['id']}/discard").status_code == 403
        assert ForecastVersion.objects.filter(pk=draft["id"]).exists()
        assert not AuditEvent.objects.filter(action=Action.FORECAST_DISCARDED).exists()


class TestWithdrawingTheLiveForecast:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_archive_the_live_forecast(self, role: Role) -> None:
        live = live_version()
        response = post(login(role), f"{VERSIONS}/{live['id']}/archive")
        assert response.status_code == 200, response.content
        assert response.json()["status"] == "archived"
        assert not ForecastVersion.objects.filter(status=ForecastStatus.PUBLISHED).exists()

    def test_the_reason_is_audited_as_the_last_write(self) -> None:
        live = live_version()
        post(login(), f"{VERSIONS}/{live['id']}/archive")

        event = AuditEvent.objects.get(action=Action.FORECAST_ARCHIVED)
        assert (event.entity_id, event.reason) == (live["id"], REASON["reason"])
        assert event == AuditEvent.objects.latest("chain_seq")
        change = AuditChange.objects.get(event=event, field="status")
        assert (change.old_value, change.new_value) == ("published", "archived")

    # Failure caught: the roster keeping on showing old numbers after the forecast was withdrawn.
    def test_the_roster_then_has_no_forecast_for_the_queue(self) -> None:
        live = live_version()
        planner = User.objects.get(username="u-planner")
        assert week_plan(planner, queue_id(), MON_25).forecast is not None

        post(login(), f"{VERSIONS}/{live['id']}/archive")

        assert week_plan(planner, queue_id(), MON_25).forecast is None

    def test_an_archived_version_stays_viewable(self) -> None:
        live = live_version()
        post(login(), f"{VERSIONS}/{live['id']}/archive")
        listing = login(Role.LEAD).get(VERSIONS).json()
        assert [(v["id"], v["status"]) for v in listing] == [(live["id"], "archived")]
        assert len(login(Role.LEAD).get(f"{VERSIONS}/{live['id']}/intervals").json()) == 48

    def test_a_draft_cannot_be_archived(self) -> None:
        draft = run(login()).json()
        response = post(login(), f"{VERSIONS}/{draft['id']}/archive")
        assert (response.status_code, response.json()["code"]) == (409, "forecast.not_published")
        assert ForecastVersion.objects.get(pk=draft["id"]).status == ForecastStatus.DRAFT

    def test_archiving_twice_is_a_409_not_a_second_audit_event(self) -> None:
        live = live_version()
        post(login(), f"{VERSIONS}/{live['id']}/archive")
        again = post(login(), f"{VERSIONS}/{live['id']}/archive")
        assert (again.status_code, again.json()["code"]) == (409, "forecast.not_published")
        assert AuditEvent.objects.filter(action=Action.FORECAST_ARCHIVED).count() == 1

    def test_an_archive_whose_audit_event_cannot_be_written_stays_live(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        live = live_version()

        def refuse(**kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_services, "record", refuse)
        with pytest.raises(RuntimeError):
            post(login(), f"{VERSIONS}/{live['id']}/archive")
        assert ForecastVersion.objects.get(pk=live["id"]).status == ForecastStatus.PUBLISHED

    def test_an_unknown_version_is_a_404(self) -> None:
        assert post(login(), f"{VERSIONS}/{UNKNOWN}/archive").status_code == 404

    def test_a_reason_is_required(self) -> None:
        live = live_version()
        assert post(login(), f"{VERSIONS}/{live['id']}/archive", {}).status_code in (400, 422)
        assert ForecastVersion.objects.get(pk=live["id"]).status == ForecastStatus.PUBLISHED

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_every_other_role_is_refused_and_the_forecast_stays_live(self, role: Role) -> None:
        live = live_version()
        assert post(login(role), f"{VERSIONS}/{live['id']}/archive").status_code == 403
        assert ForecastVersion.objects.get(pk=live["id"]).status == ForecastStatus.PUBLISHED


def week_version() -> dict[str, Any]:
    """Monday 25 to Sunday 31 May: only the Monday has history, so only it is forecast."""
    return run(login(), MON_25, "2026-05-31").json()  # type: ignore[no-any-return]


def rng(client: Client, version_id: str, start: str, end: str, **extra: Any) -> Any:
    return client.get(
        f"{VERSIONS}/{version_id}/range", {"date_from": start, "date_to": end, **extra}
    )


class TestTheRangeEndpoint:
    def test_a_day_is_added_up_as_worked_out_by_hand(self) -> None:
        version = week_version()
        body = rng(login(), version["id"], "2026-05-25", "2026-05-31").json()

        monday = body["days"][0]
        assert monday["hasForecast"] is True
        assert monday["calls"] == pytest.approx(HAND_VOLUME)
        assert monday["ahtS"] == pytest.approx(180)
        assert (monday["peakRequired"], monday["hoursRequired"]) == (6, 3.0)
        assert (monday["complete"], monday["busiestSlot"]) == (True, 20)  # 10:00

    # Failure caught: a day nobody could forecast shown as a quiet day with 0 calls.
    def test_days_without_a_forecast_say_so_and_carry_no_numbers(self) -> None:
        body = rng(login(), week_version()["id"], "2026-05-25", "2026-05-31").json()
        tuesday = body["days"][1]
        assert tuesday["day"] == "2026-05-26"
        assert (tuesday["hasForecast"], tuesday["reason"]) == (False, "no_history")
        assert (tuesday["calls"], tuesday["peakRequired"], tuesday["hoursRequired"]) == (
            None,
            None,
            None,
        )
        assert len([d for d in body["days"] if d["hasForecast"]]) == 1

    def test_days_outside_the_version_are_told_apart_from_days_it_could_not_forecast(self) -> None:
        version = run(login()).json()  # the Monday only
        body = rng(login(), version["id"], "2026-05-24", "2026-05-26").json()
        assert [(d["day"], d["hasForecast"], d["reason"]) for d in body["days"]] == [
            ("2026-05-24", False, "outside_version"),
            ("2026-05-25", True, None),
            ("2026-05-26", False, "outside_version"),
        ]

    def test_says_which_version_and_status_the_figures_rest_on(self) -> None:
        version = run(login(), label="Week 22").json()
        login().post(f"{VERSIONS}/{version['id']}/publish")
        body = rng(login(), version["id"], "2026-05-25", "2026-05-31").json()
        assert (body["status"], body["label"], body["queue"]) == ("published", "Week 22", "QueueA")
        assert (body["versionDateFrom"], body["versionDateTo"]) == ("2026-05-25", "2026-05-25")

    def test_the_half_hour_grid_comes_only_when_asked_for(self) -> None:
        version = week_version()
        plain = rng(login(), version["id"], "2026-05-25", "2026-05-31").json()
        assert plain["days"][0]["requiredBySlot"] is None

        detailed = rng(login(), version["id"], "2026-05-25", "2026-05-31", detail="true").json()
        grid = detailed["days"][0]["requiredBySlot"]
        assert len(grid) == 48
        assert (grid[20], grid[21], grid[0]) == (6, 0, 0)
        assert detailed["days"][1]["requiredBySlot"] is None  # no forecast, no grid

    def test_busiest_and_quietest_are_named_only_among_forecast_days(self) -> None:
        # Two forecast Mondays, 1 June being a repeat of 25 May's shape but built from different
        # history: both exist, so a busiest and a quietest can be named.
        import_mondays({MON_25: 55})
        version = run(login(), MON_25, "2026-06-01").json()
        body = rng(login(), version["id"], "2026-05-25", "2026-06-01").json()
        forecast_days = [d for d in body["days"] if d["hasForecast"]]
        assert len(forecast_days) == 2
        busiest = max(forecast_days, key=lambda d: d["calls"])["day"]
        quietest = min(forecast_days, key=lambda d: d["calls"])["day"]
        assert (body["busiestDay"], body["quietestDay"]) == (busiest, quietest)

    def test_a_single_forecast_day_is_neither_busiest_nor_quietest(self) -> None:
        body = rng(login(), week_version()["id"], "2026-05-25", "2026-05-31").json()
        assert (body["busiestDay"], body["quietestDay"]) == (None, None)

    def test_events_touching_the_range_are_listed_for_the_queue_and_for_all_queues(self) -> None:
        version = week_version()
        owner = User.objects.get(username="u-planner")
        ForecastEvent.objects.create(
            name="Payday", date_from=date(2026, 5, 25), date_to=date(2026, 5, 26),
            uplift_pct=20, created_by=owner,
        )  # fmt: skip
        ForecastEvent.objects.create(
            name="Next month", date_from=date(2026, 7, 1), date_to=date(2026, 7, 2),
            uplift_pct=5, created_by=owner,
        )  # fmt: skip
        body = rng(login(), version["id"], "2026-05-25", "2026-05-31").json()
        assert [(e["name"], e["upliftPct"]) for e in body["events"]] == [("Payday", 20.0)]

    @pytest.mark.parametrize(
        ("start", "end"), [("2026-05-31", "2026-05-25"), ("2026-05-01", "2026-06-15")]
    )
    def test_a_backwards_or_too_long_range_is_refused(self, start: str, end: str) -> None:
        response = rng(login(), week_version()["id"], start, end)
        assert (response.status_code, response.json()["code"]) == (422, "forecast.range_invalid")

    def test_a_six_week_month_view_is_accepted(self) -> None:
        assert rng(login(), week_version()["id"], "2026-04-27", "2026-06-07").status_code == 200

    def test_an_unknown_version_is_a_404(self) -> None:
        assert rng(login(), UNKNOWN, "2026-05-25", "2026-05-31").status_code == 404

    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN, Role.LEAD])
    def test_readers_can_read_it(self, role: Role) -> None:
        version = week_version()
        assert rng(login(role), version["id"], "2026-05-25", "2026-05-31").status_code == 200

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role) -> None:
        version = week_version()
        assert rng(login(role), version["id"], "2026-05-25", "2026-05-31").status_code == 403
