"""Synthetic Call Detail Report workbooks for tests. Never real data.

The phone and name cells hold CANARY values, so tests can prove they are never stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO

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
EXTRA_SHEETS = [
    "Call Disposition Details",
    "Call IVR Details",
    "Agent Offered Call",
    "Transfer Call Details",
    "Call Mute Details",
    "Call Hold Details",
]


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
        for name in EXTRA_SHEETS:
            book.create_sheet(name).append(["Call ID", "Anything"])
    out = BytesIO()
    book.save(out)
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
