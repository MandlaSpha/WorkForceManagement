"""Capacity planning against the 100 permanent + 250 seasonal workforce, on a real PostgreSQL.

The week of Monday 25 May 2026 is built by hand from two queues' PUBLISHED forecasts
(agents to roster, shrinkage already included, summed across queues at each half-hour):

  Monday     A: 60 at 10:00, 70 at 10:30      B: 50 at 10:00, 90 at 10:30
             sums 110 and 160 -> peak 160 at 10:30 -> 100 permanent + 60 seasonal
  Tuesday    A only (B has no forecast that day): 200 at 11:00
             -> peak 200, but only one queue of two, so a minimum: 100 + 100
  Wednesday  A: 400 at 10:00   B: 10 at 10:00 -> peak 410
             -> 100 permanent + 250 seasonal + 60 overflow
  Thursday to Sunday: no forecast, so no figures (never zeros)
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.forecasting.models import ForecastInterval, ForecastStatus, ForecastVersion
from wfm.scheduling.models import ContractType, Employee
from wfm.telephony.models import Queue

pytestmark = pytest.mark.django_db

CAPACITY = "/api/v1/capacity"
LIMITS = "/api/v1/capacity/limits"
MON = date(2026, 5, 25)
ZONE = ZoneInfo("Africa/Johannesburg")


def login(role: Role = Role.PLANNER) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def publish(
    queue: Queue,
    needs: dict[tuple[date, int], int | None],
    status: str = ForecastStatus.PUBLISHED,
) -> ForecastVersion:
    """A forecast for `queue` with `needs[(day, slot)]` agents to roster; every other half-hour of
    each day mentioned is 0. A day not mentioned has no forecast at all."""
    owner, _ = User.objects.get_or_create(username="u-maker", defaults={"role": Role.PLANNER})
    days = sorted({d for d, _ in needs})
    version = ForecastVersion.objects.create(
        queue=queue,
        status=status,
        method="baseline-v1",
        date_from=days[0],
        date_to=days[-1],
        created_by=owner,
    )
    rows = []
    for day in days:
        for slot in range(48):
            start = datetime.combine(day, time(slot // 2, 30 * (slot % 2)), tzinfo=ZONE)
            rows.append(
                ForecastInterval(
                    version=version,
                    interval_start=start,
                    volume=1.0,
                    required=needs.get((day, slot), 0),
                    required_raw=0,
                    days_used=1,
                )
            )
    ForecastInterval.objects.bulk_create(rows)
    return version


@pytest.fixture
def queues() -> tuple[Queue, Queue]:
    return Queue.objects.create(name="QueueA"), Queue.objects.create(name="QueueB")


@pytest.fixture
def week(queues: tuple[Queue, Queue]) -> None:
    a, b = queues
    tue, wed = MON + timedelta(days=1), MON + timedelta(days=2)
    publish(a, {(MON, 20): 60, (MON, 21): 70, (tue, 22): 200, (wed, 20): 400})
    publish(b, {(MON, 20): 50, (MON, 21): 90, (wed, 20): 10})


def get(client: Client, weeks: int = 1, start: date = MON) -> Any:
    return client.get(f"{CAPACITY}?week_start={start}&weeks={weeks}")


def days_of(response: Any, week: int = 0) -> dict[str, dict[str, Any]]:
    return {d["day"]: d for d in response.json()["weeks"][week]["days"]}


@pytest.mark.usefixtures("week")
class TestTheWeekByHand:
    def test_a_covered_day_is_split_permanent_first_then_seasonal(self) -> None:
        monday = days_of(get(login()))[str(MON)]
        assert (monday["peak"], monday["permanent"], monday["seasonal"], monday["overflow"]) == (
            160,
            100,
            60,
            0,
        )
        assert (monday["queuesCovered"], monday["queuesTotal"], monday["complete"]) == (2, 2, True)

    def test_a_day_missing_a_queue_gives_a_minimum_and_says_so(self) -> None:
        tuesday = days_of(get(login()))[str(MON + timedelta(days=1))]
        assert (tuesday["peak"], tuesday["permanent"], tuesday["seasonal"]) == (200, 100, 100)
        assert (tuesday["queuesCovered"], tuesday["queuesTotal"]) == (1, 2)
        assert tuesday["complete"] is False

    def test_demand_beyond_the_whole_workforce_is_overflow(self) -> None:
        wednesday = days_of(get(login()))[str(MON + timedelta(days=2))]
        assert wednesday["peak"] == 410
        assert (wednesday["permanent"], wednesday["seasonal"], wednesday["overflow"]) == (
            100,
            250,
            60,
        )

    def test_days_with_no_forecast_have_no_figures_not_zeros(self) -> None:
        thursday = days_of(get(login()))[str(MON + timedelta(days=3))]
        assert thursday["queuesCovered"] == 0
        for field in ("peak", "permanent", "seasonal", "overflow", "seasonalToHire"):
            assert thursday[field] is None
        assert thursday["complete"] is False

    def test_the_week_summary(self) -> None:
        summary = get(login()).json()["weeks"][0]
        assert summary["weekStart"] == str(MON)
        assert (summary["peak"], summary["peakDay"]) == (410, str(MON + timedelta(days=2)))
        assert summary["seasonalPeak"] == 250
        assert summary["overflowDays"] == 1
        assert summary["daysForecast"] == 3
        assert summary["daysIncomplete"] == 1  # Tuesday

    def test_more_weeks_are_more_rows_and_empty_weeks_say_nothing_is_forecast(self) -> None:
        response = get(login(), weeks=3)
        weeks = response.json()["weeks"]
        assert [w["weekStart"] for w in weeks] == [
            str(MON),
            str(MON + timedelta(days=7)),
            str(MON + timedelta(days=14)),
        ]
        assert (weeks[1]["peak"], weeks[1]["peakDay"], weeks[1]["daysForecast"]) == (None, None, 0)

    def test_the_busiest_moment_not_the_sum_of_the_day(self) -> None:
        # Monday's two half-hours need 110 and 160: the answer is 160, not 270.
        assert days_of(get(login()))[str(MON)]["peak"] == 160


class TestOnlyWhatIsPublished:
    def test_drafts_and_archived_forecasts_do_not_count(self, queues: tuple[Queue, Queue]) -> None:
        a, _ = queues
        publish(a, {(MON, 20): 60})
        publish(a, {(MON, 20): 999}, status=ForecastStatus.DRAFT)
        # The one-published rule is a database constraint; archived versions are history.
        publish(a, {(MON, 20): 888}, status=ForecastStatus.ARCHIVED)
        assert days_of(get(login()))[str(MON)]["peak"] == 60

    def test_an_unknown_half_hour_makes_the_peak_a_minimum(
        self, queues: tuple[Queue, Queue]
    ) -> None:
        a, b = queues
        publish(a, {(MON, 20): 60, (MON, 30): None})
        publish(b, {(MON, 20): 5})
        monday = days_of(get(login()))[str(MON)]
        assert monday["peak"] == 65
        assert monday["complete"] is False

    def test_when_nothing_is_published_every_day_is_empty(self) -> None:
        response = get(login())
        assert response.status_code == 200
        assert all(d["peak"] is None for d in days_of(response).values())


class TestPeopleOnTheBooks:
    def test_counts_who_is_employed_each_day_by_contract(self, week: None) -> None:
        Employee.objects.create(emp_no="P1", name="Perm One")
        Employee.objects.create(emp_no="P2", name="Perm Two", end_date=MON)  # leaves after Mon
        for n in range(3):
            Employee.objects.create(
                emp_no=f"S{n}",
                name=f"Seasonal {n}",
                contract_type=ContractType.SEASONAL,
                start_date=MON + timedelta(days=2),  # from Wednesday
            )
        days = days_of(get(login()))
        monday, tuesday, wednesday = (days[str(MON + timedelta(days=n))] for n in range(3))
        assert (monday["permanentOnBooks"], monday["seasonalOnBooks"]) == (2, 0)
        assert (tuesday["permanentOnBooks"], tuesday["seasonalOnBooks"]) == (1, 0)
        assert (wednesday["permanentOnBooks"], wednesday["seasonalOnBooks"]) == (1, 3)

    def test_says_how_many_seasonal_agents_are_still_to_find(self, week: None) -> None:
        for n in range(3):
            Employee.objects.create(
                emp_no=f"S{n}",
                name=f"Seasonal {n}",
                contract_type=ContractType.SEASONAL,
                start_date=MON + timedelta(days=2),
            )
        days = days_of(get(login()))
        assert days[str(MON)]["seasonalToHire"] == 60  # need 60, none engaged
        assert days[str(MON + timedelta(days=2))]["seasonalToHire"] == 247  # need 250, 3 engaged

    def test_more_seasonal_agents_than_needed_is_not_a_negative_hire(self, week: None) -> None:
        for n in range(80):
            Employee.objects.create(
                emp_no=f"S{n}", name=f"S {n}", contract_type=ContractType.SEASONAL
            )
        assert days_of(get(login()))[str(MON)]["seasonalToHire"] == 0  # need 60, have 80

    def test_the_response_carries_counts_never_names(self, week: None) -> None:
        Employee.objects.create(emp_no="P1", name="Pat Secret")
        assert "Pat Secret" not in get(login()).content.decode()
        assert "P1" not in get(login()).content.decode()


class TestTheLimits:
    def test_start_as_the_tenders_figures_and_unconfirmed(self) -> None:
        limits = get(login()).json()["limits"]
        assert limits == {"permanentLimit": 100, "seasonalLimit": 250, "confirmed": False}

    def test_an_admin_sets_them_and_the_split_follows(self, week: None) -> None:
        response = login(Role.ADMIN).put(
            LIMITS, {"permanentLimit": 50, "seasonalLimit": 100}, content_type="application/json"
        )
        assert response.status_code == 200
        assert response.json() == {"permanentLimit": 50, "seasonalLimit": 100, "confirmed": True}
        monday = days_of(get(login()))[str(MON)]
        assert (monday["permanent"], monday["seasonal"], monday["overflow"]) == (50, 100, 10)

    @pytest.mark.parametrize(
        ("body", "code"),
        [
            ({"permanentLimit": -1, "seasonalLimit": 250}, "capacity.permanent_invalid"),
            ({"permanentLimit": 100, "seasonalLimit": 5001}, "capacity.seasonal_invalid"),
            ({"permanentLimit": 0, "seasonalLimit": 0}, "capacity.no_workforce"),
        ],
    )
    def test_nonsense_is_refused_and_nothing_changes(self, body: dict[str, int], code: str) -> None:
        response = login(Role.ADMIN).put(LIMITS, body, content_type="application/json")
        assert response.status_code == 422
        assert response.json()["code"] == code
        assert get(login()).json()["limits"]["confirmed"] is False

    def test_the_audit_trail_records_the_change_with_before_and_after(self) -> None:
        login(Role.ADMIN).put(
            LIMITS, {"permanentLimit": 120, "seasonalLimit": 250}, content_type="application/json"
        )
        event = AuditEvent.objects.get(action=Action.CAPACITY_LIMITS_CHANGED)
        assert event.actor_role == Role.ADMIN
        changes = {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }
        assert changes == {"permanent_limit": ("100", "120"), "confirmed": ("False", "True")}

    def test_confirming_the_same_figures_records_only_the_confirmation(self) -> None:
        login(Role.ADMIN).put(
            LIMITS, {"permanentLimit": 100, "seasonalLimit": 250}, content_type="application/json"
        )
        event = AuditEvent.objects.get(action=Action.CAPACITY_LIMITS_CHANGED)
        fields = [c.field for c in AuditChange.objects.filter(event=event)]
        assert fields == ["confirmed"]


class TestRefusals:
    def test_a_week_must_start_on_a_monday(self) -> None:
        response = get(login(), start=date(2026, 5, 26))
        assert (response.status_code, response.json()["code"]) == (422, "capacity.not_a_monday")

    @pytest.mark.parametrize("weeks", [0, 13, -1])
    def test_the_number_of_weeks_is_limited(self, weeks: int) -> None:
        response = get(login(), weeks=weeks)
        assert (response.status_code, response.json()["code"]) == (422, "capacity.weeks_invalid")


class TestWhoMay:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.EXECUTIVE, Role.CUSTOMER_OPS])
    def test_these_roles_read_capacity(self, role: Role, week: None) -> None:
        response = get(login(role))
        assert response.status_code == 200
        assert days_of(response)[str(MON)]["peak"] == 160  # and the figures are real, not blank

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT])
    def test_other_roles_cannot(self, role: Role) -> None:
        assert get(login(role)).status_code == 403

    def test_only_an_admin_sets_the_limits(self) -> None:
        body = {"permanentLimit": 1, "seasonalLimit": 1}
        for role in (Role.PLANNER, Role.LEAD, Role.AGENT, Role.EXECUTIVE, Role.CUSTOMER_OPS):
            response = login(role).put(LIMITS, body, content_type="application/json")
            assert response.status_code == 403, role
        assert get(login()).json()["limits"]["confirmed"] is False
