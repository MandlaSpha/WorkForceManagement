"""The weekly plan: scheduled people against required agents. The exit test of Phase 2 is that the
variance changes when a shift is assigned. Numbers are worked out by hand.

Monday 25 May, QueueA. Published requirement (agents to roster, shrinkage included):
    09:00 3, 09:30 3, 10:00 2, 10:30 2, every other half-hour 0.
Roster: E001 on D1 09:00-17:30 (17 half-hours), E002 on P1 10:00-14:00 (8 half-hours).

    scheduled   09:00 1, 09:30 1, 10:00 2, 10:30 2, then 2 until 14:00, then 1 until 17:30
    variance    09:00 -2, 09:30 -2, 10:00 0, 10:30 0, 11:00-13:30 +2, 14:00-17:00 +1
    under-staffed half-hours 2; gap 2 + 2 = 4 (over-staffing later does not offset it)
    required total 3 + 3 + 2 + 2 = 10; scheduled total 17 + 8 = 25; worst: 09:00, -2
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from wfm.accounts.models import Role
from wfm.forecasting.models import ForecastStatus, ForecastVersion

from .helpers import (
    MON,
    PLAN,
    SUN,
    SUN_24,
    TUE,
    assign,
    login,
    params,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)

pytestmark = pytest.mark.django_db

REQUIRED: dict[tuple[date, int], int | None] = {
    (MON, 18): 3,
    (MON, 19): 3,
    (MON, 20): 2,
    (MON, 21): 2,
}


def plan(day: Any = MON, role: Role = Role.PLANNER, q: str = "QueueA") -> dict[str, Any]:
    response = login(role).get(PLAN, params(queue(q), day))
    assert response.status_code == 200, response.content
    return response.json()  # type: ignore[no-any-return]


def cell(body: dict[str, Any], day: str, slot: int) -> dict[str, Any]:
    return body["cells"][day][slot]  # type: ignore[no-any-return]


@pytest.fixture
def week() -> dict[str, Any]:
    shifts = standard_shifts()
    publish_forecast(queue(), REQUIRED)
    e1, e2 = person("E001"), person("E002")
    assign(login(), queue(), e1, MON, shifts["D1"])
    assign(login(), queue(), e2, MON, shifts["P1"])
    return {"shifts": shifts, "e1": e1, "e2": e2}


class TestVarianceByHand:
    def test_scheduled_required_and_variance_of_each_half_hour(self, week: dict[str, Any]) -> None:
        body = plan()
        monday = "2026-05-25"
        slots = (
            18,
            19,
            20,
            21,
            22,
            27,
            28,
            34,
            35,
        )  # 09:00 09:30 10:00 10:30 11:00 13:30 14:00 17:00 17:30
        assert [
            (c["scheduled"], c["required"], c["variance"], c["state"])
            for c in (cell(body, monday, s) for s in slots)
        ] == [
            (1, 3, -2, "under"),  # 09:00: only D1
            (1, 3, -2, "under"),  # 09:30
            (2, 2, 0, "met"),  # 10:00: D1 and P1
            (2, 2, 0, "met"),  # 10:30
            (2, 0, 2, "over"),  # 11:00: nobody is required, two are on
            (2, 0, 2, "over"),  # 13:30: P1's last half-hour
            (1, 0, 1, "over"),  # 14:00: P1 has gone, D1 remains
            (1, 0, 1, "over"),  # 17:00: D1's last half-hour
            (0, 0, 0, "met"),  # 17:30: nobody on, nobody required
        ]

    def test_the_week_in_numbers(self, week: dict[str, Any]) -> None:
        summary = plan()["summary"]
        assert summary["underIntervals"] == 2
        assert summary["gap"] == 4  # the later over-staffing does not offset it
        assert summary["requiredTotal"] == 10
        assert summary["scheduledTotal"] == 25
        assert summary["worst"] == {"day": "2026-05-25", "slot": 18, "variance": -2}

    def test_the_half_hours_after_the_shift_ends_are_not_covered(
        self, week: dict[str, Any]
    ) -> None:
        body = plan()["cells"]["2026-05-25"]
        assert body[34]["scheduled"] == 1  # 17:00-17:30, the last half-hour of D1
        assert body[35]["scheduled"] == 0  # 17:30 onwards: nobody


class TestTheVarianceMovesWhenAShiftIsAssigned:
    """Phase 2 exit: variance updates on assign."""

    def test_adding_a_shift_closes_the_gap_and_removing_it_reopens_it(
        self, week: dict[str, Any]
    ) -> None:
        before = plan()["summary"]
        assert (before["underIntervals"], before["gap"]) == (2, 4)

        e3 = person("E003")
        assign(login(), queue(), e3, MON, week["shifts"]["D1"])  # 09:00-17:30 as well
        after = plan()
        assert cell(after, "2026-05-25", 18)["variance"] == -1  # 09:00: 2 against 3
        assert (after["summary"]["underIntervals"], after["summary"]["gap"]) == (2, 2)
        assert after["summary"]["scheduledTotal"] == 25 + 17

        assign(login(), queue(), e3, MON, None)  # take it away again
        again = plan()["summary"]
        assert (again["underIntervals"], again["gap"]) == (2, 4)

    def test_a_third_person_at_the_busy_time_turns_under_into_met(
        self, week: dict[str, Any]
    ) -> None:
        extra = person("E003")
        assign(login(), queue(), extra, MON, week["shifts"]["D1"])
        extra2 = person("E004")
        assign(login(), queue(), extra2, MON, week["shifts"]["D1"])
        body = plan()
        assert cell(body, "2026-05-25", 18)["state"] == "met"  # three on, three required
        assert body["summary"]["underIntervals"] == 0
        assert body["summary"]["worst"] is None


class TestHonestyAboutWhatIsNotKnown:
    def test_days_the_forecast_does_not_reach_have_no_requirement_not_zero(
        self, week: dict[str, Any]
    ) -> None:
        tuesday = cell(plan(), "2026-05-26", 20)
        assert (tuesday["required"], tuesday["variance"], tuesday["state"]) == (None, None, None)

    def test_with_no_published_forecast_nothing_is_claimed(self) -> None:
        shifts = standard_shifts()
        assign(login(), queue(), person(), MON, shifts["D1"])
        body = plan()
        assert body["forecast"] is None
        assert body["summary"]["intervalsKnown"] == 0
        assert body["summary"]["underIntervals"] == 0
        assert cell(body, "2026-05-25", 20)["required"] is None

    def test_a_draft_forecast_is_not_a_requirement(self, week: dict[str, Any]) -> None:
        ForecastVersion.objects.update(status=ForecastStatus.DRAFT)
        assert plan()["forecast"] is None

    def test_says_which_forecast_the_requirement_comes_from(self, week: dict[str, Any]) -> None:
        forecast = plan()["forecast"]
        assert forecast["label"] == "published"
        assert forecast["assumptionsConfirmed"] is True

    def test_the_requirement_with_shrinkage_is_what_is_compared(self) -> None:
        # required_raw is the agents on the phone; required is what must be rostered.
        from wfm.forecasting.models import ForecastInterval

        shifts = standard_shifts()
        publish_forecast(queue(), {(MON, 20): 6})
        ForecastInterval.objects.filter(required=6).update(required_raw=4)
        assign(login(), queue(), person(), MON, shifts["D1"])
        assert cell(plan(), "2026-05-25", 20)["required"] == 6


class TestCoverageEdges:
    def test_a_night_shift_from_sunday_covers_monday_morning(self) -> None:
        shifts = standard_shifts()
        publish_forecast(queue(), {(MON, 2): 1, (SUN_24, 46): 1})
        assign(login(), queue(), person(), SUN_24, shifts["N1"])  # 22:00 Sunday to 06:00 Monday
        monday = plan(MON)["cells"]["2026-05-25"]
        assert [monday[s]["scheduled"] for s in (0, 5, 11, 12)] == [1, 1, 1, 0]
        assert cell(plan(MON), "2026-05-25", 2)["state"] == "met"
        # In the week it started, only the Sunday evening belongs to that week.
        previous = plan(date(2026, 5, 18))["cells"]["2026-05-24"]
        assert [previous[s]["scheduled"] for s in (43, 44, 47)] == [0, 1, 1]

    def test_another_queues_roster_does_not_count(self) -> None:
        shifts = standard_shifts()
        publish_forecast(queue("QueueA"), {(MON, 20): 1})
        other = person("E009", queues=("QueueB",))
        assign(login(), queue("QueueB"), other, MON, shifts["D1"])
        assert cell(plan(), "2026-05-25", 20)["scheduled"] == 0

    def test_the_last_day_of_the_week_is_included(self) -> None:
        shifts = standard_shifts()
        publish_forecast(queue(), {(SUN, 20): 1})
        assign(login(), queue(), person(), SUN, shifts["D1"])
        assert cell(plan(), "2026-05-31", 20)["state"] == "met"

    def test_a_week_starts_on_a_monday(self) -> None:
        queue()
        response = login().get(PLAN, params(queue(), TUE))
        assert response.status_code == 422
        assert response.json()["code"] == "roster.not_a_monday"


class TestWhoMayRead:
    def test_a_lead_reads_the_plan(self, week: dict[str, Any]) -> None:
        assert plan(role=Role.LEAD)["summary"]["underIntervals"] == 2

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_nobody_else_does(self, role: Role, week: dict[str, Any]) -> None:
        response = login(role).get(PLAN, params(queue(), MON))
        assert response.status_code == 403

    def test_an_unknown_queue_is_a_404(self) -> None:
        response = login().get(PLAN, {"queue_id": "99999", "week_start": str(MON)})
        assert response.status_code == 404
