"""Read the ACD Call Detail Report workbook (tech spec section 5).

The upload is untrusted. openpyxl parses its XML with defusedxml when that is installed (it is a
dependency; a test pins this), and only the columns WFM needs are ever read out of a row: caller
and dialled numbers and agent display names stay inside the spreadsheet library.

Only the "Call Record Report" sheet is read in this version. The other six sheets (dispositions,
IVR, agent offers, transfers, mute, hold) are listed as ignored in the import report instead of
being silently dropped.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BytesIO

import openpyxl
from wfm_engine.cdr import CallRow, CallRowError, parse_call_row

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
class ParsedWorkbook:
    rows: list[tuple[int, CallRow]] = field(default_factory=list)  # (sheet row number, row)
    rejected: Counter[str] = field(default_factory=Counter)  # reason code -> count
    rejected_samples: list[dict[str, object]] = field(default_factory=list)
    warnings: Counter[str] = field(default_factory=Counter)  # code -> calls with a cleared cell
    rows_read: int = 0
    sheets_ignored: list[str] = field(default_factory=list)


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
        parsed = ParsedWorkbook(
            sheets_ignored=[name for name in workbook.sheetnames if name != PRIMARY_SHEET]
        )
        rows = workbook[PRIMARY_SHEET].iter_rows(values_only=True)
        columns = _find_header(rows)
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
        return parsed
    finally:
        workbook.close()


@dataclass(frozen=True)
class _Columns:
    positions: dict[str, int]
    next_row_number: int


def _find_header(rows: Iterator[tuple[object, ...]]) -> _Columns:
    for number, cells in enumerate(rows, start=1):
        if number > HEADER_SEARCH_ROWS:
            break
        names = [str(c).strip() if c is not None else "" for c in cells]
        if "Call ID" in names:
            where = {name: at for at, name in enumerate(names) if name}
            missing = tuple(c for c in REQUIRED_COLUMNS if c not in where)
            if missing:
                raise WorkbookError(
                    "import.columns_missing",
                    "The sheet is missing required columns: " + ", ".join(missing) + ".",
                    missing,
                )
            return _Columns(
                {name: where[name] for name in USED_COLUMNS if name in where}, number + 1
            )
    raise WorkbookError(
        "import.header_missing", 'No header row with a "Call ID" column was found.', ("Call ID",)
    )


def _cell(cells: tuple[object, ...], at: int) -> object:
    return cells[at] if at < len(cells) else None
