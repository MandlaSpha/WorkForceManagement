"""Reading a quality-results file (CSV or Excel), one evaluation per row (QUA-01).

The layout is SYNTHETIC until Gijima names its quality tool. Required columns: login, date, score.
Optional: kind (call or ticket), ref (the tool's evaluation id), csat (1 to 5), coaching_due. Any
other column (a name, a comment, a transcript) is ignored and reported by NAME only: it is never
stored. A row that cannot be used is counted with a reason code and its line number, never its
content. The row maths is `wfm_engine.quality.read_row`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from wfm_engine.quality import Evaluation, read_row

from wfm.scheduling.employee_import import UnreadableFileError, read_table

from .policy import MAX_ERRORS_KEPT, MAX_ROWS

ALIASES: dict[str, str] = {
    "login": "login",
    "agent_login": "login",
    "agent": "login",
    "agent_id": "login",
    "username": "login",
    "date": "date",
    "evaluated_on": "date",
    "evaluation_date": "date",
    "score": "score",
    "score_pct": "score",
    "qa_score": "score",
    "quality_score": "score",
    "kind": "kind",
    "type": "kind",
    "channel": "kind",
    "ref": "ref",
    "evaluation_id": "ref",
    "reference": "ref",
    "csat": "csat",
    "csat_score": "csat",
    "coaching_due": "coaching_due",
    "coaching_due_date": "coaching_due",
    "coaching_date": "coaching_due",
}
REQUIRED = ("login", "date", "score")

REASONS: dict[str, str] = {
    "bad_login": "The login is missing or too long.",
    "bad_date": "The date must be YYYY-MM-DD or DD/MM/YYYY.",
    "date_in_future": "The date is in the future.",
    "date_too_old": "The date is more than about two years back.",
    "bad_score": "The score must be a number from 0 to 100.",
    "bad_kind": "The kind must be call or ticket.",
    "bad_ref": "The evaluation reference is too long (40 characters at most).",
    "bad_csat": "The CSAT must be a whole number from 1 to 5.",
    "bad_coaching_due": "The coaching date must be YYYY-MM-DD or DD/MM/YYYY.",
    "repeated_in_file": "The same person, day, kind and reference appeared earlier in the file.",
}


@dataclass(slots=True)
class Parsed:
    rows: list[tuple[int, Evaluation]] = field(default_factory=list)  # (file row, evaluation)
    errors: list[tuple[int, str]] = field(default_factory=list)  # (file row, reason text)
    rejected: int = 0
    rows_read: int = 0
    ignored_columns: list[str] = field(default_factory=list)

    def reject(self, number: int, code: str) -> None:
        self.rejected += 1
        if len(self.errors) < MAX_ERRORS_KEPT:
            self.errors.append((number, REASONS.get(code, "The row cannot be used.")))


def _canonical(header: str) -> str | None:
    key = header.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")
    return ALIASES.get(key)


def parse(content: bytes, filename: str, today: date) -> Parsed:
    table = read_table(content, filename)
    if not table:
        raise UnreadableFileError("The file is empty.")
    header, *body = table
    columns = [_canonical(h) for h in header]
    missing = [c for c in REQUIRED if c not in columns]
    if missing:
        raise UnreadableFileError(f"The header is missing: {', '.join(missing)}.")
    if len(body) > MAX_ROWS:
        raise UnreadableFileError(f"At most {MAX_ROWS} rows a file.")
    parsed = Parsed(
        ignored_columns=[h for h, c in zip(header, columns, strict=False) if c is None and h]
    )
    seen: set[tuple[str, date, str, str]] = set()
    for number, cells in enumerate(body, start=2):  # file row 1 is the header
        fields = {c: v for c, v in zip(columns, cells, strict=False) if c is not None}
        if not any(fields.values()):  # blank lines are skipped, not counted
            continue
        parsed.rows_read += 1
        found = read_row(fields, today)
        if isinstance(found, str):
            parsed.reject(number, found)
            continue
        key = (found.login, found.evaluated_on, found.kind, found.ref)
        if key in seen:
            parsed.reject(number, "repeated_in_file")
            continue
        seen.add(key)
        parsed.rows.append((number, found))
    return parsed
