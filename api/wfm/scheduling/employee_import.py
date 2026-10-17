"""Reading an employee master file (DAT-06): CSV or Excel, one employee per row.

Only known columns are read; anything else in the file is ignored and reported by name (never by
value). The parser does no database work; `import_services` decides what each row does.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import date, datetime

MAX_ROWS = 5000
# What the file's header may call each column. Spelling, case, spaces and dashes are forgiven.
ALIASES: dict[str, str] = {
    "emp_no": "emp_no",
    "employee_no": "emp_no",
    "employee_number": "emp_no",
    "employee_id": "emp_no",
    "name": "name",
    "full_name": "name",
    "contract": "contract",
    "contract_type": "contract",
    "weekly_hours": "hours",
    "hours": "hours",
    "work_mode": "mode",
    "mode": "mode",
    "site": "mode",
    "start_date": "start",
    "hire_date": "start",
    "start": "start",
    "end_date": "end",
    "end": "end",
    "manager": "manager",
    "manager_emp_no": "manager",
    "manager_no": "manager",
    "queues": "queues",
    "skills": "queues",
    "acd_logins": "logins",
    "acd_login": "logins",
    "agent_logins": "logins",
    "logins": "logins",
}


class UnreadableFileError(Exception):
    """The file is not a CSV or Excel workbook this importer can read."""


@dataclass(slots=True)
class Parsed:
    rows: list[tuple[int, dict[str, str]]] = field(default_factory=list)  # (file row, columns)
    ignored_columns: list[str] = field(default_factory=list)


def _canonical(header: str) -> str | None:
    key = header.strip().lower().replace(" ", "_").replace("-", "_").replace(".", "_")
    return ALIASES.get(key)


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def parse(content: bytes, filename: str) -> Parsed:
    name = filename.lower()
    if name.endswith(".xlsx"):
        table = _read_xlsx(content)
    elif name.endswith(".csv"):
        table = _read_csv(content)
    else:
        raise UnreadableFileError("Use a .csv or .xlsx file.")
    if not table:
        raise UnreadableFileError("The file is empty.")
    raw_header, *body = table
    header = [_cell(h) for h in raw_header]
    columns = [_canonical(h) for h in header]
    if "emp_no" not in columns or "name" not in columns:
        raise UnreadableFileError(
            "The first row must name the columns, and include an employee number and a name."
        )
    if len(body) > MAX_ROWS:
        raise UnreadableFileError(f"At most {MAX_ROWS} employees at a time.")
    parsed = Parsed(
        ignored_columns=[
            h for h, c in zip(header, columns, strict=False) if c is None and h.strip()
        ]
    )
    for index, cells in enumerate(body, start=2):  # file row 1 is the header
        row = {c: _cell(v) for c, v in zip(columns, cells, strict=False) if c is not None}
        if any(row.values()):  # blank lines are skipped
            parsed.rows.append((index, row))
    return parsed


def read_table(content: bytes, filename: str) -> list[list[str]]:
    """The rows of a .csv or .xlsx file as text, header first, for the other file importers (so
    reading a workbook exists once). Raises `UnreadableFileError`."""
    name = filename.lower()
    if name.endswith(".xlsx"):
        table = _read_xlsx(content)
    elif name.endswith(".csv"):
        table = _read_csv(content)
    else:
        raise UnreadableFileError("Use a .csv or .xlsx file.")
    return [[_cell(v) for v in row] for row in table]


def _read_csv(content: bytes) -> list[list[object]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise UnreadableFileError("The file is not UTF-8 text.") from error
    return [list(r) for r in csv.reader(io.StringIO(text))]


def _read_xlsx(content: bytes) -> list[list[object]]:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as error:  # a damaged or non-Excel file raises many different errors
        raise UnreadableFileError("The file is not a readable Excel workbook.") from error
    sheet = workbook.worksheets[0]
    return [list(r) for r in sheet.iter_rows(values_only=True)]


def parse_date(text: str) -> date | None:
    """ISO (2026-05-25) or South African day-first (25/05/2026); None when blank; ValueError when
    it is neither."""
    if not text:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise ValueError(text)
