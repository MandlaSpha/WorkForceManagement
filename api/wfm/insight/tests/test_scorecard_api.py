"""The scorecard: figures worked out by hand, labelled by source, and shown only to roles that may
see their inputs."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.scheduling.models import RosterStatus, RosterWeek, ShiftAssignment
from wfm.scheduling.tests.helpers import person, queue, standard_shifts
from wfm.telephony.models import IntervalActual

pytestmark = pytest.mark.django_db

URL = "/api/v1/insight/scorecard"
ZONE = ZoneInfo(settings.TIME_ZONE)
MON, TUE = date(2031, 3, 3), date(2031, 3, 4)


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def calls(day: date, offered: int, in_sl: int, abandoned: int = 0, handle_s: int = 0) -> None:
    answered = offered - abandoned
    IntervalActual.objects.create(
        queue=queue(),
        interval_start=datetime(day.year, day.month, day.day, 10, 0, tzinfo=ZONE),
        offered=offered,
        answered=answered,
        abandoned=abandoned,
        answered_in_sl=in_sl,
        sum_wait_s=answered * 10,
        sum_handle_s=handle_s,
    )


def card(role: Role, first: date = MON, last: date = TUE) -> dict[str, Any]:
    response = client(role).get(URL, {"date_from": str(first), "date_to": str(last)})
    assert response.status_code == 200, response.content
    return dict(response.json())


def items(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["key"]: i for i in body["items"]}


class TestTheFigures:
    def test_measured_service_figures_are_worked_out_from_the_calls(self) -> None:
        # Failure caught: service level over answered calls instead of offered, or a wrong unit.
        calls(MON, offered=10, in_sl=8, abandoned=1, handle_s=1800)
        got = items(card(Role.PLANNER))
        assert got["service_level"]["value"] == pytest.approx(80.0)
        assert got["abandon_rate"]["value"] == pytest.approx(10.0)
        assert got["asa"]["value"] == pytest.approx(10.0)
        assert got["aht"]["value"] == pytest.approx(200.0)
        assert got["offered"]["value"] == 10
        assert all(got[k]["basis"] == "measured" for k in ("service_level", "abandon_rate", "aht"))

    def test_no_calls_is_no_figure_not_zero(self) -> None:
        # Failure caught: "no data" reading as a perfect or a terrible score.
        got = items(card(Role.PLANNER))
        assert got["service_level"]["value"] is None
        assert got["aht"]["value"] is None

    def test_occupancy_is_handling_time_over_paid_time_on_a_published_roster_only(self) -> None:
        # Failure caught: occupancy computed against a draft roster nobody has been promised.
        calls(MON, offered=10, in_sl=8, handle_s=14400)  # four hours of handling
        q = queue()
        d1 = standard_shifts()["D1"]  # 480 paid minutes
        e1 = person("E001")
        week = RosterWeek.objects.create(queue=q, week_start=MON, status=RosterStatus.DRAFT)
        ShiftAssignment.objects.create(roster_week=week, employee=e1, day=MON, template=d1)
        assert items(card(Role.PLANNER))["occupancy"]["value"] is None
        RosterWeek.objects.filter(pk=week.pk).update(status=RosterStatus.PUBLISHED)
        occupancy = items(card(Role.PLANNER))["occupancy"]
        assert occupancy["value"] == pytest.approx(50.0)  # 4 h of 8 h
        assert occupancy["basis"] == "modelled"

    def test_cost_per_contact_says_what_is_missing_instead_of_inventing_a_number(self) -> None:
        got = items(card(Role.EXECUTIVE))["cost_per_contact"]
        assert (got["value"], got["basis"]) == (None, "needs_data")
        assert "payroll" in got["note"]

    def test_the_trend_has_one_row_per_day_with_calls(self) -> None:
        calls(MON, offered=10, in_sl=8)
        calls(TUE, offered=20, in_sl=10)
        days = card(Role.PLANNER)["days"]
        assert [(d["day"], d["offered"], d["serviceLevelPct"]) for d in days] == [
            ("2031-03-03", 10, 80.0),
            ("2031-03-04", 20, 50.0),
        ]

    def test_only_the_range_asked_for_is_counted(self) -> None:
        calls(MON, offered=10, in_sl=10)
        calls(date(2031, 3, 20), offered=99, in_sl=0)
        assert items(card(Role.PLANNER))["offered"]["value"] == 10


class TestWhoSeesWhat:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_these_roles_can_open_it(self, role: Role) -> None:
        assert items(card(role))["service_level"]

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT])
    def test_other_roles_are_refused(self, role: Role) -> None:
        r = client(role).get(URL, {"date_from": str(MON), "date_to": str(TUE)})
        assert r.status_code == 403

    def test_signed_out_is_refused(self) -> None:
        assert Client().get(URL).status_code in (401, 403)

    def test_an_executive_gets_no_figure_built_on_rosters_or_leave(self) -> None:
        # Failure caught: an executive reading roster, leave or planning figures they may not see.
        got = items(card(Role.EXECUTIVE))
        assert not {"occupancy", "planned_shrinkage", "coverage_gap"} & got.keys()
        planner = items(card(Role.PLANNER))
        assert {"occupancy", "planned_shrinkage", "coverage_gap"} <= planner.keys()

    def test_customer_ops_see_only_the_queues_their_contracts_hold(self) -> None:
        # Failure caught: a customer reading the demand of queues that are not theirs.
        calls(MON, offered=50, in_sl=50)
        assert items(card(Role.CUSTOMER_OPS))["offered"]["value"] == 0
        assert items(card(Role.CUSTOMER_OPS))["service_level"]["value"] is None
        assert items(card(Role.PLANNER))["offered"]["value"] == 50


class TestRange:
    def test_backwards_and_over_long_ranges_are_refused(self) -> None:
        c = client(Role.PLANNER)
        backwards = c.get(URL, {"date_from": "2031-03-05", "date_to": "2031-03-01"})
        too_long = c.get(URL, {"date_from": "2020-01-01", "date_to": "2031-03-01"})
        assert (backwards.status_code, too_long.status_code) == (422, 422)


class TestScorecardCsv:
    CSV = "/api/v1/insight/scorecard.csv"

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_these_roles_can_download_it(self, role: Role) -> None:
        calls(MON, 10, 8)
        response = client(role).get(self.CSV, {"date_from": str(MON), "date_to": str(TUE)})
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        text = response.content.decode()
        assert text.startswith("section,key_or_day,label")
        assert "figure,service_level" in text
        assert ("day,2031-03-03" in text) == (role != Role.CUSTOMER_OPS)  # scoped like the screen
        assert "cost_per_contact" not in text  # no money figure leaves in a file

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT])
    def test_other_roles_are_refused(self, role: Role) -> None:
        response = client(role).get(self.CSV, {"date_from": str(MON), "date_to": str(TUE)})
        assert response.status_code == 403

    def test_a_bad_range_is_refused(self) -> None:
        response = client(Role.ADMIN).get(self.CSV, {"date_from": str(TUE), "date_to": str(MON)})
        assert response.status_code == 422

    def test_it_needs_a_login(self) -> None:
        anonymous = Client().get(self.CSV, {"date_from": str(MON), "date_to": str(TUE)})
        assert anonymous.status_code in (401, 403)
