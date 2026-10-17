"""The detail sheets keep logins, labels, durations and incident numbers, and nothing else."""

from __future__ import annotations

from datetime import datetime

import pytest

from wfm_engine.cdr import CallRowError
from wfm_engine.cdr_details import (
    incident_ref,
    parse_disposition,
    parse_ivr,
    parse_offer,
    parse_pause,
    parse_transfer,
    safe_label,
)


def test_a_remark_gives_only_its_incident_number() -> None:
    assert incident_ref("rang Jane on 0829990001 re inc000064329272 thanks") == "INC000064329272"
    assert incident_ref("no ticket here, call 0829990001") == ""
    assert incident_ref(None) == ""


def test_a_label_that_looks_like_text_or_a_number_is_not_kept() -> None:
    assert safe_label("Resolved") == "Resolved"
    assert safe_label("  ") == ""
    assert safe_label("0829990001") == "other"
    assert safe_label("Called Jane Doe back, she said: ok!") == "other"


def test_disposition_row() -> None:
    row = parse_disposition(
        {
            "Call ID": 7,
            "Disposition": "Resolved",
            "Disposition Remark": "x INC000064329272",
            "Disposition Duration": "00:00:42",
        }
    )
    assert (row.disposition, row.incident_ref, row.after_call_s) == (
        "Resolved",
        "INC000064329272",
        42,
    )


def test_ivr_keeps_a_menu_key_but_not_typed_digits() -> None:
    assert parse_ivr({"Call ID": 1, "IVR Digit": "3"}).digit == "3"
    assert parse_ivr({"Call ID": 1, "IVR Digit": "0829990001"}).digit == ""


def test_offer_uses_the_login_and_measures_the_ring() -> None:
    row = parse_offer(
        {
            "Call ID": 1,
            "Agent Name": "Jane Doe (Agent012)",
            "Call Offered Date": "2026-05-04",
            "Call Offered Time": "23:59:58",
            "Call Hangup Time": "00:00:03",
        }
    )
    assert row.agent_login == "Agent012"
    assert row.offered_at == datetime(2026, 5, 4, 23, 59, 58)
    assert row.ring_s == 5


def test_offer_without_a_login_is_refused_by_code() -> None:
    with pytest.raises(CallRowError) as error:
        parse_offer({"Call ID": 1, "Agent Name": "Jane Doe", "Call Offered Time": "x"})
    assert error.value.code == "agent.missing"


def test_transfer_and_pause_durations() -> None:
    transfer = parse_transfer(
        {
            "Call ID": 1,
            "Transfer Call ID": 2,
            "Transfer By": "Jane Doe (Agent012)",
            "Transfer Call Start Time": "2026-05-04 08:00:00",
            "Transfer Call Answer Time": "2026-05-04 08:00:05",
            "Transfer Call Hangup Time": "2026-05-04 08:01:05",
        }
    )
    assert (transfer.by_login, transfer.answer_s, transfer.duration_s) == ("Agent012", 5, 60)
    pause = parse_pause(
        {
            "Call ID": 1,
            "Type": "Hold",
            "Start Time": "2026-05-04 08:00:00",
            "End Time": "2026-05-04 08:00:30",
        }
    )
    assert pause.duration_s == 30
