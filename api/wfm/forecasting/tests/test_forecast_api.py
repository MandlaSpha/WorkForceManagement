"""Running, publishing and reading forecasts, end to end on a real PostgreSQL.

The staffing numbers are worked out by hand, independently of the engine:
 history at 10:00 on the three Mondays before 25 May: 40, 20 and 10 calls (oldest first), 180 s each
 weights (decay 0.7, newest first): 1, 0.7, 0.49 -> volume (10 + 0.7*20 + 0.49*40) / 2.19 = 19.909
 traffic 19.909 / 1800 s * 180 s = 1.991 Erlangs
 3 agents reach SL 60.7% (below 80%); 4 agents reach 86.3% -> 4 on the phone
 30% shrinkage: ceil(4 / 0.7) = 6 to roster
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.db import IntegrityError, transaction
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit import services as audit_services
from wfm.audit.models import Action, AuditChange, AuditEvent, Outcome
from wfm.forecasting import services
from wfm.forecasting.models import ForecastInterval, ForecastStatus, ForecastVersion
from wfm.telephony.models import Queue

from .helpers import MON_4, MON_11, MON_18, MON_25, import_mondays, login

pytestmark = pytest.mark.django_db

VERSIONS = "/api/v1/forecasting/versions"
HAND_VOLUME = (10 + 0.7 * 20 + 0.49 * 40) / 2.19


@pytest.fixture
def history() -> None:
    import_mondays({MON_4: 40, MON_11: 20, MON_18: 10})


def queue_id() -> int:
    return Queue.objects.get(name="QueueA").pk


def run(client: Client, day: Any = MON_25, to: Any = None, **extra: Any) -> Any:
    body = {"queueId": queue_id(), "dateFrom": str(day), "dateTo": str(to or day), **extra}
    return client.post(VERSIONS, body, content_type="application/json")


def intervals(client: Client, version_id: str) -> list[dict[str, Any]]:
    return client.get(f"{VERSIONS}/{version_id}/intervals").json()  # type: ignore[no-any-return]


@pytest.mark.usefixtures("history")
class TestRunningAForecast:
    def test_creates_a_draft_with_a_forecast_for_every_half_hour(self) -> None:
        response = run(login())
        assert response.status_code == 201, response.content
        version = response.json()
        assert (version["status"], version["intervalCount"], version["queue"]) == (
            "draft",
            48,
            "QueueA",
        )
        assert version["publishedAt"] is None

    def test_the_busy_half_hour_is_forecast_and_staffed_as_worked_out_by_hand(self) -> None:
        version = run(login()).json()
        busy = next(i for i in intervals(login(), version["id"]) if i["volume"] > 0)

        # 10:00 South African time is 08:00 UTC.
        assert datetime.fromisoformat(busy["start"]) == datetime(2026, 5, 25, 8, 0, tzinfo=UTC)
        assert busy["volume"] == pytest.approx(HAND_VOLUME)
        assert busy["ahtS"] == pytest.approx(180.0)
        assert busy["requiredRaw"] == 4
        assert busy["required"] == 6
        assert busy["daysUsed"] == 3

    def test_quiet_half_hours_need_nobody(self) -> None:
        version = run(login()).json()
        quiet = [i for i in intervals(login(), version["id"]) if i["volume"] == 0]
        assert len(quiet) == 47
        assert {(i["requiredRaw"], i["required"]) for i in quiet} == {(0, 0)}

    def test_says_the_staffing_assumptions_are_still_defaults(self) -> None:
        version = run(login()).json()
        assert version["assumptionsConfirmed"] is False
        assert version["params"]["slTargetPct"] == 80
        assert version["params"]["shrinkagePct"] == 30

    def test_uses_the_queue_settings_and_records_them_on_the_version(self) -> None:
        Queue.objects.filter(pk=queue_id()).update(shrinkage_pct=0, settings_confirmed=True)
        version = run(login()).json()
        busy = next(i for i in intervals(login(), version["id"]) if i["volume"] > 0)
        assert busy["required"] == busy["requiredRaw"] == 4  # no shrinkage to add
        assert version["assumptionsConfirmed"] is True
        assert version["params"]["shrinkagePct"] == 0

    def test_says_how_old_the_newest_call_data_it_could_use_is(self) -> None:
        version = run(login()).json()
        assert version["historyThrough"] == "2026-05-18"

    def test_a_label_is_kept(self) -> None:
        assert run(login(), label="Week 22 plan").json()["label"] == "Week 22 plan"


@pytest.mark.usefixtures("history")
class TestHonestyAboutWhatCannotBeForecast:
    def test_a_week_forecasts_only_the_days_with_history_and_names_the_others(self) -> None:
        # Only Mondays have history, so Tuesday to Sunday cannot be forecast. They are left out
        # and named, never filled with invented zeros.
        version = run(login(), MON_25, date_to := "2026-05-31").json()
        assert version["intervalCount"] == 48
        assert version["daysWithoutHistory"] == [
            "2026-05-26",
            "2026-05-27",
            "2026-05-28",
            "2026-05-29",
            "2026-05-30",
            date_to,
        ]

    def test_refuses_when_nothing_can_be_forecast_and_stores_nothing(self) -> None:
        response = run(login(), "2026-05-26")  # a Tuesday: no earlier Tuesday has data
        assert response.status_code == 422
        assert response.json()["code"] == "forecast.no_history"
        assert ForecastVersion.objects.count() == 0
        refusal = AuditEvent.objects.get(action=Action.FORECAST_REFUSED)
        assert (refusal.outcome, refusal.reason) == (Outcome.FAILED, "forecast.no_history")

    def test_never_looks_at_the_day_it_predicts_or_later(self) -> None:
        before = intervals(login(), run(login()).json()["id"])
        # A big spike on the day itself (55 calls against a forecast of about 20) must not change
        # the forecast for 25 May.
        import_mondays({MON_25: 55})
        later = intervals(login(), run(login()).json()["id"])
        assert before == later

    @pytest.mark.parametrize(
        ("start", "end", "code"),
        [
            ("2026-05-31", "2026-05-25", "forecast.range_invalid"),
            ("2026-05-01", "2026-07-15", "forecast.range_too_long"),
        ],
    )
    def test_refuses_a_bad_range_and_says_why(self, start: str, end: str, code: str) -> None:
        response = run(login(), start, end)
        assert (response.status_code, response.json()["code"]) == (422, code)

    def test_an_unknown_queue_is_a_404(self) -> None:
        response = login().post(
            VERSIONS,
            {"queueId": 999999, "dateFrom": "2026-05-25", "dateTo": "2026-05-25"},
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.usefixtures("history")
class TestPublishing:
    def test_publishing_makes_a_draft_live(self) -> None:
        draft = run(login()).json()
        response = login().post(f"{VERSIONS}/{draft['id']}/publish")
        assert response.status_code == 200
        assert response.json()["status"] == "published"
        assert response.json()["publishedAt"] is not None

    def test_a_second_publish_archives_the_first_so_exactly_one_is_live(self) -> None:
        first = run(login()).json()
        second = run(login()).json()
        login().post(f"{VERSIONS}/{first['id']}/publish")
        login().post(f"{VERSIONS}/{second['id']}/publish")

        statuses = {str(k): v for k, v in ForecastVersion.objects.values_list("id", "status")}
        assert statuses[first["id"]] == ForecastStatus.ARCHIVED
        assert statuses[second["id"]] == ForecastStatus.PUBLISHED
        assert ForecastVersion.objects.filter(status=ForecastStatus.PUBLISHED).count() == 1

    def test_publishing_the_live_version_again_changes_nothing(self) -> None:
        draft = run(login()).json()
        login().post(f"{VERSIONS}/{draft['id']}/publish")
        before = AuditEvent.objects.filter(action=Action.FORECAST_PUBLISHED).count()

        again = login().post(f"{VERSIONS}/{draft['id']}/publish")

        assert again.status_code == 200
        assert AuditEvent.objects.filter(action=Action.FORECAST_PUBLISHED).count() == before

    def test_an_archived_version_cannot_be_brought_back(self) -> None:
        first = run(login()).json()
        second = run(login()).json()
        login().post(f"{VERSIONS}/{first['id']}/publish")
        login().post(f"{VERSIONS}/{second['id']}/publish")

        response = login().post(f"{VERSIONS}/{first['id']}/publish")

        assert (response.status_code, response.json()["code"]) == (409, "forecast.archived")

    def test_publishing_an_unknown_version_is_a_404(self) -> None:
        response = login().post(f"{VERSIONS}/00000000-0000-4000-8000-000000000000/publish")
        assert response.status_code == 404

    def test_two_people_publishing_at_once_get_one_winner_and_a_clear_conflict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        draft = run(login()).json()

        def lose_the_race(self: ForecastVersion, *args: Any, **kwargs: Any) -> None:
            raise IntegrityError("duplicate key value violates forecasting_one_published_per_queue")

        monkeypatch.setattr(ForecastVersion, "save", lose_the_race)
        response = login().post(f"{VERSIONS}/{draft['id']}/publish")

        assert (response.status_code, response.json()["code"]) == (409, "forecast.conflict")
        assert AuditEvent.objects.filter(action=Action.FORECAST_REFUSED).count() == 1

    def test_the_database_itself_refuses_two_live_versions_for_one_queue(self) -> None:
        a = run(login()).json()
        b = run(login()).json()
        ForecastVersion.objects.filter(pk=a["id"]).update(status=ForecastStatus.PUBLISHED)
        with pytest.raises(IntegrityError), transaction.atomic():
            ForecastVersion.objects.filter(pk=b["id"]).update(status=ForecastStatus.PUBLISHED)


@pytest.mark.usefixtures("history")
class TestAudit:
    def test_a_run_says_who_what_and_how_much(self) -> None:
        version = run(login()).json()
        event = AuditEvent.objects.get(action=Action.FORECAST_RUN)
        assert (event.actor_role, event.entity_id) == (Role.PLANNER, version["id"])
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes == {"queue": "QueueA", "range": "2026-05-25..2026-05-25", "intervals": "48"}

    def test_a_publish_records_both_the_new_live_version_and_the_one_it_archived(self) -> None:
        first = run(login()).json()
        second = run(login()).json()
        login().post(f"{VERSIONS}/{first['id']}/publish")
        login().post(f"{VERSIONS}/{second['id']}/publish")

        event = AuditEvent.objects.filter(action=Action.FORECAST_PUBLISHED).latest("chain_seq")
        changes = {
            (c.entity_id, c.new_value)
            for c in AuditChange.objects.filter(event=event, field="status")
        }
        assert changes == {(second["id"], "published"), (first["id"], "archived")}


@pytest.mark.usefixtures("history")
class TestNothingHalfDone:
    def test_a_run_whose_audit_event_cannot_be_written_leaves_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def refuse(**kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_services, "record", refuse)
        login()  # creates the planner
        with pytest.raises(RuntimeError):
            services.run_forecast(
                user=User.objects.get(username="u-planner"),
                queue_id=queue_id(),
                date_from=MON_25,
                date_to=MON_25,
            )
        assert (ForecastVersion.objects.count(), ForecastInterval.objects.count()) == (0, 0)

    def test_a_publish_whose_audit_event_cannot_be_written_stays_a_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        draft = run(login()).json()

        def refuse(**kwargs: Any) -> None:
            raise RuntimeError("audit store unavailable")

        monkeypatch.setattr(audit_services, "record", refuse)
        with pytest.raises(RuntimeError):
            login().post(f"{VERSIONS}/{draft['id']}/publish")
        assert ForecastVersion.objects.get(pk=draft["id"]).status == ForecastStatus.DRAFT


@pytest.mark.usefixtures("history")
class TestWhoMayDoWhat:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_run_and_publish(self, role: Role) -> None:
        draft = run(login(role))
        assert draft.status_code == 201
        assert login(role).post(f"{VERSIONS}/{draft.json()['id']}/publish").status_code == 200

    def test_a_lead_can_read_forecasts_but_not_change_them(self) -> None:
        draft = run(login(Role.PLANNER)).json()
        lead = login(Role.LEAD)

        assert len(lead.get(VERSIONS).json()) == 1
        assert lead.get(f"{VERSIONS}/{draft['id']}/intervals").status_code == 200
        assert run(lead).status_code == 403
        assert lead.post(f"{VERSIONS}/{draft['id']}/publish").status_code == 403
        assert ForecastVersion.objects.get(pk=draft["id"]).status == ForecastStatus.DRAFT
        assert ForecastVersion.objects.count() == 1

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_see_and_change_nothing(self, role: Role) -> None:
        draft = run(login(Role.PLANNER)).json()
        other = login(role)
        assert other.get(VERSIONS).status_code == 403
        assert other.get(f"{VERSIONS}/{draft['id']}/intervals").status_code == 403
        assert run(other).status_code == 403
        assert ForecastVersion.objects.count() == 1


@pytest.mark.usefixtures("history")
class TestReading:
    def test_lists_versions_newest_first_with_their_interval_counts(self) -> None:
        run(login(), label="first")
        run(login(), label="second")
        listing = login().get(VERSIONS).json()
        assert [v["label"] for v in listing] == ["second", "first"]
        assert {v["intervalCount"] for v in listing} == {48}

    def test_can_be_filtered_by_queue(self) -> None:
        run(login())
        assert login().get(VERSIONS, {"queue_id": queue_id()}).json() != []
        assert login().get(VERSIONS, {"queue_id": 999999}).json() == []

    def test_an_unknown_version_has_no_intervals(self) -> None:
        response = login().get(f"{VERSIONS}/00000000-0000-4000-8000-000000000000/intervals")
        assert response.status_code == 404


class TestAccuracy:
    """History at 10:00 on Mondays 4, 11 and 18 May: 10, 12 and 14 calls.
    11 May is forecast from 4 May alone: 10 against 12, error 2 of 12 -> 83.33%.
    18 May is forecast from 11 and 4 May: (12 + 0.7*10) / 1.7 = 11.176 against 14,
    error 2.824 of 14 -> 79.83%. Pooled: 4.824 / 26 -> 81.45%. 4 May has nothing before it.
    All the calls are in one half-hour, so the daily score is the same number here; the engine
    tests show a case where they differ.
    """

    ACCURACY = "/api/v1/forecasting/accuracy"

    @pytest.fixture(autouse=True)
    def _history(self) -> None:
        import_mondays({MON_4: 10, MON_11: 12, MON_18: 14})

    def test_scores_each_day_against_only_the_days_before_it(self) -> None:
        body = login().get(self.ACCURACY, {"queue_id": queue_id()}).json()
        assert [d["date"] for d in body["days"]] == ["2026-05-11", "2026-05-18"]
        assert [d["daysUsed"] for d in body["days"]] == [1, 2]
        assert body["days"][0]["accuracyPct"] == pytest.approx(100 * (1 - 2 / 12))
        assert body["days"][1]["accuracyPct"] == pytest.approx(100 * (1 - (14 - 19 / 1.7) / 14))
        assert body["overallAccuracyPct"] == pytest.approx(100 * (1 - (2 + 14 - 19 / 1.7) / 26))

    def test_scores_the_days_total_as_well_as_each_half_hour(self) -> None:
        body = login().get(self.ACCURACY, {"queue_id": queue_id()}).json()
        assert [d["dailyAccuracyPct"] for d in body["days"]] == [
            pytest.approx(100 * (1 - 2 / 12)),
            pytest.approx(100 * (1 - (14 - 19 / 1.7) / 14)),
        ]
        assert body["overallDailyAccuracyPct"] == pytest.approx(
            100 * (1 - (2 + 14 - 19 / 1.7) / 26)
        )

    def test_states_the_method_so_the_number_can_be_judged(self) -> None:
        body = login().get(self.ACCURACY, {"queue_id": queue_id()}).json()
        assert (body["weeks"], body["decay"]) == (4, 0.7)

    def test_an_unknown_queue_is_a_404(self) -> None:
        assert login().get(self.ACCURACY, {"queue_id": 999999}).status_code == 404

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_is_not_for_every_role(self, role: Role) -> None:
        assert login(role).get(self.ACCURACY, {"queue_id": queue_id()}).status_code == 403


class TestQueueSettingsAreVisibleAsAssumptions:
    def test_the_queues_endpoint_says_the_settings_are_unconfirmed_defaults(self) -> None:
        import_mondays({MON_4: 1})
        queue = login().get("/api/v1/telephony/queues").json()[0]
        assert queue["settingsConfirmed"] is False
        assert (queue["slTargetPct"], queue["slThresholdS"]) == (80, 20)
        assert (queue["occupancyCeilingPct"], queue["shrinkagePct"]) == (85, 30)
