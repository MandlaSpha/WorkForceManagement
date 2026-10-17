"""Quality results per agent, as imported from the quality tool (requirement QUA-01).

Pure: no Django, no clock, no I/O. The scoring itself stays in the quality tool; this module only
checks a row of its export and adds up what was already scored. There is deliberately no ranking,
no percentile and no comparison between people here: a summary is about ONE person's own results.

A ratio with nothing to divide by is None, never 0.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

KINDS = ("call", "ticket")
MAX_REF_LEN = 40
CSAT_MIN, CSAT_MAX = 1, 5
MAX_AGE_DAYS = 800  # an evaluation older than this is a mistake in the file, not history
MAX_COACHING_AHEAD_DAYS = 730


@dataclass(frozen=True, slots=True)
class Evaluation:
    login: str
    evaluated_on: date
    kind: str
    ref: str
    score_pct: float
    csat: int | None
    coaching_due: date | None


def parse_day(text: str) -> date | None:
    """ISO (2026-05-25) or South African day-first (25/05/2026); None when it is neither."""
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    return None


def read_row(fields: Mapping[str, str], today: date) -> Evaluation | str:
    """One row of the export as an `Evaluation`, or the reason it cannot be used (a short code,
    never the row's content)."""
    login = fields.get("login", "").strip()
    if not login or len(login) > 100:
        return "bad_login"
    day = parse_day(fields.get("date", "").strip())
    if day is None:
        return "bad_date"
    if day > today:
        return "date_in_future"
    if day < today - timedelta(days=MAX_AGE_DAYS):
        return "date_too_old"
    try:
        score = float(fields.get("score", "").strip().rstrip("%"))
    except ValueError:
        return "bad_score"
    if not 0 <= score <= 100:  # also false for NaN
        return "bad_score"
    kind = fields.get("kind", "").strip().lower() or "call"
    if kind not in KINDS:
        return "bad_kind"
    ref = fields.get("ref", "").strip()
    if len(ref) > MAX_REF_LEN:
        return "bad_ref"
    csat_text = fields.get("csat", "").strip()
    csat: int | None = None
    if csat_text:
        if not csat_text.isdigit() or not CSAT_MIN <= int(csat_text) <= CSAT_MAX:
            return "bad_csat"
        csat = int(csat_text)
    due_text = fields.get("coaching_due", "").strip()
    due: date | None = None
    if due_text:
        due = parse_day(due_text)
        if due is None or due > today + timedelta(days=MAX_COACHING_AHEAD_DAYS):
            return "bad_coaching_due"
    return Evaluation(login, day, kind, ref, round(score, 2), csat, due)


@dataclass(frozen=True, slots=True)
class Summary:
    evaluations: int
    average_score_pct: float | None
    latest_score_pct: float | None
    latest_on: date | None
    csat_count: int
    csat_average: float | None  # 1 to 5
    coaching_due: date | None  # from the newest evaluation that names one
    coaching_is_due: bool  # that date is today or earlier


def summarise(rows: Iterable[Evaluation], today: date) -> Summary:
    """One person's own results. Order of the input does not matter."""
    ordered = sorted(rows, key=lambda r: (r.evaluated_on, r.ref, r.kind))
    if not ordered:
        return Summary(0, None, None, None, 0, None, None, False)
    scores = [r.score_pct for r in ordered]
    rated = [r.csat for r in ordered if r.csat is not None]
    due = next((r.coaching_due for r in reversed(ordered) if r.coaching_due is not None), None)
    return Summary(
        evaluations=len(ordered),
        average_score_pct=round(sum(scores) / len(scores), 1),
        latest_score_pct=ordered[-1].score_pct,
        latest_on=ordered[-1].evaluated_on,
        csat_count=len(rated),
        csat_average=round(sum(rated) / len(rated), 2) if rated else None,
        coaching_due=due,
        coaching_is_due=due is not None and due <= today,
    )
