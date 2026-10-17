"""Service desk workload on a real PostgreSQL, with the numbers worked out by hand.

As of Monday 25 May 2026, a 5-day horizon (5 working days), pool "Service Desk" with 360 productive
minutes a day, so one person does 1800 minutes in the horizon. Open items (all opened in April,
before the 28-day window):

  A  480 min  due Tue 26 12:00      in the horizon
  B  240 min  due Sun 24 17:00      already breached, still has to be done
  C  600 min  due Wed 3 Jun         outside the horizon
  D  no estimate, due Thu 28        in the horizon, effort unknown
  E  120 min  no deadline           in the backlog, not in the requirement
  backlog 480 + 240 + 600 + 120 = 1440; due in horizon 480 + 240 = 720; breached 1

Arrivals: three closed items opened in the window (27 Apr to 24 May, 20 working days) with 1800,
1200 and 600 minutes: 3600 / 20 = 180 a working day, 900 over the horizon.
  required = (720 + 900) / 1800 = 0.9 people

Pool "NOC": one open item, 360 min due Monday noon, opened in April, nothing opened in the
window, so arrivals are unknown (not zero): required 360 / 1800 = 0.2 people, a minimum.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent
from wfm.servicedesk.models import ServicePool, WorkItem

pytestmark = pytest.mark.django_db

DEMAND = "/api/v1/service-desk/demand"
IMPORTS = "/api/v1/service-desk/imports"
POOLS = "/api/v1/service-desk/pools"
AS_OF = date(2026, 5, 25)

HEADER = "ref,pool,priority,opened,due,effort_minutes,closed"
ROWS = [
    "INC1,Service Desk,P2,2026-04-01 09:00,2026-05-26 12:00,480,",
    "INC2,Service Desk,P1,2026-04-02 09:00,2026-05-24 17:00,240,",
    "INC3,Service Desk,P3,2026-04-03 09:00,2026-06-03 12:00,600,",
    "INC4,Service Desk,P2,2026-04-04 09:00,2026-05-28 12:00,,",
    "INC5,Service Desk,P4,2026-04-05 09:00,,120,",
    "INC6,Service Desk,P3,2026-04-28 09:00,2026-05-04 12:00,1800,2026-05-02 10:00",
    "INC7,Service Desk,P3,2026-05-05 09:00,2026-05-12 12:00,1200,2026-05-08 10:00",
    "INC8,Service Desk,P3,2026-05-12 09:00,2026-05-19 12:00,600,2026-05-15 10:00",
    "INC9,NOC,P1,2026-04-10 09:00,2026-05-25 12:00,360,",
]


def login(role: Role = Role.PLANNER) -> Client:
    user, _ = User.objects.get_or_create(username=f"u-{role.value}", defaults={"role": role})
    client = Client()
    client.force_login(user)
    return client


def upload(client: Client, text: str) -> Any:
    file = SimpleUploadedFile("items.csv", text.encode("utf-8"), content_type="text/csv")
    return client.post(IMPORTS, {"file": file})


def csv_of(rows: list[str] = ROWS, header: str = HEADER) -> str:
    return "\n".join([header, *rows]) + "\n"


def demand(client: Client | None = None, days: int = 5) -> dict[str, Any]:
    query: dict[str, str | int] = {"as_of": str(AS_OF), "days": days}
    response = (client or login()).get(DEMAND, query)
    assert response.status_code == 200, response.content
    return response.json()  # type: ignore[no-any-return]


@pytest.fixture
def loaded() -> None:
    assert upload(login(), csv_of()).status_code == 201


def pool_row(body: dict[str, Any], name: str) -> dict[str, Any]:
    return next(p for p in body["pools"] if p["pool"] == name)


@pytest.mark.usefixtures("loaded")
class TestTheDemandByHand:
    def test_a_pool_needs_the_effort_due_plus_what_arrives_over_one_persons_productive_time(
        self,
    ) -> None:
        sd = pool_row(demand(), "Service Desk")
        assert (sd["openCount"], sd["breached"]) == (5, 1)
        assert (sd["backlogMin"], sd["dueMin"]) == (1440, 720)
        assert sd["arrivingMin"] == pytest.approx(900)
        assert sd["requiredFte"] == pytest.approx(0.9)

    def test_what_is_missing_is_counted_and_the_figure_is_a_minimum(self) -> None:
        sd = pool_row(demand(), "Service Desk")
        assert (sd["unestimated"], sd["noDeadline"]) == (1, 1)
        assert sd["complete"] is False

    def test_a_pool_with_nothing_opened_recently_has_unknown_arrivals_not_zero(self) -> None:
        noc = pool_row(demand(), "NOC")
        assert noc["arrivingMin"] is None
        assert noc["requiredFte"] == pytest.approx(360 / 1800)
        assert noc["complete"] is False

    def test_pools_come_most_people_first_and_the_totals_add_up(self) -> None:
        body = demand()
        assert [p["pool"] for p in body["pools"]] == ["Service Desk", "NOC"]
        assert body["requiredFte"] == pytest.approx(0.9 + 0.2)
        assert (body["backlogMin"], body["breached"], body["workingDays"]) == (1800, 1, 5)
        assert body["arrivingMin"] == pytest.approx(900)  # only the pool that has a rate
        assert body["complete"] is False

    def test_a_shorter_horizon_needs_only_what_falls_due_in_it(self) -> None:
        # Monday and Tuesday: A (Tue noon) and B (breached) are due; arrivals 180 * 2 = 360.
        sd = pool_row(demand(days=2), "Service Desk")
        assert sd["dueMin"] == 720
        assert sd["arrivingMin"] == pytest.approx(360)
        assert sd["requiredFte"] == pytest.approx((720 + 360) / (360 * 2))

    def test_a_horizon_of_only_a_weekend_has_no_requirement(self) -> None:
        query: dict[str, str | int] = {"as_of": "2026-05-30", "days": 2}
        response = login().get(DEMAND, query)
        sd = pool_row(response.json(), "Service Desk")
        assert sd["requiredFte"] is None

    def test_a_closed_item_is_not_work_any_more(self) -> None:
        upload(
            login(),
            csv_of(["INC1,Service Desk,P2,2026-04-01 09:00,2026-05-26 12:00,480,2026-05-22 10:00"]),
        )
        sd = pool_row(demand(), "Service Desk")
        assert sd["openCount"] == 4  # INC1 is closed now
        assert sd["dueMin"] == 240

    def test_the_period_must_be_one_to_thirty_one_days(self) -> None:
        for days in (0, 32):
            query: dict[str, str | int] = {"as_of": str(AS_OF), "days": days}
            response = login().get(DEMAND, query)
            assert (response.status_code, response.json()["code"]) == (
                422,
                "servicedesk.days_invalid",
            )


class TestTheImport:
    def test_reports_what_it_did(self) -> None:
        body = upload(login(), csv_of()).json()
        assert (body["created"], body["updated"], body["unchanged"]) == (9, 0, 0)
        assert body["rejected"] == {}
        assert ServicePool.objects.count() == 2

    def test_bringing_the_same_export_again_changes_nothing_and_adds_nothing(self) -> None:
        upload(login(), csv_of())
        body = upload(login(), csv_of()).json()
        assert (body["created"], body["updated"], body["unchanged"]) == (0, 0, 9)
        assert WorkItem.objects.count() == 9

    def test_a_ticket_worked_and_closed_is_updated_not_duplicated(self) -> None:
        upload(login(), csv_of())
        body = upload(
            login(),
            csv_of(["INC4,Service Desk,P2,2026-04-04 09:00,2026-05-28 12:00,90,2026-05-22 10:00"]),
        ).json()
        assert (body["created"], body["updated"]) == (0, 1)
        item = WorkItem.objects.get(ref="INC4")
        assert (item.effort_minutes, item.closed_at is not None) == (90, True)

    def test_survey_answers_and_the_first_contact_flag_are_stored(self) -> None:
        header = HEADER + ",fcr,csat,nps"
        rows = [
            "S1,Service Desk,P3,2026-05-04 09:00,,60,2026-05-05 09:00,Yes,5,10",
            "S2,Service Desk,P3,2026-05-04 09:00,,60,2026-05-05 09:00,no,2,3",
            "S3,Service Desk,P3,2026-05-04 09:00,,60,2026-05-05 09:00,,,",
        ]
        body = upload(login(), csv_of(rows, header)).json()
        assert (body["created"], body["rejected"]) == (3, {})
        got = {i.ref: (i.first_contact_resolved, i.csat, i.nps) for i in WorkItem.objects.all()}
        assert got == {"S1": (True, 5, 10), "S2": (False, 2, 3), "S3": (None, None, None)}

    @pytest.mark.parametrize(
        ("tail", "reason"),
        [
            (",maybe,,", "bad_fcr"),
            (",,6,", "bad_csat"),
            (",,0,", "bad_csat"),
            (",,,11", "bad_nps"),
            (",,,x", "bad_nps"),
        ],
    )
    def test_a_bad_survey_answer_rejects_the_row_by_reason(self, tail: str, reason: str) -> None:
        row = "S1,Service Desk,P3,2026-05-04 09:00,,60,2026-05-05 09:00" + tail
        body = upload(login(), csv_of([row], HEADER + ",fcr,csat,nps")).json()
        assert body["rejected"] == {reason: 1}
        assert not WorkItem.objects.exists()

    def test_a_ticket_closed_before_it_was_opened_is_rejected(self) -> None:
        row = "S1,Service Desk,P3,2026-05-04 09:00,,60,2026-05-03 09:00"
        assert upload(login(), csv_of([row])).json()["rejected"] == {"closed_before_opened": 1}

    def test_a_time_with_no_zone_is_south_african_time(self) -> None:
        upload(login(), csv_of(["INC1,Service Desk,P2,2026-04-01 09:00,2026-05-26 12:00,480,"]))
        assert WorkItem.objects.get(ref="INC1").due_at == datetime(2026, 5, 26, 10, 0, tzinfo=UTC)

    def test_a_time_with_a_zone_keeps_it(self) -> None:
        upload(
            login(), csv_of(["INC1,Service Desk,P2,2026-04-01T09:00:00Z,2026-05-26T12:00:00Z,480,"])
        )
        assert WorkItem.objects.get(ref="INC1").due_at == datetime(2026, 5, 26, 12, 0, tzinfo=UTC)

    def test_a_column_that_is_not_read_never_reaches_the_database(self) -> None:
        text = csv_of(
            ["INC1,Service Desk,P2,2026-04-01 09:00,,480,,Pat Secret"],
            header=HEADER + ",requester",
        )
        body = upload(login(), text).json()
        assert body["ignoredColumns"] == ["requester"]
        stored = " ".join(str(v) for v in WorkItem.objects.values().first().values())  # type: ignore[union-attr]
        assert "Pat Secret" not in stored
        audited = " ".join(
            f"{c.field}{c.old_value}{c.new_value}" for c in AuditChange.objects.all()
        )
        assert "Pat Secret" not in audited

    def test_rows_that_cannot_be_read_are_counted_by_reason_and_the_rest_is_kept(self) -> None:
        rows = [
            "OK1,Service Desk,P2,2026-04-01 09:00,,60,",
            ",Service Desk,P2,2026-04-01 09:00,,60,",  # no reference
            "BAD2,,P2,2026-04-01 09:00,,60,",  # no pool
            "BAD3,Service Desk,P2,not a date,,60,",
            "BAD4,Service Desk,P2,2026-04-01 09:00,soon,60,",  # an unreadable deadline
            "BAD5,Service Desk,P2,2026-04-01 09:00,,sixty,",
            "OK1,Service Desk,P2,2026-04-01 09:00,,60,",  # the same reference again
        ]
        body = upload(login(), csv_of(rows)).json()
        assert body["created"] == 1
        assert body["rejected"] == {
            "bad_ref": 1,
            "bad_pool": 1,
            "bad_opened": 1,
            "bad_date": 1,
            "bad_effort": 1,
            "repeated_ref": 1,
        }

    @pytest.mark.parametrize(
        "text",
        ["", "ref,pool\nA,B\n", "just some words\n"],
    )
    def test_a_file_that_is_not_a_work_item_export_is_refused_and_audited(self, text: str) -> None:
        response = upload(login(), text)
        assert (response.status_code, response.json()["code"]) == (422, "workitems.unreadable")
        assert WorkItem.objects.count() == 0
        assert AuditEvent.objects.filter(action=Action.WORKITEMS_IMPORT_REFUSED).exists()

    def test_a_file_that_is_not_text_is_refused(self) -> None:
        file = SimpleUploadedFile("x.csv", b"\xff\xfe\x00bad", content_type="text/csv")
        response = login().post(IMPORTS, {"file": file})
        assert (response.status_code, response.json()["code"]) == (422, "workitems.unreadable")

    def test_the_audit_trail_holds_counts_only(self) -> None:
        upload(login(), csv_of())
        event = AuditEvent.objects.get(action=Action.WORKITEMS_IMPORTED)
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes == {"created": "9", "updated": "0", "unchanged": "0", "rejected": "0"}
        assert event.actor_role == Role.PLANNER


@pytest.mark.usefixtures("loaded")
class TestThePoolsProductiveTime:
    def test_starts_as_the_default_and_unconfirmed(self) -> None:
        sd = pool_row(demand(), "Service Desk")
        assert (sd["productiveMinutesPerDay"], sd["settingsConfirmed"]) == (360, False)

    def test_changing_it_changes_how_many_people_are_needed_and_confirms_it(self) -> None:
        pool = ServicePool.objects.get(name="Service Desk")
        response = login().put(
            f"{POOLS}/{pool.pk}", {"productiveMinutesPerDay": 480}, content_type="application/json"
        )
        assert response.status_code == 200
        sd = pool_row(demand(), "Service Desk")
        assert sd["settingsConfirmed"] is True
        assert sd["requiredFte"] == pytest.approx((720 + 900) / (480 * 5))  # 0.675

    @pytest.mark.parametrize("minutes", [29, 601])
    def test_nonsense_is_refused_and_nothing_changes(self, minutes: int) -> None:
        pool = ServicePool.objects.get(name="Service Desk")
        response = login().put(
            f"{POOLS}/{pool.pk}",
            {"productiveMinutesPerDay": minutes},
            content_type="application/json",
        )
        assert (response.status_code, response.json()["code"]) == (422, "pool.minutes_invalid")
        pool.refresh_from_db()
        assert (pool.productive_minutes_per_day, pool.settings_confirmed) == (360, False)

    def test_an_unknown_pool_is_not_found(self) -> None:
        response = login().put(
            f"{POOLS}/999999", {"productiveMinutesPerDay": 400}, content_type="application/json"
        )
        assert response.status_code == 404

    def test_the_audit_trail_records_before_and_after(self) -> None:
        pool = ServicePool.objects.get(name="Service Desk")
        login(Role.ADMIN).put(
            f"{POOLS}/{pool.pk}", {"productiveMinutesPerDay": 420}, content_type="application/json"
        )
        event = AuditEvent.objects.get(action=Action.SERVICE_POOL_CHANGED)
        changes = {
            c.field: (c.old_value, c.new_value) for c in AuditChange.objects.filter(event=event)
        }
        assert changes == {
            "productive_minutes_per_day": ("360", "420"),
            "settings_confirmed": ("False", "True"),
        }


@pytest.mark.usefixtures("loaded")
class TestWhoMay:
    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER, Role.CUSTOMER_OPS])
    def test_these_roles_read_the_workload(self, role: Role) -> None:
        assert demand(login(role))["requiredFte"] == pytest.approx(1.1)

    @pytest.mark.parametrize("role", [Role.LEAD, Role.AGENT, Role.EXECUTIVE])
    def test_other_roles_are_refused(self, role: Role) -> None:
        response = login(role).get(DEMAND, {"as_of": str(AS_OF)})
        assert response.status_code == 403

    @pytest.mark.parametrize("role", [Role.ADMIN, Role.PLANNER])
    def test_planners_and_admins_bring_work_in_and_set_the_productive_time(
        self, role: Role
    ) -> None:
        assert upload(login(role), csv_of()).status_code == 201
        pool = ServicePool.objects.first()
        assert pool is not None
        response = login(role).put(
            f"{POOLS}/{pool.pk}", {"productiveMinutesPerDay": 400}, content_type="application/json"
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("role", [Role.CUSTOMER_OPS, Role.LEAD, Role.AGENT, Role.EXECUTIVE])
    def test_nobody_else_changes_anything(self, role: Role) -> None:
        pool = ServicePool.objects.first()
        assert pool is not None
        assert (
            upload(login(role), csv_of(["NEW,Service Desk,P1,2026-05-01 09:00,,10,"])).status_code
            == 403
        )
        put = login(role).put(
            f"{POOLS}/{pool.pk}", {"productiveMinutesPerDay": 400}, content_type="application/json"
        )
        assert put.status_code == 403
        assert not WorkItem.objects.filter(ref="NEW").exists()
        pool.refresh_from_db()
        assert pool.productive_minutes_per_day == 360
