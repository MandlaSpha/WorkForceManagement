"""Forecast tuning and its back-test (RPT-07), on a real PostgreSQL with the numbers worked by hand.

History at 10:00 on three Mondays, rising: 10, 20 and 30 calls (4, 11 and 18 May). The baseline
forecasts each Monday only from the Mondays before it, newest counting more (weights 1, 0.7):

  11 May   from 4 May only                   10          actual 20
  18 May   (20 + 0.7 * 10) / 1.7 = 15.882               actual 30
  total forecast 25.882, actual 50
    accuracy of the day totals  100 * (1 - 24.118 / 50) = 51.76%
    bias                        (25.882 - 50) / 50      = -48.24%  (ran low)
    suggested multiplier        1 / (1 - 0.4824)        = 1.93

  looking back 1 week only: 11 May 10, 18 May 20 -> total 30, accuracy 60%, bias -40%, suggest 1.67
"""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.forecasting.models import ForecastInterval, ForecastTuning
from wfm.telephony.models import Queue

from .helpers import MON_4, MON_11, MON_18, MON_25, import_mondays, login

pytestmark = pytest.mark.django_db

TUNING = "/api/v1/forecasting/tuning"
BACKTEST = "/api/v1/forecasting/tuning/backtest"
VERSIONS = "/api/v1/forecasting/versions"
ACCURACY = "/api/v1/forecasting/accuracy"


@pytest.fixture
def history() -> None:
    import_mondays({MON_4: 10, MON_11: 20, MON_18: 30})


def queue_id() -> int:
    return Queue.objects.get(name="QueueA").pk


def save(client: Client, **over: Any) -> Any:
    body = {
        "queueId": queue_id(),
        "weeks": 4,
        "decay": 0.7,
        "volumeMultiplier": 1,
        "ahtMultiplier": 1,
        **over,
    }
    return client.put(TUNING, body, content_type="application/json")


def trial(client: Client, **query: Any) -> dict[str, Any]:
    response = client.get(BACKTEST, {"queue_id": queue_id(), **query})
    assert response.status_code == 200, response.content
    return response.json()  # type: ignore[no-any-return]


def run(client: Client) -> dict[str, Any]:
    body = {"queueId": queue_id(), "dateFrom": str(MON_25), "dateTo": str(MON_25)}
    return client.post(VERSIONS, body, content_type="application/json").json()  # type: ignore[no-any-return]


def ten_am(version_id: str) -> ForecastInterval:
    return ForecastInterval.objects.get(
        version__pk=version_id,
        interval_start__date=MON_25,
        interval_start__hour=10,
        interval_start__minute=0,
    )


@pytest.mark.usefixtures("history")
class TestTheTuning:
    def test_starts_as_the_defaults_and_says_nobody_has_saved_it(self) -> None:
        body = login().get(TUNING, {"queue_id": queue_id()}).json()
        assert body == {
            "queueId": queue_id(),
            "queue": "QueueA",
            "weeks": 4,
            "decay": 0.7,
            "volumeMultiplier": 1.0,
            "ahtMultiplier": 1.0,
            "saved": False,
        }

    def test_saving_it_is_remembered(self) -> None:
        response = save(login(), weeks=2, decay=0.5, volumeMultiplier=1.1)
        assert response.status_code == 200, response.content
        body = login().get(TUNING, {"queue_id": queue_id()}).json()
        assert (body["weeks"], body["decay"], body["volumeMultiplier"], body["saved"]) == (
            2,
            0.5,
            1.1,
            True,
        )

    @pytest.mark.parametrize(
        ("over", "code"),
        [
            ({"weeks": 0}, "tuning.weeks_invalid"),
            ({"weeks": 13}, "tuning.weeks_invalid"),
            ({"decay": 0.05}, "tuning.decay_invalid"),
            ({"decay": 1.01}, "tuning.decay_invalid"),
            ({"volumeMultiplier": 0.4}, "tuning.volume_multiplier_invalid"),
            ({"volumeMultiplier": 2.1}, "tuning.volume_multiplier_invalid"),
            ({"ahtMultiplier": 0.4}, "tuning.aht_multiplier_invalid"),
            ({"ahtMultiplier": 2.1}, "tuning.aht_multiplier_invalid"),
        ],
    )
    def test_nonsense_is_refused_and_nothing_is_saved(
        self, over: dict[str, Any], code: str
    ) -> None:
        response = save(login(), **over)
        assert (response.status_code, response.json()["code"]) == (422, code)
        assert ForecastTuning.objects.count() == 0

    def test_the_limits_themselves_are_allowed(self) -> None:
        for over in (
            {"weeks": 1},
            {"weeks": 12},
            {"decay": 0.1},
            {"decay": 1},
            {"volumeMultiplier": 0.5},
            {"volumeMultiplier": 2},
            {"ahtMultiplier": 0.5},
            {"ahtMultiplier": 2},
        ):
            assert save(login(), **over).status_code == 200, over

    def test_an_unknown_queue_is_not_found(self) -> None:
        assert login().get(TUNING, {"queue_id": 999_999}).status_code == 404
        assert save(login(), queueId=999_999).status_code == 404
        assert login().get(BACKTEST, {"queue_id": 999_999}).status_code == 404


@pytest.mark.usefixtures("history")
class TestTheBacktestByHand:
    def test_the_saved_tuning_scored_against_what_happened(self) -> None:
        body = trial(login())
        assert body["candidate"]["days"] == 2
        assert body["candidate"]["dailyPct"] == pytest.approx(51.76, abs=0.01)
        assert body["candidate"]["biasPct"] == pytest.approx(-48.24, abs=0.01)
        assert body["suggestedVolumeMultiplier"] == pytest.approx(1.93)
        # With nothing different asked, the candidate IS the saved one.
        assert body["current"] == body["candidate"]

    def test_looking_back_one_week_only_does_better_on_rising_demand(self) -> None:
        body = trial(login(), weeks=1)
        assert body["candidate"]["dailyPct"] == pytest.approx(60.0)
        assert body["candidate"]["biasPct"] == pytest.approx(-40.0)
        assert body["suggestedVolumeMultiplier"] == pytest.approx(1.67)
        assert body["current"]["dailyPct"] == pytest.approx(51.76, abs=0.01)  # the saved one

    def test_the_suggested_multiplier_removes_the_bias_it_was_worked_out_from(self) -> None:
        asked = trial(login())["suggestedVolumeMultiplier"]
        corrected = trial(login(), volume_multiplier=asked)
        assert abs(corrected["candidate"]["biasPct"]) < 1.0
        assert corrected["candidate"]["dailyPct"] > 95.0

    def test_the_suggestion_builds_on_the_multiplier_already_asked_about(self) -> None:
        # At 1.93 the bias is gone, so the suggestion stays about 1.93 rather than going to 1.
        assert trial(login(), volume_multiplier=1.93)["suggestedVolumeMultiplier"] == (
            pytest.approx(1.93, abs=0.02)
        )

    def test_trying_a_tuning_saves_nothing(self) -> None:
        trial(login(), weeks=1, volume_multiplier=1.5)
        assert ForecastTuning.objects.count() == 0
        assert not AuditEvent.objects.filter(action=Action.FORECAST_TUNING_CHANGED).exists()

    def test_nonsense_in_a_trial_is_refused(self) -> None:
        response = login().get(BACKTEST, {"queue_id": queue_id(), "weeks": 99})
        assert (response.status_code, response.json()["code"]) == (422, "tuning.weeks_invalid")

    def test_with_no_history_there_is_nothing_to_score_or_suggest(self) -> None:
        Queue.objects.create(name="Empty")
        response = login().get(BACKTEST, {"queue_id": Queue.objects.get(name="Empty").pk})
        body = response.json()
        assert (body["candidate"]["dailyPct"], body["candidate"]["biasPct"]) == (None, None)
        assert body["suggestedVolumeMultiplier"] is None
        assert body["candidate"]["days"] == 0


@pytest.mark.usefixtures("history")
class TestTheTuningReachesForecasts:
    def test_a_saved_volume_multiplier_scales_the_forecast_and_is_recorded(self) -> None:
        plain = run(login())
        save(login(), volumeMultiplier=2)
        tuned = run(login())

        assert ten_am(tuned["id"]).volume == pytest.approx(2 * ten_am(plain["id"]).volume)
        assert tuned["params"]["tuning"]["volumeMultiplier"] == 2
        assert plain["params"]["tuning"]["volumeMultiplier"] == 1  # what it was run with

    def test_a_forecast_already_run_is_not_changed_by_later_tuning(self) -> None:
        before = run(login())
        volume = ten_am(before["id"]).volume
        save(login(), volumeMultiplier=2, weeks=1)
        assert ten_am(before["id"]).volume == volume

    def test_looking_back_one_week_forecasts_from_the_latest_monday_alone(self) -> None:
        save(login(), weeks=1)
        assert ten_am(run(login())["id"]).volume == pytest.approx(30)  # 18 May's 30 calls

    def test_a_saved_handling_time_multiplier_scales_handling_time_and_so_staffing(self) -> None:
        plain = ten_am(run(login())["id"])
        save(login(), ahtMultiplier=2)
        tuned = ten_am(run(login())["id"])
        assert plain.aht_s == pytest.approx(180)
        assert tuned.aht_s == pytest.approx(360)
        assert tuned.required is not None
        assert plain.required is not None
        assert tuned.required > plain.required

    def test_accuracy_is_measured_with_the_saved_tuning(self) -> None:
        save(login(), weeks=1)
        body = login().get(ACCURACY, {"queue_id": queue_id()}).json()
        assert body["weeks"] == 1
        assert body["overallDailyAccuracyPct"] == pytest.approx(60.0)
        assert body["biasPct"] == pytest.approx(-40.0)


@pytest.mark.usefixtures("history")
class TestAudit:
    @staticmethod
    def changes() -> dict[str, tuple[str | None, str | None]]:
        event = AuditEvent.objects.filter(action=Action.FORECAST_TUNING_CHANGED).latest("chain_seq")
        return {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }

    def test_the_first_save_records_what_changed_from_the_defaults(self) -> None:
        save(login(), weeks=2, volumeMultiplier=1.1)
        assert self.changes() == {
            "weeks": ("4", "2"),
            "volume_multiplier": ("1.0", "1.1"),
            "saved": ("False", "True"),
        }

    def test_a_later_save_records_only_what_changed(self) -> None:
        save(login(), weeks=2)
        save(login(), weeks=2, decay=0.5)
        assert self.changes() == {"decay": ("0.7", "0.5")}

    def test_saving_the_same_again_records_nothing_more(self) -> None:
        save(login(), weeks=2)
        save(login(), weeks=2)
        assert AuditEvent.objects.filter(action=Action.FORECAST_TUNING_CHANGED).count() == 1

    def test_says_who(self) -> None:
        save(login(Role.ADMIN), weeks=3)
        event = AuditEvent.objects.get(action=Action.FORECAST_TUNING_CHANGED)
        assert event.actor_role == Role.ADMIN


@pytest.mark.usefixtures("history")
class TestWhoMay:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_these_roles_read_the_tuning_and_the_backtest(self, role: Role) -> None:
        assert login(role).get(TUNING, {"queue_id": queue_id()}).status_code == 200
        assert login(role).get(BACKTEST, {"queue_id": queue_id()}).status_code == 200

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role) -> None:
        assert login(role).get(TUNING, {"queue_id": queue_id()}).status_code == 403
        assert login(role).get(BACKTEST, {"queue_id": queue_id()}).status_code == 403

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planners_and_admins_save_it(self, role: Role) -> None:
        assert save(login(role), weeks=3).status_code == 200

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_saves_it(self, role: Role) -> None:
        assert save(login(role), weeks=3).status_code == 403
        assert ForecastTuning.objects.count() == 0
