"""Parsing the six secondary sheets of the ACD Call Detail Report (DAT-01, tech spec section 4.29).

Pure functions: no Django, no clock, no I/O. Every parser keeps ONLY what workforce planning needs
and has no field for anything else (POPIA):
- the agent is the login (`Agent124`) from `Name (Agent124)`, never the display name;
- free text (disposition remarks, hangup reasons) is never kept; a remark yields at most the ITSM
  incident number inside it (`INC000064329272`);
- labels (disposition, IVR menu, hold type) are kept only when they look like a system label, so
  a typed-in number or a sentence cannot be stored as one;
- caller digits typed in the IVR are never kept (only a single menu key).
Errors carry a stable code and never a cell value.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .cdr import (
    CallRowError,
    agent_login,
    parse_call_id,
    parse_duration_s,
    parse_timestamp,
)

SHEET_DISPOSITION = "Call Disposition Details"
SHEET_IVR = "Call IVR Details"
SHEET_OFFERED = "Agent Offered Call"
SHEET_TRANSFER = "Transfer Call Details"
SHEET_MUTE = "Call Mute Details"
SHEET_HOLD = "Call Hold Details"

_INCIDENT = re.compile(r"\bINC\d{9,15}\b", re.IGNORECASE)
_LABEL = re.compile(r"^[A-Za-z][A-Za-z0-9 _\-/.&]{0,59}$")
_LONG_DIGITS = re.compile(r"\d{6,}")
_MENU_KEY = re.compile(r"^[0-9*#]$")
OTHER_LABEL = "other"


@dataclass(frozen=True, slots=True)
class DispositionRow:
    call_id: int
    disposition: str
    incident_ref: str
    after_call_s: int | None


@dataclass(frozen=True, slots=True)
class IvrRow:
    call_id: int
    digit: str
    activity: str
    action: str
    at: datetime | None


@dataclass(frozen=True, slots=True)
class OfferRow:
    call_id: int
    agent_login: str
    offered_at: datetime
    ring_s: int | None


@dataclass(frozen=True, slots=True)
class TransferRow:
    call_id: int
    transfer_call_id: int | None
    by_login: str
    answer_s: int | None
    duration_s: int | None


@dataclass(frozen=True, slots=True)
class PauseRow:
    call_id: int
    kind: str
    duration_s: int | None


def safe_label(value: object) -> str:
    """A system label (a disposition name, an IVR menu) or "" when blank. Anything that does not
    look like a label (a sentence with digits, a phone number) becomes "other"."""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    if not text:
        return ""
    if _LABEL.match(text) and not _LONG_DIGITS.search(text):
        return text
    return OTHER_LABEL


def incident_ref(value: object) -> str:
    """The first ITSM incident number in a free-text remark, upper-cased, or ""."""
    if value is None:
        return ""
    found = _INCIDENT.search(str(value))
    return found.group(0).upper() if found else ""


def _login(value: object) -> str:
    """Login from `Name (AgentNNN)`. A cell with no recognisable login gives "" (a display name
    on its own is never kept)."""
    if not isinstance(value, str):
        return ""
    found = re.search(r"\((Agent\d+)\)", value)
    if found:
        return found.group(1)
    bare = agent_login(value)
    return bare if bare and re.fullmatch(r"Agent\d+", bare) else ""


def _soft_duration(value: object) -> int | None:
    try:
        return parse_duration_s(value)
    except CallRowError:
        return None


def _soft_timestamp(value: object) -> datetime | None:
    try:
        return parse_timestamp(value)
    except CallRowError:
        return None


def parse_disposition(row: Mapping[str, object]) -> DispositionRow:
    return DispositionRow(
        call_id=parse_call_id(row.get("Call ID")),
        disposition=safe_label(row.get("Disposition")),
        incident_ref=incident_ref(row.get("Disposition Remark")),
        after_call_s=_soft_duration(row.get("Disposition Duration")),
    )


def parse_ivr(row: Mapping[str, object]) -> IvrRow:
    digit = str(row.get("IVR Digit") or "").strip()
    return IvrRow(
        call_id=parse_call_id(row.get("Call ID")),
        digit=digit if _MENU_KEY.match(digit) else "",
        activity=safe_label(row.get("IVR Call Activity")),
        action=safe_label(row.get("Action")),
        at=_soft_timestamp(row.get("IVR Time")),
    )


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _as_time(value: object) -> time | None:
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%H:%M:%S").time()
        except ValueError:
            return None
    return None


def parse_offer(row: Mapping[str, object]) -> OfferRow:
    call_id = parse_call_id(row.get("Call ID"))
    login = _login(row.get("Agent Name"))
    if not login:
        raise CallRowError("agent.missing")
    time_cell = row.get("Call Offered Time")
    offered = _soft_timestamp(time_cell)
    if offered is None:
        day, clock = _as_date(row.get("Call Offered Date")), _as_time(time_cell)
        if day is None or clock is None:
            raise CallRowError("offered_time.unreadable")
        offered = datetime.combine(day, clock)
    hangup_cell = row.get("Call Hangup Time")
    hangup = _soft_timestamp(hangup_cell)
    if hangup is None:
        clock = _as_time(hangup_cell)
        if clock is not None:
            hangup = datetime.combine(offered.date(), clock)
            if hangup < offered:
                hangup += timedelta(days=1)
    ring = int((hangup - offered).total_seconds()) if hangup is not None else None
    if ring is not None and ring < 0:
        ring = None
    return OfferRow(call_id=call_id, agent_login=login, offered_at=offered, ring_s=ring)


def parse_transfer(row: Mapping[str, object]) -> TransferRow:
    call_id = parse_call_id(row.get("Call ID"))
    try:
        leg = parse_call_id(row.get("Transfer Call ID"))
    except CallRowError:
        leg = None
    start = _soft_timestamp(row.get("Transfer Call Start Time"))
    answer = _soft_timestamp(row.get("Transfer Call Answer Time"))
    hangup = _soft_timestamp(row.get("Transfer Call Hangup Time"))

    def between(a: datetime | None, b: datetime | None) -> int | None:
        if a is None or b is None or b < a:
            return None
        return int((b - a).total_seconds())

    return TransferRow(
        call_id=call_id,
        transfer_call_id=leg,
        by_login=_login(row.get("Transfer By")),
        answer_s=between(start, answer),
        duration_s=between(answer or start, hangup),
    )


def parse_pause(row: Mapping[str, object]) -> PauseRow:
    """A mute or a hold: its type label and how long it lasted."""
    duration = _soft_duration(row.get("Duration"))
    if duration is None:
        start, end = _soft_timestamp(row.get("Start Time")), _soft_timestamp(row.get("End Time"))
        if start is not None and end is not None and end >= start:
            duration = int((end - start).total_seconds())
    return PauseRow(
        call_id=parse_call_id(row.get("Call ID")),
        kind=safe_label(row.get("Type")),
        duration_s=duration,
    )


@dataclass(frozen=True, slots=True)
class SheetSpec:
    required: tuple[str, ...]
    columns: tuple[str, ...]  # every column the parser may read; nothing else leaves the sheet
    parse: Callable[[Mapping[str, object]], object]


SECONDARY_SHEETS: dict[str, SheetSpec] = {
    SHEET_DISPOSITION: SheetSpec(
        ("Call ID",),
        ("Call ID", "Disposition", "Disposition Remark", "Disposition Duration"),
        parse_disposition,
    ),
    SHEET_IVR: SheetSpec(
        ("Call ID",),
        ("Call ID", "IVR Digit", "IVR Call Activity", "Action", "IVR Time"),
        parse_ivr,
    ),
    SHEET_OFFERED: SheetSpec(
        ("Call ID", "Agent Name"),
        ("Call ID", "Agent Name", "Call Offered Date", "Call Offered Time", "Call Hangup Time"),
        parse_offer,
    ),
    SHEET_TRANSFER: SheetSpec(
        ("Call ID",),
        (
            "Call ID",
            "Transfer Call ID",
            "Transfer By",
            "Transfer Call Start Time",
            "Transfer Call Answer Time",
            "Transfer Call Hangup Time",
        ),
        parse_transfer,
    ),
    SHEET_MUTE: SheetSpec(
        ("Call ID",), ("Call ID", "Type", "Start Time", "End Time", "Duration"), parse_pause
    ),
    SHEET_HOLD: SheetSpec(
        ("Call ID",), ("Call ID", "Type", "Start Time", "End Time", "Duration"), parse_pause
    ),
}
