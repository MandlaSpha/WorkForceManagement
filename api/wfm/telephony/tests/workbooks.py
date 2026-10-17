"""Synthetic Call Detail Report workbooks for tests. Never real data.

The phone and name cells hold CANARY values, so tests can prove they are never stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile

HEADERS = [
    "Call ID", "Phone Number", "Access Number", "Caller Number", "Call Type", "Queue", "Agent",
    "Campaign", "Start Time", "Queue Time", "Agent Time", "Hangup Time", "Call Disposition Time",
    "Call Duration", "Agent Duration", "Queue Wait Time", "Agent Wait Time", "Disposition Name",
    "Call Status", "Hangup Reason", "Hangup Reason Code", "Hangup By", "Callback Type",
    "Transfer ID", "Total Hold Duration", "Total Mute Duration", "Disposition Duration",
    "Transcription Status", "Transcription Duration (s)",
]  # fmt: skip

CANARY_PHONE = "27829990001"
CANARY_CALLER = "27829990002"
CANARY_NAME = "Canary Person"
CANARY_REMARK = "Customer rang about printer"
CANARY_DIGITS = "0829990004"  # digits a caller typed into the IVR
CANARY_OTHER_AGENT = "Other Canary (Agent008)"
INCIDENT = "INC000064329272"
ORPHAN_CALL_ID = 999999  # on the detail sheets but not in the call sheet
EXTRA_SHEETS = [
    "Call Disposition Details",
    "Call IVR Details",
    "Agent Offered Call",
    "Transfer Call Details",
    "Call Mute Details",
    "Call Hold Details",
]
DETAIL_HEADERS = {
    "Call Disposition Details": [
        "Call ID", "Disposition", "Disposition Remark", "Disposition Time", "Disposition Duration",
        "Callback Time",
    ],
    "Call IVR Details": ["Call ID", "IVR Digit", "IVR Call Activity", "Action", "IVR Time"],
    "Agent Offered Call": [
        "Call ID", "Agent  Name", "Call Offered Date", "Call Offered Time", "Call Hangup Time",
        "Call Hangup Reason",
    ],
    "Transfer Call Details": [
        "Call ID", "Transfer Call ID", "Transfer By", "Transfer Call Start Time",
        "Transfer Call Answer Time", "Transfer Call Queue Time", "Transfer Call Agent Time",
        "Transfer Call Hangup Time",
    ],
    "Call Mute Details": ["Call ID", "Type", "Start Time", "End Time", "Duration"],
    "Call Hold Details": ["Call ID", "Type", "Start Time", "End Time", "Duration"],
}  # fmt: skip


def hms(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


@dataclass
class Call:
    call_id: int
    queue: str
    status: str  # "Agent" or "Abandoned" (or "Dial" for outbound)
    start: str  # "2026-05-04 08:05:00", local time as the ACD writes it
    wait: int | None = 0
    talk: int | None = 0
    wrap: int | None = None  # None leaves the cell blank, as the ACD does
    call_type: str = "INBOUND"
    agent: str | None = f"{CANARY_NAME} (Agent007)"

    def cells(self) -> dict[str, object]:
        answered = self.status == "Agent"
        start = datetime.strptime(self.start, "%Y-%m-%d %H:%M:%S")
        wait = self.wait or 0
        return {
            "Call ID": self.call_id,
            "Phone Number": CANARY_PHONE,
            "Caller Number": CANARY_CALLER,
            "Call Type": self.call_type,
            "Queue": self.queue,
            "Agent": self.agent if answered else None,
            "Start Time": self.start,
            "Queue Time": (start + timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "Agent Time": (
                (start + timedelta(seconds=wait + 2)).strftime("%Y-%m-%d %H:%M:%S")
                if answered
                else "0000-00-00 00:00:00"
            ),
            "Hangup Time": (start + timedelta(seconds=wait + (self.talk or 0) + 5)).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "Call Duration": hms(wait + (self.talk or 0) + 5),
            "Agent Duration": hms(self.talk if answered else 0),
            "Queue Wait Time": hms(wait),
            "Call Status": self.status,
            "Hangup By": "USER",
            "Total Hold Duration": hms(0),
            "Disposition Duration": hms(self.wrap),
        }


def workbook_bytes(
    calls: list[Call],
    *,
    extra_rows: list[dict[str, object]] | None = None,
    headers: list[str] | None = None,
    sheet: str = "Call Record Report",
    other_sheets: bool = True,
    canary_phone: str = CANARY_PHONE,
    detail_rows: dict[str, list[list[object]]] | None = None,
    skip_sheets: tuple[str, ...] = (),
) -> bytes:
    book = openpyxl.Workbook()
    ws = book.active
    assert ws is not None
    ws.title = sheet
    names = headers if headers is not None else HEADERS
    ws.append(names)
    rows = [c.cells() for c in calls] + (extra_rows or [])
    for cells in rows:
        if cells:  # an empty dict is a blank row
            cells = {**cells, "Phone Number": canary_phone}
        ws.append([cells.get(name) for name in names])
    if other_sheets:
        rows_by_sheet = detail_sheets(calls) if detail_rows is None else detail_rows
        for name in EXTRA_SHEETS:
            if name in skip_sheets:
                continue
            sheet_ws = book.create_sheet(name)
            sheet_ws.append(DETAIL_HEADERS[name])
            for detail in rows_by_sheet.get(name, []):
                sheet_ws.append(detail)
    out = BytesIO()
    book.save(out)
    return _frozen(out.getvalue())


def detail_sheets(calls: list[Call]) -> dict[str, list[list[object]]]:
    """Rows for the six detail sheets, built from the calls. Every free-text cell holds a canary.
    One orphan row per sheet names a call that is not in the call sheet."""

    def stamp(call: Call, seconds: int) -> str:
        moment = datetime.strptime(call.start, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=seconds)
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    rows: dict[str, list[list[object]]] = {name: [] for name in EXTRA_SHEETS}
    for call in calls:
        if call.status != "Agent" or call.call_type != "INBOUND":
            continue
        remark = (
            f"Rang {CANARY_NAME} on {CANARY_PHONE} about {INCIDENT} please"
            if call.call_id == 1
            else CANARY_REMARK
        )
        rows["Call Disposition Details"].append(
            [call.call_id, "Resolved", remark, stamp(call, 60), hms(call.wrap), None]
        )
        rows["Call IVR Details"] += [
            [call.call_id, "1", "Main Menu", "Selected", stamp(call, 1)],
            [call.call_id, CANARY_DIGITS, "Account Entry", "Typed", stamp(call, 2)],
        ]
        offered = datetime.strptime(call.start, "%Y-%m-%d %H:%M:%S") + timedelta(seconds=2)
        rows["Agent Offered Call"].append(
            [
                call.call_id, call.agent, offered.strftime("%Y-%m-%d"),
                offered.strftime("%H:%M:%S"),
                (offered + timedelta(seconds=7)).strftime("%H:%M:%S"), "Answered",
            ]
        )  # fmt: skip
        if call.call_id == 1:
            rows["Agent Offered Call"].append(
                [
                    1, CANARY_OTHER_AGENT, offered.strftime("%Y-%m-%d"),
                    offered.strftime("%H:%M:%S"),
                    (offered + timedelta(seconds=4)).strftime("%H:%M:%S"), "No answer",
                ]
            )  # fmt: skip
            rows["Call Mute Details"].append(
                [1, "Agent mute", stamp(call, 10), stamp(call, 25), hms(15)]
            )
        if call.call_id == 2:
            rows["Call Hold Details"].append(
                [2, "Customer hold", stamp(call, 20), stamp(call, 80), hms(60)]
            )
    transfer = next((c for c in calls if c.call_type == "AGENT TRANSFER"), None)
    if transfer is not None:
        rows["Transfer Call Details"].append(
            [
                transfer.call_id, 70001, transfer.agent, stamp(transfer, 0), stamp(transfer, 6),
                None, None, stamp(transfer, 126),
            ]
        )  # fmt: skip
    orphan = ORPHAN_CALL_ID
    rows["Call Disposition Details"].append([orphan, "Resolved", CANARY_REMARK, None, hms(5), None])
    rows["Call IVR Details"].append([orphan, "1", "Main Menu", "Selected", None])
    rows["Agent Offered Call"].append(
        [orphan, "Ghost Canary (Agent099)", "2026-05-04", "08:00:00", "08:00:05", "x"]
    )
    rows["Transfer Call Details"].append([orphan, 70002, None, None, None, None, None, None])
    rows["Call Mute Details"].append([orphan, "Agent mute", None, None, hms(3)])
    rows["Call Hold Details"].append([orphan, "Customer hold", None, None, hms(3)])
    return rows


def _frozen(xlsx: bytes) -> bytes:
    """The same workbook as the same bytes. openpyxl stamps the file with the current time, inside
    the properties and in every zip entry, so two workbooks built a moment apart would differ and
    "the same file twice" would sometimes not be the same file."""
    fixed = datetime(2026, 1, 1, tzinfo=UTC)
    stamp = fixed.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    out = BytesIO()
    with ZipFile(BytesIO(xlsx)) as source, ZipFile(out, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(
                    rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*", rb"\g<1>" + stamp, data
                )
            entry = ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            target.writestr(entry, data)
    return out.getvalue()


def upload(content: bytes, name: str = "report.xlsx") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# The hand-worked scenario. Expected figures (offered / answered / abandoned / answered within
# 20s / wait of answered / talk+wrap of answered):
#   QueueA 08:00-08:29  4 / 3 / 1 / 3 (0,10,20) / 30 / 120+180+210 = 510
#   QueueA 08:30-08:59  3 / 2 / 1 / 0 (21,30)   / 51 / 120+100     = 220
#   QueueB 08:00-08:29  3 / 3 / 0 / 2 (5,15)    / 60 / 100+300+100 = 500
#   all queues          10 / 8 / 2 / 5          / 141 / 1230
#   -> abandon 20%, SL 5/10 = 50%, ASA 141/8 = 17.625 s, AHT 1230/8 = 153.75 s
#   QueueA alone: 7 / 5 / 2, SL 3/7, ASA 81/5 = 16.2, AHT 730/5 = 146
#   QueueB alone: 3 / 3 / 0, SL 2/3, ASA 60/3 = 20,   AHT 500/3
DAY = "2026-05-04"


def scenario() -> list[Call]:
    def at(hh_mm_ss: str) -> str:
        return f"{DAY} {hh_mm_ss}"

    return [
        Call(1, "QueueA", "Agent", at("08:05:00"), wait=0, talk=100, wrap=20),
        Call(2, "QueueA", "Agent", at("08:10:00"), wait=10, talk=150, wrap=30),
        Call(3, "QueueA", "Agent", at("08:20:00"), wait=20, talk=200, wrap=10),
        Call(4, "QueueA", "Abandoned", at("08:25:00"), wait=7),
        Call(5, "QueueA", "Agent", at("08:35:00"), wait=21, talk=120),
        Call(6, "QueueA", "Agent", at("08:40:00"), wait=30, talk=60, wrap=40),
        Call(7, "QueueA", "Abandoned", at("08:50:00"), wait=60),
        Call(8, "QueueB", "Agent", at("08:02:00"), wait=5, talk=80, wrap=20),
        Call(9, "QueueB", "Agent", at("08:12:00"), wait=40, talk=300),
        Call(10, "QueueB", "Agent", at("08:22:00"), wait=15, talk=90, wrap=10),
        # work that is not an inbound call: it must change no service figure
        Call(11, "QueueA", "Dial", at("09:00:00"), wait=0, talk=60, call_type="OUTBOUND"),
        Call(
            12, "QueueA", "Agent", at("09:05:00"),
            wait=1, talk=500, wrap=500, call_type="AGENT TRANSFER",
        ),
    ]  # fmt: skip
