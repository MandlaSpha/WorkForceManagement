"""Peaks and troughs (RPT-03): the ranking, local time, and who may ask."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.telephony.models import IntervalActual, Queue

pytestmark = pytest.mark.django_db

URL = "/api/v1/telephony/peaks"
ZONE = ZoneInfo(settings.TIME_ZONE)


def client(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    c = Client()
    c.force_login(user)
    return c


def calls(queue: Queue, day: int, hh: int, mm: int, offered: int) -> None:
    IntervalActual.objects.create(
        queue=queue,
        interval_start=datetime(2031, 3, day, hh, mm, tzinfo=ZONE),
        offered=offered,
        answered=offered,
        abandoned=0,
        answered_in_sl=offered,
        sum_wait_s=0,
        sum_handle_s=0,
    )


def get(c: Client, queue_id: int, first: str, last: str) -> Any:
    return c.get(URL, {"queue_id": str(queue_id), "date_from": first, "date_to": last})


def ask(
    c: Client, queue: Queue, first: str = "2031-03-01", last: str = "2031-03-31"
) -> dict[str, Any]:
    response = get(c, queue.pk, first, last)
    assert response.status_code == 200, response.content
    return dict(response.json())


def test_ranks_days_and_half_hours_in_local_time() -> None:
    # Failure caught: UTC times reported, so an 08:00 peak shows as 06:00.
    q = Queue.objects.create(name="Q")
    calls(q, 3, 8, 0, 30)
    calls(q, 3, 8, 30, 10)
    calls(q, 4, 8, 0, 20)
    body = ask(client(Role.PLANNER), q)
    assert body["busiestIntervals"][0] == {"start": "2031-03-03 08:00", "offered": 30}
    assert body["busiestDays"][0] == {"day": "2031-03-03", "offered": 40}
    assert body["busiestSlots"][0]["slot"] == "08:00"
    assert body["quietestSlots"][0]["slot"] == "08:30"
    assert body["daysMeasured"] == 2


def test_only_the_range_asked_for_is_read() -> None:
    # Failure caught: the whole history ranked when a week was asked for.
    q = Queue.objects.create(name="Q")
    calls(q, 3, 8, 0, 99)
    calls(q, 20, 8, 0, 5)
    body = ask(client(Role.PLANNER), q, "2031-03-10", "2031-03-31")
    assert body["busiestDays"] == [{"day": "2031-03-20", "offered": 5}]


def test_a_queue_with_no_calls_is_empty_not_an_error() -> None:
    body = ask(client(Role.PLANNER), Queue.objects.create(name="Q"))
    assert body["busiestDays"] == []
    assert body["daysMeasured"] == 0


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE])
def test_roles_that_may_see_aggregates_can_ask(role: Role) -> None:
    ask(client(role), Queue.objects.create(name="Q"))


def test_an_agent_is_refused() -> None:
    q = Queue.objects.create(name="Q")
    assert get(client(Role.AGENT), q.pk, "2031-03-01", "2031-03-02").status_code == 403


def test_customer_ops_cannot_see_a_queue_no_contract_holds() -> None:
    # Failure caught: a customer's view reading demand of queues outside their contracts.
    q = Queue.objects.create(name="Q")
    assert get(client(Role.CUSTOMER_OPS), q.pk, "2031-03-01", "2031-03-02").status_code == 404


def test_an_unknown_queue_is_not_found() -> None:
    assert get(client(Role.PLANNER), 999999, "2031-03-01", "2031-03-02").status_code == 404


def test_bad_ranges_are_refused() -> None:
    q = Queue.objects.create(name="Q")
    c = client(Role.PLANNER)
    backwards = get(c, q.pk, "2031-03-05", "2031-03-01")
    too_long = get(c, q.pk, "2020-01-01", "2031-03-01")
    assert (backwards.status_code, too_long.status_code) == (422, 422)


def test_daily_profile_and_heat_cover_the_range() -> None:
    # Failure caught: the charts getting only the top five, or a gap day sent as zero calls.
    q = Queue.objects.create(name="Q")
    calls(q, 3, 8, 0, 30)  # Monday
    calls(q, 3, 8, 30, 10)
    calls(q, 5, 8, 0, 20)  # Wednesday; the 4th has no rows
    calls(q, 10, 8, 0, 10)  # Monday again
    body = ask(client(Role.PLANNER), q)
    assert body["daily"] == [
        {"day": "2031-03-03", "offered": 40},
        {"day": "2031-03-05", "offered": 20},
        {"day": "2031-03-10", "offered": 10},
    ]
    assert [(s["slot"], s["averageOffered"], s["days"]) for s in body["profile"]] == [
        ("08:00", "20.0", 3),
        ("08:30", "10.0", 1),
    ]
    monday_8 = next(c for c in body["heat"] if c["weekday"] == 0 and c["slot"] == 16)
    assert (monday_8["averageOffered"], monday_8["days"]) == ("20.0", 2)
    assert len(body["heat"]) == 3


def test_new_fields_are_empty_for_an_empty_queue() -> None:
    body = ask(client(Role.PLANNER), Queue.objects.create(name="Q"))
    assert (body["daily"], body["profile"], body["heat"]) == ([], [], [])


@pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE])
def test_every_allowed_role_gets_the_new_fields(role: Role) -> None:
    q = Queue.objects.create(name="Q")
    calls(q, 3, 8, 0, 3)
    assert len(ask(client(role), q)["daily"]) == 1
