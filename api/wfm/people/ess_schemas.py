from __future__ import annotations

from datetime import date, time

from ninja import Schema

# camelCase on the wire; the noqa comments mark that deliberate choice.


class AvailabilityIn(Schema):
    weekday: int  # Monday is 0
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815 - 00:00 means the end of the day
    kind: str  # unavailable or preferred
    employeeId: int | None = None  # noqa: N815 - on someone's behalf; planners and admins only


class AvailabilityOut(Schema):
    id: int
    employeeId: int  # noqa: N815
    employee: str
    weekday: int
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    kind: str


class MyActivityOut(Schema):
    kind: str
    startTime: str  # noqa: N815 - "HH:MM"
    endTime: str  # noqa: N815


class MyShiftOut(Schema):
    day: date
    shift: str
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    queue: str
    activities: list[MyActivityOut]  # breaks and activities inside this shift


class MyLeaveOut(Schema):
    startDate: date  # noqa: N815
    endDate: date  # noqa: N815
    leaveType: str  # noqa: N815
    status: str


class MyScheduleOut(Schema):
    employee: str
    fromDate: date  # noqa: N815
    toDate: date  # noqa: N815
    shifts: list[MyShiftOut]
    leave: list[MyLeaveOut]
    unpublishedShifts: int  # noqa: N815 - shifts in weeks the planner has not published
    openSwaps: int  # noqa: N815 - swaps waiting for an answer or an approval
