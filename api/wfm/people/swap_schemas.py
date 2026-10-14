from __future__ import annotations

from datetime import date, datetime, time

from ninja import Schema

# camelCase on the wire; the noqa comments mark that deliberate choice.


class SwapShiftOut(Schema):
    assignmentId: int  # noqa: N815
    queueId: int  # noqa: N815
    queue: str
    day: date
    shift: str  # the shift code, e.g. D1
    startTime: time  # noqa: N815
    endTime: time  # noqa: N815
    employeeId: int  # noqa: N815
    employee: str


class SwapIn(Schema):
    giveAssignmentId: int  # noqa: N815 - your shift
    takeAssignmentId: int  # noqa: N815 - the colleague's shift you would take
    employeeId: int | None = None  # noqa: N815 - on someone's behalf; planners and admins only


class SwapOut(Schema):
    id: int
    queue: str
    status: str
    fromEmployee: str  # noqa: N815
    fromDay: date  # noqa: N815
    fromShift: str  # noqa: N815
    toEmployee: str  # noqa: N815
    toDay: date  # noqa: N815
    toShift: str  # noqa: N815
    createdAt: datetime  # noqa: N815
    decidedAt: datetime | None  # noqa: N815
    asker: bool  # the signed-in person is the one who asked
    colleague: bool  # the signed-in person is the one asked
