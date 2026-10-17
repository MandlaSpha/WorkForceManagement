"""Parsing one row of the ACD Call Detail Report (tech spec section 5).

Pure functions: no Django, no clock, no I/O. Timestamps come back naive, exactly as the ACD wrote
them; the caller says which time zone that is (an open question for the ACD vendor).

Data minimisation (POPIA): this module deliberately has no field for the caller's phone number,
the access number or the agent's name. WFM does not need them, so they are never read.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

INBOUND = "INBOUND"
STATUS_ANSWERED = "Agent"
STATUS_ABANDONED = "Abandoned"

# The ACD writes this for "no value" in a timestamp column (for example Agent Time on an
# abandoned call).
_ZERO_TIMESTAMP = "0000-00-00 00:00:00"
_AGENT_NUMBER = re.compile(r"\((Agent\d+)\)")
_DURATION = re.compile(r"^(\d{1,3}):([0-5]\d):([0-5]\d)$")


class CallRowError(ValueError):
    """A row could not be read. `code` is a stable machine-readable reason. The message never
    contains a cell value, because cells can hold personal data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class CallRow:
    call_id: int
    call_type: str
    queue: str
    status: str
    agent_login: str | None
    start_at: datetime
    queue_at: datetime | None
    agent_at: datetime | None
    hangup_at: datetime | None
    call_duration_s: int | None
    wait_s: int | None
    talk_s: int | None
    wrap_s: int | None
    hold_s: int | None
    hangup_by: str
    # Optional cells that could not be read were cleared instead of rejecting the whole call.
    # Codes only (for example "queue_wait.negative"), never the cell value.
    warnings: tuple[str, ...] = ()


def parse_duration_s(value: object) -> int | None:
    """`HH:MM:SS` or `H:MM:SS` to seconds. Blank is None; anything else unreadable raises."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if not isinstance(value, str):
        raise CallRowError("duration.unreadable")
    match = _DURATION.match(value.strip())
    if match is None:
        raise CallRowError("duration.unreadable")
    hours, minutes, seconds = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def parse_timestamp(value: object) -> datetime | None:
    """`YYYY-MM-DD HH:MM:SS` (or a real datetime) to a naive datetime. Blank and the ACD's
    all-zero date are None; anything else unreadable raises."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, microsecond=0)
    if not isinstance(value, str):
        raise CallRowError("timestamp.unreadable")
    text = value.strip()
    if not text or text == _ZERO_TIMESTAMP:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise CallRowError("timestamp.unreadable") from None


def agent_login(value: object) -> str | None:
    """`Name (Agent124)` gives `Agent124`; a bare login stays as it is; blank is None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    match = _AGENT_NUMBER.search(text)
    return match.group(1) if match else text


def parse_call_id(raw_id: object) -> int:
    """A positive whole-number call ID, or `CallRowError` (`call_id.missing` / `.unreadable`)."""
    if isinstance(raw_id, bool) or raw_id is None:
        raise CallRowError("call_id.missing")
    try:
        call_id = int(str(raw_id).strip())
    except ValueError:
        raise CallRowError("call_id.unreadable") from None
    if call_id <= 0:
        raise CallRowError("call_id.unreadable")
    return call_id


def _soft[T](
    read: Callable[[object], T | None],
    row: Mapping[str, object],
    key: str,
    name: str,
    warnings: list[str],
) -> T | None:
    """Read an OPTIONAL cell. If it is unusable, clear it and say so, because the call itself is
    real and still counts (the real May report has an abandoned call with a wait of "-0:00:23")."""
    value = row.get(key)
    try:
        return read(value)
    except CallRowError:
        negative = isinstance(value, str) and value.strip().startswith("-")
        warnings.append(f"{name}.{'negative' if negative else 'unreadable'}")
        return None


def _text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    return str(value).strip() if value is not None else ""


def parse_call_row(row: Mapping[str, object]) -> CallRow:
    """Turn one spreadsheet row (header name to cell) into a `CallRow`, or raise `CallRowError`."""
    call_id = parse_call_id(row.get("Call ID"))

    call_type = _text(row, "Call Type").upper()
    if not call_type:
        raise CallRowError("call_type.missing")
    queue = _text(row, "Queue")
    if not queue:
        raise CallRowError("queue.missing")
    status = _text(row, "Call Status")
    if not status:
        raise CallRowError("status.missing")
    start_at = parse_timestamp(row.get("Start Time"))
    if start_at is None:
        raise CallRowError("start_time.missing")

    warnings: list[str] = []
    return CallRow(
        call_id=call_id,
        call_type=call_type,
        queue=queue,
        status=status,
        agent_login=agent_login(row.get("Agent")),
        start_at=start_at,
        queue_at=_soft(parse_timestamp, row, "Queue Time", "queue_time", warnings),
        agent_at=_soft(parse_timestamp, row, "Agent Time", "agent_time", warnings),
        hangup_at=_soft(parse_timestamp, row, "Hangup Time", "hangup_time", warnings),
        call_duration_s=_soft(parse_duration_s, row, "Call Duration", "call_duration", warnings),
        wait_s=_soft(parse_duration_s, row, "Queue Wait Time", "queue_wait", warnings),
        talk_s=_soft(parse_duration_s, row, "Agent Duration", "agent_duration", warnings),
        wrap_s=_soft(parse_duration_s, row, "Disposition Duration", "disposition", warnings),
        hold_s=_soft(parse_duration_s, row, "Total Hold Duration", "hold", warnings),
        hangup_by=_text(row, "Hangup By").upper(),
        warnings=tuple(warnings),
    )
