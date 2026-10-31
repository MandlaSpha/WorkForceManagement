"""The smoothed forecast (method "smoothed", tech spec 4.3): the day's level and a pooled shape,
against a real PostgreSQL.

The history is hand-worked. Three Mondays (4, 11, 18 May 2026) of 100 calls, a Tuesday (19 May) of
200 and a Wednesday (20 May) of 300, spread evenly over five half-hours. The target is Monday
25 May.

- The baseline for that Monday is 100 (the Mondays only).
- The weekday level weighs the five days newest first by 1, 0.9, 0.81, 0.729 and 0.6561:
  (300 + 180 + 81 + 72.9 + 65.61) / 4.0951 = 170.82.
- Half of each: 0.5 * 100 + 0.5 * 170.82 = 135.41 calls.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.forecasting.models import ForecastInterval, ForecastVersion
from wfm.telephony.models import Queue

from .helpers import add_days, login

pytestmark = pytest.mark.django_db

VERSIONS = "/api/v1/forecasting/versions"
ACCURACY = "/api/v1/forecasting/accuracy"
TARGET = date(2026, 5, 25)
HISTORY = {
    date(2026, 5, 4): 100,
    date(2026, 5, 11): 100,
    date(2026, 5, 18): 100,
    date(2026, 5, 19): 200,
    date(2026, 5, 20): 300,
}
EXPECTED_TOTAL = 135.41


@pytest.fixture
def queue() -> Queue:
    return add_days("QueueSmooth", HISTORY)


def run(client: Client, queue: Queue, method: str = "smoothed") -> Any:
    body = {"queueId": queue.pk, "dateFrom": str(TARGET), "dateTo": str(TARGET), "method": method}
    return client.post(VERSIONS, body, content_type="application/json")


def accuracy(client: Client, queue_id: int | None, method: str = "smoothed") -> Any:
    return client.get(ACCURACY, {"queue_id": str(queue_id), "method": method})


def day_total(version_id: str) -> float:
    rows = ForecastInterval.objects.filter(version__pk=version_id, interval_start__date=TARGET)
    return float(sum(r.volume for r in rows))


class TestRunningIt:
    def test_the_day_total_is_half_the_baseline_and_half_the_weekday_level(
        self, queue: Queue
    ) -> None:
        response = run(login(), queue)

        assert response.status_code == 201, response.content
        version = response.json()
        assert version["method"] == "smoothed-v1"
        assert day_total(version["id"]) == pytest.approx(EXPECTED_TOTAL, abs=0.05)

    def test_the_baseline_for_the_same_day_is_unchanged(self, queue: Queue) -> None:
        # The new method must not move the old one.
        version = run(login(), queue, method="baseline").json()
        assert version["method"] == "baseline-v1"
        assert day_total(version["id"]) == pytest.approx(100.0, abs=0.05)

    def test_the_version_says_how_it_was_tuned_and_the_trail_records_the_model(
        self, queue: Queue
    ) -> None:
        version = run(login(), queue).json()

        assert version["params"]["tuning"]["weeks"] == 4
        assert "fallback" not in version["params"]
        event = AuditEvent.objects.filter(action=Action.FORECAST_RUN).earliest("chain_seq")
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes["method"] == "smoothed-v1"

    def test_a_day_with_nothing_to_go_on_is_refused_and_nothing_is_invented(
        self, queue: Queue
    ) -> None:
        # Sunday 31 May: there is no earlier Sunday with data.
        body = {
            "queueId": queue.pk,
            "dateFrom": "2026-05-31",
            "dateTo": "2026-05-31",
            "method": "smoothed",
        }
        response = login().post(VERSIONS, body, content_type="application/json")

        assert response.status_code == 422
        assert response.json()["code"] == "forecast.no_history"
        assert not ForecastInterval.objects.filter(version__queue=queue).exists()

    def test_an_unknown_method_is_refused(self, queue: Queue) -> None:
        response = run(login(), queue, method="magic")
        assert response.status_code == 422
        assert ForecastVersion.objects.count() == 0

    def test_an_unknown_queue_is_a_404(self) -> None:
        body = {
            "queueId": 999999,
            "dateFrom": str(TARGET),
            "dateTo": str(TARGET),
            "method": "smoothed",
        }
        response = login().post(VERSIONS, body, content_type="application/json")
        assert response.status_code == 404


class TestWhoMayRunIt:
    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN])
    def test_planners_and_admins_may(self, role: Role, queue: Queue) -> None:
        assert run(login(role), queue).status_code == 201

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_may_and_nothing_is_stored(self, role: Role, queue: Queue) -> None:
        assert run(login(role), queue).status_code == 403
        assert ForecastVersion.objects.count() == 0


class TestScoringIt:
    """GET /accuracy?method=smoothed: how the model would have done on past days."""

    @pytest.mark.parametrize("role", [Role.PLANNER, Role.ADMIN, Role.LEAD])
    def test_planners_admins_and_leads_may_read_it(self, role: Role, queue: Queue) -> None:
        response = accuracy(login(role), queue.pk)

        assert response.status_code == 200, response.content
        body = response.json()
        assert body["queue"] == "QueueSmooth"
        assert body["days"]  # Mondays 11 and 18 can be forecast from the Mondays before them
        assert body["overallDailyAccuracyPct"] is not None

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role, queue: Queue) -> None:
        response = accuracy(login(role), queue.pk)
        assert response.status_code == 403

    def test_an_unknown_queue_is_a_404(self) -> None:
        response = accuracy(login(), 999999)
        assert response.status_code == 404

    def test_it_scores_the_same_days_the_baseline_could_forecast(self, queue: Queue) -> None:
        smoothed = accuracy(login(), queue.pk).json()
        baseline = accuracy(login(), queue.pk, "baseline").json()
        assert [d["date"] for d in smoothed["days"]] == [d["date"] for d in baseline["days"]]

    def test_an_unknown_method_is_refused(self, queue: Queue) -> None:
        response = accuracy(login(), queue.pk, "magic")
        assert response.status_code == 422
