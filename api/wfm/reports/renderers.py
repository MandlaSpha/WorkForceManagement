"""The workbooks that go out by email: one sheet of figures and one of days, built from the same
selectors the screens use, as the schedule's owner. Nothing here reads data directly."""

from __future__ import annotations

import io
from datetime import date

from openpyxl import Workbook

from wfm.accounts.models import User
from wfm.capacity.board_selectors import latest_plan
from wfm.insight import selectors as insight
from wfm.telephony import peaks_selectors
from wfm.telephony.selectors import kpi_summary

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


BOARD_NOTES = [
    ("Period", "The days the pack covers, in South African time."),
    ("Measured", "Taken from imported calls, approved leave or past forecasts."),
    ("Modelled", "Measured work set against a plan, such as the published roster."),
    ("Needs data", "A figure that cannot honestly be given yet; the note says what is missing."),
    ("Service level", "Calls answered within the queue's threshold, over calls offered."),
    ("Abandon rate", "Calls abandoned, over calls offered."),
    ("Occupancy", "Handling time over paid time on published rosters."),
    ("Hiring plan", "People needed, people on the books, hires and the gap, by month."),
    ("Money", "The pack holds no pay or cost figures."),
]


def board_book(owner: User, first: date, last: date) -> bytes:
    """The investment-board pack: headline figures, queues, the latest hiring plan (only for a
    role that may read plans; otherwise the sheet is absent) and the definitions. No pay."""
    card = insight.scorecard(owner, first, last)
    book = Workbook()
    headline = book.active
    headline.title = "Headline"  # type: ignore[union-attr]
    headline.append(["Period", f"{first.isoformat()} to {last.isoformat()}"])  # type: ignore[union-attr]
    headline.append(["Figure", "Value", "Unit", "Basis", "Note"])  # type: ignore[union-attr]
    for i in card.items:
        if i.unit == "R":  # a rand figure is pay data: not in this pack, for any role
            continue
        headline.append([i.label, i.value, i.unit, i.basis, _cell(i.note)])  # type: ignore[union-attr]
    queues = book.create_sheet("By queue")
    queues.append(["Queue", "Calls offered", "Service level (%)", "Abandon rate (%)"])
    for q in kpi_summary(owner, first, last).queues:
        queues.append([_cell(q.name), q.kpis.offered, q.kpis.service_level_pct, q.kpis.abandon_pct])
    plan = latest_plan(owner)
    if plan is not None:
        capacity = book.create_sheet("Capacity")
        capacity.append(["Plan", _cell(plan.name)])
        capacity.append(["Month", "Needed", "On the books", "Hires", "Effective", "Gap"])
        for m in plan.months:
            capacity.append(
                [m.month.strftime("%Y-%m"), m.required, m.headcount, m.hires, m.effective, m.gap]
            )
    notes = book.create_sheet("Notes")
    notes.append(["Term", "Meaning"])
    for term, meaning in BOARD_NOTES:
        notes.append([term, meaning])
    return _bytes(book)


def render(schedule: ReportSchedule, first: date, last: date) -> tuple[str, bytes]:
    """The report's title and workbook, built as the schedule's owner."""
    owner = schedule.owner
    if schedule.report == ReportKind.SCORECARD:
        return "Analytics scorecard", scorecard_book(owner, first, last)
    if schedule.report == ReportKind.BOARD:
        return "Investment-board KPI pack", board_book(owner, first, last)
    if schedule.queue_id is None:  # a peaks schedule always names its queue
        raise ValueError("a peaks report needs a queue")
    return "Peaks and troughs", peaks_book(owner, schedule.queue_id, first, last)
