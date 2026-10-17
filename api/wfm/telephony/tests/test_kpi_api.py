"""Reading service figures: the numbers, the DAT-10 honesty fields, and who sees what."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import Client

from wfm.accounts.models import Role, User

from .workbooks import Call, scenario, upload, workbook_bytes

pytestmark = pytest.mark.django_db

KPIS = "/api/v1/telephony/kpis"
QUEUES = "/api/v1/telephony/queues"
DAY = {"date_from": "2026-05-04", "date_to": "2026-05-04"}


def login(role: Role) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def imported_scenario() -> None:
    planner = login(Role.PLANNER)
    response = planner.post(
        "/api/v1/telephony/imports", {"file": upload(workbook_bytes(scenario()))}
    )
    assert response.status_code == 201, response.content


def kpis(role: Role = Role.PLANNER, **params: Any) -> Any:
    return login(role).get(KPIS, {**DAY, **params})


class TestTheFigures:
    """Expected values are worked out by hand in workbooks.py."""

    def test_all_queues(self) -> None:
        total = kpis().json()["total"]
        assert (total["offered"], total["answered"], total["abandoned"]) == (10, 8, 2)
        assert total["abandonPct"]["value"] == pytest.approx(20.0)
        assert total["serviceLevelPct"]["value"] == pytest.approx(50.0)  # 5 / 10 offered
        assert total["asaS"]["value"] == pytest.approx(17.625)
        assert total["ahtS"]["value"] == pytest.approx(153.75)

    def test_each_queue(self) -> None:
        queues = {q["queue"]: q for q in kpis().json()["queues"]}
        a, b = queues["QueueA"], queues["QueueB"]
        assert (a["offered"], a["answered"], a["abandoned"]) == (7, 5, 2)
        assert a["serviceLevelPct"]["value"] == pytest.approx(300 / 7)
        assert a["asaS"]["value"] == pytest.approx(16.2)
        assert a["ahtS"]["value"] == pytest.approx(146.0)
        assert (b["offered"], b["answered"], b["abandoned"]) == (3, 3, 0)
        assert b["serviceLevelPct"]["value"] == pytest.approx(200 / 3)
        assert b["asaS"]["value"] == pytest.approx(20.0)
        assert b["ahtS"]["value"] == pytest.approx(500 / 3)

    def test_one_queue_can_be_asked_for(self) -> None:
        queue_id = next(q["queueId"] for q in kpis().json()["queues"] if q["queue"] == "QueueB")
        body = kpis(queue_id=queue_id).json()
        assert [q["queue"] for q in body["queues"]] == ["QueueB"]
        assert body["total"]["offered"] == 3

    def test_a_day_with_no_calls_has_no_figures_not_zeroes(self) -> None:
        body = kpis(date_from="2026-05-10", date_to="2026-05-10").json()
        total = body["total"]
        assert total["offered"] == 0
        for name in ("abandonPct", "serviceLevelPct", "asaS", "ahtS"):
            assert total[name]["value"] is None
        assert total["serviceLevelPct"]["coverage"]["intervalsUsed"] == 0

    def test_a_call_just_after_midnight_belongs_to_the_south_african_day(self) -> None:
        # 00:30 SAST on 5 May is 22:30 UTC on 4 May. Cut by UTC it would land on the wrong day,
        # and every day's figures would be wrong for the first two hours of the day.
        after_midnight = Call(700, "QueueA", "Agent", "2026-05-05 00:30:00", wait=1, talk=10)
        planner = login(Role.PLANNER)
        response = planner.post(
            "/api/v1/telephony/imports", {"file": upload(workbook_bytes([after_midnight]))}
        )
        assert response.status_code == 201, response.content

        assert kpis().json()["total"]["offered"] == 10  # 4 May: the scenario only
        fifth = kpis(date_from="2026-05-05", date_to="2026-05-05").json()["total"]
        assert fifth["offered"] == 1


class TestMonthsWithData:
    """The dashboard offers exactly these months and opens on the latest, so they decide what
    people see first. They are South African months, not UTC months."""

    MONTHS = "/api/v1/telephony/months"

    def test_lists_only_months_that_have_calls(self) -> None:
        # The scenario is in May. A call in July leaves June out: no empty months are offered.
        july = Call(702, "QueueA", "Agent", "2026-07-10 09:00:00", wait=1, talk=10)
        login(Role.PLANNER).post(
            "/api/v1/telephony/imports", {"file": upload(workbook_bytes([july]))}
        )
        assert login(Role.PLANNER).get(self.MONTHS).json() == {"months": ["2026-05", "2026-07"]}

    def test_a_call_just_after_midnight_counts_to_the_next_south_african_month(self) -> None:
        # 00:30 SAST on 1 June is 22:30 UTC on 31 May: cut by UTC it would be counted to May.
        late = Call(701, "QueueA", "Agent", "2026-06-01 00:30:00", wait=1, talk=10)
        login(Role.PLANNER).post(
            "/api/v1/telephony/imports", {"file": upload(workbook_bytes([late]))}
        )
        assert login(Role.PLANNER).get(self.MONTHS).json()["months"] == ["2026-05", "2026-06"]

    def test_is_empty_for_a_role_that_sees_no_queues(self) -> None:
        assert login(Role.CUSTOMER_OPS).get(self.MONTHS).json() == {"months": []}


class TestHonestyFields:
    """DAT-10: every figure says it was measured and what share of intervals it rests on."""

    def test_every_metric_is_marked_measured_with_its_coverage(self) -> None:
        total = kpis().json()["total"]
        for name in ("abandonPct", "serviceLevelPct", "asaS", "ahtS"):
            assert total[name]["basis"] == "measured"
            assert total[name]["coverage"] == {"intervalsUsed": 3, "intervalsTotal": 48}

    def test_coverage_scales_with_the_range(self) -> None:
        body = kpis(date_to="2026-05-07").json()
        assert body["total"]["serviceLevelPct"]["coverage"]["intervalsTotal"] == 4 * 48


class TestValidation:
    def test_the_end_may_not_be_before_the_start(self) -> None:
        response = kpis(date_from="2026-05-05", date_to="2026-05-04")
        assert response.status_code == 422
        assert response.json()["code"] == "range.invalid"

    def test_a_very_long_range_is_refused(self) -> None:
        response = kpis(date_from="2020-01-01", date_to="2026-05-04")
        assert response.status_code == 422
        assert response.json()["code"] == "range.too_long"

    def test_an_unknown_queue_is_not_found(self) -> None:
        response = kpis(queue_id=999999)
        assert response.status_code == 404
        assert response.json()["code"] == "resource.not_found"


class TestWhoSeesWhat:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.LEAD, Role.EXECUTIVE])
    def test_these_roles_see_every_queue(self, role: Role) -> None:
        body = kpis(role).json()
        assert body["total"]["offered"] == 10
        assert len(login(role).get(QUEUES).json()) == 2

    def test_customer_ops_may_open_the_screen_but_sees_no_queue_until_contracts_exist(
        self,
    ) -> None:
        body = kpis(Role.CUSTOMER_OPS).json()
        assert body["queues"] == []
        assert body["total"]["offered"] == 0
        assert login(Role.CUSTOMER_OPS).get(QUEUES).json() == []

    def test_a_queue_outside_the_role_scope_is_a_404_not_a_403(self) -> None:
        # Existence is not revealed: asking for a real queue id as customer ops looks the same
        # as asking for one that does not exist.
        from wfm.telephony.models import Queue

        real = Queue.objects.get(name="QueueA").pk
        response = kpis(Role.CUSTOMER_OPS, queue_id=real)
        assert response.status_code == 404


class TestNoCallLevelSurface:
    def test_the_api_offers_no_way_to_read_a_call_or_a_person(self) -> None:
        from wfm.api import api

        paths = api.get_openapi_schema()["paths"]
        telephony = sorted(p for p in paths if "/telephony" in p)
        # Adding a route means deciding, on purpose, that it exposes only aggregates.
        assert telephony == [
            # Sums per queue; per-login rows only for admin, planner and a lead's own team.
            "/api/v1/telephony/call-detail",
            "/api/v1/telephony/imports",
            "/api/v1/telephony/kpis",
            "/api/v1/telephony/months",
            "/api/v1/telephony/peaks",  # day and half-hour totals only
            "/api/v1/telephony/queues",
            "/api/v1/telephony/queues/{queue_id}/settings",
        ]
