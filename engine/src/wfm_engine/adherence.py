"""Schedule adherence for one person-day (requirement ATT-01, RTA-01).

Pure: no Django, no clock, no I/O. The caller gives the time a person was SCHEDULED to be on the
phones (the shift less its breaks and activities) and the agent-state intervals the ACD recorded,
all as datetimes of one kind (all naive local, or all aware); this module only does the sums.

What counts as working. A person is adhering while they are in a state where they are doing the
queue's work: `available` (ready for a call), `on_call` and `wrap_up` (after-call work). Everything
else, `break`, `lunch`, `training`, `meeting`, `away` and `logged_out`, is not the work the
schedule asked for in that moment. Adherence % is the scheduled minutes spent in a working state
over the scheduled minutes. Time worked outside the schedule neither helps nor hurts it.

The real ACD feed format is not known yet. `parse_state_csv` reads a SYNTHETIC format defined in
the tech spec (login, state, from, to); it is to be confirmed with the ACD vendor.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

STATES = (
    "available",
    "on_call",
    "wrap_up",
    "break",
    "lunch",
    "training",
    "meeting",
    "away",
    "logged_out",
)
WORKING_STATES = frozenset({"available", "on_call", "wrap_up"})
GRACE_MIN = 5  # a late start or early finish within this is not an exception
MAX_INTERVAL_HOURS = 24
MAX_ERRORS_KEPT = 50

Span = tuple[datetime, datetime]
StateSpan = tuple[str, datetime, datetime]


@dataclass(frozen=True, slots=True)
class Adherence:
    scheduled_min: int
    in_adherence_min: int
    out_of_adherence_min: int
    adherence_pct: float | None  # None when nothing was scheduled
    late_start_min: int  # first scheduled minute to the first working minute inside the schedule
    early_finish_min: int  # last working minute inside the schedule to the last scheduled minute
    exceptions: list[str]  # no_show, late_start, early_finish, out_of_adherence


def _merge(spans: Iterable[Span]) -> list[Span]:
    """Sorted, non-overlapping spans: touching or overlapping ones become one."""
    merged: list[Span] = []
    for start, end in sorted(s for s in spans if s[1] > s[0]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _intersect(a: Sequence[Span], b: Sequence[Span]) -> list[Span]:
    """The time inside both lists of merged spans."""
    out: list[Span] = []
    i = j = 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if end > start:
            out.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def _minutes(spans: Iterable[Span]) -> int:
    return round(sum((end - start).total_seconds() for start, end in spans) / 60)


def scheduled_spans(
    start: datetime, end: datetime, activities: Iterable[tuple[int, int]] = ()
) -> list[Span]:
    """The on-the-phones time of one shift: the shift less its activities, each given as
    (half-hours from the start of the shift, half-hours long), as in the roster."""
    holes = _merge(
        (start + timedelta(minutes=30 * offset), start + timedelta(minutes=30 * (offset + count)))
        for offset, count in activities
    )
    return _merge(_subtract((start, end), holes))


def _subtract(whole: Span, holes: Sequence[Span]) -> list[Span]:
    out: list[Span] = []
    cursor = whole[0]
    for hole_start, hole_end in holes:
        if hole_start > cursor:
            out.append((cursor, min(hole_start, whole[1])))
        cursor = max(cursor, hole_end)
    if cursor < whole[1]:
        out.append((cursor, whole[1]))
    return out


def adherence(
    scheduled: Iterable[Span],
    actual: Iterable[StateSpan],
    *,
    grace_min: int = GRACE_MIN,
    threshold_pct: float = 90.0,
) -> Adherence:
    """Adherence of one person-day. `scheduled` is the on-the-phone time (overlaps are merged,
    not counted twice). `actual` is every state interval; an unknown state is not working."""
    plan = _merge(scheduled)
    working = _merge((s, e) for state, s, e in actual if state in WORKING_STATES)
    kept = _intersect(plan, working)

    scheduled_min = _minutes(plan)
    in_min = _minutes(kept)
    pct = round(in_min / scheduled_min * 100, 1) if scheduled_min else None

    late = early = 0
    exceptions: list[str] = []
    if scheduled_min:
        if not kept:
            exceptions.append("no_show")
            late = scheduled_min
        else:
            late = _minutes([(plan[0][0], kept[0][0])]) if kept[0][0] > plan[0][0] else 0
            early = _minutes([(kept[-1][1], plan[-1][1])]) if plan[-1][1] > kept[-1][1] else 0
            if late > grace_min:
                exceptions.append("late_start")
            if early > grace_min:
                exceptions.append("early_finish")
        if pct is not None and pct < threshold_pct:
            exceptions.append("out_of_adherence")
    return Adherence(
        scheduled_min=scheduled_min,
        in_adherence_min=in_min,
        out_of_adherence_min=scheduled_min - in_min,
        adherence_pct=pct,
        late_start_min=late,
        early_finish_min=early,
        exceptions=exceptions,
    )


def team_adherence_pct(parts: Iterable[Adherence]) -> float | None:
    """Scheduled-minutes-weighted adherence of several people; None with nothing scheduled."""
    scheduled = in_adherence = 0
    for part in parts:
        scheduled += part.scheduled_min
        in_adherence += part.in_adherence_min
    return round(in_adherence / scheduled * 100, 1) if scheduled else None


# --- the synthetic agent-state file ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StateRow:
    login: str
    state: str
    start: datetime  # naive, local time
    end: datetime


@dataclass(slots=True)
class ParsedStates:
    rows: list[StateRow] = field(default_factory=list)
    rows_read: int = 0
    rows_rejected: int = 0
    # (row number, reason) for the first few rejected rows. Reasons never quote the row, so a
    # login or a time cannot leak through an error message.
    errors: list[tuple[int, str]] = field(default_factory=list)
    header_error: str | None = None


def _reject(parsed: ParsedStates, number: int, reason: str) -> None:
    parsed.rows_rejected += 1
    if len(parsed.errors) < MAX_ERRORS_KEPT:
        parsed.errors.append((number, reason))


def _local(text: str) -> datetime | None:
    try:
        value = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return value if value.tzinfo is None else None  # the file is local time; an offset is refused


def parse_state_csv(text: str) -> ParsedStates:
    """Parse `login,state,from,to` (header row required, any column order). A bad row is counted
    and given a reason, never stored; a bad header refuses the whole file."""
    parsed = ParsedStates()
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    names = [h.strip().lower() for h in header] if header else []
    if sorted(names) != ["from", "login", "state", "to"]:
        parsed.header_error = "The first line must name the columns login, state, from and to."
        return parsed
    where = {name: names.index(name) for name in names}
    for number, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells):
            continue  # a blank line is not a row
        parsed.rows_read += 1
        if len(cells) != 4:
            _reject(parsed, number, "wrong number of columns")
            continue
        login = cells[where["login"]].strip()
        state = cells[where["state"]].strip().lower()
        start, end = _local(cells[where["from"]]), _local(cells[where["to"]])
        if not login or len(login) > 100:
            _reject(parsed, number, "login is empty or too long")
        elif state not in STATES:
            _reject(parsed, number, "state is not one of the known states")
        elif start is None or end is None:
            _reject(parsed, number, "from and to must be local ISO date-times without an offset")
        elif end <= start:
            _reject(parsed, number, "to must be after from")
        elif (end - start).total_seconds() > MAX_INTERVAL_HOURS * 3600:
            _reject(parsed, number, "an interval cannot be longer than 24 hours")
        else:
            parsed.rows.append(StateRow(login, state, start, end))
    return parsed
