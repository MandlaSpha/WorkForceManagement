"""Intraday: the day against its forecast, the re-forecast from calls so far, and the alerts."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from wfm.accounts.models import Role, User
from wfm.intraday import selectors
from wfm.scheduling.tests.helpers import (
    MON,
    assign,
    login,
    person,
    publish_forecast,
    queue,
    standard_shifts,
)
from wfm.telephony.models import IntervalActual

pytestmark = pytest.mark.django_db

ZONE = ZoneInfo(settings.TIME_ZONE)
URL = "/api/v1/intraday"


def planner() -> User:
    return User.objects.get_or_create(username="u-planner", defaults={"role": Role.PLANNER})[0]


def calls(day: date, slot: int, offered: int, in_sl: int) -> None:
    IntervalActual.objects.create(
        queue=queue(),
        interval_start=datetime(
            day.year, day.month, day.day, slot // 2, 30 * (slot % 2), tzinfo=ZONE
        ),
        offered=offered,
        answered=offered,
        abandoned=0,
        answered_in_sl=in_sl,
        sum_wait_s=0,
        sum_handle_s=offered * 180,
    )


def at(hour: int, minute: int = 0, day: date = MON) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZONE)


@pytest.fixture
def staffed() -> None:
    """A published forecast for Monday and one person on the 09:00 to 17:30 shift."""
    shifts = standard_shifts()
    publish_forecast(queue(), {(MON, slot): 1 for slot in range(48)})
    assign(login(), queue(), person(), MON, shifts["D1"])


class TestTheReforecast:
    @pytest.mark.usefixtures("staffed")
    def test_a_busy_morning_raises_what_the_rest_of_the_day_needs(self) -> None:
        # Failure caught: the afternoon staffed to the morning's forecast after the morning ran
        # at several times it.
        for slot in range(18, 22):  # 09:00 to 10:59
            calls(MON, slot, offered=20, in_sl=10)
        found = selectors.intraday(planner(), queue().pk, MON, now=at(11, 0))
        assert found.elapsed == 22
        assert found.ratio == 2.0  # four times the forecast, held to double
        assert found.data_through == 21
        assert found.service_level_pct == pytest.approx(50.0)
        slots = {s.slot: s for s in found.slots}
        assert slots[19].actual == 20  # what happened is kept
        assert slots[25].actual is None  # not yet
        assert slots[25].reforecast == pytest.approx(2.0)
        assert slots[25].forecast == 1.0
        assert slots[25].expected_required is not None

    @pytest.mark.usefixtures("staffed")
    def test_alerts_look_only_at_half_hours_still_to_come(self) -> None:
        for slot in range(18, 22):
            calls(MON, slot, offered=20, in_sl=10)
        found = selectors.intraday(planner(), queue().pk, MON, now=at(11, 0))
        assert found.alerts, "one person against double the forecast should fall short"
        assert all(a.slot >= found.elapsed for a in found.alerts)
        assert all(a.required > a.scheduled for a in found.alerts)

    @pytest.mark.usefixtures("staffed")
    def test_no_calls_imported_is_not_a_quiet_day(self) -> None:
        # Failure caught: an empty import read as "nobody rang" and the rest of the day cut.
        found = selectors.intraday(planner(), queue().pk, MON, now=at(11, 0))
        assert (found.ratio, found.data_through, found.service_level_pct) == (None, None, None)
        assert all(s.actual is None for s in found.slots)
        assert found.slots[25].reforecast == found.slots[25].forecast

    def test_a_day_with_no_published_forecast_claims_nothing(self) -> None:
        found = selectors.intraday(planner(), queue().pk, MON, now=at(11, 0))
        assert (found.has_forecast, found.alerts, found.ratio) == (False, [], None)
        assert all(s.forecast is None and s.required is None for s in found.slots)

    @pytest.mark.usefixtures("staffed")
    def test_a_day_that_is_over_has_no_alerts_and_one_still_to_come_has_no_actuals(self) -> None:
        over = selectors.intraday(planner(), queue().pk, MON, now=at(9, 0, MON + timedelta(days=2)))
        assert (over.elapsed, over.alerts) == (48, [])
        ahead = selectors.intraday(
            planner(), queue().pk, MON, now=at(9, 0, MON - timedelta(days=2))
        )
        assert ahead.elapsed == 0
        assert all(s.actual is None for s in ahead.slots)


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def get(c: Client, queue_id: int, day: date) -> Any:
    return c.get(URL, {"queue_id": str(queue_id), "day": str(day)})


class TestTheEndpoint:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD])
    def test_these_roles_can_open_it(self, role: Role) -> None:
        day = timezone.localdate() - timedelta(days=2)
        r = get(client(role), queue().pk, day)
        assert r.status_code == 200, r.content
        assert len(r.json()["slots"]) == 48

    @pytest.mark.parametrize("role", [Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_others_are_refused(self, role: Role) -> None:
        day = timezone.localdate() - timedelta(days=2)
        assert get(client(role), queue().pk, day).status_code == 403

    def test_an_unknown_queue_is_not_found(self) -> None:
        assert get(client(Role.PLANNER), 99999, timezone.localdate()).status_code == 404

    def test_a_day_far_away_is_refused(self) -> None:
        q = queue().pk
        assert (
            get(client(Role.PLANNER), q, timezone.localdate() - timedelta(days=400)).status_code
            == 422
        )
        assert (
            get(client(Role.PLANNER), q, timezone.localdate() + timedelta(days=100)).status_code
            == 422
        )

    def test_signed_out_is_refused(self) -> None:
        assert Client().get(URL).status_code in (401, 403)
