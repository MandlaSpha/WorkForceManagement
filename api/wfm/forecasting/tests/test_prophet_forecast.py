"""Prophet forecasts and the rule that it must beat the baseline to be used (ADR 0002), against a
real PostgreSQL and the real Prophet.

The history is synthetic and its truth is known by hand: 12 weeks from Monday 2 March 2026 where
day n (n = 0 on 2 March) brings (200 + 4n) calls on a weekday, 40% of that on a Saturday and 20%
on a Sunday. Volume grows steadily, which a weighted average of the last few weeks always lags
behind and a trend model should not. Monday 25 May is day 84: 200 + 4 * 84 = 536 calls.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.forecasting.models import ForecastInterval
from wfm.telephony.models import Queue

from .helpers import add_days, login

pytestmark = pytest.mark.django_db

VERSIONS = "/api/v1/forecasting/versions"
ACCURACY = "/api/v1/forecasting/accuracy"
START = date(2026, 3, 2)  # a Monday
TARGET = date(2026, 5, 25)  # day 84
WEEKEND = {5: 0.4, 6: 0.2}


def growing(weeks: int = 12) -> dict[date, int]:
    days = (START + timedelta(days=n) for n in range(weeks * 7))
    return {d: round((200 + 4 * (d - START).days) * WEEKEND.get(d.weekday(), 1.0)) for d in days}


def repeating(weeks: int = 8) -> dict[date, int]:
    """The same week over and over: the baseline cannot be beaten on it."""
    week = [300, 320, 310, 330, 340, 120, 60]
    return {START + timedelta(days=n): week[n % 7] for n in range(weeks * 7)}


def run(client: Client, queue: Queue, method: str = "prophet", day: date = TARGET) -> Any:
    body = {"queueId": queue.pk, "dateFrom": str(day), "dateTo": str(day), "method": method}
    return client.post(VERSIONS, body, content_type="application/json")


def day_total(version_id: str, day: date) -> float:
    rows = ForecastInterval.objects.filter(version__pk=version_id, interval_start__date=day)
    return float(sum(r.volume for r in rows))


def volumes(version_id: str) -> list[tuple[float, int | None]]:
    rows = ForecastInterval.objects.filter(version__pk=version_id).order_by("interval_start")
    return list(rows.values_list("volume", "required"))


class TestWhenProphetWins:
    def test_growing_demand_is_forecast_by_prophet_and_says_so(self) -> None:
        queue = add_days("QueueGrow", growing())
        response = run(login(), queue)

        assert response.status_code == 201, response.content
        version = response.json()
        assert version["method"] == "prophet-v1"
        assert version["fallback"] is None
        evidence = version["params"]["backtest"]
        assert evidence["daysScored"] >= 7
        assert evidence["prophetDailyPct"] > evidence["baselineDailyPct"]
        # The settings used are stored, so the forecast can be explained later.
        model = version["params"]["model"]
        assert model["holidays"] == "ZA"
        assert model["seasonalityMode"] == "multiplicative"
        assert model["yearlySeasonality"] is False  # under two years of history
        assert model["monthlySeasonality"] is False  # under three months

    def test_the_day_total_follows_the_trend_the_baseline_lags_behind(self) -> None:
        queue = add_days("QueueGrow", growing())
        prophet = run(login(), queue).json()
        baseline = run(login(), queue, method="baseline").json()

        truth = 200 + 4 * 84  # 536
        prophet_total = day_total(prophet["id"], TARGET)
        baseline_total = day_total(baseline["id"], TARGET)
        assert abs(prophet_total - truth) / truth < 0.02
        assert abs(prophet_total - truth) < abs(baseline_total - truth)

    def test_each_half_hour_has_a_range_around_the_forecast(self) -> None:
        queue = add_days("QueueGrow", growing())
        version = run(login(), queue).json()
        busy = ForecastInterval.objects.filter(version_id=version["id"], volume__gt=1)
        assert busy.exists()
        for row in busy:
            assert row.volume_lower is not None
            assert row.volume_upper is not None
            assert 0 <= row.volume_lower <= row.volume <= row.volume_upper

    def test_the_range_reaches_the_screen_through_the_api(self) -> None:
        queue = add_days("QueueGrow", growing())
        version = run(login(), queue).json()
        rows = login().get(f"{VERSIONS}/{version['id']}/intervals").json()
        assert all(r["volumeLower"] is not None for r in rows)

    def test_the_audit_trail_records_the_model_used(self) -> None:
        queue = add_days("QueueGrow", growing())
        run(login(), queue)
        event = AuditEvent.objects.get(action=Action.FORECAST_RUN)
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes["method"] == "prophet-v1"
        assert "fallback" not in changes


class TestWhenProphetIsNotUsed:
    def test_the_baseline_is_used_when_it_is_already_perfect(self) -> None:
        queue = add_days("QueueSteady", repeating())
        version = run(login(), queue).json()

        assert version["method"] == "baseline-v1"
        assert version["fallback"]["reason"] == "not_better"
        assert version["fallback"]["requested"] == "prophet"
        assert version["fallback"]["baselineDailyPct"] == pytest.approx(100.0)
        assert version["fallback"]["prophetDailyPct"] <= 100.0

    def test_a_fallback_forecast_is_exactly_the_baseline_forecast(self) -> None:
        queue = add_days("QueueSteady", repeating())
        asked = run(login(), queue).json()
        plain = run(login(), queue, method="baseline").json()

        assert volumes(asked["id"]) == volumes(plain["id"])
        ranges = ForecastInterval.objects.filter(version_id=asked["id"]).values_list(
            "volume_lower", flat=True
        )
        assert all(v is None for v in ranges)  # the baseline has no range, and says so

    def test_too_little_history_never_reaches_prophet(self) -> None:
        queue = add_days("QueueNew", {START + timedelta(days=n): 100 for n in range(10)})
        version = run(login(), queue, day=START + timedelta(days=14)).json()
        assert version["method"] == "baseline-v1"
        assert version["fallback"]["reason"] == "too_little_history"

    def test_too_few_past_days_to_check_it_means_the_baseline_not_a_guess(self) -> None:
        # 17 days: Prophet can be fitted, but only 3 days have 14 days before them to be scored.
        short = {d: v for d, v in growing().items() if d < START + timedelta(days=17)}
        queue = add_days("QueueFew", short)
        version = run(login(), queue, day=START + timedelta(days=17)).json()
        assert version["method"] == "baseline-v1"
        assert version["fallback"]["reason"] == "too_little_to_compare"
        assert version["fallback"]["daysScored"] < 7

    def test_the_audit_trail_records_why_it_fell_back(self) -> None:
        queue = add_days("QueueSteady", repeating())
        run(login(), queue)
        event = AuditEvent.objects.get(action=Action.FORECAST_RUN)
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes["method"] == "baseline-v1"
        assert changes["fallback"] == "not_better"


class TestAskingForTheBaseline:
    def test_is_the_default_and_leaves_no_prophet_traces(self) -> None:
        queue = add_days("QueueGrow", growing())
        body = {"queueId": queue.pk, "dateFrom": str(TARGET), "dateTo": str(TARGET)}
        version = login().post(VERSIONS, body, content_type="application/json").json()
        assert version["method"] == "baseline-v1"
        assert version["fallback"] is None
        assert "model" not in version["params"]

    def test_an_unknown_method_is_refused(self) -> None:
        queue = add_days("QueueGrow", growing())
        assert run(login(), queue, method="crystal-ball").status_code == 422


class TestAccuracyPerModel:
    def test_prophet_is_scored_only_on_days_it_could_be_refitted_for(self) -> None:
        queue = add_days("QueueGrow", growing())
        client = login()
        base = client.get(f"{ACCURACY}?queue_id={queue.pk}").json()
        prophet = client.get(f"{ACCURACY}?queue_id={queue.pk}&method=prophet").json()

        assert len(prophet["days"]) <= 6 * 7  # at most six weekly refits
        assert len(prophet["days"]) < len(base["days"])
        # Every scored day has at least 14 days of history before its week.
        assert min(d["date"] for d in prophet["days"]) >= str(START + timedelta(days=14))
        # On growing demand the model that can see the trend is the more accurate one.
        assert prophet["overallDailyAccuracyPct"] > base["overallDailyAccuracyPct"] - 5

    def test_an_unknown_method_is_refused(self) -> None:
        queue = add_days("QueueGrow", growing())
        assert login().get(f"{ACCURACY}?queue_id={queue.pk}&method=oracle").status_code == 422


class TestWhoMayAskForProphet:
    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role) -> None:
        queue = add_days("QueueGrow", growing())
        assert run(login(role), queue).status_code == 403

    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_may(self, role: Role) -> None:
        queue = add_days("QueueGrow", growing())
        assert run(login(role), queue).status_code == 201
