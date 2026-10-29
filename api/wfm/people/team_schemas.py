from __future__ import annotations

from datetime import date

from ninja import Schema

# camelCase on the wire; the noqa comments mark that deliberate choice. Nothing here carries pay,
# a wellbeing reason or score, or a colleague's name beside a swap.


class TeamManagerOut(Schema):
    id: int
    name: str


class TeamShiftOut(Schema):
    day: date
    shift: str
    startTime: str  # noqa: N815 - "HH:MM"
    endTime: str  # noqa: N815
    paidHours: float  # noqa: N815
    adherencePct: float | None  # noqa: N815 - none: no agent-state data for that day


class TeamLeaveBalanceOut(Schema):
    leaveType: str  # noqa: N815
    entitlementDays: float | None  # noqa: N815 - none: the customer has not set one
    takenDays: float  # noqa: N815
    pendingDays: float  # noqa: N815
    availableDays: float | None  # noqa: N815


class TeamPendingLeaveOut(Schema):
    leaveType: str  # noqa: N815
    startDate: date  # noqa: N815
    endDate: date  # noqa: N815
    days: int


class TeamPersonOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    name: str
    contractType: str  # noqa: N815
    contractHours: float  # noqa: N815
    rosteredHours: float  # noqa: N815
    shifts: int
    adherencePct: float | None  # noqa: N815 - none: no agent-state data this week
    onTrack: bool | None  # noqa: N815 - none when there is no adherence data
    pendingLeave: int  # noqa: N815 - requests waiting for a decision
    openSwaps: int  # noqa: N815 - swaps waiting for an answer or approval
    checkIn: bool  # noqa: N815 - a wellbeing prompt exists; the reason is on the Wellbeing screen
    shiftList: list[TeamShiftOut]  # noqa: N815
    leaveBalances: list[TeamLeaveBalanceOut]  # noqa: N815
    pendingRequests: list[TeamPendingLeaveOut]  # noqa: N815


class TeamSummaryOut(Schema):
    headcount: int
    withAdherence: int  # noqa: N815
    onTrack: int  # noqa: N815
    rosteredHours: float  # noqa: N815
    contractHours: float  # noqa: N815
    rosteredPct: float | None  # noqa: N815 - of contract hours


class TeamOverviewOut(Schema):
    weekStart: date  # noqa: N815
    weekEnd: date  # noqa: N815
    adherenceThresholdPct: float  # noqa: N815
    summary: TeamSummaryOut
    managers: list[TeamManagerOut]  # the team filter: planners and admins only, else empty
    people: list[TeamPersonOut]
