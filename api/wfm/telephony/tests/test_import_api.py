"""Importing call data end to end: HTTP upload, real PostgreSQL, hand-worked expected figures."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from django.db.models import F
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditChange, AuditEvent, Outcome
from wfm.telephony import reconciliation
from wfm.telephony.models import CallRecord, ImportBatch, IntervalActual, Queue
from wfm.telephony.workbook import read_call_records

from .workbooks import (
    CANARY_CALLER,
    CANARY_NAME,
    CANARY_PHONE,
    Call,
    scenario,
    upload,
    workbook_bytes,
)

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/telephony/imports"


def login(role: Role = Role.PLANNER) -> Client:
    user = User.objects.create_user(username=f"u-{role.value}", password="x", role=role)
    client = Client()
    client.force_login(user)
    return client


def post(client: Client, content: bytes, name: str = "report.xlsx") -> Any:
    return client.post(IMPORTS, {"file": upload(content, name)})


@pytest.fixture
def imported() -> tuple[Client, dict[str, Any]]:
    client = login()
    response = post(client, workbook_bytes(scenario()))
    assert response.status_code == 201, response.content
    return client, response.json()


class TestAHappyImport:
    def test_reports_what_it_read_and_stored(self, imported: tuple[Client, dict[str, Any]]) -> None:
        _, report = imported
        assert report["rowsRead"] == 12
        assert report["rowsInserted"] == 12
        assert report["rowsDuplicate"] == 0
        assert report["rowsRejected"] == 0
        assert report["fileName"] == "report.xlsx"
        assert report["sourceTimezone"] == "Africa/Johannesburg"

    def test_says_which_sheets_it_did_not_read(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        _, report = imported
        assert "Call IVR Details" in report["sheetsIgnored"]
        assert len(report["sheetsIgnored"]) == 6

    def test_creates_queues_unconfirmed_for_an_admin_to_confirm(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        assert set(Queue.objects.values_list("name", "confirmed")) == {
            ("QueueA", False),
            ("QueueB", False),
        }

    def test_builds_the_thirty_minute_intervals(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        def row(queue: str, hh: int, mm: int) -> tuple[int, ...]:
            slot = IntervalActual.objects.get(
                queue__name=queue,
                interval_start=datetime(2026, 5, 4, hh - 2, mm, tzinfo=UTC),  # SAST = UTC+2
            )
            return (
                slot.offered, slot.answered, slot.abandoned,
                slot.answered_in_sl, slot.sum_wait_s, slot.sum_handle_s,
            )  # fmt: skip

        assert row("QueueA", 8, 0) == (4, 3, 1, 3, 30, 510)
        assert row("QueueA", 8, 30) == (3, 2, 1, 0, 51, 220)
        assert row("QueueB", 8, 0) == (3, 3, 0, 2, 60, 500)
        # outbound and transfer legs at 09:00 and 09:05 produce no interval at all
        assert IntervalActual.objects.count() == 3

    def test_reconciles_three_independent_ways(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        _, report = imported
        assert report["reconciles"] is True
        recon = report["reconciliation"]
        assert recon["excluded"] == {"not_inbound": 2}
        assert recon["total"]["source"] == recon["total"]["stored"]
        assert recon["total"]["source"]["offered"] == 10
        assert recon["intervals"]["calls"] == recon["intervals"]["intervals"]

    def test_a_planner_can_list_imports(self, imported: tuple[Client, dict[str, Any]]) -> None:
        client, report = imported
        listing = client.get(IMPORTS).json()
        assert [b["id"] for b in listing] == [report["id"]]


class TestPrivacy:
    def test_phone_numbers_and_agent_names_are_never_stored(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        stored = [str(value) for call in CallRecord.objects.all() for value in vars(call).values()]
        everything = " ".join(stored)
        for canary in (CANARY_PHONE, CANARY_CALLER, CANARY_NAME):
            assert canary not in everything
        assert "Agent007" in everything  # the login is kept; the name is not

    def test_they_do_not_reach_the_import_report_or_the_audit_trail(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        _, report = imported
        audit_text = " ".join(
            f"{e.reason} {e.entity_id} {e.user_agent}" for e in AuditEvent.objects.all()
        ) + " ".join(f"{c.old_value} {c.new_value}" for c in AuditChange.objects.all())
        for canary in (CANARY_PHONE, CANARY_CALLER, CANARY_NAME):
            assert canary not in str(report)
            assert canary not in audit_text

    def test_call_level_rows_are_never_visible_to_any_role(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        for role in Role:
            user = User.objects.get_or_create(username=f"v-{role.value}", defaults={"role": role})[
                0
            ]
            assert CallRecord.objects.for_user(user).count() == 0


class TestRefusals:
    def refused(self, client: Client, content: bytes, status: int, code: str) -> dict[str, Any]:
        response = post(client, content)
        assert response.status_code == status, response.content
        body = response.json()
        assert body["code"] == code
        event = AuditEvent.objects.get(action=Action.CDR_IMPORT_REFUSED)
        assert (event.outcome, event.reason) == (Outcome.FAILED, code)
        return body  # type: ignore[no-any-return]

    def test_the_same_file_twice(self, imported: tuple[Client, dict[str, Any]]) -> None:
        client, _ = imported
        self.refused(client, workbook_bytes(scenario()), 409, "import.duplicate_file")
        assert ImportBatch.objects.count() == 1

    def test_a_month_exported_twice_is_caught_even_when_the_bytes_differ(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        # The June report really was May again. Another export of the same month has the same
        # dates and row count but different bytes (here, a different cell nobody reads).
        client, _ = imported
        again = workbook_bytes(scenario(), canary_phone="27820000000")
        self.refused(client, again, 409, "import.duplicate_period")
        assert CallRecord.objects.count() == 12

    def test_a_file_with_nothing_new(self, imported: tuple[Client, dict[str, Any]]) -> None:
        client, _ = imported
        subset = workbook_bytes(scenario()[:9])  # same calls, fewer rows, so a different period
        self.refused(client, subset, 409, "import.nothing_new")

    def test_not_a_workbook(self) -> None:
        self.refused(login(), b"this is not a spreadsheet", 422, "import.not_a_workbook")

    def test_the_wrong_sheet(self) -> None:
        wrong = workbook_bytes(scenario(), sheet="Something Else")
        self.refused(login(), wrong, 422, "import.sheet_missing")

    def test_missing_columns_are_named(self) -> None:
        headers = ["Call ID", "Call Type", "Queue"]
        body = self.refused(
            login(), workbook_bytes(scenario(), headers=headers), 422, "import.columns_missing"
        )
        assert {v["field"] for v in body["violations"]} == {"Call Status", "Start Time"}

    def test_no_header_row(self) -> None:
        wrong = workbook_bytes([], headers=["Alpha", "Beta"])
        self.refused(login(), wrong, 422, "import.header_missing")

    def test_a_header_with_no_rows(self) -> None:
        self.refused(login(), workbook_bytes([]), 422, "import.no_rows")

    def test_too_large(self, settings: Any) -> None:
        settings.WFM_CDR_MAX_UPLOAD_MB = 0
        response = post(login(), workbook_bytes(scenario()))
        assert response.status_code == 413
        assert response.json()["code"] == "import.too_large"

    def test_a_refusal_stores_nothing(self) -> None:
        post(login(), b"nope")
        assert (ImportBatch.objects.count(), CallRecord.objects.count()) == (0, 0)
        assert Queue.objects.count() == 0


class TestAuditOfASuccess:
    def test_one_event_says_who_what_and_how_much(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        _, report = imported
        event = AuditEvent.objects.get(action=Action.CDR_IMPORTED)
        assert event.outcome == Outcome.SUCCESS
        assert event.actor_role == Role.PLANNER
        assert event.entity_type == "import_batch"
        assert event.entity_id == report["id"]
        assert str(event.batch_id) == report["id"]
        changes = {c.field: c.new_value for c in AuditChange.objects.filter(event=event)}
        assert changes == {
            "rows_read": "12",
            "rows_inserted": "12",
            "rows_duplicate": "0",
            "rows_rejected": "0",
            "reconciles": "True",
        }


class TestMessyFiles:
    def test_a_row_that_is_not_a_call_is_rejected_by_reason_and_the_rest_import(self) -> None:
        broken = Call(99, "QueueA", "Agent", "2026-05-04 09:30:00", wait=3, talk=10)
        extra = [{**broken.cells(), "Call Type": ""}]
        report = post(login(), workbook_bytes(scenario(), extra_rows=extra)).json()
        assert (report["rowsRead"], report["rowsInserted"], report["rowsRejected"]) == (13, 12, 1)
        assert report["rejectedSummary"] == {"call_type.missing": 1}

    def test_an_unusable_optional_cell_keeps_the_call_and_is_reported(self) -> None:
        # The real May report has an abandoned inbound call with a wait of "-0:00:23". The deck
        # counts it as offered and abandoned, so dropping it would break the reconciliation.
        odd = Call(99, "QueueA", "Abandoned", "2026-05-04 09:30:00")
        extra = [{**odd.cells(), "Queue Wait Time": "-0:00:23"}]
        report = post(login(), workbook_bytes(scenario(), extra_rows=extra)).json()
        assert (report["rowsInserted"], report["rowsRejected"]) == (13, 0)
        assert report["warnings"] == {"queue_wait.negative": 1}
        assert "-0:00:23" not in str(report)
        assert CallRecord.objects.get(call_id=99).wait_s is None
        assert report["reconciliation"]["total"]["source"]["abandoned"] == 3  # 2 + this one

    def test_a_call_repeated_inside_the_file_counts_once(self) -> None:
        calls = scenario()
        response = post(login(), workbook_bytes([*calls, calls[0]]))
        report = response.json()
        assert report["rowsInserted"] == 12
        assert report["rowsDuplicate"] == 1
        assert report["reconciles"] is True


class TestImportingMoreData:
    def test_an_overlapping_file_adds_only_new_calls_and_rebuilds_shared_intervals(self) -> None:
        client = login()
        post(client, workbook_bytes(scenario()))
        later = [
            *scenario(),
            # lands in an interval that already has calls, and a day that does not
            Call(13, "QueueA", "Agent", "2026-05-04 08:08:00", wait=8, talk=50, wrap=5),
            Call(14, "QueueA", "Agent", "2026-05-05 10:00:00", wait=4, talk=70, wrap=0),
        ]
        report = post(client, workbook_bytes(later)).json()
        assert (report["rowsInserted"], report["rowsDuplicate"]) == (2, 12)
        assert report["reconciles"] is True

        shared = IntervalActual.objects.get(
            queue__name="QueueA", interval_start=datetime(2026, 5, 4, 6, 0, tzinfo=UTC)
        )
        assert (shared.offered, shared.answered, shared.sum_wait_s) == (5, 4, 38)
        assert CallRecord.objects.count() == 14

    def test_the_source_time_zone_is_configurable(self, settings: Any) -> None:
        settings.WFM_CDR_SOURCE_TIMEZONE = "UTC"
        post(login(), workbook_bytes(scenario()))
        first = CallRecord.objects.get(call_id=8)  # starts 08:02 in the file
        assert first.start_at == datetime(2026, 5, 4, 8, 2, tzinfo=UTC)


class TestReconciliationCanFail:
    def test_it_notices_when_the_intervals_disagree_with_the_calls(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        # A reconciliation that cannot fail proves nothing. Corrupt one interval and check.
        IntervalActual.objects.filter(queue__name="QueueB").update(offered=F("offered") + 1)
        batch = ImportBatch.objects.get()
        fresh = [row for _, row in read_call_records(workbook_bytes(scenario())).rows]
        first = datetime(2026, 5, 4, 6, 0, tzinfo=UTC)
        result = reconciliation.reconcile(
            batch, fresh, first, datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
        )
        assert result["matches"] is False

    def test_it_notices_when_the_stored_calls_disagree_with_the_file(
        self, imported: tuple[Client, dict[str, Any]]
    ) -> None:
        CallRecord.objects.filter(call_id=1).update(status="Abandoned")
        batch = ImportBatch.objects.get()
        fresh = [row for _, row in read_call_records(workbook_bytes(scenario())).rows]
        first = datetime(2026, 5, 4, 6, 0, tzinfo=UTC)
        result = reconciliation.reconcile(
            batch, fresh, first, datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
        )
        assert result["matches"] is False
        assert result["queues"]["QueueA"]["matches"] is False
