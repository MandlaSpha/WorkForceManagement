"""Reading a work-item CSV (an export from an ITSM tool).

Required columns: ref, pool, opened. Optional: priority, due, effort_minutes, closed, and the
survey answers fcr (yes/no: resolved at first contact), csat (1 to 5) and nps (0 to 10), which
KPI-01 reports. Any other
column is ignored and never stored, so a personal column (requester, assignee, email...) cannot
reach the database by being in the file. Times are ISO 8601; one with no zone is South African
time. A row that cannot be read is counted and the reason is kept, never its content.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

REQUIRED = ("ref", "pool", "opened")
OPTIONAL = ("priority", "due", "effort_minutes", "closed", "fcr", "csat", "nps")
KNOWN = (*REQUIRED, *OPTIONAL)
MAX_ROWS = 50_000


@dataclass(frozen=True, slots=True)
class Row:
    ref: str
    pool: str
    priority: str
    opened_at: datetime
    due_at: datetime | None
    effort_minutes: int | None
    closed_at: datetime | None
    first_contact_resolved: bool | None = None
    csat: int | None = None
    nps: int | None = None


@dataclass(slots=True)
class Parsed:
    rows: list[Row] = field(default_factory=list)
    rejected: dict[str, int] = field(default_factory=dict)
    ignored_columns: list[str] = field(default_factory=list)

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1


class UnreadableFileError(ValueError):
    """The file cannot be a work-item export at all (not text, no header, a column missing)."""


def parse(content: bytes, zone: ZoneInfo) -> Parsed:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UnreadableFileError("The file is not UTF-8 text.") from error
    reader = csv.DictReader(io.StringIO(text))
    names = [(n or "").strip().lower() for n in (reader.fieldnames or [])]
    if not names:
        raise UnreadableFileError("The file has no header row.")
    missing = [c for c in REQUIRED if c not in names]
    if missing:
        raise UnreadableFileError(f"The header is missing: {', '.join(missing)}.")

    parsed = Parsed(ignored_columns=[n for n in names if n and n not in KNOWN])
    seen: set[str] = set()
    for count, raw in enumerate(reader, start=1):
        if count > MAX_ROWS:
            raise UnreadableFileError(f"More than {MAX_ROWS} rows; split the file.")
        record = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        row = _row(record, zone, parsed)
        if row is None:
            continue
        if row.ref in seen:
            parsed.reject("repeated_ref")  # the first occurrence wins, like the call importer
            continue
        seen.add(row.ref)
        parsed.rows.append(row)
    return parsed


def _row(record: dict[str, str], zone: ZoneInfo, parsed: Parsed) -> Row | None:
    ref, pool = record.get("ref", ""), record.get("pool", "")
    if not ref or len(ref) > 40:
        parsed.reject("bad_ref")
        return None
    if not pool or len(pool) > 100:
        parsed.reject("bad_pool")
        return None
    opened = _moment(record.get("opened", ""), zone)
    if opened is None:
        parsed.reject("bad_opened")
        return None
    try:
        due = _optional_moment(record.get("due", ""), zone)
        closed = _optional_moment(record.get("closed", ""), zone)
    except ValueError:
        parsed.reject("bad_date")
        return None
    effort = record.get("effort_minutes", "")
    minutes: int | None = None
    if effort:
        if not effort.isdigit() or int(effort) > 100_000:
            parsed.reject("bad_effort")
            return None
        minutes = int(effort)
    if closed is not None and closed < opened:
        parsed.reject("closed_before_opened")
        return None
    try:
        fcr = _flag(record.get("fcr", ""))
        csat = _score(record.get("csat", ""), 1, 5)
        nps = _score(record.get("nps", ""), 0, 10)
    except ValueError as bad:
        parsed.reject(f"bad_{bad}")
        return None
    return Row(
        ref=ref,
        pool=pool,
        priority=record.get("priority", "")[:10],
        opened_at=opened,
        due_at=due,
        effort_minutes=minutes,
        closed_at=closed,
        first_contact_resolved=fcr,
        csat=csat,
        nps=nps,
    )


def _flag(value: str) -> bool | None:
    """True or False for a yes/no answer, None for a blank; ValueError("fcr") for anything else."""
    text = value.strip().lower()
    if not text:
        return None
    if text in ("yes", "y", "true", "1"):
        return True
    if text in ("no", "n", "false", "0"):
        return False
    raise ValueError("fcr")


def _score(value: str, low: int, high: int) -> int | None:
    """The whole number in range, None for a blank; ValueError("csat" or "nps") is raised by the
    caller's name for it, so the reason code says which column was wrong."""
    if not value:
        return None
    if not value.isdigit() or not low <= int(value) <= high:
        raise ValueError("csat" if high == 5 else "nps")
    return int(value)


def _moment(value: str, zone: ZoneInfo) -> datetime | None:
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=zone)


def _optional_moment(value: str, zone: ZoneInfo) -> datetime | None:
    """None for a blank; the moment for a good value; ValueError for one that cannot be read."""
    if not value:
        return None
    moment = _moment(value, zone)
    if moment is None:
        raise ValueError(value)
    return moment
