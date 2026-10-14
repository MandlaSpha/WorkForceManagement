"""The planning dashboard's overview: every queue's week at a glance, worked out by hand.

Monday 25 May. QueueA is the roster of test_plan: two people short at 09:00 and 09:30, gap 4,
required 10, scheduled 25 (a draft roster). QueueB has a forecast needing 4 at 10:00 and 10:30 and
nobody rostered: two half-hours short, gap 8, required 8, scheduled 0. QueueC has no forecast.

    totals     3 queues, 2 with a forecast, 96 known half-hours, 4 under-staffed, gap 12
    day gap    Monday 4 + 8 = 12 (variance below zero only; over-staffing offsets nothing)
    order      worst-staffed first: QueueB (8), QueueA (4), then QueueC (no requirement)
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from wfm.accounts.models import Role
from wfm.scheduling.models import RosterStatus, RosterWeek

from .helpers import MON, ROSTER, assign, login, person, publish_forecast, queue, standard_shifts

pytestmark = pytest.mark.django_db

OVERVIEW = "/api/v1/scheduling/overview"


@pytest.fixture
def world() -> None:
    shifts = standard_shifts()
    publish_forecast(queue("QueueA"), {(MON, 18): 3, (MON, 19): 3, (MON, 20): 2, (MON, 21): 2})
    publish_forecast(queue("QueueB"), {(MON, 20): 4, (MON, 21): 4})
    queue("QueueC")
    e1, e2 = person("E001"), person("E002")
    assign(login(), queue("QueueA"), e1, MON, shifts["D1"])
    assign(login(), queue("QueueA"), e2, MON, shifts["P1"])


def overview(day: date = MON, role: Role = Role.PLANNER) -> dict[str, Any]:
    response = login(role).get(OVERVIEW, {"week_start": str(day)})
    assert response.status_code == 200, response.content
    return response.json()  # type: ignore[no-any-return]


@pytest.mark.usefixtures("world")
class TestTheWeekByHand:
    def test_totals(self) -> None:
        totals = overview()["totals"]
        assert totals == {
            "queues": 3,
            "queuesWithForecast": 2,
            "intervalsKnown": 96,
            "underIntervals": 4,
            "gap": 12,
            "headcount": 2,
            "rostersPublished": 0,
        }

    def test_queues_come_worst_staffed_first_and_those_without_a_requirement_last(self) -> None:
        queues = overview()["queues"]
        assert [q["queue"] for q in queues] == ["QueueB", "QueueA", "QueueC"]

    def test_each_queue_carries_its_own_figures(self) -> None:
        by_name = {q["queue"]: q for q in overview()["queues"]}
        a, b, c = by_name["QueueA"], by_name["QueueB"], by_name["QueueC"]
        assert (a["gap"], a["underIntervals"], a["requiredTotal"], a["scheduledTotal"]) == (
            4,
            2,
            10,
            25,
        )
        assert (a["worstVariance"], a["worstDay"], a["worstSlot"]) == (-2, str(MON), 18)
        assert (b["gap"], b["underIntervals"], b["requiredTotal"], b["scheduledTotal"]) == (
            8,
            2,
            8,
            0,
        )
        assert b["worstVariance"] == -4
        assert (a["rosterStatus"], b["rosterStatus"]) == ("draft", "draft")
        assert (a["forecastLabel"], c["forecastLabel"]) == ("published", None)

    def test_a_queue_with_no_forecast_has_no_figures_not_zeros(self) -> None:
        c = {q["queue"]: q for q in overview()["queues"]}["QueueC"]
        assert (
            c["intervalsKnown"],
            c["worstVariance"],
            c["worstDay"],
            c["assumptionsConfirmed"],
        ) == (
            0,
            None,
            None,
            None,
        )

    def test_the_gap_by_day_adds_the_queues_up(self) -> None:
        days = {d["day"]: d for d in overview()["days"]}
        assert len(days) == 7
        assert (days[str(MON)]["gap"], days[str(MON)]["underIntervals"]) == (12, 4)
        tuesday = days[str(MON + timedelta(days=1))]
        assert (tuesday["gap"], tuesday["underIntervals"]) == (0, 0)

    def test_what_needs_attention_most_serious_first(self) -> None:
        items = overview()["attention"]
        assert [(i["severity"], i["kind"], i["queue"], i["count"]) for i in items] == [
            ("warning", "understaffed", "QueueA", 2),
            ("warning", "understaffed", "QueueB", 2),
            ("warning", "no_forecast", "QueueC", 0),
            ("info", "draft_roster", "QueueA", 0),
        ]
        assert items[0]["text"] == "QueueA: 2 under-staffed intervals"


@pytest.mark.usefixtures("world")
class TestWhenThingsChange:
    def test_publishing_the_roster_clears_its_draft_note_and_counts_it(self) -> None:
        response = login().post(
            f"{ROSTER}/publish",
            {"queueId": queue("QueueA").pk, "weekStart": str(MON)},
            content_type="application/json",
        )
        assert response.status_code == 200, response.content
        body = overview()
        assert body["totals"]["rostersPublished"] == 1
        assert "draft_roster" not in [i["kind"] for i in body["attention"]]
        assert RosterWeek.objects.get(queue=queue("QueueA")).status == RosterStatus.PUBLISHED

    def test_a_week_the_forecast_does_not_reach_says_so_instead_of_claiming_coverage(self) -> None:
        body = overview(MON + timedelta(days=7))
        assert body["totals"]["queuesWithForecast"] == 0
        assert body["totals"]["gap"] == 0
        kinds = [(i["kind"], i["queue"]) for i in body["attention"]]
        assert kinds == [
            ("no_forecast", "QueueA"),
            ("no_forecast", "QueueB"),
            ("no_forecast", "QueueC"),
        ]

    def test_headcount_counts_only_people_employed_in_the_week(self) -> None:
        person("E003", end_date=MON - timedelta(days=1))  # left the Sunday before
        person("E004", start_date=MON + timedelta(days=7))  # starts next week
        person("E005", start_date=MON + timedelta(days=3))  # starts mid-week
        assert overview()["totals"]["headcount"] == 3  # E001, E002, E005


class TestRefusals:
    def test_a_week_must_start_on_a_monday(self) -> None:
        response = login().get(OVERVIEW, {"week_start": "2026-05-26"})
        assert (response.status_code, response.json()["code"]) == (422, "roster.not_a_monday")

    def test_with_no_queues_it_is_empty_not_an_error(self) -> None:
        body = overview()
        assert (body["queues"], body["attention"]) == ([], [])
        assert body["totals"]["queues"] == 0


@pytest.mark.usefixtures("world")
class TestWhoMay:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_these_roles_may(self, role: Role) -> None:
        assert overview(role=role)["totals"]["gap"] == 12  # and the figures are real

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_other_roles_are_refused(self, role: Role) -> None:
        response = login(role).get(OVERVIEW, {"week_start": str(MON)})
        assert response.status_code == 403
