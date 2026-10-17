"""Reading the workbook: no database needed."""

from __future__ import annotations

import openpyxl
import pytest

from wfm.telephony.workbook import WorkbookError, read_call_records

from .workbooks import HEADERS, Call, scenario, workbook_bytes


def test_reads_the_call_record_sheet_and_every_detail_sheet() -> None:
    parsed = read_call_records(workbook_bytes(scenario()))
    assert [row.call_id for _, row in parsed.rows] == list(range(1, 13))
    assert parsed.rows_read == 12
    assert parsed.sheets_ignored == []
    assert len(parsed.sheet_reports) == 7


def test_row_numbers_point_at_the_sheet_row_so_a_person_can_find_it() -> None:
    parsed = read_call_records(workbook_bytes(scenario()))
    assert parsed.rows[0][0] == 2  # row 1 is the header


def test_columns_can_be_in_any_order() -> None:
    shuffled = [*reversed(HEADERS)]
    parsed = read_call_records(workbook_bytes(scenario(), headers=shuffled))
    assert parsed.rows_read == 12
    assert parsed.rejected == {}


def test_the_header_may_sit_a_few_rows_down() -> None:
    book = openpyxl.Workbook()
    ws = book.active
    assert ws is not None
    ws.title = "Call Record Report"
    ws.append(["Gijima call detail report"])
    ws.append([])
    ws.append(HEADERS)
    ws.append(
        [Call(1, "Q", "Agent", "2026-05-04 08:00:00", talk=5).cells().get(h) for h in HEADERS]
    )
    from io import BytesIO

    out = BytesIO()
    book.save(out)
    parsed = read_call_records(out.getvalue())
    assert parsed.rows_read == 1
    assert parsed.rows[0][0] == 4


def test_rejected_samples_are_capped_and_carry_no_values() -> None:
    bad = [
        {**Call(i, "Q", "Agent", "2026-05-04 08:00:00").cells(), "Call Type": ""}
        for i in range(1, 80)
    ]
    parsed = read_call_records(workbook_bytes([], extra_rows=bad))
    assert parsed.rejected == {"call_type.missing": 79}
    assert len(parsed.rejected_samples) == 50
    assert set(parsed.rejected_samples[0]) == {"row", "code"}


@pytest.mark.parametrize("junk", [b"", b"PK\x03\x04 not really", b"%PDF-1.7 hello"])
def test_garbage_is_not_a_workbook(junk: bytes) -> None:
    with pytest.raises(WorkbookError) as caught:
        read_call_records(junk)
    assert caught.value.code == "import.not_a_workbook"
