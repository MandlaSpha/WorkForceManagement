"""Read the ACD Call Detail Report workbook (tech spec section 5).

The upload is untrusted. openpyxl parses its XML with defusedxml when that is installed (it is a
dependency; a test pins this), and only the columns WFM needs are ever read out of a row: caller
and dialled numbers and agent display names stay inside the spreadsheet library.

All seven sheets are read (DAT-01). "Call Record Report" is required. The six detail sheets are
optional: a missing or unusable one is a warning in the per-sheet report, never an error. Their
rows are parsed by `wfm_engine.cdr_details`, which keeps only logins, counts, durations, labels
and incident numbers.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BytesIO

import openpyxl
from wfm_engine.cdr import CallRow, CallRowError, parse_call_row
from wfm_engine.cdr_details import SECONDARY_SHEETS, SheetSpec

PRIMARY_SHEET = "Call Record Report"
REQUIRED_COLUMNS = ("Call ID", "Call Type", "Queue", "Call Status", "Start Time")
USED_COLUMNS = (
    *REQUIRED_COLUMNS,
    "Agent",
    "Queue Time",
    "Agent Time",
    "Hangup Time",
    "Call Duration",
    "Agent Duration",
    "Queue Wait Time",
    "Disposition Duration",
    "Total Hold Duration",
    "Hangup By",
)
HEADER_SEARCH_ROWS = 10
MAX_REJECTED_SAMPLES = 50


class WorkbookError(Exception):
    """The file is not a usable Call Detail Report. `code` is stable; `columns` lists header names
    (never cell values) when columns are missing."""

    def __init__(self, code: str, detail: str, columns: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.columns = columns


@dataclass
class SheetReport:
    """What happened to one sheet. Codes and counts only, never cell values."""

    sheet: str
    read: bool = False
    rows_read: int = 0
    rows_kept: int = 0
    warnings: Counter[str] = field(default_factory=Counter)

    def as_json(self) -> dict[str, object]:
        return {
            "sheet": self.sheet,
            "read": self.read,
            "rows_read": self.rows_read,
            "rows_kept": self.rows_kept,
            "warnings": dict(self.warnings),
        }


@dataclass
class ParsedWorkbook:
    rows: list[tuple[int, CallRow]] = field(default_factory=list)  # (sheet row number, row)
    rejected: Counter[str] = field(default_factory=Counter)  # reason code -> count
    rejected_samples: list[dict[str, object]] = field(default_factory=list)
    warnings: Counter[str] = field(default_factory=Counter)  # code -> calls with a cleared cell
    rows_read: int = 0
    sheets_ignored: list[str] = field(default_factory=list)  # optional sheets not read
    sheet_reports: dict[str, SheetReport] = field(default_factory=dict)
    details: dict[str, list[object]] = field(default_factory=dict)  # sheet -> rows


def read_call_records(content: bytes) -> ParsedWorkbook:
    try:
        workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception:  # untrusted bytes: any parser failure means "not a workbook", and the
        # original message could echo file content, so it is not kept
        raise WorkbookError("import.not_a_workbook", "This is not an .xlsx workbook.") from None

    try:
        if PRIMARY_SHEET not in workbook.sheetnames:
            raise WorkbookError(
                "import.sheet_missing", f'The workbook has no "{PRIMARY_SHEET}" sheet.'
            )
        parsed = ParsedWorkbook()
        rows = workbook[PRIMARY_SHEET].iter_rows(values_only=True)
        columns = _find_header(rows, REQUIRED_COLUMNS, USED_COLUMNS)
        for number, cells in enumerate(rows, start=columns.next_row_number):
            if cells is None or all(cell is None or cell == "" for cell in cells):
                continue
            parsed.rows_read += 1
            row = {name: _cell(cells, at) for name, at in columns.positions.items()}
            try:
                call = parse_call_row(row)
                parsed.rows.append((number, call))
                parsed.warnings.update(call.warnings)
            except CallRowError as error:
                parsed.rejected[error.code] += 1
                if len(parsed.rejected_samples) < MAX_REJECTED_SAMPLES:
                    parsed.rejected_samples.append({"row": number, "code": error.code})
        parsed.sheet_reports[PRIMARY_SHEET] = SheetReport(
            PRIMARY_SHEET, read=True, rows_read=parsed.rows_read, rows_kept=len(parsed.rows)
        )
        for name, spec in SECONDARY_SHEETS.items():
            _read_detail_sheet(workbook, name, spec, parsed)
        return parsed
    finally:
        workbook.close()


def _read_detail_sheet(
    workbook: openpyxl.Workbook, name: str, spec: SheetSpec, parsed: ParsedWorkbook
) -> None:
    report = SheetReport(name)
    parsed.sheet_reports[name] = report
    if name not in workbook.sheetnames:
        report.warnings["sheet.missing"] += 1
        parsed.sheets_ignored.append(name)
        return
    rows = workbook[name].iter_rows(values_only=True)
    try:
        columns = _find_header(rows, spec.required, spec.columns)
    except WorkbookError as error:  # an optional sheet we cannot use is a warning
        report.warnings["sheet.columns_missing" if error.columns else "sheet.header_missing"] += 1
        parsed.sheets_ignored.append(name)
        return
    report.read = True
    kept: list[object] = []
    for cells in rows:
        if cells is None or all(cell is None or cell == "" for cell in cells):
            continue
        report.rows_read += 1
        try:
            kept.append(spec.parse({n: _cell(cells, at) for n, at in columns.positions.items()}))
        except CallRowError as error:
            report.warnings[f"row.{error.code}"] += 1
    parsed.details[name] = kept


@dataclass(frozen=True)
class _Columns:
    positions: dict[str, int]
    next_row_number: int


def _find_header(
    rows: Iterator[tuple[object, ...]], required: tuple[str, ...], used: tuple[str, ...]
) -> _Columns:
    for number, cells in enumerate(rows, start=1):
        if number > HEADER_SEARCH_ROWS:
            break
        names = [" ".join(str(c).split()) if c is not None else "" for c in cells]
        if "Call ID" in names:
            where = {name: at for at, name in enumerate(names) if name}
            missing = tuple(c for c in required if c not in where)
            if missing:
                raise WorkbookError(
                    "import.columns_missing",
                    "The sheet is missing required columns: " + ", ".join(missing) + ".",
                    missing,
                )
            return _Columns({name: where[name] for name in used if name in where}, number + 1)
    raise WorkbookError(
        "import.header_missing", 'No header row with a "Call ID" column was found.', ("Call ID",)
    )


def _cell(cells: tuple[object, ...], at: int) -> object:
    return cells[at] if at < len(cells) else None
