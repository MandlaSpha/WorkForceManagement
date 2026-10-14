"""What-if scenarios on a real PostgreSQL, with the staffing worked out by hand.

History: two Mondays with 10 calls at 10:00, handled in 180 s each, so the forecast for Monday
25 May is 10 calls at 10:00 and the base requirement is (80% in 20 s, 85% occupancy, 30% shrinkage):

  traffic 10 / 1800 s * 180 s = 1 Erlang -> 3 agents on the phone -> ceil(3 / 0.7) = 5 to roster

and the scenarios:
  calls +100%          20 calls, 2 Erlangs  -> 4 on the phone -> ceil(4 / 0.7) = 6
  handling time +100%  360 s each, 2 Erlangs -> 4 -> 6
  shrinkage 0%         3 on the phone, nothing added -> 3
  target 95% in 20 s   3 agents reach only 92.7%, 4 do -> 4 -> 6
  calls -100%          no calls -> 0
  agent-hours = agents to roster x half an hour: base 5 x 0.5 = 2.5; scenario 6 x 0.5 = 3.0
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import AuditEvent
from wfm.forecasting.models import ForecastInterval, ForecastVersion
from wfm.telephony.models import Queue

from .helpers import MON_4, MON_11, MON_25, import_mondays, login

pytestmark = pytest.mark.django_db

SCENARIOS = "/api/v1/forecasting/scenarios"
VERSIONS = "/api/v1/forecasting/versions"


@pytest.fixture
def version() -> dict[str, Any]:
    import_mondays({MON_4: 10, MON_11: 10})
    queue = Queue.objects.get(name="QueueA")
    payload = {"queueId": queue.pk, "dateFrom": str(MON_25), "dateTo": str(MON_25)}
    return login().post(VERSIONS, payload, content_type="application/json").json()  # type: ignore[no-any-return]


def ask(client: Client, version_id: str, **changes: Any) -> Any:
    return client.post(
        SCENARIOS, {"versionId": version_id, **changes}, content_type="application/json"
    )


def monday(response: Any) -> dict[str, Any]:
    days = response.json()["days"]
    assert [d["day"] for d in days] == [str(MON_25)]
    return days[0]  # type: ignore[no-any-return]


class TestTheScenariosByHand:
    def test_no_change_gives_back_the_base_exactly(self, version: dict[str, Any]) -> None:
        day = monday(ask(login(), version["id"]))
        assert (day["peakBase"], day["peakScenario"]) == (5, 5)
        assert (day["hoursBase"], day["hoursScenario"]) == (2.5, 2.5)
        assert (day["callsBase"], day["callsScenario"]) == (pytest.approx(10), pytest.approx(10))
        assert day["complete"] is True

    def test_more_calls_need_more_agents(self, version: dict[str, Any]) -> None:
        day = monday(ask(login(), version["id"], volumeChangePct=100))
        assert (day["peakBase"], day["peakScenario"]) == (5, 6)
        assert (day["hoursBase"], day["hoursScenario"]) == (2.5, 3.0)
        assert day["callsScenario"] == pytest.approx(20)

    def test_longer_calls_need_more_agents(self, version: dict[str, Any]) -> None:
        day = monday(ask(login(), version["id"], ahtChangePct=100))
        assert (day["peakBase"], day["peakScenario"]) == (5, 6)
        assert day["callsScenario"] == pytest.approx(10)  # the volume itself did not change

    def test_no_shrinkage_adds_nobody_to_the_agents_on_the_phone(
        self, version: dict[str, Any]
    ) -> None:
        response = ask(login(), version["id"], shrinkagePct=0)
        assert monday(response)["peakScenario"] == 3
        assert response.json()["base"]["shrinkagePct"] == 30
        assert response.json()["scenario"]["shrinkagePct"] == 0

    def test_a_tougher_service_target_needs_more_agents(self, version: dict[str, Any]) -> None:
        response = ask(login(), version["id"], slTargetPct=95)
        assert monday(response)["peakScenario"] == 6
        assert response.json()["scenario"]["slTargetPct"] == 95

    def test_no_calls_need_nobody(self, version: dict[str, Any]) -> None:
        day = monday(ask(login(), version["id"], volumeChangePct=-100))
        assert (day["peakScenario"], day["hoursScenario"], day["callsScenario"]) == (0, 0, 0)

    def test_changes_combine(self, version: dict[str, Any]) -> None:
        # Twice the calls but no shrinkage: 4 on the phone, nothing added.
        day = monday(ask(login(), version["id"], volumeChangePct=100, shrinkagePct=0))
        assert day["peakScenario"] == 4

    def test_the_forecast_assumptions_are_the_ones_it_was_run_with(
        self, version: dict[str, Any]
    ) -> None:
        # Someone changes the queue's shrinkage afterwards; this forecast was run at 30%.
        Queue.objects.filter(name="QueueA").update(shrinkage_pct=50)
        response = ask(login(), version["id"])
        assert response.json()["base"]["shrinkagePct"] == 30
        assert monday(response)["peakScenario"] == 5


class TestNothingIsChanged:
    def test_a_scenario_leaves_the_forecast_and_the_trail_alone(
        self, version: dict[str, Any]
    ) -> None:
        before = list(
            ForecastInterval.objects.filter(version__pk=version["id"])
            .order_by("interval_start")
            .values_list("volume", "required")
        )
        events = AuditEvent.objects.count()
        versions = ForecastVersion.objects.count()

        ask(login(), version["id"], volumeChangePct=300, shrinkagePct=10)

        after = list(
            ForecastInterval.objects.filter(version__pk=version["id"])
            .order_by("interval_start")
            .values_list("volume", "required")
        )
        assert after == before
        assert AuditEvent.objects.count() == events
        assert ForecastVersion.objects.count() == versions


class TestHonestyAboutWhatCannotBeStaffed:
    def test_a_half_hour_with_calls_but_no_handling_time_makes_the_figures_minimums(self) -> None:
        owner, _ = User.objects.get_or_create(username="u-maker", defaults={"role": Role.PLANNER})
        queue = Queue.objects.create(name="QueueX")
        made = ForecastVersion.objects.create(
            queue=queue,
            method="baseline-v1",
            date_from=MON_25,
            date_to=MON_25,
            created_by=owner,
            params={
                "slTargetPct": 80,
                "slThresholdS": 20,
                "occupancyCeilingPct": 85,
                "shrinkagePct": 30,
            },
        )
        zone = ZoneInfo("Africa/Johannesburg")
        ForecastInterval.objects.bulk_create(
            [
                ForecastInterval(
                    version=made,
                    interval_start=datetime.combine(MON_25, time(10, 0), tzinfo=zone),
                    volume=10,
                    aht_s=180,
                    required=5,
                    required_raw=3,
                    days_used=1,
                ),
                ForecastInterval(
                    version=made,
                    interval_start=datetime.combine(MON_25, time(10, 30), tzinfo=zone),
                    volume=4,
                    aht_s=None,
                    required=None,
                    required_raw=None,
                    days_used=1,
                ),
            ]
        )
        day = monday(ask(login(), str(made.id)))
        assert day["complete"] is False
        assert (day["peakBase"], day["peakScenario"]) == (5, 5)  # at least this many


class TestRefusals:
    @pytest.mark.parametrize(
        ("changes", "code"),
        [
            ({"volumeChangePct": 501}, "scenario.volume_invalid"),
            ({"volumeChangePct": -101}, "scenario.volume_invalid"),
            ({"ahtChangePct": -91}, "scenario.aht_invalid"),
            ({"ahtChangePct": 501}, "scenario.aht_invalid"),
            ({"slTargetPct": 0}, "scenario.sl_invalid"),
            ({"slTargetPct": 101}, "scenario.sl_invalid"),
            ({"shrinkagePct": 100}, "scenario.shrinkage_invalid"),
            ({"shrinkagePct": -1}, "scenario.shrinkage_invalid"),
        ],
    )
    def test_nonsense_is_refused_with_a_reason(
        self, version: dict[str, Any], changes: dict[str, float], code: str
    ) -> None:
        response = ask(login(), version["id"], **changes)
        assert response.status_code == 422
        assert response.json()["code"] == code

    def test_the_limits_themselves_are_allowed(self, version: dict[str, Any]) -> None:
        for changes in (
            {"volumeChangePct": -100},
            {"volumeChangePct": 500},
            {"ahtChangePct": -90},
            {"ahtChangePct": 500},
            {"slTargetPct": 100},
            {"shrinkagePct": 0},
        ):
            assert ask(login(), version["id"], **changes).status_code == 200, changes

    def test_an_unknown_forecast_is_not_found(self) -> None:
        response = ask(login(), "00000000-0000-0000-0000-000000000000")
        assert response.status_code == 404


class TestWhoMayAsk:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_these_roles_may(self, role: Role, version: dict[str, Any]) -> None:
        assert ask(login(role), version["id"]).status_code == 200

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role, version: dict[str, Any]) -> None:
        assert ask(login(role), version["id"]).status_code == 403
