from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

from ninja import Field, Schema

# camelCase on the wire; the noqa comments mark that deliberate choice.


class ShiftIn(Schema):
    code: str = Field(..., max_length=10)
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    paidMinutes: int  # noqa: N815


class ShiftOut(Schema):
    id: int
    code: str
    startTime: str  # noqa: N815 - "09:00"
    endTime: str  # noqa: N815
    paidMinutes: int  # noqa: N815
    minutes: int  # the length on the clock, breaks not taken off
    overnight: bool
    kind: str  # early, day, late or night (the roster legend)


class SkillIn(Schema):
    queueId: int  # noqa: N815
    level: int = 1


class SkillOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    level: int


class EmployeeIn(Schema):
    empNo: str = Field(..., max_length=20)  # noqa: N815
    name: str = Field(..., max_length=100)
    contractType: str = "permanent"  # noqa: N815
    workMode: str = "office"  # noqa: N815
    weeklyHours: Decimal | None = None  # noqa: N815 - blank means "use the default, and say so"
    startDate: date | None = None  # noqa: N815
    endDate: date | None = None  # noqa: N815
    skills: list[SkillIn] = Field(default_factory=list)
    # Who approves this person's leave and swaps. Left out on a change: unchanged; null: none.
    managerId: int | None = None  # noqa: N815


class EmployeeOut(Schema):
    id: int
    empNo: str  # noqa: N815
    name: str
    contractType: str  # noqa: N815
    workMode: str  # noqa: N815
    weeklyHours: float  # noqa: N815
    weeklyHoursIsDefault: bool  # noqa: N815 - true while nobody has entered the hours (DAT-10)
    startDate: date | None  # noqa: N815
    endDate: date | None  # noqa: N815
    skills: list[SkillOut]
    managerId: int | None  # noqa: N815
    manager: str | None  # the manager's name
    canManage: bool  # noqa: N815 - has a login that can approve, so can be a manager


class RosterCellOut(Schema):
    day: date
    shiftId: int  # noqa: N815
    code: str


class RosterRowOut(Schema):
    employeeId: int  # noqa: N815
    empNo: str  # noqa: N815
    name: str
    weeklyHours: float  # noqa: N815
    daysWorked: int  # noqa: N815
    paidMinutes: int  # noqa: N815
    cells: list[RosterCellOut]


class RosterOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    weekStart: date  # noqa: N815
    days: list[date]
    status: str
    publishedAt: datetime | None  # noqa: N815
    rows: list[RosterRowOut]
    onCounts: dict[str, int]  # noqa: N815 - date to people on a shift that day
    shifts: list[ShiftOut]


class AssignIn(Schema):
    queueId: int  # noqa: N815
    employeeId: int  # noqa: N815
    day: date
    templateId: int | None = None  # noqa: N815 - null clears the shift


class AssignOut(Schema):
    employeeId: int  # noqa: N815
    day: date
    shiftId: int | None  # noqa: N815
    code: str | None
    weekStatus: str  # noqa: N815


class WeekIn(Schema):
    queueId: int  # noqa: N815
    weekStart: date  # noqa: N815


class WeekOut(Schema):
    queueId: int  # noqa: N815
    weekStart: date  # noqa: N815
    status: str
    publishedAt: datetime | None  # noqa: N815


class PlanCellOut(Schema):
    slot: int
    scheduled: int
    required: int | None
    variance: int | None
    state: str | None  # under, met or over; null when the requirement is unknown


class WorstOut(Schema):
    day: date
    slot: int
    variance: int


class PlanSummaryOut(Schema):
    intervalsKnown: int  # noqa: N815 - half-hours that have a requirement
    underIntervals: int  # noqa: N815
    gap: int
    requiredTotal: int  # noqa: N815
    scheduledTotal: int  # noqa: N815
    worst: WorstOut | None


class PlanForecastOut(Schema):
    id: str
    label: str
    publishedAt: datetime | None  # noqa: N815
    assumptionsConfirmed: bool  # noqa: N815


class PlanOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    weekStart: date  # noqa: N815
    days: list[date]
    rosterStatus: str  # noqa: N815
    forecast: PlanForecastOut | None  # null: no published forecast, so no requirement
    cells: dict[str, list[PlanCellOut]]  # date to its 48 half-hours
    summary: PlanSummaryOut


class OverviewQueueOut(Schema):
    queueId: int  # noqa: N815
    queue: str
    rosterStatus: str  # noqa: N815
    forecastLabel: str | None  # noqa: N815 - none when no forecast is published
    assumptionsConfirmed: bool | None  # noqa: N815 - none without a forecast
    intervalsKnown: int  # noqa: N815
    underIntervals: int  # noqa: N815
    gap: int
    requiredTotal: int  # noqa: N815
    scheduledTotal: int  # noqa: N815
    worstVariance: int | None  # noqa: N815
    worstDay: date | None  # noqa: N815
    worstSlot: int | None  # noqa: N815


class OverviewDayOut(Schema):
    day: date
    gap: int
    underIntervals: int  # noqa: N815


class AttentionOut(Schema):
    severity: str  # critical, warning or info
    kind: str  # understaffed, no_forecast, assumptions or draft_roster
    queueId: int  # noqa: N815
    queue: str
    text: str
    count: int


class OverviewTotalsOut(Schema):
    queues: int
    queuesWithForecast: int  # noqa: N815
    intervalsKnown: int  # noqa: N815
    underIntervals: int  # noqa: N815
    gap: int
    headcount: int
    rostersPublished: int  # noqa: N815


class OverviewOut(Schema):
    weekStart: date  # noqa: N815
    totals: OverviewTotalsOut
    queues: list[OverviewQueueOut]
    days: list[OverviewDayOut]
    attention: list[AttentionOut]
