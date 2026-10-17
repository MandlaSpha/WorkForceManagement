"""The workbooks that go out by email: one sheet of figures and one of days, built from the same
selectors the screens use, as the schedule's owner. Nothing here reads data directly."""

from __future__ import annotations

import io
from datetime import date

from openpyxl import Workbook

from wfm.accounts.models import User
from wfm.insight import selectors as insight
from wfm.telephony import peaks_selectors

from .models import ReportKind, ReportSchedule

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _bytes(book: Workbook) -> bytes:
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def _cell(value: object) -> object:
    """Text a spreadsheet would run as a formula is stored as plain text with an apostrophe."""
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def scorecard_book(owner: User, first: date, last: date) -> bytes:
    card = insight.scorecard(owner, first, last)
    book = Workbook()
    figures = book.active
    figures.title = "Figures"  # type: ignore[union-attr]
    figures.append(["Figure", "Value", "Unit", "Basis", "Note"])  # type: ignore[union-attr]
    for i in card.items:
        figures.append(  # type: ignore[union-attr]
            [i.label, i.value, i.unit, i.basis, _cell(i.note)]
        )
    days = book.create_sheet("By day")
    days.append(["Day", "Calls offered", "Service level (%)"])
    for d in card.days:
        days.append([d.day.isoformat(), d.offered, d.service_level_pct])
    return _bytes(book)


def peaks_book(owner: User, queue_id: int, first: date, last: date) -> bytes:
    found = peaks_selectors.peaks_report(owner, queue_id, first, last)
    r = found.report
    book = Workbook()
    days = book.active
    days.title = "Days"  # type: ignore[union-attr]
    days.append(["", "Day", "Calls offered"])  # type: ignore[union-attr]
    for d in r.busiest_days:
        days.append(["Busiest", d.day.isoformat(), d.offered])  # type: ignore[union-attr]
    for d in r.quietest_days:
        days.append(["Quietest", d.day.isoformat(), d.offered])  # type: ignore[union-attr]
    slots = book.create_sheet("Half-hours")
    slots.append(["", "Half-hour", "Average calls", "Days measured"])
    for s in r.busiest_slots:
        slots.append(["Busiest", f"{s.slot:%H:%M}", float(s.average_offered), s.days])
    for s in r.quietest_slots:
        slots.append(["Quietest", f"{s.slot:%H:%M}", float(s.average_offered), s.days])
    return _bytes(book)


def render(schedule: ReportSchedule, first: date, last: date) -> tuple[str, bytes]:
    """The report's title and workbook, built as the schedule's owner."""
    owner = schedule.owner
    if schedule.report == ReportKind.SCORECARD:
        return "Analytics scorecard", scorecard_book(owner, first, last)
    if schedule.queue_id is None:  # a peaks schedule always names its queue
        raise ValueError("a peaks report needs a queue")
    return "Peaks and troughs", peaks_book(owner, schedule.queue_id, first, last)
