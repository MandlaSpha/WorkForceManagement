"""The six detail sheets of the Call Detail Report (DAT-01): what is stored, what is reported, and
the proof that no personal data comes with them."""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

import openpyxl
import pytest
from django.db import connection
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import AuditChange, AuditEvent
from wfm.telephony.models import (
    AgentOffer,
    CallDisposition,
    CallIvrStep,
    CallPause,
    CallRecord,
    CallTransfer,
    ImportBatch,
)
from wfm.telephony.workbook import read_call_records

from .workbooks import (
    CANARY_CALLER,
    CANARY_DIGITS,
    CANARY_NAME,
    CANARY_OTHER_AGENT,
    CANARY_PHONE,
    CANARY_REMARK,
    EXTRA_SHEETS,
    INCIDENT,
    ORPHAN_CALL_ID,
    scenario,
    upload,
    workbook_bytes,
)

pytestmark = pytest.mark.django_db

IMPORTS = "/api/v1/telephony/imports"
CANARIES = (
    CANARY_PHONE,
    CANARY_CALLER,
    CANARY_NAME,
    CANARY_REMARK,
    CANARY_DIGITS,
    "Canary",
    "Ghost",
    "Agent099",  # a call that is not in the batch is not stored at all
)


def import_it(content: bytes) -> dict[str, Any]:
    user = User.objects.create_user(username="planner-d", password="x", role=Role.PLANNER)
    client = Client()
    client.force_login(user)
    response = client.post(IMPORTS, {"file": upload(content)})
    assert response.status_code == 201, response.content
    body: dict[str, Any] = response.json()
    return body


def sheet(report: dict[str, Any], name: str) -> dict[str, Any]:
    return next(s for s in report["sheets"] if s["sheet"] == name)


def test_the_report_says_per_sheet_what_was_read_kept_and_warned() -> None:
    report = import_it(workbook_bytes(scenario()))
    assert [s["sheet"] for s in report["sheets"]] == ["Call Record Report", *EXTRA_SHEETS]
    primary = sheet(report, "Call Record Report")
    assert (primary["rowsRead"], primary["rowsKept"], primary["warnings"]) == (12, 12, {})
    disposition = sheet(report, "Call Disposition Details")
    # 8 answered inbound calls plus one orphan row
    assert disposition["read"] is True
    assert disposition["rowsRead"] == 9
    assert disposition["rowsKept"] == 8
    assert disposition["warnings"] == {"row.call_not_in_batch": 1}
    assert sheet(report, "Agent Offered Call")["rowsKept"] == 9  # 8 answered + 1 ring-no-answer


def test_disposition_keeps_the_label_the_incident_number_and_after_call_time_only() -> None:
    import_it(workbook_bytes(scenario()))
    first = CallDisposition.objects.get(call__call_id=1)
    assert (first.disposition, first.incident_ref, first.after_call_s) == ("Resolved", INCIDENT, 20)
    other = CallDisposition.objects.get(call__call_id=2)
    assert other.incident_ref == ""
    assert other.after_call_s == 30


def test_ivr_keeps_the_menu_path_but_never_typed_digits() -> None:
    import_it(workbook_bytes(scenario()))
    steps = list(CallIvrStep.objects.filter(call__call_id=1).order_by("step"))
    assert [(s.step, s.digit, s.activity, s.action, s.offset_s) for s in steps] == [
        (1, "1", "Main Menu", "Selected", 1),
        (2, "", "Account Entry", "Typed", 2),
    ]


def test_offers_are_by_login_and_only_the_agent_who_took_the_call_answered() -> None:
    import_it(workbook_bytes(scenario()))
    offers = AgentOffer.objects.filter(call__call_id=1).order_by("agent_login")
    assert [(o.agent_login, o.answered, o.ring_s) for o in offers] == [
        ("Agent007", True, 7),
        ("Agent008", False, 4),
    ]


def test_transfers_mutes_and_holds_are_counted_with_durations() -> None:
    import_it(workbook_bytes(scenario()))
    transfer = CallTransfer.objects.get()
    assert (transfer.call.call_id, transfer.by_login, transfer.answer_s) == (12, "Agent007", 6)
    assert transfer.duration_s == 120
    mute = CallPause.objects.get(kind="mute")
    hold = CallPause.objects.get(kind="hold")
    assert (mute.call.call_id, mute.duration_s) == (1, 15)
    assert (hold.call.call_id, hold.duration_s) == (2, 60)


def test_a_missing_optional_sheet_is_a_warning_not_an_error() -> None:
    report = import_it(workbook_bytes(scenario(), skip_sheets=("Call IVR Details",)))
    ivr = sheet(report, "Call IVR Details")
    assert (ivr["read"], ivr["rowsKept"], ivr["warnings"]) == (False, 0, {"sheet.missing": 1})
    assert report["sheetsIgnored"] == ["Call IVR Details"]
    assert CallIvrStep.objects.count() == 0
    assert CallRecord.objects.count() == 12


def test_a_workbook_with_only_the_call_sheet_still_imports() -> None:
    report = import_it(workbook_bytes(scenario(), other_sheets=False))
    assert len(report["sheetsIgnored"]) == 6
    assert report["reconciles"] is True


def test_a_detail_sheet_without_its_columns_is_a_warning() -> None:
    content = workbook_bytes(scenario())
    book = openpyxl.load_workbook(BytesIO(content))
    book["Agent Offered Call"].delete_cols(2)  # the agent column
    out = BytesIO()
    book.save(out)
    report = read_call_records(out.getvalue()).sheet_reports["Agent Offered Call"]
    assert report.read is False
    assert dict(report.warnings) == {"sheet.columns_missing": 1}


def test_an_unreadable_detail_row_is_counted_not_stored_and_never_echoed() -> None:
    from .workbooks import detail_sheets

    rows = detail_sheets(scenario())
    rows["Call Hold Details"].append(["not-a-number", "Customer hold", None, None, "00:00:09"])
    report = import_it(workbook_bytes(scenario(), detail_rows=rows))
    hold = sheet(report, "Call Hold Details")
    assert hold["warnings"] == {"row.call_id.unreadable": 1, "row.call_not_in_batch": 1}
    assert "not-a-number" not in str(report)


def test_a_row_for_a_call_that_is_not_in_the_batch_is_not_stored() -> None:
    import_it(workbook_bytes(scenario()))
    assert not CallRecord.objects.filter(call_id=ORPHAN_CALL_ID).exists()
    assert AgentOffer.objects.filter(agent_login="Agent099").count() == 0
    assert CallPause.objects.count() == 2


class TestNoPersonalDataIsKept:
    def test_canaries_reach_no_table_report_audit_trail_or_log(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.DEBUG):
            report = import_it(workbook_bytes(scenario()))
        stored: list[str] = []
        for model in (
            CallRecord,
            CallDisposition,
            CallIvrStep,
            AgentOffer,
            CallTransfer,
            CallPause,
            ImportBatch,
        ):
            stored += [str(v) for row in model.objects.all() for v in vars(row).values()]
        audit_text = " ".join(
            f"{e.reason} {e.entity_id}" for e in AuditEvent.objects.all()
        ) + " ".join(f"{c.old_value} {c.new_value}" for c in AuditChange.objects.all())
        haystack = " ".join([*stored, str(report), audit_text, caplog.text])
        for canary in (*CANARIES, CANARY_OTHER_AGENT):
            assert canary not in haystack
        assert INCIDENT in haystack  # the incident number is the one thing kept from a remark
        assert "Agent008" in haystack  # logins are kept

    def test_the_detail_tables_have_no_name_phone_or_remark_column(self) -> None:
        with connection.cursor() as cursor:
            for table in (
                "telephony_calldisposition",
                "telephony_callivrstep",
                "telephony_agentoffer",
                "telephony_calltransfer",
                "telephony_callpause",
            ):
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
                    [table],
                )
                names = {row[0] for row in cursor.fetchall()}
                assert names
                assert not {n for n in names if "name" in n or "phone" in n or "remark" in n}

    def test_nothing_serves_detail_rows_to_any_role(self) -> None:
        for role in Role:
            user = User.objects.get_or_create(username=f"d-{role.value}", defaults={"role": role})[
                0
            ]
            for model in (CallDisposition, CallIvrStep, AgentOffer, CallTransfer, CallPause):
                assert model.objects.for_user(user).count() == 0
