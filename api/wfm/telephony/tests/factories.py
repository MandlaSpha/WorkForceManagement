"""Synthetic call records and detail rows made directly, for tests that are not about importing."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

from wfm.accounts.models import Role, User
from wfm.telephony.models import (
    AgentOffer,
    CallDisposition,
    CallIvrStep,
    CallPause,
    CallRecord,
    CallTransfer,
    ImportBatch,
    Queue,
)

ZONE = ZoneInfo(settings.TIME_ZONE)
ALL_SHEETS = (
    "Call Record Report",
    "Call Disposition Details",
    "Call IVR Details",
    "Agent Offered Call",
    "Transfer Call Details",
    "Call Mute Details",
    "Call Hold Details",
)
_next_id = [1000]


def batch() -> ImportBatch:
    existing = ImportBatch.objects.first()
    if existing:
        return existing
    user = User.objects.get_or_create(username="u-importer", defaults={"role": Role.ADMIN})[0]
    return ImportBatch.objects.create(
        file_name="synthetic.xlsx",
        sha256="0" * 64,
        uploaded_by=user,
        source_timezone="Africa/Johannesburg",
        period_start=datetime(2031, 3, 1, tzinfo=ZONE),
        period_end=datetime(2031, 3, 31, tzinfo=ZONE),
        rows_read=0,
        rows_inserted=0,
        rows_duplicate=0,
        rows_rejected=0,
        sheets_report=[
            {"sheet": name, "read": True, "rows_read": 0, "rows_kept": 0, "warnings": {}}
            for name in ALL_SHEETS
        ],
    )


def only_sheets(*names: str) -> None:
    """Make the import hold just these sheets (the others were not in the file)."""
    b = batch()
    b.sheets_report = [
        {"sheet": n, "read": True, "rows_read": 0, "rows_kept": 0, "warnings": {}} for n in names
    ]
    b.save(update_fields=["sheets_report"])


def call(
    queue: Queue,
    *,
    day: int = 3,
    hour: int = 9,
    agent: str = "",
    status: str = "Agent",
    hold_s: int | None = None,
) -> CallRecord:
    _next_id[0] += 1
    return CallRecord.objects.create(
        call_id=_next_id[0],
        batch=batch(),
        queue=queue,
        call_type="INBOUND",
        status=status,
        agent_login=agent,
        start_at=datetime(2031, 3, day, hour, 0, tzinfo=ZONE),
        hold_s=hold_s,
    )


def offer(c: CallRecord, login: str, *, answered: bool, ring_s: int | None = 10) -> AgentOffer:
    return AgentOffer.objects.create(
        call=c, agent_login=login, offered_at=c.start_at, ring_s=ring_s, answered=answered
    )


def transfer(c: CallRecord, by: str, *, answer_s: int = 5, duration_s: int = 60) -> CallTransfer:
    return CallTransfer.objects.create(
        call=c, transfer_call_id=None, by_login=by, answer_s=answer_s, duration_s=duration_s
    )


def pause(c: CallRecord, kind: str, duration_s: int) -> CallPause:
    return CallPause.objects.create(call=c, kind=kind, label="Hold", duration_s=duration_s)


def disposition(c: CallRecord, incident: str = "", label: str = "Resolved") -> CallDisposition:
    return CallDisposition.objects.create(
        call=c, disposition=label, incident_ref=incident, after_call_s=30
    )


def ivr(c: CallRecord, step: int, digit: str, activity: str, offset_s: int = 5) -> CallIvrStep:
    return CallIvrStep.objects.create(
        call=c, step=step, digit=digit, activity=activity, action="Menu", offset_s=offset_s
    )
